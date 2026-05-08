"""Tests for INTENT_DEFERRED (v0.2.5).

Covers:
* Coordinator stores deferral, broadcasts INTENT_DEFERRED back.
* Deferral auto-resolves when the observed intent terminates.
* Deferral auto-resolves when the deferring principal later announces.
* TTL expiry via check_expiry.
* Same principal / same overlap idempotent (replace by deferral_id).
"""
from __future__ import annotations

from datetime import timedelta

from mpac_protocol.core.coordinator import SessionCoordinator, _now
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


def test_defer_intent_creates_deferral_and_broadcasts():
    session_id = "sess-deferred-1"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)

    # Alice announces.
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice work",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))

    # Bob sees Alice's intent (via check_overlap, not part of this test) and
    # decides to defer rather than announce.
    responses = coord.process_message(bob.defer_intent(
        session_id=session_id,
        deferral_id="defer-bob-1",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
        reason="yielded_to_alice",
        observed_intent_ids=["intent-alice-1"],
        observed_principals=["alice"],
        ttl_sec=120.0,
    ))

    deferred = _filter(responses, MessageType.INTENT_DEFERRED.value)
    assert len(deferred) == 1
    payload = deferred[0]["payload"]
    assert payload["principal_id"] == "bob"
    assert payload["observed_intent_ids"] == ["intent-alice-1"]
    assert payload["reason"] == "yielded_to_alice"

    # Coordinator stored it.
    assert "defer-bob-1" in coord.deferrals
    assert coord.deferrals["defer-bob-1"].principal_id == "bob"


def test_deferral_auto_resolves_when_observed_intent_withdrawn():
    session_id = "sess-deferred-2"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice work",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))
    coord.process_message(bob.defer_intent(
        session_id=session_id,
        deferral_id="defer-bob-1",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
        observed_intent_ids=["intent-alice-1"],
    ))
    assert "defer-bob-1" in coord.deferrals

    # Alice withdraws → deferral should auto-resolve and broadcast a status update.
    responses = coord.process_message(alice.withdraw_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
    ))

    assert "defer-bob-1" not in coord.deferrals
    deferred_resolves = [
        r for r in responses
        if r.get("message_type") == MessageType.INTENT_DEFERRED.value
        and r.get("payload", {}).get("status") == "resolved"
    ]
    assert len(deferred_resolves) == 1
    assert deferred_resolves[0]["payload"]["principal_id"] == "bob"


def test_deferral_resolves_when_principal_later_announces():
    session_id = "sess-deferred-3"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))
    coord.process_message(bob.defer_intent(
        session_id=session_id,
        deferral_id="defer-bob-1",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
        observed_intent_ids=["intent-alice-1"],
    ))

    # Bob changes his mind, announces on a different file (no longer yielding).
    responses = coord.process_message(bob.announce_intent(
        session_id=session_id,
        intent_id="intent-bob-1",
        objective="bob actually decided to work",
        scope=Scope(kind="file_set", resources=["notes_app/api.py"]),
    ))

    assert "defer-bob-1" not in coord.deferrals
    resolves = [
        r for r in responses
        if r.get("message_type") == MessageType.INTENT_DEFERRED.value
        and r.get("payload", {}).get("status") == "resolved"
    ]
    assert len(resolves) == 1
    assert resolves[0]["payload"]["reason"] == "principal_announced"


def test_deferral_ttl_expiry():
    session_id = "sess-deferred-4"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))
    coord.process_message(bob.defer_intent(
        session_id=session_id,
        deferral_id="defer-bob-1",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
        observed_intent_ids=["intent-alice-1"],
        ttl_sec=10.0,
    ))
    assert "defer-bob-1" in coord.deferrals

    # Fake-advance time past expiry.
    future = _now() + timedelta(seconds=15)
    responses = coord.check_expiry(now=future)

    assert "defer-bob-1" not in coord.deferrals
    expired = [
        r for r in responses
        if r.get("message_type") == MessageType.INTENT_DEFERRED.value
        and r.get("payload", {}).get("status") == "expired"
    ]
    assert len(expired) == 1


def test_deferral_with_multiple_observed_intents_keeps_alive_until_all_terminate():
    """If Bob's deferral observes BOTH Alice's and Carol's intents,
    withdrawing only Alice's shouldn't drop the deferral. Bob is still
    yielding to Carol.

    NOTE: Alice and Carol must announce on DIFFERENT files because
    v0.2.8 race-locks cross-principal same-file announces. The deferral-
    cleanup logic is independent of file overlap — it tracks intent_ids
    in the deferral's observed_intent_ids list, not file scopes."""
    session_id = "sess-deferred-5"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    carol, hello_c = _make("carol", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(hello_c)

    coord.process_message(alice.announce_intent(
        session_id=session_id, intent_id="intent-alice-1",
        objective="alice",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))
    coord.process_message(carol.announce_intent(
        session_id=session_id, intent_id="intent-carol-1",
        objective="carol",
        scope=Scope(kind="file_set", resources=["notes_app/api.py"]),
    ))
    coord.process_message(bob.defer_intent(
        session_id=session_id, deferral_id="defer-bob-1",
        scope=Scope(kind="file_set", resources=["notes_app/db.py", "notes_app/api.py"]),
        observed_intent_ids=["intent-alice-1", "intent-carol-1"],
    ))

    # Alice withdraws — Carol still active, deferral should remain.
    coord.process_message(alice.withdraw_intent(
        session_id=session_id, intent_id="intent-alice-1",
    ))
    assert "defer-bob-1" in coord.deferrals
    assert coord.deferrals["defer-bob-1"].observed_intent_ids == ["intent-carol-1"]

    # Now Carol withdraws — deferral resolves.
    coord.process_message(carol.withdraw_intent(
        session_id=session_id, intent_id="intent-carol-1",
    ))
    assert "defer-bob-1" not in coord.deferrals


def test_deferral_resolves_when_principal_id_passed_as_observed_intent_id():
    """v0.2.6 defense in depth: pre-0.2.6 check_overlap didn't expose
    intent_id, so Claude was observed passing principal_ids in the
    observed_intent_ids field. Cleanup should still fire when the
    terminating intent's principal matches one of those bogus entries.
    """
    session_id = "sess-deferred-mislabel"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))

    # Bob defers but passes ALICE'S PRINCIPAL_ID where intent_id was
    # expected (the actual 0.2.5 production bug).
    coord.process_message(bob.defer_intent(
        session_id=session_id,
        deferral_id="defer-bob-mislabel",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
        observed_intent_ids=["alice"],   # ← should have been "intent-alice-1"
    ))
    assert "defer-bob-mislabel" in coord.deferrals

    # Alice withdraws → cleanup matches via the principal_id-in-intents-field fallback.
    responses = coord.process_message(alice.withdraw_intent(
        session_id=session_id, intent_id="intent-alice-1",
    ))

    assert "defer-bob-mislabel" not in coord.deferrals, (
        "principal-id-in-intents-field fallback should have cleaned up the deferral"
    )
    resolves = [
        r for r in responses
        if r.get("message_type") == MessageType.INTENT_DEFERRED.value
        and r.get("payload", {}).get("status") == "resolved"
    ]
    assert len(resolves) == 1


def test_deferral_resolves_via_observed_principals():
    """Symmetric: when Claude DOES correctly pass principal_id in
    observed_principals (not observed_intent_ids), cleanup also fires."""
    session_id = "sess-deferred-principal"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))
    coord.process_message(bob.defer_intent(
        session_id=session_id,
        deferral_id="defer-bob-principal",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
        observed_intent_ids=[],   # empty
        observed_principals=["alice"],   # populated correctly
    ))
    assert "defer-bob-principal" in coord.deferrals

    coord.process_message(alice.withdraw_intent(
        session_id=session_id, intent_id="intent-alice-1",
    ))
    assert "defer-bob-principal" not in coord.deferrals


def test_deferral_resolves_immediately_when_observed_intent_already_terminal():
    """v0.2.7: if the observed intent has ALREADY withdrawn by the time
    the defer message arrives, the coordinator must emit `resolved`
    in the SAME response — not wait for TTL.

    Reproduces 2026-04-29 case-4 round 3 in prod: Bob's Claude took 14s
    to call defer_intent and Alice's 12s task had already withdrawn. Pre-fix,
    the deferral sat with status=active and the yield-chip hung in the
    Conflicts panel until the 60s TTL fired. After fix, resolved is
    emitted alongside the active broadcast so the client clears the chip
    immediately.
    """
    session_id = "sess-deferred-late"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)

    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))
    # Alice withdraws BEFORE Bob's defer arrives.
    coord.process_message(alice.withdraw_intent(
        session_id=session_id, intent_id="intent-alice-1",
    ))

    responses = coord.process_message(bob.defer_intent(
        session_id=session_id,
        deferral_id="defer-bob-late",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
        observed_intent_ids=["intent-alice-1"],
    ))

    deferred = _filter(responses, MessageType.INTENT_DEFERRED.value)
    statuses = [d["payload"].get("status", "active") for d in deferred]
    # We expect BOTH the initial active broadcast AND the immediate
    # resolved broadcast in the same response.
    assert "resolved" in statuses, (
        f"defer arriving after observed intent withdrew should resolve "
        f"immediately, got statuses={statuses}"
    )
    # Deferral registry empty — no dangling entry waiting for TTL.
    assert "defer-bob-late" not in coord.deferrals
    # The resolved broadcast should attribute the resolution correctly.
    resolved = [d for d in deferred if d["payload"].get("status") == "resolved"]
    assert resolved[0]["payload"]["reason"] == "observed_intents_terminated"
    assert resolved[0]["payload"]["principal_id"] == "bob"


def test_deferral_with_some_observed_terminated_does_not_immediately_resolve():
    """If only SOME of the observed intents are terminal at defer time,
    keep the deferral alive — Bob is still yielding to whoever's left.

    NOTE: Alice and Carol must announce on DIFFERENT files because
    v0.2.8 race-locks cross-principal same-file announces. The
    fast-resolve logic is independent of file overlap — it tracks
    intent_ids in the deferral's observed_intent_ids list."""
    session_id = "sess-deferred-mixed"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    carol, hello_c = _make("carol", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(hello_c)

    coord.process_message(alice.announce_intent(
        session_id=session_id, intent_id="intent-alice-1",
        objective="alice",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))
    coord.process_message(carol.announce_intent(
        session_id=session_id, intent_id="intent-carol-1",
        objective="carol",
        scope=Scope(kind="file_set", resources=["notes_app/api.py"]),
    ))
    # Alice withdraws — Carol still active.
    coord.process_message(alice.withdraw_intent(
        session_id=session_id, intent_id="intent-alice-1",
    ))

    responses = coord.process_message(bob.defer_intent(
        session_id=session_id, deferral_id="defer-bob-mixed",
        scope=Scope(kind="file_set", resources=["notes_app/db.py", "notes_app/api.py"]),
        observed_intent_ids=["intent-alice-1", "intent-carol-1"],
    ))

    deferred = _filter(responses, MessageType.INTENT_DEFERRED.value)
    statuses = [d["payload"].get("status", "active") for d in deferred]
    assert "resolved" not in statuses, (
        f"deferral with at least one still-alive observed intent must "
        f"NOT resolve immediately, got statuses={statuses}"
    )
    assert "defer-bob-mixed" in coord.deferrals


def test_deferral_with_no_observed_targets_does_not_auto_resolve():
    """Degenerate input: no observed_intent_ids and no observed_principals.
    We don't auto-resolve — let TTL handle it so the user notices their
    agent emitted a defer with nothing to attribute it to.
    """
    session_id = "sess-deferred-empty"
    coord = SessionCoordinator(session_id, security_profile="open")

    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_b)

    responses = coord.process_message(bob.defer_intent(
        session_id=session_id, deferral_id="defer-bob-empty",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
        observed_intent_ids=[],
        observed_principals=[],
    ))

    deferred = _filter(responses, MessageType.INTENT_DEFERRED.value)
    statuses = [d["payload"].get("status", "active") for d in deferred]
    assert "resolved" not in statuses, (
        f"empty-observed defer should NOT auto-resolve, got statuses={statuses}"
    )
    assert "defer-bob-empty" in coord.deferrals


def test_defer_intent_does_not_create_conflict_or_intent():
    """A deferral is not an intent — no scope claim, no conflict computation."""
    session_id = "sess-deferred-6"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    scope = Scope(kind="file_set", resources=["notes_app/db.py"])
    coord.process_message(alice.announce_intent(
        session_id=session_id, intent_id="intent-alice-1",
        objective="alice", scope=scope,
    ))

    responses = coord.process_message(bob.defer_intent(
        session_id=session_id, deferral_id="defer-bob-1",
        scope=scope,
        observed_intent_ids=["intent-alice-1"],
    ))

    # Bob has no Intent in the registry.
    assert all(i.principal_id != "bob" for i in coord.intents.values())
    # No CONFLICT_REPORT.
    assert not _filter(responses, MessageType.CONFLICT_REPORT.value)
    # But the deferral envelope was emitted.
    assert _filter(responses, MessageType.INTENT_DEFERRED.value)


# ── v0.2.13: category field on INTENT_DEFERRED ───────────────────────


def _defer_payload(coord, principal, session_id, *, category=None,
                   deferral_id="defer-cat-1"):
    """Helper: defer + return the INTENT_DEFERRED payload (active record)."""
    msg = principal.defer_intent(
        session_id=session_id,
        deferral_id=deferral_id,
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
        reason="yielded",
        observed_intent_ids=["intent-alice-1"],
        observed_principals=["alice"],
        category=category,
    )
    responses = coord.process_message(msg)
    deferred = [
        r for r in responses
        if r.get("message_type") == MessageType.INTENT_DEFERRED.value
        and r.get("payload", {}).get("status") in (None, "active")
    ]
    assert deferred, "expected an active INTENT_DEFERRED broadcast"
    return deferred[0].get("payload", {})


def test_defer_intent_default_category_is_queue():
    """v0.2.13: when the deferring agent doesn't pass category, the
    coordinator broadcasts ``category="queue"`` so siblings render the
    new neutral chip rather than the legacy yield framing."""
    session_id = "sess-cat-default"
    coord = SessionCoordinator(session_id, security_profile="open")
    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice work",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))

    payload = _defer_payload(coord, bob, session_id, category=None)
    assert payload.get("category") == "queue"


def test_defer_intent_propagates_duplicate_yield_category():
    """When the prior STALE_INTENT response had ``duplicate_candidate``,
    the agent's defer_intent call should set
    ``category="duplicate_yield"`` and the coordinator must propagate
    it verbatim into INTENT_DEFERRED."""
    session_id = "sess-cat-dup"
    coord = SessionCoordinator(session_id, security_profile="open")
    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice work",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))

    payload = _defer_payload(
        coord, bob, session_id, category="duplicate_yield"
    )
    assert payload.get("category") == "duplicate_yield"


def test_defer_intent_unknown_category_falls_back_to_queue():
    """Defensive: a typo or unrecognised category from a buggy client
    falls back to ``queue`` rather than poisoning the union type the
    frontend reads."""
    session_id = "sess-cat-bogus"
    coord = SessionCoordinator(session_id, security_profile="open")
    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice work",
        scope=Scope(kind="file_set", resources=["notes_app/db.py"]),
    ))

    payload = _defer_payload(coord, bob, session_id, category="bananas")
    assert payload.get("category") == "queue"
