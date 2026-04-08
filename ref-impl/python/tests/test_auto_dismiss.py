"""Tests for Conflict Auto-Dismissal (Section 17.9)."""
from datetime import timedelta

from mpac.models import Scope, IntentState, ConflictState, OperationState
from mpac.coordinator import SessionCoordinator
from mpac.participant import Participant


def _make_conflicting_session():
    """Create a session with two overlapping intents and a conflict."""
    session_id = "test-dismiss-session"
    coordinator = SessionCoordinator(session_id, intent_expiry_grace_sec=0)

    alice = Participant(
        principal_id="agent:alice",
        principal_type="agent",
        display_name="Alice",
        roles=["contributor"],
    )
    bob = Participant(
        principal_id="agent:bob",
        principal_type="agent",
        display_name="Bob",
        roles=["contributor"],
    )

    # Join
    coordinator.process_message(alice.hello(session_id))
    coordinator.process_message(bob.hello(session_id))

    # Alice announces intent with TTL
    scope_a = Scope(kind="file_set", resources=["src/auth.py", "src/middleware.py"])
    intent_a = alice.announce_intent(session_id, "intent-alice", "Fix auth", scope_a)
    intent_a["payload"]["ttl_sec"] = 120
    coordinator.process_message(intent_a)

    # Bob announces overlapping intent with TTL
    scope_b = Scope(kind="file_set", resources=["src/auth.py", "src/models.py"])
    intent_b = bob.announce_intent(session_id, "intent-bob", "Refactor auth", scope_b)
    intent_b["payload"]["ttl_sec"] = 120
    responses = coordinator.process_message(intent_b)

    # Should have a conflict
    assert len(responses) == 1
    assert responses[0]["message_type"] == "CONFLICT_REPORT"
    conflict_id = responses[0]["payload"]["conflict_id"]

    return session_id, coordinator, alice, bob, conflict_id


def test_auto_dismiss_both_intents_expired():
    """Conflict is auto-dismissed when both related intents expire."""
    session_id, coordinator, alice, bob, conflict_id = _make_conflicting_session()

    conflict = coordinator.conflicts[conflict_id]
    assert conflict.state_machine.current_state == ConflictState.OPEN

    # Both intents expire
    now_expired = coordinator.intents["intent-alice"].received_at + timedelta(seconds=121)
    responses = coordinator.check_expiry(now=now_expired)

    # Both intents should be EXPIRED
    assert coordinator.intents["intent-alice"].state_machine.current_state == IntentState.EXPIRED
    assert coordinator.intents["intent-bob"].state_machine.current_state == IntentState.EXPIRED

    # Conflict should be auto-dismissed
    assert conflict.state_machine.current_state == ConflictState.DISMISSED

    # Should have a system RESOLUTION with decision=dismissed
    resolution_msgs = [r for r in responses if r["message_type"] == "RESOLUTION"]
    assert len(resolution_msgs) == 1
    assert resolution_msgs[0]["payload"]["decision"] == "dismissed"
    assert resolution_msgs[0]["payload"]["rationale"] == "all_related_entities_terminated"
    assert resolution_msgs[0]["payload"]["conflict_id"] == conflict_id


def test_auto_dismiss_one_withdrawn_one_expired():
    """Conflict is auto-dismissed when one intent is withdrawn and the other expired."""
    session_id, coordinator, alice, bob, conflict_id = _make_conflicting_session()

    # Alice withdraws her intent
    withdraw = alice.withdraw_intent(session_id, "intent-alice")
    coordinator.process_message(withdraw)
    assert coordinator.intents["intent-alice"].state_machine.current_state == IntentState.WITHDRAWN

    # Bob's intent is still active — conflict should NOT be dismissed yet
    conflict = coordinator.conflicts[conflict_id]
    assert not conflict.state_machine.is_terminal()

    # Bob's intent expires
    now_expired = coordinator.intents["intent-bob"].received_at + timedelta(seconds=121)
    responses = coordinator.check_expiry(now=now_expired)

    # Now both are terminal — conflict auto-dismissed
    assert conflict.state_machine.current_state == ConflictState.DISMISSED


def test_no_dismiss_if_committed_op_exists():
    """Conflict is NOT auto-dismissed if a related operation is COMMITTED."""
    # Build a custom session where alice commits BEFORE bob creates the conflict
    session_id = "test-dismiss-committed"
    coordinator = SessionCoordinator(session_id, intent_expiry_grace_sec=0)

    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
    bob = Participant("agent:bob", "agent", "Bob", ["contributor"])

    coordinator.process_message(alice.hello(session_id))
    coordinator.process_message(bob.hello(session_id))

    scope_a = Scope(kind="file_set", resources=["src/auth.py", "src/middleware.py"])
    intent_a = alice.announce_intent(session_id, "intent-alice", "Fix auth", scope_a)
    intent_a["payload"]["ttl_sec"] = 120
    coordinator.process_message(intent_a)

    # Alice commits BEFORE bob creates overlapping intent (no frozen scope yet)
    commit_msg = alice.commit_op(
        session_id, "op-alice-1", "intent-alice", "src/auth.py", "patch",
        state_ref_before="sha:a", state_ref_after="sha:b",
    )
    coordinator.process_message(commit_msg)

    # Now bob announces overlapping intent → creates conflict
    scope_b = Scope(kind="file_set", resources=["src/auth.py", "src/models.py"])
    intent_b = bob.announce_intent(session_id, "intent-bob", "Refactor auth", scope_b)
    intent_b["payload"]["ttl_sec"] = 120
    responses = coordinator.process_message(intent_b)
    assert len(responses) == 1
    conflict_id = responses[0]["payload"]["conflict_id"]

    # Manually track the op in the conflict
    conflict = coordinator.conflicts[conflict_id]
    conflict.related_ops.append("op-alice-1")

    # Both intents expire
    now_expired = coordinator.intents["intent-alice"].received_at + timedelta(seconds=121)
    coordinator.check_expiry(now=now_expired)

    # Both intents are terminal
    assert coordinator.intents["intent-alice"].state_machine.current_state == IntentState.EXPIRED
    assert coordinator.intents["intent-bob"].state_machine.current_state == IntentState.EXPIRED

    # But conflict should NOT be auto-dismissed (committed op exists)
    assert not conflict.state_machine.is_terminal()


def test_dismiss_with_rejected_ops():
    """Conflict IS auto-dismissed when all related ops are REJECTED (terminal)."""
    # Build a custom session: propose op BEFORE conflict, so frozen-scope doesn't block
    session_id = "test-dismiss-rejected"
    coordinator = SessionCoordinator(session_id, intent_expiry_grace_sec=0)

    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
    bob = Participant("agent:bob", "agent", "Bob", ["contributor"])

    coordinator.process_message(alice.hello(session_id))
    coordinator.process_message(bob.hello(session_id))

    scope_a = Scope(kind="file_set", resources=["src/auth.py", "src/middleware.py"])
    intent_a = alice.announce_intent(session_id, "intent-alice", "Fix auth", scope_a)
    intent_a["payload"]["ttl_sec"] = 120
    coordinator.process_message(intent_a)

    # Alice proposes BEFORE bob creates conflict
    op_msg = alice.propose_op(session_id, "op-alice-2", "intent-alice", "src/auth.py", "patch")
    coordinator.process_message(op_msg)

    # Now bob creates overlapping intent → conflict
    scope_b = Scope(kind="file_set", resources=["src/auth.py", "src/models.py"])
    intent_b = bob.announce_intent(session_id, "intent-bob", "Refactor auth", scope_b)
    intent_b["payload"]["ttl_sec"] = 120
    responses = coordinator.process_message(intent_b)
    assert len(responses) == 1
    conflict_id = responses[0]["payload"]["conflict_id"]

    # Track op in conflict
    conflict = coordinator.conflicts[conflict_id]
    conflict.related_ops.append("op-alice-2")

    # Both intents expire — this rejects the proposed op AND auto-dismisses
    now_expired = coordinator.intents["intent-alice"].received_at + timedelta(seconds=121)
    responses = coordinator.check_expiry(now=now_expired)

    # Op should be rejected
    assert coordinator.operations["op-alice-2"].state_machine.current_state == OperationState.REJECTED

    # Conflict should be dismissed (all intents terminal + all ops terminal)
    assert conflict.state_machine.current_state == ConflictState.DISMISSED


def test_no_dismiss_partial_intent_termination():
    """Conflict is NOT auto-dismissed if only one of two intents is terminal."""
    session_id, coordinator, alice, bob, conflict_id = _make_conflicting_session()

    # Only Alice withdraws
    withdraw = alice.withdraw_intent(session_id, "intent-alice")
    coordinator.process_message(withdraw)

    conflict = coordinator.conflicts[conflict_id]
    assert not conflict.state_machine.is_terminal()

    # check_expiry at current time should not dismiss (Bob's intent still active)
    responses = coordinator.check_expiry(now=coordinator.intents["intent-alice"].received_at)
    assert not conflict.state_machine.is_terminal()
