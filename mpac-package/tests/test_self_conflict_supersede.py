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


def test_cross_principal_overlap_still_conflicts():
    """The same-principal skip in _detect_scope_overlaps must not
    accidentally suppress the legitimate Alice ↔ Dave case."""
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

    conflicts = _filter(responses, MessageType.CONFLICT_REPORT.value)
    assert len(conflicts) == 1, (
        "Expected exactly one Alice↔Dave conflict, got "
        f"{[c['payload'] for c in conflicts]}"
    )
    payload = conflicts[0]["payload"]
    principals = {payload["principal_a"], payload["principal_b"]}
    assert principals == {"alice", "dave"}


def test_orphan_after_retry_does_not_block_fresh_announce_with_third_party():
    """Realistic recovery: Dave's first attempt orphans an intent (no
    Alice involved at that point); Dave retries and his orphan is
    superseded; then Alice arrives and announces the same file. The
    resulting conflict must reference Dave's CURRENT intent (the retry),
    not the dead orphan."""
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

    # Dave retries → supersede.
    coord.process_message(dave.announce_intent(
        session_id=session_id,
        intent_id="intent-dave-retry",
        objective="retry",
        scope=scope,
    ))

    # Alice now announces — should conflict with the LIVE retry intent
    # (not Dave's WITHDRAWN orphan).
    responses = coord.process_message(alice.announce_intent(
        session_id=session_id,
        intent_id="intent-alice-1",
        objective="alice's work",
        scope=scope,
    ))

    conflicts = _filter(responses, MessageType.CONFLICT_REPORT.value)
    assert len(conflicts) == 1
    payload = conflicts[0]["payload"]
    referenced = {payload["intent_a"], payload["intent_b"]}
    assert "intent-dave-orphan" not in referenced, (
        "fresh conflict must not reference the superseded orphan"
    )
    assert referenced == {"intent-alice-1", "intent-dave-retry"}
