from datetime import timedelta

from mpac_protocol.core.coordinator import SessionCoordinator, _now
from mpac_protocol.core.models import IntentState, Scope
from mpac_protocol.core.participant import Participant


def test_core_profile_claim_approval_carries_required_metadata_and_snapshots():
    session_id = "claim-smoke"
    coordinator = SessionCoordinator(
        session_id,
        intent_claim_grace_sec=0,
        unavailability_timeout_sec=10,
    )
    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
    bob = Participant("agent:bob", "agent", "Bob", ["contributor"])
    scope = Scope(kind="file_set", resources=["README.md"])

    coordinator.process_message(alice.hello(session_id))
    coordinator.process_message(bob.hello(session_id))
    coordinator.process_message(
        alice.announce_intent(session_id, "intent-a", "Edit README", scope)
    )

    coordinator.participants["agent:alice"].last_seen = _now() - timedelta(seconds=11)
    coordinator.check_liveness()
    assert coordinator.intents["intent-a"].state_machine.current_state == IntentState.SUSPENDED

    responses = coordinator.process_message(
        bob.claim_intent(
            session_id,
            "claim-1",
            "intent-a",
            "agent:alice",
            "intent-b",
            "Continue README edit",
            scope,
            justification="Alice is unavailable",
        )
    )

    status = next(
        response for response in responses
        if response["message_type"] == "INTENT_CLAIM_STATUS"
    )
    assert status["payload"]["decision"] == "approved"
    assert coordinator.intents["intent-b"].state_machine.current_state == IntentState.ACTIVE
    assert coordinator.snapshot()["pending_claims"] == []
