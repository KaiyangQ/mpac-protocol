"""Tests for MPAC v0.1.10 execution and governance closure changes."""

from datetime import timedelta

from mpac.coordinator import SessionCoordinator
from mpac.models import ComplianceProfile, IntentState, MessageType, OperationState, Scope
from mpac.participant import Participant


def test_session_info_declares_execution_model_and_epoch():
    """SESSION_INFO should expose v0.1.10 coordination fields."""
    sid = "test-v0110-session-info"
    coord = SessionCoordinator(sid)
    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

    responses = coord.process_message(alice.hello(sid))
    assert len(responses) == 1

    session_info = responses[0]
    assert session_info["message_type"] == "SESSION_INFO"
    assert session_info["version"] == "0.1.13"
    assert session_info["coordinator_epoch"] == 1
    assert session_info["sender"]["principal_type"] == "service"
    assert session_info["sender"]["sender_instance_id"].startswith(f"service:coordinator-{sid}:epoch-")
    assert session_info["payload"]["execution_model"] == "post_commit"
    assert session_info["payload"]["granted_roles"] == ["contributor"]
    assert session_info["payload"]["state_ref_format"] == "sha256"


def test_pre_commit_commit_requires_authorization_round_trip():
    """Pre-commit sessions should authorize first and commit on the second OP_COMMIT."""
    sid = "test-v0110-pre-commit"
    coord = SessionCoordinator(
        sid,
        compliance_profile=ComplianceProfile.GOVERNANCE.value,
        execution_model="pre_commit",
    )
    alice = Participant("agent:alice", "agent", "Alice", ["owner"])

    coord.process_message(alice.hello(sid))
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope))

    initial = coord.process_message(
        alice.commit_op(
            sid,
            "op-1",
            "intent-a",
            "src/auth.py",
            "patch",
            state_ref_before="sha256:old",
            state_ref_after="sha256:new",
        )
    )

    assert coord.operations["op-1"].state_machine.current_state == OperationState.PROPOSED
    assert coord.operations["op-1"].authorized_by == f"service:coordinator-{sid}"
    assert any(
        response["message_type"] == "COORDINATOR_STATUS"
        and response["payload"]["event"] == "authorization"
        for response in initial
    )

    completion = coord.process_message(
        alice.commit_op(
            sid,
            "op-1",
            "intent-a",
            "src/auth.py",
            "patch",
            state_ref_before="sha256:old",
            state_ref_after="sha256:new",
        )
    )

    assert completion == []
    assert coord.operations["op-1"].state_machine.current_state == OperationState.COMMITTED


def test_op_batch_commit_commits_multiple_operations():
    """Post-commit batches should register individual committed operations."""
    sid = "test-v0110-batch"
    coord = SessionCoordinator(sid)
    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

    coord.process_message(alice.hello(sid))
    scope = Scope(kind="file_set", resources=["src/auth.py", "src/routes.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Batch refactor", scope))

    responses = coord.process_message(
        alice.batch_commit_op(
            sid,
            batch_id="batch-1",
            intent_id="intent-a",
            atomicity="all_or_nothing",
            operations=[
                {
                    "op_id": "op-1",
                    "target": "src/auth.py",
                    "op_kind": "replace",
                    "state_ref_before": "sha256:auth-old",
                    "state_ref_after": "sha256:auth-new",
                },
                {
                    "op_id": "op-2",
                    "target": "src/routes.py",
                    "op_kind": "replace",
                    "state_ref_before": "sha256:routes-old",
                    "state_ref_after": "sha256:routes-new",
                },
            ],
        )
    )

    assert responses == []
    assert coord.operations["op-1"].state_machine.current_state == OperationState.COMMITTED
    assert coord.operations["op-2"].state_machine.current_state == OperationState.COMMITTED
    assert coord.operations["op-1"].batch_id == "batch-1"
    assert coord.operations["op-2"].batch_id == "batch-1"


def test_resolution_conflict_rejects_second_valid_resolution():
    """Only the first valid resolution for a conflict should be accepted."""
    sid = "test-v0110-resolution-conflict"
    coord = SessionCoordinator(sid)
    alice = Participant("agent:alice", "agent", "Alice", ["owner"])
    bob = Participant("agent:bob", "agent", "Bob", ["owner"])

    coord.process_message(alice.hello(sid))
    coord.process_message(bob.hello(sid))
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope))
    conflict_responses = coord.process_message(bob.announce_intent(sid, "intent-b", "Refactor auth", scope))

    conflict_id = next(
        response["payload"]["conflict_id"]
        for response in conflict_responses
        if response["message_type"] == MessageType.CONFLICT_REPORT.value
    )

    first = coord.process_message(alice.resolve_conflict(sid, conflict_id, "dismissed", "Alice backs off"))
    second = coord.process_message(bob.resolve_conflict(sid, conflict_id, "approved", "Bob insists"))

    assert first == []
    assert len(second) == 1
    assert second[0]["message_type"] == "PROTOCOL_ERROR"
    assert second[0]["payload"]["error_code"] == "RESOLUTION_CONFLICT"


def test_governance_claim_status_records_approver():
    """Governance profile claims should include approved_by in INTENT_CLAIM_STATUS."""
    sid = "test-v0110-claim-approval"
    coord = SessionCoordinator(
        sid,
        compliance_profile=ComplianceProfile.GOVERNANCE.value,
        execution_model="post_commit",
    )
    owner = Participant("human:owner", "human", "Owner", ["owner"])
    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
    bob = Participant("agent:bob", "agent", "Bob", ["contributor"])

    coord.process_message(owner.hello(sid))
    coord.process_message(alice.hello(sid))
    coord.process_message(bob.hello(sid))
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope))
    coord.participants["agent:alice"].last_seen = coord.participants["agent:alice"].last_seen - timedelta(seconds=120)
    coord.check_liveness()

    responses = coord.process_message(
        bob.claim_intent(
            sid,
            "claim-1",
            "intent-a",
            "agent:alice",
            "intent-b",
            "Continue fix",
            scope,
        )
    )

    status = next(response for response in responses if response["message_type"] == "INTENT_CLAIM_STATUS")
    assert status["payload"]["decision"] == "approved"
    assert status["payload"]["approved_by"] == "human:owner"
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.TRANSFERRED
