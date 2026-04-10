"""Adversarial / negative-path tests for v0.1.12 runtime enforcement gaps.

Covers 6 enforcement rules + P1/P2 corrections:
1. HELLO-first gate: unregistered senders (except HELLO) are rejected with INVALID_REFERENCE
2. Credential validation: non-open security profiles require credentials in HELLO
3. Resolution authority: only owner/arbiter can resolve pre-escalation conflicts
4. Frozen-scope enforcement: ops blocked on frozen scope; intents differentiate full vs partial overlap;
   batch per-entry intent_ids checked; scope_frozen survives snapshot/recovery
5. Batch atomicity rollback: all_or_nothing batches clean up registered ops on failure
6. Error codes: CAUSAL_GAP and INTENT_BACKOFF are valid error codes
"""
from datetime import timedelta

from mpac.coordinator import _now
from mpac.models import (
    ConflictState,
    ErrorCode,
    IntentState,
    MessageType,
    OperationState,
    Scope,
    CoordinatorEvent,
)
from mpac.coordinator import SessionCoordinator, _now
from mpac.participant import Participant


# ============================================================================
#  1. HELLO-first gate
# ============================================================================

class TestHelloFirstGate:
    def test_intent_before_hello_rejected(self):
        """INTENT_ANNOUNCE from unregistered sender returns INVALID_REFERENCE (Section 14.1)."""
        coord = SessionCoordinator("test-hello-gate")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        scope = Scope(kind="file_set", resources=["src/main.py"])
        msg = alice.announce_intent("test-hello-gate", "intent-1", "Fix main", scope)
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["message_type"] == "PROTOCOL_ERROR"
        assert responses[0]["payload"]["error_code"] == "INVALID_REFERENCE"

    def test_heartbeat_before_hello_rejected(self):
        """HEARTBEAT from unregistered sender returns INVALID_REFERENCE."""
        coord = SessionCoordinator("test-hello-gate-hb")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        msg = alice.heartbeat("test-hello-gate-hb", "idle")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "INVALID_REFERENCE"

    def test_goodbye_before_hello_rejected(self):
        """GOODBYE from unregistered sender triggers INVALID_REFERENCE (must HELLO first)."""
        coord = SessionCoordinator("test-hello-gate-bye")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        msg = alice.goodbye("test-hello-gate-bye", "user_exit")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "INVALID_REFERENCE"

    def test_goodbye_cannot_affect_other_principals_intents(self):
        """A registered sender's GOODBYE cannot withdraw another principal's intents."""
        coord = SessionCoordinator("test-goodbye-ownership")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        bob = Participant("agent:bob", "agent", "Bob", ["contributor"])

        coord.process_message(alice.hello("test-goodbye-ownership"))
        coord.process_message(bob.hello("test-goodbye-ownership"))

        scope = Scope(kind="file_set", resources=["src/main.py"])
        coord.process_message(alice.announce_intent(
            "test-goodbye-ownership", "intent-alice", "Fix", scope))
        assert coord.intents["intent-alice"].state_machine.current_state == IntentState.ACTIVE

        # Bob sends GOODBYE with alice's intent in active_intents
        msg = bob.goodbye("test-goodbye-ownership", "user_exit")
        msg["payload"]["active_intents"] = ["intent-alice"]
        coord.process_message(msg)

        # Alice's intent should NOT be affected
        assert coord.intents["intent-alice"].state_machine.current_state == IntentState.ACTIVE

    def test_hello_itself_allowed(self):
        """HELLO from unregistered sender is allowed (normal join flow)."""
        coord = SessionCoordinator("test-hello-gate-ok")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        msg = alice.hello("test-hello-gate-ok")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["message_type"] == "SESSION_INFO"

    def test_registered_sender_can_announce(self):
        """After HELLO, sender can INTENT_ANNOUNCE normally."""
        coord = SessionCoordinator("test-hello-gate-post")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        coord.process_message(alice.hello("test-hello-gate-post"))
        scope = Scope(kind="file_set", resources=["src/main.py"])
        msg = alice.announce_intent("test-hello-gate-post", "intent-1", "Fix", scope)
        responses = coord.process_message(msg)

        # Should succeed (no AUTHORIZATION_FAILED)
        error_msgs = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"
                      and r["payload"].get("error_code") == "AUTHORIZATION_FAILED"]
        assert len(error_msgs) == 0


# ============================================================================
#  2. Credential validation
# ============================================================================

class TestCredentialValidation:
    def test_authenticated_profile_rejects_no_credential(self):
        """Authenticated security profile rejects HELLO without credential."""
        coord = SessionCoordinator("test-cred-auth", security_profile="authenticated")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        msg = alice.hello("test-cred-auth")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["message_type"] == "PROTOCOL_ERROR"
        assert responses[0]["payload"]["error_code"] == "CREDENTIAL_REJECTED"

    def test_verified_profile_rejects_no_credential(self):
        """Verified security profile also rejects HELLO without credential."""
        coord = SessionCoordinator("test-cred-verified", security_profile="verified")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        msg = alice.hello("test-cred-verified")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "CREDENTIAL_REJECTED"

    def test_authenticated_profile_accepts_valid_credential(self):
        """Authenticated profile accepts HELLO with valid credential."""
        coord = SessionCoordinator("test-cred-ok", security_profile="authenticated",
                                    role_policy={"default_role": "contributor"})
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        msg = alice.hello("test-cred-ok")
        msg["payload"]["credential"] = {"type": "bearer_token", "value": "tok-abc123"}
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["message_type"] == "SESSION_INFO"

    def test_open_profile_allows_no_credential(self):
        """Open security profile allows HELLO without credential."""
        coord = SessionCoordinator("test-cred-open", security_profile="open")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        msg = alice.hello("test-cred-open")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["message_type"] == "SESSION_INFO"

    def test_credential_with_empty_value_rejected(self):
        """Credential with empty value is rejected."""
        coord = SessionCoordinator("test-cred-empty", security_profile="authenticated")
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        msg = alice.hello("test-cred-empty")
        msg["payload"]["credential"] = {"type": "bearer_token", "value": ""}
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "CREDENTIAL_REJECTED"


# ============================================================================
#  3. Resolution authority
# ============================================================================

class TestResolutionAuthority:
    def _make_conflict(self, sid="test-res-auth"):
        """Create a session with an open conflict."""
        coord = SessionCoordinator(sid)
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        bob = Participant("agent:bob", "agent", "Bob", ["contributor"])
        owner = Participant("human:owner", "human", "Owner", ["owner"])
        arbiter = Participant("human:arbiter", "human", "Arbiter", ["arbiter"])

        coord.process_message(alice.hello(sid))
        coord.process_message(bob.hello(sid))
        coord.process_message(owner.hello(sid))
        coord.process_message(arbiter.hello(sid))

        scope = Scope(kind="file_set", resources=["src/auth.py"])
        coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))
        responses = coord.process_message(bob.announce_intent(sid, "intent-b", "Refactor", scope))

        conflict_id = responses[0]["payload"]["conflict_id"]
        return coord, alice, bob, owner, arbiter, conflict_id

    def test_contributor_cannot_resolve_pre_escalation(self):
        """Contributor role cannot resolve a pre-escalation conflict."""
        coord, alice, _, _, _, conflict_id = self._make_conflict()

        responses = coord.process_message(
            alice.resolve_conflict("test-res-auth", conflict_id, "dismissed")
        )

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "AUTHORIZATION_FAILED"

    def test_owner_can_resolve_pre_escalation(self):
        """Owner role can resolve a pre-escalation conflict."""
        coord, _, _, owner, _, conflict_id = self._make_conflict()

        responses = coord.process_message(
            owner.resolve_conflict("test-res-auth", conflict_id, "dismissed")
        )

        assert responses == []
        assert coord.conflicts[conflict_id].state_machine.is_terminal()

    def test_arbiter_can_resolve_pre_escalation(self):
        """Arbiter role can resolve a pre-escalation conflict."""
        coord, _, _, _, arbiter, conflict_id = self._make_conflict()

        responses = coord.process_message(
            arbiter.resolve_conflict("test-res-auth", conflict_id, "dismissed")
        )

        assert responses == []
        assert coord.conflicts[conflict_id].state_machine.is_terminal()

    def test_post_escalation_only_escalate_to_or_arbiter(self):
        """After escalation, only escalate_to target or arbiter can resolve."""
        coord, alice, bob, owner, arbiter, conflict_id = self._make_conflict()

        # Escalate to arbiter
        coord.process_message(alice.escalate_conflict(
            "test-res-auth", conflict_id, "human:arbiter", "need help"
        ))

        # Owner cannot resolve post-escalation (not the escalate_to target)
        responses = coord.process_message(
            owner.resolve_conflict("test-res-auth", conflict_id, "dismissed")
        )
        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "AUTHORIZATION_FAILED"

        # Arbiter (escalate_to target) can resolve
        responses = coord.process_message(
            arbiter.resolve_conflict("test-res-auth", conflict_id, "approved")
        )
        assert responses == []
        assert coord.conflicts[conflict_id].state_machine.current_state == ConflictState.CLOSED


# ============================================================================
#  4. Frozen-scope enforcement
# ============================================================================

class TestFrozenScope:
    def _make_frozen_session(self, sid="test-frozen"):
        """Create a session with a frozen scope (conflict that has timed out).

        Per Section 18.6.2, scopes only enter frozen state after resolution_timeout_sec
        expires, not immediately on conflict creation. This helper creates the conflict
        and then triggers the timeout to enter frozen state.
        """
        # Use short resolution timeout for testing
        coord = SessionCoordinator(sid, resolution_timeout_sec=1)
        alice = Participant("agent:alice", "agent", "Alice", ["owner"])
        bob = Participant("agent:bob", "agent", "Bob", ["contributor"])

        coord.process_message(alice.hello(sid))
        coord.process_message(bob.hello(sid))

        scope = Scope(kind="file_set", resources=["src/auth.py"])
        coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))
        responses = coord.process_message(bob.announce_intent(sid, "intent-b", "Refactor", scope))

        conflict_id = responses[0]["payload"]["conflict_id"]

        # Trigger resolution timeout — no arbiter, so scope enters frozen state
        conflict = coord.conflicts[conflict_id]
        conflict.created_at = _now() - timedelta(seconds=2)
        coord.check_resolution_timeouts()
        assert conflict.scope_frozen, "Scope should be frozen after timeout with no arbiter"

        return coord, alice, bob, conflict_id

    def test_conflict_without_timeout_does_not_freeze(self):
        """A new conflict does NOT immediately freeze the scope."""
        sid = "test-no-freeze"
        coord = SessionCoordinator(sid, resolution_timeout_sec=300)
        alice = Participant("agent:alice", "agent", "Alice", ["owner"])
        bob = Participant("agent:bob", "agent", "Bob", ["contributor"])

        coord.process_message(alice.hello(sid))
        coord.process_message(bob.hello(sid))

        scope = Scope(kind="file_set", resources=["src/auth.py"])
        coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))
        coord.process_message(bob.announce_intent(sid, "intent-b", "Refactor", scope))

        # Operations should still be allowed (scope not frozen yet)
        msg = alice.commit_op(sid, "op-1", "intent-a", "src/auth.py", "patch",
                              state_ref_before="sha:a", state_ref_after="sha:b")
        responses = coord.process_message(msg)

        error_msgs = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"
                      and r["payload"].get("error_code") == "SCOPE_FROZEN"]
        assert len(error_msgs) == 0

    def test_new_intent_fully_contained_in_frozen_scope_rejected(self):
        """INTENT_ANNOUNCE fully contained in frozen scope returns SCOPE_FROZEN."""
        coord, _, _, _ = self._make_frozen_session()

        charlie = Participant("agent:charlie", "agent", "Charlie", ["contributor"])
        coord.process_message(charlie.hello("test-frozen"))

        scope = Scope(kind="file_set", resources=["src/auth.py"])
        msg = charlie.announce_intent("test-frozen", "intent-c", "Also fix", scope)
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["message_type"] == "PROTOCOL_ERROR"
        assert responses[0]["payload"]["error_code"] == "SCOPE_FROZEN"

    def test_new_intent_partially_overlapping_frozen_scope_accepted_with_warning(self):
        """INTENT_ANNOUNCE partially overlapping frozen scope is accepted but warned (Section 18.6.2)."""
        coord, _, _, _ = self._make_frozen_session()

        charlie = Participant("agent:charlie", "agent", "Charlie", ["contributor"])
        coord.process_message(charlie.hello("test-frozen"))

        # Partially overlaps: src/auth.py is frozen, src/utils.py is not
        scope = Scope(kind="file_set", resources=["src/auth.py", "src/utils.py"])
        msg = charlie.announce_intent("test-frozen", "intent-c", "Mixed scope", scope)
        responses = coord.process_message(msg)

        # Intent should be registered (accepted)
        assert "intent-c" in coord.intents

        # Should include a SCOPE_FROZEN warning
        frozen_warnings = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"
                           and r["payload"].get("error_code") == "SCOPE_FROZEN"]
        assert len(frozen_warnings) == 1
        assert "Warning" in frozen_warnings[0]["payload"]["description"]

    def test_propose_on_frozen_scope_rejected(self):
        """OP_PROPOSE on a frozen scope returns SCOPE_FROZEN."""
        coord, alice, _, _ = self._make_frozen_session()

        msg = alice.propose_op("test-frozen", "op-1", "intent-a", "src/auth.py", "patch")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "SCOPE_FROZEN"

    def test_commit_on_frozen_scope_rejected(self):
        """OP_COMMIT (post-commit) on a frozen scope returns SCOPE_FROZEN."""
        coord, alice, _, _ = self._make_frozen_session()

        msg = alice.commit_op("test-frozen", "op-1", "intent-a", "src/auth.py", "patch",
                              state_ref_before="sha:a", state_ref_after="sha:b")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "SCOPE_FROZEN"

    def test_non_overlapping_scope_not_frozen(self):
        """Operations on non-overlapping scope are allowed despite active conflict."""
        coord, alice, _, _ = self._make_frozen_session()

        # Different file, not overlapping with conflict scope
        scope_c = Scope(kind="file_set", resources=["src/utils.py"])
        coord.process_message(alice.announce_intent("test-frozen", "intent-c", "Fix utils", scope_c))

        msg = alice.commit_op("test-frozen", "op-1", "intent-c", "src/utils.py", "patch",
                              state_ref_before="sha:a", state_ref_after="sha:b")
        responses = coord.process_message(msg)

        # Should succeed (no SCOPE_FROZEN error)
        error_msgs = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"
                      and r["payload"].get("error_code") == "SCOPE_FROZEN"]
        assert len(error_msgs) == 0

    def test_batch_commit_on_frozen_scope_rejected(self):
        """OP_BATCH_COMMIT on a frozen scope returns SCOPE_FROZEN."""
        coord, alice, _, _ = self._make_frozen_session()

        msg = alice.batch_commit_op(
            "test-frozen",
            batch_id="batch-frozen",
            intent_id="intent-a",
            atomicity="all_or_nothing",
            operations=[{
                "op_id": "op-batch-1",
                "target": "src/auth.py",
                "op_kind": "patch",
                "state_ref_before": "sha:a",
                "state_ref_after": "sha:b",
            }],
        )
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "SCOPE_FROZEN"

    def test_batch_commit_per_entry_intent_id_frozen_scope_blocked(self):
        """OP_BATCH_COMMIT with per-entry intent_id (no top-level) is also blocked when scope is frozen."""
        coord, alice, _, _ = self._make_frozen_session()

        # Batch with no top-level intent_id, only per-entry intent_id
        msg = alice.batch_commit_op(
            "test-frozen",
            batch_id="batch-bypass",
            intent_id=None,
            atomicity="all_or_nothing",
            operations=[{
                "op_id": "op-bypass-1",
                "intent_id": "intent-a",  # per-entry intent_id
                "target": "src/auth.py",
                "op_kind": "patch",
                "state_ref_before": "sha:a",
                "state_ref_after": "sha:b",
            }],
        )
        # Remove top-level intent_id if participant helper set it
        msg["payload"].pop("intent_id", None)
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "SCOPE_FROZEN"

    def test_batch_commit_no_intent_id_anywhere_frozen_scope_blocked(self):
        """OP_BATCH_COMMIT with no intent_id at any level is blocked by target-based frozen-scope check."""
        coord, alice, _, _ = self._make_frozen_session()

        msg = alice.batch_commit_op(
            "test-frozen",
            batch_id="batch-no-intent",
            intent_id=None,
            atomicity="all_or_nothing",
            operations=[{
                "op_id": "op-no-intent-1",
                "target": "src/auth.py",
                "op_kind": "patch",
                "state_ref_before": "sha:a",
                "state_ref_after": "sha:b",
            }],
        )
        msg["payload"].pop("intent_id", None)
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "SCOPE_FROZEN"

    def test_propose_no_intent_id_frozen_scope_blocked(self):
        """OP_PROPOSE with no intent_id is blocked by target-based frozen-scope check."""
        coord, alice, _, _ = self._make_frozen_session()

        msg = alice.propose_op("test-frozen", "op-no-intent", None, "src/auth.py", "patch")
        msg["payload"].pop("intent_id", None)
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "SCOPE_FROZEN"

    def test_commit_no_intent_id_frozen_scope_blocked(self):
        """OP_COMMIT (post-commit) with no intent_id is blocked by target-based frozen-scope check."""
        coord, alice, _, _ = self._make_frozen_session()

        msg = alice.commit_op("test-frozen", "op-no-intent", None, "src/auth.py", "patch",
                              state_ref_before="sha:a", state_ref_after="sha:b")
        msg["payload"].pop("intent_id", None)
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "SCOPE_FROZEN"

    def test_snapshot_preserves_scope_frozen(self):
        """scope_frozen flag survives snapshot/recovery cycle."""
        coord, alice, _, conflict_id = self._make_frozen_session()

        # Verify scope is frozen
        assert coord.conflicts[conflict_id].scope_frozen is True

        # Take snapshot and recover
        snapshot = coord.snapshot()
        coord2 = SessionCoordinator("test-frozen-recovered")
        coord2.recover_from_snapshot(snapshot)

        # Verify scope_frozen is preserved after recovery
        assert coord2.conflicts[conflict_id].scope_frozen is True

        # Operations on frozen scope should still be blocked after recovery
        msg = alice.commit_op("test-frozen-recovered", "op-recover", "intent-a", "src/auth.py", "patch",
                              state_ref_before="sha:a", state_ref_after="sha:b")
        responses = coord2.process_message(msg)
        frozen_errors = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"
                         and r["payload"].get("error_code") == "SCOPE_FROZEN"]
        assert len(frozen_errors) == 1

    def test_resolved_conflict_unfreezes_scope(self):
        """After conflict resolution, scope is no longer frozen."""
        coord, alice, _, conflict_id = self._make_frozen_session()

        # Resolve conflict (alice is owner, can resolve OPEN/ACKED)
        coord.process_message(alice.resolve_conflict("test-frozen", conflict_id, "dismissed"))
        assert coord.conflicts[conflict_id].state_machine.is_terminal()

        # Now propose should work
        msg = alice.propose_op("test-frozen", "op-1", "intent-a", "src/auth.py", "patch")
        responses = coord.process_message(msg)

        error_msgs = [r for r in responses if r.get("message_type") == "PROTOCOL_ERROR"
                      and r["payload"].get("error_code") == "SCOPE_FROZEN"]
        assert len(error_msgs) == 0


# ============================================================================
#  5. Batch atomicity rollback
# ============================================================================

class TestBatchAtomicityRollback:
    def test_all_or_nothing_cleans_up_on_failure(self):
        """all_or_nothing batch with one bad op should not leave ops registered."""
        sid = "test-batch-rollback"
        coord = SessionCoordinator(sid)
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        coord.process_message(alice.hello(sid))
        scope = Scope(kind="file_set", resources=["src/auth.py"])
        coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))

        # Batch with one valid op and one referencing a non-existent intent
        responses = coord.process_message(
            alice.batch_commit_op(
                sid,
                batch_id="batch-bad",
                intent_id="intent-a",
                atomicity="all_or_nothing",
                operations=[
                    {
                        "op_id": "op-good",
                        "target": "src/auth.py",
                        "op_kind": "patch",
                        "state_ref_before": "sha:a",
                        "state_ref_after": "sha:b",
                    },
                    {
                        "op_id": "op-bad",
                        "intent_id": "intent-nonexistent",  # mismatched intent
                        "target": "src/auth.py",
                        "op_kind": "patch",
                        "state_ref_before": "sha:c",
                        "state_ref_after": "sha:d",
                    },
                ],
            )
        )

        # Should get a rejection
        assert len(responses) == 1
        assert responses[0]["message_type"] == "OP_REJECT"

        # The good op should NOT remain registered (rollback)
        assert "op-good" not in coord.operations

    def test_best_effort_does_not_rollback(self):
        """best_effort batch does not rollback on partial failure."""
        sid = "test-batch-best-effort"
        coord = SessionCoordinator(sid)
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])

        coord.process_message(alice.hello(sid))
        scope = Scope(kind="file_set", resources=["src/auth.py", "src/routes.py"])
        coord.process_message(alice.announce_intent(sid, "intent-a", "Fix", scope))

        responses = coord.process_message(
            alice.batch_commit_op(
                sid,
                batch_id="batch-partial",
                intent_id="intent-a",
                atomicity="best_effort",
                operations=[
                    {
                        "op_id": "op-1",
                        "target": "src/auth.py",
                        "op_kind": "patch",
                        "state_ref_before": "sha:a",
                        "state_ref_after": "sha:b",
                    },
                    {
                        "op_id": "op-2",
                        "target": "src/routes.py",
                        "op_kind": "patch",
                        "state_ref_before": "sha:c",
                        "state_ref_after": "sha:d",
                    },
                ],
            )
        )

        # Both should be committed (no validation failures)
        assert "op-1" in coord.operations
        assert "op-2" in coord.operations


# ============================================================================
#  6. Error codes: CAUSAL_GAP and INTENT_BACKOFF
# ============================================================================

class TestErrorCodes:
    def test_causal_gap_in_enum(self):
        """CAUSAL_GAP is a valid ErrorCode enum member."""
        assert ErrorCode.CAUSAL_GAP.value == "CAUSAL_GAP"

    def test_intent_backoff_in_enum(self):
        """INTENT_BACKOFF is a valid ErrorCode enum member."""
        assert ErrorCode.INTENT_BACKOFF.value == "INTENT_BACKOFF"

    def test_authorization_event_in_coordinator_event(self):
        """authorization is a valid CoordinatorEvent."""
        assert CoordinatorEvent.AUTHORIZATION.value == "authorization"

    def test_all_error_codes_present(self):
        """All 17 spec error codes are present."""
        expected = [
            "MALFORMED_MESSAGE", "UNKNOWN_MESSAGE_TYPE", "INVALID_REFERENCE",
            "VERSION_MISMATCH", "CAPABILITY_UNSUPPORTED", "AUTHORIZATION_FAILED",
            "PARTICIPANT_UNAVAILABLE", "RESOLUTION_TIMEOUT", "SCOPE_FROZEN",
            "CLAIM_CONFLICT", "RESOLUTION_CONFLICT", "COORDINATOR_CONFLICT",
            "STATE_DIVERGENCE", "SESSION_CLOSED", "CREDENTIAL_REJECTED",
            "CAUSAL_GAP", "INTENT_BACKOFF",
        ]
        actual = [e.value for e in ErrorCode]
        for code in expected:
            assert code in actual, f"Missing error code: {code}"
