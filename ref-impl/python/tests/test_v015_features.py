"""Tests for MPAC v0.1.5 features: session lifecycle, status, snapshots, credentials."""
from datetime import timedelta

from mpac.models import Scope, IntentState, OperationState, ConflictState, ConflictCategory, Severity
from mpac.coordinator import SessionCoordinator, _now
from mpac.participant import Participant


def _make_session(unavailability_timeout_sec=10):
    """Create a test session with two participants."""
    sid = "test-v015"
    coord = SessionCoordinator(sid, unavailability_timeout_sec=unavailability_timeout_sec)
    alice = Participant("agent:alice", "agent", "Alice", ["owner"])
    bob = Participant("agent:bob", "agent", "Bob", ["contributor"])
    coord.process_message(alice.hello(sid))
    coord.process_message(bob.hello(sid))
    return sid, coord, alice, bob


# ============================================================================
#  COORDINATOR_STATUS tests
# ============================================================================

def test_coordinator_status_heartbeat():
    """Call coordinator_status() and verify response contains expected fields."""
    sid, coord, _, _ = _make_session()

    responses = coord.coordinator_status(event="heartbeat")

    assert len(responses) == 1
    msg = responses[0]
    assert msg["message_type"] == "COORDINATOR_STATUS"

    payload = msg["payload"]
    assert payload["event"] == "heartbeat"
    assert payload["coordinator_id"] == f"service:coordinator-{sid}"
    assert payload["session_health"] in ("healthy", "degraded", "recovering")
    assert "active_participants" in payload
    assert "open_conflicts" in payload
    assert "snapshot_lamport_clock" in payload


def test_coordinator_status_health_degraded():
    """Create a conflict and verify session_health is degraded."""
    sid, coord, alice, bob = _make_session()

    # Alice and Bob both announce intents on the same scope
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope))
    coord.process_message(bob.announce_intent(sid, "intent-b", "Fix auth too", scope))

    # Report a conflict
    coord.process_message(alice.report_conflict(
        sid, "conflict-1",
        category=ConflictCategory.SCOPE_OVERLAP.value,
        severity=Severity.HIGH.value,
        principal_a="agent:alice",
        principal_b="agent:bob",
        intent_a="intent-a",
        intent_b="intent-b",
    ))

    # Verify conflict exists and is OPEN
    assert "conflict-1" in coord.conflicts
    assert coord.conflicts["conflict-1"].state_machine.current_state == ConflictState.OPEN

    responses = coord.coordinator_status(event="heartbeat")
    payload = responses[0]["payload"]

    # Should be degraded because there's an open conflict
    assert payload["session_health"] == "degraded"
    assert payload["open_conflicts"] > 0


# ============================================================================
#  SESSION_CLOSE tests
# ============================================================================

def test_session_close_manual():
    """Close session manually and verify SESSION_CLOSE message."""
    sid, coord, alice, bob = _make_session()

    # Add some activity
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope))
    coord.process_message(alice.propose_op(sid, "op-1", "intent-a", "src/auth.py", "patch"))

    # Verify intent and operation exist
    assert "intent-a" in coord.intents
    assert "op-1" in coord.operations

    # Close the session
    responses = coord.close_session("manual")

    assert len(responses) == 1
    msg = responses[0]
    assert msg["message_type"] == "SESSION_CLOSE"

    payload = msg["payload"]
    assert payload["reason"] == "manual"
    assert "final_lamport_clock" in payload
    assert "summary" in payload
    assert payload["active_intents_disposition"] == "withdraw_all"

    # Verify session is marked closed
    assert coord.session_closed is True

    # Verify intent was withdrawn
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.WITHDRAWN

    # Verify operation was abandoned
    assert coord.operations["op-1"].state_machine.current_state == OperationState.ABANDONED


def test_session_close_rejects_new_messages():
    """After session close, new messages should be rejected with SESSION_CLOSED error."""
    sid, coord, alice, bob = _make_session()

    # Close the session
    coord.close_session("manual")

    # Try to announce a new intent
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    responses = coord.process_message(alice.announce_intent(sid, "intent-x", "Fix", scope))

    # Should get PROTOCOL_ERROR with SESSION_CLOSED
    assert len(responses) == 1
    msg = responses[0]
    assert msg["message_type"] == "PROTOCOL_ERROR"
    assert msg["payload"]["error_code"] == "SESSION_CLOSED"


# ============================================================================
#  AUTO_CLOSE tests
# ============================================================================

def test_auto_close_when_all_terminal():
    """All intents/ops terminal → check_auto_close() should return SESSION_CLOSE."""
    sid, coord, alice, _ = _make_session()

    # Create complete workflow: announce → propose → commit → withdraw
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope))
    coord.process_message(alice.propose_op(sid, "op-1", "intent-a", "src/auth.py", "patch"))
    coord.process_message(alice.commit_op(sid, "op-1", "intent-a", "src/auth.py", "patch"))
    coord.process_message(alice.withdraw_intent(sid, "intent-a"))

    # Verify all are terminal
    assert coord.intents["intent-a"].state_machine.is_terminal()
    assert coord.operations["op-1"].state_machine.is_terminal()

    # Check auto-close
    responses = coord.check_auto_close()

    # Should trigger and close session
    assert len(responses) == 1
    msg = responses[0]
    assert msg["message_type"] == "SESSION_CLOSE"
    assert msg["payload"]["reason"] == "completed"
    assert coord.session_closed is True


def test_auto_close_not_triggered_with_active_intent():
    """If there's an active intent, auto_close should not trigger."""
    sid, coord, alice, _ = _make_session()

    # Announce intent but don't withdraw
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope))

    # Intent is ACTIVE (or still in ANNOUNCED state)
    current_state = coord.intents["intent-a"].state_machine.current_state
    assert not coord.intents["intent-a"].state_machine.is_terminal()

    # Check auto-close
    responses = coord.check_auto_close()

    # Should NOT trigger
    assert len(responses) == 0
    assert coord.session_closed is False


# ============================================================================
#  SNAPSHOT tests
# ============================================================================

def test_snapshot_contains_all_state():
    """Snapshot should contain participants, intents, operations, conflicts."""
    sid, coord, alice, bob = _make_session()

    # Add some state - use different scopes to avoid auto-conflict detection
    scope_a = Scope(kind="file_set", resources=["src/auth.py"])
    scope_b = Scope(kind="file_set", resources=["src/config.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope_a))
    coord.process_message(bob.announce_intent(sid, "intent-b", "Fix config", scope_b))
    coord.process_message(alice.propose_op(sid, "op-1", "intent-a", "src/auth.py", "patch"))

    # Create a conflict
    coord.process_message(alice.report_conflict(
        sid, "conflict-1",
        category=ConflictCategory.SEMANTIC_GOAL_CONFLICT.value,
        severity=Severity.MEDIUM.value,
        principal_a="agent:alice",
        principal_b="agent:bob",
        intent_a="intent-a",
        intent_b="intent-b",
    ))

    # Get snapshot
    snapshot = coord.snapshot()

    # Verify structure
    assert snapshot["snapshot_version"] == 2
    assert snapshot["session_id"] == sid
    assert snapshot["protocol_version"] == "0.1.13"
    assert "captured_at" in snapshot
    assert "coordinator_epoch" in snapshot
    assert "lamport_clock" in snapshot
    assert "anti_replay" in snapshot
    assert "recent_message_ids" in snapshot["anti_replay"]
    assert "sender_frontier" in snapshot["anti_replay"]

    # Verify participants
    assert len(snapshot["participants"]) == 2
    participant_ids = {p["principal_id"] for p in snapshot["participants"]}
    assert "agent:alice" in participant_ids
    assert "agent:bob" in participant_ids

    # Verify participants have required fields
    for p in snapshot["participants"]:
        assert "principal_id" in p
        assert "display_name" in p
        assert "roles" in p
        assert "status" in p
        assert "is_available" in p
        assert "last_seen" in p

    # Verify intents
    assert len(snapshot["intents"]) == 2
    intent_ids = {i["intent_id"] for i in snapshot["intents"]}
    assert "intent-a" in intent_ids
    assert "intent-b" in intent_ids

    # Verify intents have required fields
    for intent in snapshot["intents"]:
        assert "intent_id" in intent
        assert "principal_id" in intent
        assert "state" in intent
        assert "scope" in intent
        assert "expires_at" in intent

    # Verify operations
    assert len(snapshot["operations"]) == 1
    assert snapshot["operations"][0]["op_id"] == "op-1"
    assert snapshot["operations"][0]["intent_id"] == "intent-a"
    assert "state" in snapshot["operations"][0]
    assert "target" in snapshot["operations"][0]

    # Verify conflicts (at least one, which is the one we reported)
    assert len(snapshot["conflicts"]) >= 1
    conflict_ids = {c["conflict_id"] for c in snapshot["conflicts"]}
    assert "conflict-1" in conflict_ids
    for conflict in snapshot["conflicts"]:
        assert "conflict_id" in conflict
        assert "state" in conflict
        assert "related_intents" in conflict
        assert "related_ops" in conflict

    # Verify session_closed flag
    assert snapshot["session_closed"] is False


def test_snapshot_empty_session():
    """Snapshot of empty session should have zero intents/ops/conflicts."""
    sid, coord, _, _ = _make_session()

    snapshot = coord.snapshot()

    assert len(snapshot["intents"]) == 0
    assert len(snapshot["operations"]) == 0
    assert len(snapshot["conflicts"]) == 0
    assert len(snapshot["participants"]) == 2  # Alice and Bob joined


# ============================================================================
#  CREDENTIAL tests
# ============================================================================

def test_credential_in_hello():
    """Participant with credential should include it in HELLO payload."""
    sid = "test-cred"
    coord = SessionCoordinator(sid)

    # Create participant with credential
    alice = Participant(
        "agent:alice",
        "agent",
        "Alice",
        ["contributor"],
        credential={"type": "bearer_token", "value": "test-token-12345"}
    )

    # Send HELLO
    hello_msg = alice.hello(sid)
    coord.process_message(hello_msg)

    # Verify credential is in payload
    assert "credential" in hello_msg["payload"]
    assert hello_msg["payload"]["credential"]["type"] == "bearer_token"
    assert hello_msg["payload"]["credential"]["value"] == "test-token-12345"


def test_hello_without_credential():
    """Participant without credential should NOT have credential field in HELLO."""
    sid = "test-no-cred"
    coord = SessionCoordinator(sid)

    # Create participant without credential
    alice = Participant(
        "agent:alice",
        "agent",
        "Alice",
        ["contributor"],
        credential=None
    )

    # Send HELLO
    hello_msg = alice.hello(sid)
    coord.process_message(hello_msg)

    # Verify credential is NOT in payload
    assert "credential" not in hello_msg["payload"]
    assert "display_name" in hello_msg["payload"]
    assert "roles" in hello_msg["payload"]


def test_credential_various_types():
    """Test various credential types."""
    sid = "test-cred-types"

    # Test bearer_token
    alice = Participant(
        "agent:alice",
        "agent",
        "Alice",
        credential={"type": "bearer_token", "value": "token123"}
    )
    hello = alice.hello(sid)
    assert hello["payload"]["credential"]["type"] == "bearer_token"

    # Test api_key
    bob = Participant(
        "agent:bob",
        "agent",
        "Bob",
        credential={"type": "api_key", "value": "key456"}
    )
    hello = bob.hello(sid)
    assert hello["payload"]["credential"]["type"] == "api_key"

    # Test mtls_fingerprint
    charlie = Participant(
        "agent:charlie",
        "agent",
        "Charlie",
        credential={"type": "mtls_fingerprint", "value": "abc123def456"}
    )
    hello = charlie.hello(sid)
    assert hello["payload"]["credential"]["type"] == "mtls_fingerprint"


# ============================================================================
#  Integration tests
# ============================================================================

def test_snapshot_after_close():
    """Snapshot after session close should have session_closed=True."""
    sid, coord, alice, _ = _make_session()

    # Add some state
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))

    # Close session
    coord.close_session("manual")

    # Get snapshot
    snapshot = coord.snapshot()

    assert snapshot["session_closed"] is True


def test_coordinator_status_with_multiple_conflicts():
    """Status should show correct conflict count."""
    sid, coord, alice, bob = _make_session()

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))
    coord.process_message(bob.announce_intent(sid, "intent-b", "Fix", scope))

    # Note: declaring overlapping intents auto-creates a scope_overlap conflict,
    # so we start with 1 conflict. Let's report additional conflicts.
    # Get initial count
    initial_response = coord.coordinator_status()
    initial_conflicts = initial_response[0]["payload"]["open_conflicts"]
    assert initial_conflicts >= 1  # At least the auto-detected scope overlap

    # Create multiple additional conflicts
    for i in range(3):
        coord.process_message(alice.report_conflict(
            sid, f"conflict-{i}",
            category=ConflictCategory.SEMANTIC_GOAL_CONFLICT.value,
            severity=Severity.HIGH.value,
            principal_a="agent:alice",
            principal_b="agent:bob",
            intent_a="intent-a",
            intent_b="intent-b",
        ))

    responses = coord.coordinator_status()
    payload = responses[0]["payload"]

    # Should have at least 4 conflicts (1 auto-detected + 3 manually reported)
    assert payload["open_conflicts"] >= 4
    assert payload["session_health"] == "degraded"


def test_coordinator_status_all_conflicts_resolved():
    """When all conflicts are resolved/dismissed, status should be healthy."""
    sid, coord, alice, bob = _make_session()

    # Use different scopes to avoid auto-conflict creation
    scope_a = Scope(kind="file_set", resources=["src/auth.py"])
    scope_b = Scope(kind="file_set", resources=["src/config.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope_a))
    coord.process_message(bob.announce_intent(sid, "intent-b", "Fix", scope_b))

    # Create a manual conflict
    coord.process_message(alice.report_conflict(
        sid, "conflict-1",
        category=ConflictCategory.SEMANTIC_GOAL_CONFLICT.value,
        severity=Severity.MEDIUM.value,
        principal_a="agent:alice",
        principal_b="agent:bob",
        intent_a="intent-a",
        intent_b="intent-b",
    ))

    # Verify conflict exists and is OPEN
    assert "conflict-1" in coord.conflicts
    assert coord.conflicts["conflict-1"].state_machine.current_state == ConflictState.OPEN

    # Acknowledge the conflict
    coord.process_message(alice.ack_conflict(sid, "conflict-1", ack_type="seen"))
    assert coord.conflicts["conflict-1"].state_machine.current_state == ConflictState.ACKED

    # Resolve the conflict
    coord.process_message(alice.resolve_conflict(
        sid, "conflict-1",
        decision="dismissed",
        rationale="Resolved by alice"
    ))

    # Verify conflict is DISMISSED (terminal state)
    assert coord.conflicts["conflict-1"].state_machine.is_terminal()

    responses = coord.coordinator_status()
    payload = responses[0]["payload"]

    # After resolution, should be healthy
    assert payload["open_conflicts"] == 0
    assert payload["session_health"] == "healthy"


def test_close_session_multiple_operations():
    """Close session with multiple operations in various states."""
    sid, coord, alice, bob = _make_session()

    # Use non-overlapping scopes to avoid frozen-scope blocking ops
    scope_a = Scope(kind="file_set", resources=["src/auth.py"])
    scope_b = Scope(kind="file_set", resources=["src/routes.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope_a))
    coord.process_message(bob.announce_intent(sid, "intent-b", "Refactor", scope_b))

    # Create operations in different states
    coord.process_message(alice.propose_op(sid, "op-1", "intent-a", "src/auth.py", "patch"))
    coord.process_message(bob.propose_op(sid, "op-2", "intent-b", "src/routes.py", "edit"))
    coord.process_message(alice.commit_op(sid, "op-1", "intent-a", "src/auth.py", "patch"))

    # Verify states before close
    assert coord.operations["op-1"].state_machine.current_state == OperationState.COMMITTED
    assert coord.operations["op-2"].state_machine.current_state == OperationState.PROPOSED

    # Close session
    responses = coord.close_session("timeout")

    # Verify session close message
    assert len(responses) == 1
    assert responses[0]["payload"]["reason"] == "timeout"

    # PROPOSED operations should be ABANDONED
    assert coord.operations["op-2"].state_machine.current_state == OperationState.ABANDONED

    # COMMITTED operations should stay COMMITTED
    assert coord.operations["op-1"].state_machine.current_state == OperationState.COMMITTED
