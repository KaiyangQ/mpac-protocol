"""Tests for CONFLICT_ACK, CONFLICT_ESCALATE, and arbiter workflow (Section 17-18)."""
from datetime import timedelta

from mpac.models import Scope, ConflictState
from mpac.coordinator import SessionCoordinator, _now
from mpac.participant import Participant


def _make_conflict_session():
    """Create a session with an open conflict."""
    sid = "test-conflict-wf"
    coord = SessionCoordinator(sid, resolution_timeout_sec=60)

    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
    bob = Participant("agent:bob", "agent", "Bob", ["owner"])
    arbiter = Participant("human:arbiter", "human", "Arbiter", ["arbiter"])

    coord.process_message(alice.hello(sid))
    coord.process_message(bob.hello(sid))
    coord.process_message(arbiter.hello(sid))

    # Create overlapping intents → conflict
    scope_a = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope_a))

    scope_b = Scope(kind="file_set", resources=["src/auth.py", "src/models.py"])
    responses = coord.process_message(bob.announce_intent(sid, "intent-b", "Refactor auth", scope_b))

    assert len(responses) == 1
    conflict_id = responses[0]["payload"]["conflict_id"]
    return sid, coord, alice, bob, arbiter, conflict_id


def test_conflict_ack():
    """CONFLICT_ACK transitions OPEN → ACKED."""
    sid, coord, alice, _, _, conflict_id = _make_conflict_session()

    ack = alice.ack_conflict(sid, conflict_id, ack_type="seen")
    coord.process_message(ack)

    assert coord.conflicts[conflict_id].state_machine.current_state == ConflictState.ACKED


def test_conflict_escalate():
    """CONFLICT_ESCALATE transitions to ESCALATED with target recorded."""
    sid, coord, alice, _, arbiter, conflict_id = _make_conflict_session()

    esc = alice.escalate_conflict(
        sid, conflict_id,
        escalate_to="human:arbiter",
        reason="cannot agree",
        context="Need human judgment",
    )
    coord.process_message(esc)

    conflict = coord.conflicts[conflict_id]
    assert conflict.state_machine.current_state == ConflictState.ESCALATED
    assert conflict.escalated_to == "human:arbiter"
    assert conflict.escalated_at is not None


def test_arbiter_resolution_after_escalation():
    """Arbiter resolves an ESCALATED conflict → CLOSED."""
    sid, coord, alice, bob, arbiter, conflict_id = _make_conflict_session()

    # Alice escalates
    coord.process_message(alice.escalate_conflict(
        sid, conflict_id, "human:arbiter", "need help"))

    assert coord.conflicts[conflict_id].state_machine.current_state == ConflictState.ESCALATED

    # Arbiter resolves
    coord.process_message(arbiter.resolve_conflict(
        sid, conflict_id, "approved",
        rationale="Alice's approach is better",
        outcome={"accepted": ["intent-a"], "rejected": ["intent-b"]},
    ))

    assert coord.conflicts[conflict_id].state_machine.current_state == ConflictState.CLOSED


def test_resolution_timeout_auto_escalates():
    """Conflicts exceeding resolution_timeout_sec auto-escalate to arbiter."""
    sid, coord, _, _, _, conflict_id = _make_conflict_session()

    # Simulate conflict created 61 seconds ago
    coord.conflicts[conflict_id].created_at = _now() - timedelta(seconds=61)

    responses = coord.check_resolution_timeouts()

    conflict = coord.conflicts[conflict_id]
    assert conflict.state_machine.current_state == ConflictState.ESCALATED
    assert conflict.escalated_to == "human:arbiter"

    escalate_msgs = [r for r in responses if r["message_type"] == "CONFLICT_ESCALATE"]
    assert len(escalate_msgs) == 1
    assert escalate_msgs[0]["payload"]["reason"] == "resolution_timeout"


def test_resolution_timeout_no_arbiter():
    """With no arbiter, resolution timeout emits PROTOCOL_ERROR."""
    sid = "test-no-arbiter"
    coord = SessionCoordinator(sid, resolution_timeout_sec=60)

    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
    bob = Participant("agent:bob", "agent", "Bob", ["contributor"])
    # No arbiter joined

    coord.process_message(alice.hello(sid))
    coord.process_message(bob.hello(sid))

    scope_a = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope_a))

    scope_b = Scope(kind="file_set", resources=["src/auth.py"])
    responses = coord.process_message(bob.announce_intent(sid, "intent-b", "Refactor", scope_b))
    conflict_id = responses[0]["payload"]["conflict_id"]

    # Timeout
    coord.conflicts[conflict_id].created_at = _now() - timedelta(seconds=61)
    responses = coord.check_resolution_timeouts()

    error_msgs = [r for r in responses if r["message_type"] == "PROTOCOL_ERROR"]
    assert len(error_msgs) == 1
    assert error_msgs[0]["payload"]["error_code"] == "RESOLUTION_TIMEOUT"


def test_ack_then_resolve():
    """Full flow: ACK → RESOLVE → CLOSED."""
    sid, coord, alice, bob, _, conflict_id = _make_conflict_session()

    # Alice acks
    coord.process_message(alice.ack_conflict(sid, conflict_id, "seen"))
    assert coord.conflicts[conflict_id].state_machine.current_state == ConflictState.ACKED

    # Bob resolves
    coord.process_message(bob.resolve_conflict(sid, conflict_id, "merged"))
    assert coord.conflicts[conflict_id].state_machine.current_state == ConflictState.CLOSED


def test_dismiss_from_escalated():
    """A dismissed resolution from ESCALATED state works."""
    sid, coord, alice, _, arbiter, conflict_id = _make_conflict_session()

    coord.process_message(alice.escalate_conflict(
        sid, conflict_id, "human:arbiter", "need help"))
    assert coord.conflicts[conflict_id].state_machine.current_state == ConflictState.ESCALATED

    coord.process_message(arbiter.resolve_conflict(sid, conflict_id, "dismissed"))
    assert coord.conflicts[conflict_id].state_machine.current_state == ConflictState.DISMISSED
