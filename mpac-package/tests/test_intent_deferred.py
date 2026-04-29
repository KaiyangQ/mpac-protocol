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
    """If Bob's deferral observes BOTH Alice's and Carol's intents on the
    same file, withdrawing only Alice's shouldn't drop the deferral.
    Bob is still yielding to Carol."""
    session_id = "sess-deferred-5"
    coord = SessionCoordinator(session_id, security_profile="open")

    alice, hello_a = _make("alice", session_id)
    bob, hello_b = _make("bob", session_id)
    carol, hello_c = _make("carol", session_id)
    coord.process_message(hello_a)
    coord.process_message(hello_b)
    coord.process_message(hello_c)

    scope = Scope(kind="file_set", resources=["notes_app/db.py"])
    coord.process_message(alice.announce_intent(
        session_id=session_id, intent_id="intent-alice-1",
        objective="alice", scope=scope,
    ))
    coord.process_message(carol.announce_intent(
        session_id=session_id, intent_id="intent-carol-1",
        objective="carol", scope=scope,
    ))
    coord.process_message(bob.defer_intent(
        session_id=session_id, deferral_id="defer-bob-1",
        scope=scope,
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
