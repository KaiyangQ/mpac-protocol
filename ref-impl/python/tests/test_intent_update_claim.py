"""Tests for INTENT_UPDATE and INTENT_CLAIM (Sections 15.4, 14.5.4)."""
from datetime import timedelta

from mpac.models import Scope, IntentState, OperationState
from mpac.coordinator import SessionCoordinator, _now
from mpac.participant import Participant


def _make_session():
    sid = "test-update-claim"
    coord = SessionCoordinator(sid, unavailability_timeout_sec=10)
    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
    bob = Participant("agent:bob", "agent", "Bob", ["contributor"])
    coord.process_message(alice.hello(sid))
    coord.process_message(bob.hello(sid))
    return sid, coord, alice, bob


# ================================================================
#  INTENT_UPDATE tests
# ================================================================

def test_update_objective():
    """INTENT_UPDATE can change objective."""
    sid, coord, alice, _ = _make_session()
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-1", "Fix auth", scope))

    update = alice.update_intent(sid, "intent-1", objective="Fix auth v2")
    coord.process_message(update)

    assert coord.intents["intent-1"].objective == "Fix auth v2"


def test_update_ttl_extends_expiry():
    """INTENT_UPDATE can extend TTL."""
    sid, coord, alice, _ = _make_session()
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-1", "Fix", scope, ttl_sec=60))

    old_expires = coord.intents["intent-1"].expires_at

    update = alice.update_intent(sid, "intent-1", ttl_sec=300)
    coord.process_message(update)

    # expires_at should have been extended
    assert coord.intents["intent-1"].expires_at > old_expires
    assert coord.intents["intent-1"].ttl_sec == 300.0


def test_update_scope_triggers_new_conflict():
    """When scope changes via INTENT_UPDATE, new overlaps are detected."""
    sid, coord, alice, bob = _make_session()

    # Alice: only models.py
    scope_a = Scope(kind="file_set", resources=["src/models.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix models", scope_a))

    # Bob: only auth.py (no overlap with Alice)
    scope_b = Scope(kind="file_set", resources=["src/auth.py"])
    responses = coord.process_message(bob.announce_intent(sid, "intent-b", "Fix auth", scope_b))
    assert len(responses) == 0  # no conflict yet

    # Alice expands scope to include auth.py → overlap with Bob
    new_scope = Scope(kind="file_set", resources=["src/models.py", "src/auth.py"])
    update = alice.update_intent(sid, "intent-a", scope=new_scope)
    responses = coord.process_message(update)

    # New conflict detected
    assert len(responses) == 1
    assert responses[0]["message_type"] == "CONFLICT_REPORT"


def test_update_scope_no_duplicate_conflict():
    """Scope change doesn't create duplicate conflict if one already exists."""
    sid, coord, alice, bob = _make_session()

    scope_a = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope_a))

    scope_b = Scope(kind="file_set", resources=["src/auth.py"])
    responses = coord.process_message(bob.announce_intent(sid, "intent-b", "Refactor", scope_b))
    assert len(responses) == 1  # conflict already exists

    # Alice updates scope (still overlaps with Bob)
    new_scope = Scope(kind="file_set", resources=["src/auth.py", "src/models.py"])
    update = alice.update_intent(sid, "intent-a", scope=new_scope)
    responses = coord.process_message(update)

    # No duplicate conflict
    assert len(responses) == 0


def test_update_by_non_owner_ignored():
    """INTENT_UPDATE from a non-owner is silently ignored."""
    sid, coord, alice, bob = _make_session()
    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))

    # Bob tries to update Alice's intent
    update = bob.update_intent(sid, "intent-a", objective="Hijacked!")
    coord.process_message(update)

    # Objective unchanged
    assert coord.intents["intent-a"].objective == "Fix"


# ================================================================
#  INTENT_CLAIM tests
# ================================================================

def test_claim_suspended_intent():
    """Bob claims Alice's suspended intent after she goes unavailable."""
    sid, coord, alice, bob = _make_session()

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix auth", scope))

    # Alice proposes an op
    coord.process_message(alice.propose_op(sid, "op-1", "intent-a", "src/auth.py", "patch"))

    # Alice goes unavailable → intent suspended
    coord.participants["agent:alice"].last_seen = _now() - timedelta(seconds=11)
    coord.check_liveness()
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.SUSPENDED

    # Bob claims it
    claim = bob.claim_intent(
        sid,
        claim_id="claim-001",
        original_intent_id="intent-a",
        original_principal_id="agent:alice",
        new_intent_id="intent-b",
        objective="Continue fix auth (claimed)",
        scope=scope,
        justification="Alice is unavailable",
    )
    responses = coord.process_message(claim)

    status_messages = [r for r in responses if r["message_type"] == "INTENT_CLAIM_STATUS"]
    assert len(status_messages) == 1
    assert status_messages[0]["payload"]["decision"] == "approved"

    # Original intent should be TRANSFERRED under v0.1.10
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.TRANSFERRED
    assert coord.intents["intent-a"].claimed_by == "agent:bob"

    # New intent should be ACTIVE
    assert coord.intents["intent-b"].state_machine.current_state == IntentState.ACTIVE
    assert coord.intents["intent-b"].principal_id == "agent:bob"

    # Original op should be rejected (cascade from intent termination)
    assert coord.operations["op-1"].state_machine.current_state in (
        OperationState.REJECTED, OperationState.ABANDONED
    )


def test_claim_non_suspended_rejected():
    """Claiming an ACTIVE (non-suspended) intent returns PROTOCOL_ERROR."""
    sid, coord, alice, bob = _make_session()

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))

    # Intent is ACTIVE, not SUSPENDED
    claim = bob.claim_intent(
        sid, "claim-001", "intent-a", "agent:alice", "intent-b", "Steal it", scope,
    )
    responses = coord.process_message(claim)

    assert len(responses) == 1
    assert responses[0]["message_type"] == "PROTOCOL_ERROR"
    assert responses[0]["payload"]["error_code"] == "INVALID_REFERENCE"


def test_duplicate_claim_rejected():
    """Second claim on the same intent returns CLAIM_CONFLICT error."""
    sid = "test-dup-claim"
    coord = SessionCoordinator(sid, unavailability_timeout_sec=10)
    alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
    bob = Participant("agent:bob", "agent", "Bob", ["contributor"])
    charlie = Participant("agent:charlie", "agent", "Charlie", ["contributor"])
    coord.process_message(alice.hello(sid))
    coord.process_message(bob.hello(sid))
    coord.process_message(charlie.hello(sid))

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))

    # Alice goes unavailable
    coord.participants["agent:alice"].last_seen = _now() - timedelta(seconds=11)
    coord.check_liveness()

    # Bob claims successfully
    claim1 = bob.claim_intent(sid, "claim-1", "intent-a", "agent:alice", "intent-b", "Continue", scope)
    responses1 = coord.process_message(claim1)
    errors1 = [r for r in responses1 if r["message_type"] == "PROTOCOL_ERROR"]
    assert len(errors1) == 0  # no error

    # Charlie tries to claim same intent → CLAIM_CONFLICT
    claim2 = charlie.claim_intent(sid, "claim-2", "intent-a", "agent:alice", "intent-c", "Also continue", scope)
    responses2 = coord.process_message(claim2)
    errors2 = [r for r in responses2 if r["message_type"] == "PROTOCOL_ERROR"]
    assert len(errors2) == 1
    assert errors2[0]["payload"]["error_code"] == "CLAIM_CONFLICT"


def test_reconnection_before_claim_restores_intent():
    """If original participant reconnects, suspended intents are restored (claim not yet made)."""
    sid, coord, alice, bob = _make_session()

    scope = Scope(kind="file_set", resources=["src/auth.py"])
    coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))

    # Alice goes unavailable
    coord.participants["agent:alice"].last_seen = _now() - timedelta(seconds=11)
    coord.check_liveness()
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.SUSPENDED

    # Alice reconnects (via HELLO)
    coord.process_message(alice.hello(sid))
    assert coord.intents["intent-a"].state_machine.current_state == IntentState.ACTIVE
