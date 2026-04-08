"""Happy path test for MPAC protocol."""
import pytest
from mpac import (
    SessionCoordinator,
    Participant,
    Scope,
    IntentState,
    OperationState,
)


def test_happy_path():
    """Test basic protocol flow without conflicts."""
    # Setup
    session_id = "test-session-001"
    coordinator = SessionCoordinator(session_id)

    # Create two participants
    participant_a = Participant(
        principal_id="agent-a",
        principal_type="agent",
        display_name="Agent A",
        roles=["participant"],
        capabilities=["read", "write"],
    )

    participant_b = Participant(
        principal_id="agent-b",
        principal_type="agent",
        display_name="Agent B",
        roles=["participant"],
        capabilities=["read", "write"],
    )

    # Step 1: Both send HELLO
    hello_a = participant_a.hello(session_id)
    responses_a = coordinator.process_message(hello_a)
    assert len(responses_a) == 1
    assert responses_a[0]["message_type"] == "SESSION_INFO"

    hello_b = participant_b.hello(session_id)
    responses_b = coordinator.process_message(hello_b)
    assert len(responses_b) == 1
    assert responses_b[0]["message_type"] == "SESSION_INFO"

    # Verify participants registered
    assert "agent-a" in coordinator.participants
    assert "agent-b" in coordinator.participants

    # Step 2: Participant A announces intent (file_set: ["src/main.py"])
    scope_a = Scope(kind="file_set", resources=["src/main.py"])
    intent_announce_a = participant_a.announce_intent(
        session_id=session_id,
        intent_id="intent-a-001",
        objective="Modify main.py",
        scope=scope_a,
    )
    responses = coordinator.process_message(intent_announce_a)
    # No conflicts expected
    assert len(responses) == 0

    # Verify intent registered
    assert "intent-a-001" in coordinator.intents
    intent = coordinator.intents["intent-a-001"]
    assert intent.principal_id == "agent-a"
    assert intent.state_machine.current_state == IntentState.ACTIVE

    # Step 3: Participant B announces intent (file_set: ["src/utils.py"]) - no overlap
    scope_b = Scope(kind="file_set", resources=["src/utils.py"])
    intent_announce_b = participant_b.announce_intent(
        session_id=session_id,
        intent_id="intent-b-001",
        objective="Modify utils.py",
        scope=scope_b,
    )
    responses = coordinator.process_message(intent_announce_b)
    # No conflicts expected (different files)
    assert len(responses) == 0

    # Verify second intent registered
    assert "intent-b-001" in coordinator.intents
    intent_b = coordinator.intents["intent-b-001"]
    assert intent_b.principal_id == "agent-b"
    assert intent_b.state_machine.current_state == IntentState.ACTIVE

    # Step 4: Participant A proposes operation
    op_propose_a = participant_a.propose_op(
        session_id=session_id,
        op_id="op-a-001",
        intent_id="intent-a-001",
        target="src/main.py",
        op_kind="write",
    )
    responses = coordinator.process_message(op_propose_a)
    assert len(responses) == 0

    # Verify operation registered
    assert "op-a-001" in coordinator.operations
    operation = coordinator.operations["op-a-001"]
    assert operation.state_machine.current_state == OperationState.PROPOSED
    assert operation.intent_id == "intent-a-001"

    # Step 5: Participant A commits operation
    op_commit_a = participant_a.commit_op(
        session_id=session_id,
        op_id="op-a-001",
        intent_id="intent-a-001",
        target="src/main.py",
        op_kind="write",
        state_ref_before="v1.0",
        state_ref_after="v1.1",
    )
    responses = coordinator.process_message(op_commit_a)
    assert len(responses) == 0

    # Verify operation transitioned to COMMITTED
    operation = coordinator.operations["op-a-001"]
    assert operation.state_machine.current_state == OperationState.COMMITTED
    assert operation.state_ref_before == "v1.0"
    assert operation.state_ref_after == "v1.1"

    # Verify all state machines in correct states
    assert coordinator.intents["intent-a-001"].state_machine.current_state == IntentState.ACTIVE
    assert coordinator.intents["intent-b-001"].state_machine.current_state == IntentState.ACTIVE
    assert coordinator.operations["op-a-001"].state_machine.current_state == OperationState.COMMITTED


if __name__ == "__main__":
    test_happy_path()
    print("Happy path test passed!")
