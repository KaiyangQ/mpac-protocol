"""Tests for v0.1.6 features: OP_SUPERSEDE + Coordinator Fault Recovery."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from mpac.models import (
    MessageType, IntentState, OperationState, ConflictState, Scope,
)
from mpac.coordinator import SessionCoordinator
from mpac.participant import Participant
from mpac.state_machines import OperationStateMachine


SESSION = "test-v016"


def make_coordinator():
    return SessionCoordinator(SESSION)


def make_participant(name="Alice"):
    return Participant(
        principal_id=f"agent:{name}",
        principal_type="agent",
        display_name=name,
        roles=["contributor"],
        capabilities=["intent.broadcast", "op.propose", "op.commit"],
    )


def join_and_announce(coord, participant, intent_id, files):
    """Helper: join session and announce an intent."""
    hello = participant.hello(SESSION)
    coord.process_message(hello)
    scope = Scope(kind="file_set", resources=files)
    intent = participant.announce_intent(SESSION, intent_id, "work on files", scope)
    coord.process_message(intent)


def commit_op(coord, participant, op_id, intent_id, target):
    """Helper: commit an operation."""
    msg = participant.commit_op(SESSION, op_id, intent_id, target, "replace",
                                state_ref_before="sha256:aaa", state_ref_after="sha256:bbb")
    coord.process_message(msg)


# ================================================================
# OP_SUPERSEDE tests
# ================================================================


class TestOpSupersede:
    def test_supersede_committed_op(self):
        """OP_SUPERSEDE transitions old op to SUPERSEDED and creates new COMMITTED op."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])
        commit_op(coord, alice, "op-1", "intent-1", "src/main.py")

        # Supersede
        msg = alice.supersede_op(SESSION, "op-2", "op-1", "src/main.py",
                                 intent_id="intent-1", reason="revised_approach",
                                 state_ref_after="sha256:ccc")
        responses = coord.process_message(msg)

        # Old op should be SUPERSEDED
        assert coord.operations["op-1"].state_machine.current_state == OperationState.SUPERSEDED
        # New op should be COMMITTED
        assert coord.operations["op-2"].state_machine.current_state == OperationState.COMMITTED
        # No error responses
        assert len(responses) == 0

    def test_supersede_nonexistent_op(self):
        """OP_SUPERSEDE referencing non-existent op returns error."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])

        msg = alice.supersede_op(SESSION, "op-2", "op-ghost", "src/main.py")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert responses[0]["payload"]["error_code"] == "INVALID_REFERENCE"

    def test_supersede_non_committed_op(self):
        """OP_SUPERSEDE of a non-COMMITTED op returns error."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])

        # Propose but don't commit
        propose_msg = alice.propose_op(SESSION, "op-1", "intent-1", "src/main.py", "replace")
        coord.process_message(propose_msg)

        msg = alice.supersede_op(SESSION, "op-2", "op-1", "src/main.py")
        responses = coord.process_message(msg)

        assert len(responses) == 1
        assert "not COMMITTED" in responses[0]["payload"]["description"]

    def test_supersede_chains_state_ref(self):
        """OP_SUPERSEDE chains state_ref_before from old op's state_ref_after."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])
        commit_op(coord, alice, "op-1", "intent-1", "src/main.py")

        msg = alice.supersede_op(SESSION, "op-2", "op-1", "src/main.py",
                                 state_ref_after="sha256:new")
        coord.process_message(msg)

        new_op = coord.operations["op-2"]
        # state_ref_before should be chained from op-1's state_ref_after
        assert new_op.state_ref_before == "sha256:bbb"
        assert new_op.state_ref_after == "sha256:new"

    def test_supersede_tracked_in_conflicts(self):
        """New op from OP_SUPERSEDE is tracked in related conflicts."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        bob = make_participant("Bob")

        # Alice joins and announces, commits op BEFORE bob creates conflict
        join_and_announce(coord, alice, "intent-a", ["src/main.py"])
        commit_op(coord, alice, "op-1", "intent-a", "src/main.py")

        # Now bob joins and announces overlapping scope → creates conflict
        join_and_announce(coord, bob, "intent-b", ["src/main.py"])

        # There should be a conflict
        assert len(coord.conflicts) == 1
        conflict = list(coord.conflicts.values())[0]

        # Supersede is not blocked by frozen-scope (it operates on existing committed ops)
        msg = alice.supersede_op(SESSION, "op-2", "op-1", "src/main.py",
                                 intent_id="intent-a")
        coord.process_message(msg)

        assert "op-2" in conflict.related_ops

    def test_supersede_state_machine_transition(self):
        """SUPERSEDED is a valid terminal state for OperationStateMachine."""
        sm = OperationStateMachine()
        sm.transition("COMMITTED")
        sm.transition("SUPERSEDED")
        assert sm.current_state == OperationState.SUPERSEDED

    def test_supersede_double_supersede(self):
        """Can supersede a superseding op (chain of supersessions)."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])
        commit_op(coord, alice, "op-1", "intent-1", "src/main.py")

        # First supersede
        msg1 = alice.supersede_op(SESSION, "op-2", "op-1", "src/main.py",
                                  state_ref_after="sha256:v2")
        coord.process_message(msg1)

        # Second supersede
        msg2 = alice.supersede_op(SESSION, "op-3", "op-2", "src/main.py",
                                  state_ref_after="sha256:v3")
        coord.process_message(msg2)

        assert coord.operations["op-1"].state_machine.current_state == OperationState.SUPERSEDED
        assert coord.operations["op-2"].state_machine.current_state == OperationState.SUPERSEDED
        assert coord.operations["op-3"].state_machine.current_state == OperationState.COMMITTED


# ================================================================
# Coordinator Fault Recovery tests
# ================================================================


class TestFaultRecovery:
    def test_snapshot_and_recover_basic(self):
        """Snapshot + recover restores participants and intents."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])

        snap = coord.snapshot()

        # Create a new coordinator and recover
        coord2 = make_coordinator()
        coord2.recover_from_snapshot(snap)

        assert "agent:Alice" in coord2.participants
        assert "intent-1" in coord2.intents
        assert coord2.intents["intent-1"].state_machine.current_state == IntentState.ACTIVE

    def test_snapshot_and_recover_operations(self):
        """Snapshot + recover restores operations with correct states."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])
        commit_op(coord, alice, "op-1", "intent-1", "src/main.py")

        snap = coord.snapshot()
        coord2 = make_coordinator()
        coord2.recover_from_snapshot(snap)

        assert "op-1" in coord2.operations
        assert coord2.operations["op-1"].state_machine.current_state == OperationState.COMMITTED

    def test_snapshot_and_recover_conflicts(self):
        """Snapshot + recover restores conflicts."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        bob = make_participant("Bob")
        join_and_announce(coord, alice, "intent-a", ["src/main.py"])
        join_and_announce(coord, bob, "intent-b", ["src/main.py"])

        snap = coord.snapshot()
        coord2 = make_coordinator()
        coord2.recover_from_snapshot(snap)

        assert len(coord2.conflicts) == 1
        conflict = list(coord2.conflicts.values())[0]
        assert conflict.state_machine.current_state == ConflictState.OPEN

    def test_snapshot_recover_closed_session(self):
        """Snapshot + recover preserves session_closed state."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])
        coord.close_session("manual")

        snap = coord.snapshot()
        coord2 = make_coordinator()
        coord2.recover_from_snapshot(snap)

        assert coord2.session_closed is True

    def test_snapshot_recover_lamport_clock(self):
        """Snapshot + recover preserves lamport clock value."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])

        original_clock = coord.lamport_clock.value
        snap = coord.snapshot()

        coord2 = make_coordinator()
        coord2.recover_from_snapshot(snap)

        assert coord2.lamport_clock.value == original_clock

    def test_audit_log_recording(self):
        """Messages are recorded in audit log."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        hello = alice.hello(SESSION)
        coord.process_message(hello)

        assert len(coord.audit_log) == 1
        assert coord.audit_log[0]["message_type"] == "HELLO"

    def test_replay_audit_log(self):
        """Replay audit log after snapshot produces same state."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        bob = make_participant("Bob")

        # Phase 1: initial state
        join_and_announce(coord, alice, "intent-a", ["src/main.py"])
        snap = coord.snapshot()

        # Phase 2: commit BEFORE bob creates conflict (frozen-scope enforcement)
        commit_op(coord, alice, "op-1", "intent-a", "src/main.py")
        join_and_announce(coord, bob, "intent-b", ["src/main.py"])

        # The audit log has ALL messages, but we need only the ones after snapshot
        # first 2 are alice's hello + intent
        msgs_after_snap = coord.audit_log[2:]

        # Recover from snapshot + replay
        coord2 = make_coordinator()
        coord2.recover_from_snapshot(snap)
        coord2.replay_audit_log(msgs_after_snap)

        assert "agent:Bob" in coord2.participants
        assert "intent-b" in coord2.intents
        assert "op-1" in coord2.operations
        assert coord2.operations["op-1"].state_machine.current_state == OperationState.COMMITTED

    def test_recover_superseded_operation(self):
        """Snapshot + recover restores SUPERSEDED operation state."""
        coord = make_coordinator()
        alice = make_participant("Alice")
        join_and_announce(coord, alice, "intent-1", ["src/main.py"])
        commit_op(coord, alice, "op-1", "intent-1", "src/main.py")

        msg = alice.supersede_op(SESSION, "op-2", "op-1", "src/main.py",
                                 state_ref_after="sha256:new")
        coord.process_message(msg)

        snap = coord.snapshot()
        coord2 = make_coordinator()
        coord2.recover_from_snapshot(snap)

        assert coord2.operations["op-1"].state_machine.current_state == OperationState.SUPERSEDED
        assert coord2.operations["op-2"].state_machine.current_state == OperationState.COMMITTED
