"""Conflict detection and resolution test."""
import pytest
from mpac import (
    SessionCoordinator,
    Participant,
    Scope,
    ConflictState,
    IntentState,
)


def test_conflict_detection():
    """Test scope overlap detection and conflict reporting."""
    # Setup
    session_id = "test-session-002"
    coordinator = SessionCoordinator(session_id)

    # Create two participants
    participant_a = Participant(
        principal_id="agent-a",
        principal_type="agent",
        display_name="Agent A",
        roles=["owner"],
    )

    participant_b = Participant(
        principal_id="agent-b",
        principal_type="agent",
        display_name="Agent B",
        roles=["contributor"],
    )

    # Step 1: Both join session
    hello_a = participant_a.hello(session_id)
    coordinator.process_message(hello_a)

    hello_b = participant_b.hello(session_id)
    coordinator.process_message(hello_b)

    # Step 2: Participant A announces intent with files ["src/main.py", "src/config.py"]
    scope_a = Scope(kind="file_set", resources=["src/main.py", "src/config.py"])
    intent_announce_a = participant_a.announce_intent(
        session_id=session_id,
        intent_id="intent-a-001",
        objective="Modify main and config",
        scope=scope_a,
    )
    responses = coordinator.process_message(intent_announce_a)
    # No conflicts expected (first intent)
    assert len(responses) == 0

    # Verify intent registered and active
    assert "intent-a-001" in coordinator.intents
    intent_a = coordinator.intents["intent-a-001"]
    assert intent_a.state_machine.current_state == IntentState.ACTIVE

    # Step 3: Participant B announces intent with overlap ["src/config.py", "src/db.py"]
    scope_b = Scope(kind="file_set", resources=["src/config.py", "src/db.py"])
    intent_announce_b = participant_b.announce_intent(
        session_id=session_id,
        intent_id="intent-b-001",
        objective="Modify config and db",
        scope=scope_b,
    )
    responses = coordinator.process_message(intent_announce_b)

    # Conflict expected due to overlap on src/config.py
    assert len(responses) == 1
    conflict_report = responses[0]
    assert conflict_report["message_type"] == "CONFLICT_REPORT"
    assert conflict_report["payload"]["category"] == "scope_overlap"
    assert conflict_report["payload"]["severity"] == "medium"
    assert conflict_report["payload"]["principal_a"] == "agent-b"
    assert conflict_report["payload"]["principal_b"] == "agent-a"
    assert conflict_report["payload"]["intent_a"] == "intent-b-001"
    assert conflict_report["payload"]["intent_b"] == "intent-a-001"

    # Verify conflict registered
    conflict_id = conflict_report["payload"]["conflict_id"]
    assert conflict_id in coordinator.conflicts
    conflict = coordinator.conflicts[conflict_id]
    assert conflict.state_machine.current_state == ConflictState.OPEN

    # Verify intent B registered
    assert "intent-b-001" in coordinator.intents
    intent_b = coordinator.intents["intent-b-001"]
    assert intent_b.state_machine.current_state == IntentState.ACTIVE

    # Step 4: Resolve conflict
    resolution = participant_a.resolve_conflict(
        session_id=session_id,
        conflict_id=conflict_id,
        decision="accept",
    )
    responses = coordinator.process_message(resolution)

    # Verify conflict state transitioned
    conflict = coordinator.conflicts[conflict_id]
    assert conflict.state_machine.current_state == ConflictState.CLOSED


def test_path_normalization():
    """Test that path normalization works correctly for scope overlap."""
    from mpac import scope_overlap

    # Same file, different path formats
    scope_1 = Scope(kind="file_set", resources=["./src/main.py"])
    scope_2 = Scope(kind="file_set", resources=["src/main.py"])
    assert scope_overlap(scope_1, scope_2) is True

    # Collapsed slashes
    scope_3 = Scope(kind="file_set", resources=["src//main.py"])
    assert scope_overlap(scope_1, scope_3) is True

    # Trailing slashes
    scope_4 = Scope(kind="file_set", resources=["src/"])
    scope_5 = Scope(kind="file_set", resources=["src"])
    assert scope_overlap(scope_4, scope_5) is True

    # No overlap
    scope_6 = Scope(kind="file_set", resources=["src/main.py"])
    scope_7 = Scope(kind="file_set", resources=["src/utils.py"])
    assert scope_overlap(scope_6, scope_7) is False


def test_entity_set_overlap():
    """Test entity_set scope overlap detection."""
    from mpac import scope_overlap

    # Exact match
    scope_1 = Scope(kind="entity_set", entities=["entity:user:123"])
    scope_2 = Scope(kind="entity_set", entities=["entity:user:123"])
    assert scope_overlap(scope_1, scope_2) is True

    # No match
    scope_3 = Scope(kind="entity_set", entities=["entity:user:123"])
    scope_4 = Scope(kind="entity_set", entities=["entity:user:456"])
    assert scope_overlap(scope_3, scope_4) is False

    # Multiple items, one overlaps
    scope_5 = Scope(kind="entity_set", entities=["entity:user:123", "entity:user:456"])
    scope_6 = Scope(kind="entity_set", entities=["entity:user:456", "entity:user:789"])
    assert scope_overlap(scope_5, scope_6) is True


def test_task_set_overlap():
    """Test task_set scope overlap detection."""
    from mpac import scope_overlap

    # Exact match
    scope_1 = Scope(kind="task_set", task_ids=["task:deploy"])
    scope_2 = Scope(kind="task_set", task_ids=["task:deploy"])
    assert scope_overlap(scope_1, scope_2) is True

    # No match
    scope_3 = Scope(kind="task_set", task_ids=["task:deploy"])
    scope_4 = Scope(kind="task_set", task_ids=["task:test"])
    assert scope_overlap(scope_3, scope_4) is False


if __name__ == "__main__":
    test_conflict_detection()
    print("Conflict detection test passed!")

    test_path_normalization()
    print("Path normalization test passed!")

    test_entity_set_overlap()
    print("Entity set overlap test passed!")

    test_task_set_overlap()
    print("Task set overlap test passed!")
