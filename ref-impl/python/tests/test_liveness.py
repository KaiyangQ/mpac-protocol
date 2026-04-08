"""Tests for HEARTBEAT, GOODBYE, and liveness detection (Section 14)."""
from datetime import timedelta

from mpac.models import Scope, IntentState, OperationState
from mpac.coordinator import SessionCoordinator, _now
from mpac.participant import Participant


def _make_session(unavailability_timeout_sec=10):
    sid = "test-liveness"
    coord = SessionCoordinator(sid, unavailability_timeout_sec=unavailability_timeout_sec)
    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
    bob = Participant("agent:bob", "agent", "Bob", ["contributor"])
    coord.process_message(alice.hello(sid))
    coord.process_message(bob.hello(sid))
    return sid, coord, alice, bob


def test_heartbeat_updates_liveness():
    """HEARTBEAT keeps participant alive and updates status."""
    sid, coord, alice, _ = _make_session()

    hb = alice.heartbeat(sid, status="working", active_intent_id="intent-1")
    coord.process_message(hb)

    info = coord.participants["agent:alice"]
    assert info.status == "working"
    assert info.is_available is True


def test_liveness_detection_marks_unavailable():
    """Participant becomes unavailable after timeout with no messages."""
    sid, coord, alice, _ = _make_session(unavailability_timeout_sec=10)

    # Set last_seen to 11 seconds ago
    info = coord.participants["agent:alice"]
    info.last_seen = _now() - timedelta(seconds=11)

    responses = coord.check_liveness()

    assert info.is_available is False
    # Should broadcast PROTOCOL_ERROR
    errors = [r for r in responses if r["message_type"] == "PROTOCOL_ERROR"]
    assert len(errors) == 1
    assert errors[0]["payload"]["error_code"] == "PARTICIPANT_UNAVAILABLE"
    assert "agent:alice" in errors[0]["payload"]["description"]


def test_unavailable_suspends_intents():
    """When participant goes unavailable, their active intents are suspended."""
    sid, coord, alice, _ = _make_session(unavailability_timeout_sec=10)

    # Alice announces intent
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope))
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.ACTIVE

    # Alice goes unavailable
    coord.participants["agent:alice"].last_seen = _now() - timedelta(seconds=11)
    coord.check_liveness()

    assert coord.intents["intent-a"].state_machine.current_state == IntentState.SUSPENDED


def test_unavailable_abandons_proposals():
    """When participant goes unavailable, their in-flight proposals are abandoned."""
    sid, coord, alice, _ = _make_session(unavailability_timeout_sec=10)

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))
    coord.process_message(alice.propose_op(sid, "op-1", "intent-a", "src/auth.py", "patch"))

    assert coord.operations["op-1"].state_machine.current_state == OperationState.PROPOSED

    # Alice goes unavailable
    coord.participants["agent:alice"].last_seen = _now() - timedelta(seconds=11)
    coord.check_liveness()

    assert coord.operations["op-1"].state_machine.current_state == OperationState.ABANDONED


def test_reconnection_restores_intents():
    """When unavailable participant sends HEARTBEAT, suspended intents restore to ACTIVE."""
    sid, coord, alice, _ = _make_session(unavailability_timeout_sec=10)

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))

    # Go unavailable
    coord.participants["agent:alice"].last_seen = _now() - timedelta(seconds=11)
    coord.check_liveness()
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.SUSPENDED
    assert coord.participants["agent:alice"].is_available is False

    # Alice reconnects with heartbeat
    coord.process_message(alice.heartbeat(sid, status="idle"))
    assert coord.participants["agent:alice"].is_available is True
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.ACTIVE


def test_goodbye_withdraws_intents():
    """GOODBYE with disposition=withdraw withdraws all active intents."""
    sid, coord, alice, _ = _make_session()

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))
    coord.process_message(alice.propose_op(sid, "op-1", "intent-a", "src/auth.py", "patch"))

    goodbye = alice.goodbye(sid, reason="user_exit", intent_disposition="withdraw")
    responses = coord.process_message(goodbye)

    # Intent should be WITHDRAWN
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.WITHDRAWN

    # Operation should be REJECTED (via cascade) or ABANDONED
    op = coord.operations["op-1"]
    assert op.state_machine.current_state in (OperationState.REJECTED, OperationState.ABANDONED)

    # Participant should be marked unavailable
    assert coord.participants["agent:alice"].is_available is False


def test_goodbye_expire_keeps_ttl():
    """GOODBYE with disposition=expire lets intents expire via TTL."""
    sid, coord, alice, _ = _make_session()

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    msg = alice.announce_intent(sid, "intent-a", "Fix", scope, ttl_sec=120)
    coord.process_message(msg)

    goodbye = alice.goodbye(sid, reason="user_exit", intent_disposition="expire")
    coord.process_message(goodbye)

    # Intent should still be ACTIVE (not withdrawn)
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.ACTIVE


def test_offline_status_exempt_from_liveness():
    """Participants with 'offline' status are not marked unavailable."""
    sid, coord, alice, _ = _make_session(unavailability_timeout_sec=10)

    # Alice sends heartbeat with offline status
    coord.process_message(alice.heartbeat(sid, status="offline"))

    # Simulate time passing beyond timeout
    coord.participants["agent:alice"].last_seen = _now() - timedelta(seconds=11)
    responses = coord.check_liveness()

    # Should NOT be marked unavailable (offline is exempt)
    assert coord.participants["agent:alice"].is_available is True
    assert len(responses) == 0
