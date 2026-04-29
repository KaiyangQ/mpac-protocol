"""Regression tests for the 2026-04-28 self-conflict + auto-supersede fix.

Three observed bugs motivated this change:

* The CONFLICTS panel showed ``Dave's Claude ↔ Dave's Claude`` after a
  relay subprocess crashed mid-write — the orphaned intent collided with
  the next announce from the same principal.
* When the same principal re-announced overlapping work, the orphan was
  NOT cleaned up; over time orphan intents accumulated and even produced
  cross-principal phantom conflicts.

The fixes live in ``coordinator._handle_intent_announce`` and
``coordinator._detect_scope_overlaps``. This file pins the new behaviour
so a future refactor can't silently regress.
"""
from __future__ import annotations

from mpac_protocol.core.coordinator import SessionCoordinator
from mpac_protocol.core.models import IntentState, MessageType, Scope
from mpac_protocol.core.participant import Participant


def _make(pid: str, session_id: str):
    p = Participant(
        principal_id=pid,
        principal_type="agent",
        display_name=pid,
        roles=["contributor"],
        capabilities=["intent.broadcast", "op.commit"],
    )
    return p, p.hello(session_id)


def _filter(responses, message_type):
    return [r for r in responses if r.get("message_type") == message_type]


def test_same_principal_overlap_does_not_self_conflict():
    """2a: when the SAME principal_id appears in two intents on overlapping
    scope, no CONFLICT_REPORT should be emitted with both sides being that
    principal. Prior to the fix, the coordinator only filtered by
    intent_id and produced a self-conflict."""
    session_id = "sess-self-1"
    coord = SessionCoordinator(session_id, security_profile="open")

    dave, hello_dave = _make("dave", session_id)
    coord.process_message(hello_dave)

    scope = Scope(kind="file_set", resources=["notes_app/db.py"])
    first = dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-1",
        objective="append hello world",
        scope=scope,
    )
    coord.process_message(first)

    # Direct-call the coordinator with a hand-rolled second announce so we
    # bypass the participant's intent_id allocator without depending on
    # internal generator state.
    second = dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-2",
        objective="append hello world (retry)",
        scope=scope,
    )
    responses = coord.process_message(second)

    conflicts = _filter(responses, MessageType.CONFLICT_REPORT.value)
    assert conflicts == [], (
        "Expected no self-conflict but got: "
        f"{[c['payload'] for c in conflicts]}"
    )


def test_same_principal_reannounce_supersedes_prior_intent():
    """2c: a re-announce on overlapping scope must auto-withdraw the
    earlier intent. The orphan-after-subprocess-crash scenario relies on
    this so the second user retry is left with exactly ONE active intent
    on the file."""
    session_id = "sess-self-2"
    coord = SessionCoordinator(session_id, security_profile="open")

    dave, hello_dave = _make("dave", session_id)
    coord.process_message(hello_dave)

    scope_first = Scope(kind="file_set", resources=["notes_app/db.py"])
    first = dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-old",
        objective="first try",
        scope=scope_first,
    )
    coord.process_message(first)
    assert (
        coord.intents["intent-dave-old"].state_machine.current_state
        == IntentState.ACTIVE
    )

    scope_second = Scope(kind="file_set", resources=["notes_app/db.py"])
    second = dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-new",
        objective="retry",
        scope=scope_second,
    )
    coord.process_message(second)

    assert (
        coord.intents["intent-dave-old"].state_machine.current_state
        == IntentState.WITHDRAWN
    ), "old intent should have been auto-superseded"
    assert (
        coord.intents["intent-dave-new"].state_machine.current_state
        == IntentState.ACTIVE
    )


def test_supersede_only_triggers_on_overlap_not_disjoint_files():
    """A new announce on a non-overlapping file must NOT supersede an
    earlier intent on a different file — the principal is doing two
    distinct things in parallel and both claims should remain."""
    session_id = "sess-self-3"
    coord = SessionCoordinator(session_id, security_profile="open")

    dave, hello_dave = _make("dave", session_id)
    coord.process_message(hello_dave)

    a = dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-a",
        objective="edit a",
        scope=Scope(kind="file_set", resources=["a.py"]),
    )
    coord.process_message(a)

    b = dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-b",
        objective="edit b",
        scope=Scope(kind="file_set", resources=["b.py"]),
    )
    coord.process_message(b)

    assert (
        coord.intents["intent-dave-a"].state_machine.current_state
        == IntentState.ACTIVE
    )
    assert (
        coord.intents["intent-dave-b"].state_machine.current_state
        == IntentState.ACTIVE
    )


def test_cross_principal_same_file_announce_rejected_with_stale_intent():
    """v0.2.8: cross-principal same-file announce is rejected with
    STALE_INTENT (the race-lock contract), not silently merged into a
    CONFLICT_REPORT.

    Pre-0.2.8 behavior was to fire an advisory CONFLICT_REPORT and let
    both intents coexist; v0.2.8 mirrors git's merge-conflict semantics
    and rejects the second writer outright. The 'losing' agent's client
    must call defer_intent and tell the user to wait.

    Same-principal supersede (the 0.2.6 path) is unaffected — orphan
    cleanup for the SAME user retrying still works."""
    session_id = "sess-self-4"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_alice = _make("alice", session_id)
    dave, hello_dave = _make("dave", session_id)
    coord.process_message(hello_alice)
    coord.process_message(hello_dave)

    scope = Scope(kind="file_set", resources=["notes_app/db.py"])
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice edit",
        scope=scope,
    ))
    responses = coord.process_message(dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-1",
        objective="dave edit",
        scope=scope,
    ))

    # No CONFLICT_REPORT — race lock fires before _detect_scope_overlaps.
    assert not _filter(responses, MessageType.CONFLICT_REPORT.value)

    # Single PROTOCOL_ERROR with STALE_INTENT.
    errors = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"]
    assert len(errors) == 1
    err = errors[0]["payload"]
    assert err.get("error_code") == "STALE_INTENT"
    # Reason names the colliding intent so the client can defer correctly.
    assert "intent-alice-1" in err.get("description", "")

    # Dave's intent is NOT registered (the rejection is a hard reject,
    # not a soft "accept and warn").
    assert "intent-dave-1" not in coord.intents
    # Alice's still alive.
    assert "intent-alice-1" in coord.intents
    assert coord.intents["intent-alice-1"].state_machine.current_state == IntentState.ACTIVE


def test_orphan_after_retry_does_not_block_fresh_announce_with_third_party():
    """v0.2.8: Dave's orphan retry is superseded; then Alice arrives
    and her same-file announce gets STALE_INTENT — but the rejection's
    reason names Dave's CURRENT (retry) intent, NOT the dead orphan.

    Pre-0.2.8 the assertion was on the resulting CONFLICT_REPORT; v0.2.8
    rejects same-file race instead, so we validate the same anti-stale
    invariant via the error message."""
    session_id = "sess-self-5"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_alice = _make("alice", session_id)
    dave, hello_dave = _make("dave", session_id)
    coord.process_message(hello_alice)
    coord.process_message(hello_dave)

    scope = Scope(kind="file_set", resources=["notes_app/db.py"])

    # Dave's first attempt — becomes orphan when subprocess crashes.
    coord.process_message(dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-orphan",
        objective="first attempt",
        scope=scope,
    ))

    # Dave retries → 0.2.6 same-principal supersede path.
    coord.process_message(dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-retry",
        objective="retry",
        scope=scope,
    ))

    # Alice now announces — race-locked against Dave's retry.
    responses = coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice's work",
        scope=scope,
    ))

    # No CONFLICT_REPORT (race lock pre-empts it); single STALE_INTENT.
    assert not _filter(responses, MessageType.CONFLICT_REPORT.value)
    errors = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"]
    assert len(errors) == 1
    msg = errors[0]["payload"].get("description", "")
    # Critical anti-stale invariant: reject must reference the LIVE retry,
    # not the dead orphan.
    assert "intent-dave-retry" in msg
    assert "intent-dave-orphan" not in msg, (
        "STALE_INTENT message must point at the live retry, not the "
        "WITHDRAWN orphan"
    )
    # Alice's intent not registered.
    assert "intent-alice-1" not in coord.intents


# ── v0.2.8 race-lock additions: positive cases the lock must ALLOW ───


def test_race_lock_does_not_block_dependency_breakage_announce():
    """v0.2.8: the race lock fires ONLY for same-file overlap (would-be
    scope_overlap). Cross-file dependency_breakage MUST still go through
    as an advisory CONFLICT_REPORT — that's the entire point of the
    category split (mirrors git: merge conflict rejects, semantic
    conflict warns).
    """
    session_id = "sess-race-cross-file"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)

    # Alice on db.py — scope.extensions.impact will include api.py
    # (real notes_app reverse-dep), but raw scope only declares db.py.
    coord.process_message(alice.announce_intent(
        session_id=session_id, intent_id="intent-alice-1",
        objective="alice",
        scope=Scope(
            kind="file_set", resources=["notes_app/db.py"],
            extensions={"impact": ["notes_app/api.py", "notes_app/cli.py"]},
        ),
    ))

    # Bob on api.py — different file, but it's in Alice's impact.
    responses = coord.process_message(bob.announce_intent(
        session_id=session_id, intent_id="intent-bob-1",
        objective="bob",
        scope=Scope(kind="file_set", resources=["notes_app/api.py"]),
    ))

    # No PROTOCOL_ERROR — race lock did not fire (different files).
    errors = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"]
    assert not errors, (
        f"race lock must NOT block cross-file dependency_breakage, "
        f"got errors={errors}"
    )

    # Bob's intent IS registered (the announce succeeded).
    assert "intent-bob-1" in coord.intents

    # An advisory CONFLICT_REPORT(category=dependency_breakage) fires.
    conflicts = _filter(responses, MessageType.CONFLICT_REPORT.value)
    assert len(conflicts) == 1
    assert conflicts[0]["payload"]["category"] == "dependency_breakage"


def test_race_lock_does_not_block_disjoint_files():
    """Sanity: announcing on entirely unrelated files is unaffected."""
    session_id = "sess-race-disjoint"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)

    coord.process_message(alice.announce_intent(
        session_id=session_id, intent_id="intent-alice-1",
        objective="alice",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))
    responses = coord.process_message(bob.announce_intent(
        session_id=session_id, intent_id="intent-bob-1",
        objective="bob",
        scope=Scope(kind="file_set", resources=["notes_app/auth.py"]),
    ))

    errors = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"]
    assert not errors
    assert "intent-bob-1" in coord.intents


def test_race_lock_allows_same_principal_retry():
    """v0.2.6 same-principal supersede path must remain intact: the same
    user retrying the same file (e.g. after a relay subprocess crash
    orphaned an intent) is NOT blocked by the v0.2.8 race lock — that
    lock is cross-principal-only."""
    session_id = "sess-race-same-principal"
    coord = SessionCoordinator(session_id, security_profile="open")

    dave, hello_dave = _make("dave", session_id)
    coord.process_message(hello_dave)

    scope = Scope(kind="file_set", resources=["notes_app/db.py"])
    coord.process_message(dave.announce_intent(
        session_id=session_id, intent_id="intent-dave-orphan",
        objective="first attempt", scope=scope,
    ))
    responses = coord.process_message(dave.announce_intent(
        session_id=session_id, intent_id="intent-dave-retry",
        objective="retry", scope=scope,
    ))

    # No PROTOCOL_ERROR — same-principal supersede, not race-lock.
    assert not [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"]
    # Retry registered, orphan superseded.
    assert "intent-dave-retry" in coord.intents
    assert coord.intents["intent-dave-orphan"].state_machine.current_state == IntentState.WITHDRAWN


def test_race_lock_releases_on_first_intent_withdraw():
    """After the first intent withdraws, the SAME other principal can
    announce on that file successfully — the lock is tied to live state,
    not to history."""
    session_id = "sess-race-release"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)

    scope = Scope(kind="file_set", resources=["notes_app/db.py"])

    # Alice first — succeeds.
    coord.process_message(alice.announce_intent(
        session_id=session_id, intent_id="intent-alice-1",
        objective="alice", scope=scope,
    ))

    # Bob is rejected (race lock).
    rejected = coord.process_message(bob.announce_intent(
        session_id=session_id, intent_id="intent-bob-rejected",
        objective="bob attempt 1", scope=scope,
    ))
    assert any(r.get("message_type") == "PROTOCOL_ERROR" for r in rejected)
    assert "intent-bob-rejected" not in coord.intents

    # Alice withdraws — lock released.
    coord.process_message(alice.withdraw_intent(
        session_id=session_id, intent_id="intent-alice-1",
    ))

    # Bob retries — now succeeds.
    accepted = coord.process_message(bob.announce_intent(
        session_id=session_id, intent_id="intent-bob-retry",
        objective="bob attempt 2", scope=scope,
    ))
    assert not [r for r in accepted if r.get("message_type") == "PROTOCOL_ERROR"]
    assert "intent-bob-retry" in coord.intents
