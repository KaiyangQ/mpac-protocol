"""Tests for Intent Expiry Cascade (Section 15.7)."""
from datetime import datetime, timezone, timedelta

from mpac.models import Scope, IntentState, OperationState, MessageType
from mpac.coordinator import SessionCoordinator
from mpac.participant import Participant


def _make_session():
    """Create a coordinator and two participants."""
    session_id = "test-expiry-session"
    coordinator = SessionCoordinator(session_id, intent_expiry_grace_sec=0)

    alice = Participant(
        principal_id="agent:alice",
        principal_type="agent",
        display_name="Alice",
        roles=["contributor"],
        capabilities=["intent.broadcast", "op.propose", "op.commit"],
    )
    bob = Participant(
        principal_id="agent:bob",
        principal_type="agent",
        display_name="Bob",
        roles=["contributor"],
        capabilities=["intent.broadcast", "op.propose", "op.commit"],
    )

    # Join session
    coordinator.process_message(alice.hello(session_id))
    coordinator.process_message(bob.hello(session_id))

    return session_id, coordinator, alice, bob


def test_intent_expiry_basic():
    """An intent with a TTL should expire after the TTL elapses."""
    session_id, coordinator, alice, _ = _make_session()

    # Alice announces intent with 60s TTL
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    intent_msg = alice.announce_intent(session_id, "intent-alice-1", "Fix auth", scope)
    intent_msg["payload"]["ttl_sec"] = 60
    coordinator.process_message(intent_msg)

    intent = coordinator.intents["intent-alice-1"]
    assert intent.state_machine.current_state == IntentState.ACTIVE
    assert intent.ttl_sec == 60.0
    assert intent.expires_at is not None

    # Time passes: 30 seconds — not expired yet
    now_30s = intent.received_at + timedelta(seconds=30)
    responses = coordinator.check_expiry(now=now_30s)
    assert len(responses) == 0
    assert intent.state_machine.current_state == IntentState.ACTIVE

    # Time passes: 61 seconds — now expired
    now_61s = intent.received_at + timedelta(seconds=61)
    responses = coordinator.check_expiry(now=now_61s)
    assert intent.state_machine.current_state == IntentState.EXPIRED


def test_expiry_cascade_rejects_proposed_ops():
    """When an intent expires, PROPOSED operations referencing it are auto-rejected."""
    session_id, coordinator, alice, _ = _make_session()

    # Alice announces intent with TTL
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    intent_msg = alice.announce_intent(session_id, "intent-alice-2", "Fix auth", scope)
    intent_msg["payload"]["ttl_sec"] = 60
    coordinator.process_message(intent_msg)

    # Alice proposes an operation under that intent
    op_msg = alice.propose_op(session_id, "op-alice-1", "intent-alice-2", "src/auth.py", "patch")
    coordinator.process_message(op_msg)

    op = coordinator.operations["op-alice-1"]
    assert op.state_machine.current_state == OperationState.PROPOSED

    # Intent expires
    now_expired = coordinator.intents["intent-alice-2"].received_at + timedelta(seconds=61)
    responses = coordinator.check_expiry(now=now_expired)

    # Operation should be auto-rejected
    assert op.state_machine.current_state == OperationState.REJECTED

    # Should have generated an OP_REJECT message
    reject_msgs = [r for r in responses if r["message_type"] == "OP_REJECT"]
    assert len(reject_msgs) == 1
    assert reject_msgs[0]["payload"]["op_id"] == "op-alice-1"
    assert reject_msgs[0]["payload"]["reason"] == "intent_terminated"


def test_expiry_does_not_affect_committed_ops():
    """Committed operations are NOT affected by intent expiry (Rule 4)."""
    session_id, coordinator, alice, _ = _make_session()

    # Alice announces intent with TTL
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    intent_msg = alice.announce_intent(session_id, "intent-alice-3", "Fix auth", scope)
    intent_msg["payload"]["ttl_sec"] = 60
    coordinator.process_message(intent_msg)

    # Alice commits an operation (direct commit, no prior propose)
    commit_msg = alice.commit_op(
        session_id, "op-alice-2", "intent-alice-3", "src/auth.py", "patch",
        state_ref_before="sha:aaa", state_ref_after="sha:bbb",
    )
    coordinator.process_message(commit_msg)
    assert coordinator.operations["op-alice-2"].state_machine.current_state == OperationState.COMMITTED

    # Intent expires
    now_expired = coordinator.intents["intent-alice-3"].received_at + timedelta(seconds=61)
    responses = coordinator.check_expiry(now=now_expired)

    # Operation should still be COMMITTED
    assert coordinator.operations["op-alice-2"].state_machine.current_state == OperationState.COMMITTED

    # No OP_REJECT for the committed op
    reject_msgs = [r for r in responses if r["message_type"] == "OP_REJECT"]
    assert len(reject_msgs) == 0


def test_withdraw_triggers_cascade():
    """INTENT_WITHDRAW should trigger the same cascade as expiry."""
    session_id, coordinator, alice, _ = _make_session()

    # Alice announces intent (no TTL)
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    intent_msg = alice.announce_intent(session_id, "intent-alice-4", "Fix auth", scope)
    coordinator.process_message(intent_msg)

    # Alice proposes an operation
    op_msg = alice.propose_op(session_id, "op-alice-3", "intent-alice-4", "src/auth.py", "patch")
    coordinator.process_message(op_msg)
    assert coordinator.operations["op-alice-3"].state_machine.current_state == OperationState.PROPOSED

    # Alice withdraws the intent
    withdraw_msg = alice.withdraw_intent(session_id, "intent-alice-4", reason="changed my mind")
    responses = coordinator.process_message(withdraw_msg)

    # Intent should be WITHDRAWN
    assert coordinator.intents["intent-alice-4"].state_machine.current_state == IntentState.WITHDRAWN

    # Operation should be auto-rejected
    assert coordinator.operations["op-alice-3"].state_machine.current_state == OperationState.REJECTED

    # Should have generated OP_REJECT
    reject_msgs = [r for r in responses if r["message_type"] == "OP_REJECT"]
    assert len(reject_msgs) == 1


def test_propose_on_terminated_intent_rejected():
    """Proposing an operation on a terminated intent is immediately rejected."""
    session_id, coordinator, alice, _ = _make_session()

    # Alice announces and withdraws an intent
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    intent_msg = alice.announce_intent(session_id, "intent-alice-5", "Fix auth", scope)
    coordinator.process_message(intent_msg)
    withdraw_msg = alice.withdraw_intent(session_id, "intent-alice-5")
    coordinator.process_message(withdraw_msg)

    # Now try to propose on the withdrawn intent
    op_msg = alice.propose_op(session_id, "op-alice-4", "intent-alice-5", "src/auth.py", "patch")
    responses = coordinator.process_message(op_msg)

    # Should be immediately rejected
    assert coordinator.operations["op-alice-4"].state_machine.current_state == OperationState.REJECTED
    reject_msgs = [r for r in responses if r["message_type"] == "OP_REJECT"]
    assert len(reject_msgs) == 1
    assert reject_msgs[0]["payload"]["reason"] == "intent_terminated"


def test_no_ttl_no_expiry():
    """Intents without TTL should never expire via check_expiry."""
    session_id, coordinator, alice, _ = _make_session()

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    intent_msg = alice.announce_intent(session_id, "intent-alice-6", "Fix auth", scope)
    coordinator.process_message(intent_msg)

    intent = coordinator.intents["intent-alice-6"]
    assert intent.ttl_sec is None
    assert intent.expires_at is None

    # Even far in the future, no expiry
    far_future = datetime(2099, 1, 1, tzinfo=timezone.utc)
    responses = coordinator.check_expiry(now=far_future)
    assert len(responses) == 0
    assert intent.state_machine.current_state == IntentState.ACTIVE
