import { describe, it, expect } from "vitest";
import { SessionCoordinator } from "../src/coordinator.js";
import { Participant } from "../src/participant.js";
import {
  SecurityProfile, ComplianceProfile, Role, ScopeKind,
  IntentState, OperationState, MessageType, ConflictState,
} from "../src/models.js";

function makeSession(unavailabilityTimeoutSec = 10) {
  const sid = "test-v015";
  const coord = new SessionCoordinator(
    sid, SecurityProfile.OPEN, ComplianceProfile.CORE, 0, unavailabilityTimeoutSec
  );
  const alice = new Participant("agent:alice", "agent", "Alice", [Role.OWNER]);
  const bob = new Participant("agent:bob", "agent", "Bob", [Role.OWNER]);
  coord.processMessage(alice.hello(sid));
  coord.processMessage(bob.hello(sid));
  return { sid, coord, alice, bob };
}

describe("v0.1.5 Features", () => {
  describe("Coordinator Status Heartbeat (Section 8.3)", () => {
    it("coordinator status heartbeat", () => {
      const { sid, coord } = makeSession();
      const responses = coord.coordinatorStatus("heartbeat");
      expect(responses.length).toBe(1);
      const msg = responses[0];
      expect(msg.message_type).toBe(MessageType.COORDINATOR_STATUS);
      expect((msg.payload as any).event).toBe("heartbeat");
      expect((msg.payload as any).coordinator_id).toBeTruthy();
      expect((msg.payload as any).session_health).toBeDefined();
      expect((msg.payload as any).active_participants).toBe(2);
      expect((msg.payload as any).open_conflicts).toBe(0);
      expect((msg.payload as any).snapshot_lamport_clock).toBeDefined();
    });

    it("coordinator status health degraded with open conflict", () => {
      const { sid, coord, alice, bob } = makeSession();
      // Create two overlapping intents to trigger a conflict
      const resp1 = coord.processMessage(
        alice.announceIntent(sid, "i-1", "Fix bug", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] })
      );
      expect(resp1.length).toBe(0); // First intent, no conflicts yet

      const resp2 = coord.processMessage(
        bob.announceIntent(sid, "i-2", "Refactor", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] })
      );
      expect(resp2.length).toBe(1); // Should get CONFLICT_REPORT
      expect(resp2[0].message_type).toBe(MessageType.CONFLICT_REPORT);

      // Now check status
      const status = coord.coordinatorStatus("heartbeat");
      expect(status.length).toBe(1);
      const msg = status[0];
      expect((msg.payload as any).session_health).toBe("degraded");
      expect((msg.payload as any).open_conflicts).toBeGreaterThan(0);
    });
  });

  describe("Session Close (Section 9.1)", () => {
    it("session close manual", () => {
      const { sid, coord, alice } = makeSession();
      // Add participant, announce intent
      coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));
      expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.ACTIVE);

      // Close session manually
      const closeResponses = coord.closeSession("manual");
      expect(closeResponses.length).toBe(1);
      const msg = closeResponses[0];
      expect(msg.message_type).toBe(MessageType.SESSION_CLOSE);
      expect((msg.payload as any).reason).toBe("manual");
      expect((msg.payload as any).final_lamport_clock).toBeDefined();
      expect((msg.payload as any).summary).toBeDefined();
      expect((msg.payload as any).active_intents_disposition).toBe("withdraw_all");

      // Intent should be withdrawn
      expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.WITHDRAWN);
    });

    it("session close rejects new messages", () => {
      const { sid, coord, alice } = makeSession();
      coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));

      // Close the session
      coord.closeSession("manual");

      // Try to send a new message
      const responses = coord.processMessage(
        alice.announceIntent(sid, "i-2", "Another fix", { kind: ScopeKind.FILE_SET, resources: ["src/b.py"] })
      );
      expect(responses.length).toBe(1);
      expect(responses[0].message_type).toBe(MessageType.PROTOCOL_ERROR);
      expect((responses[0].payload as any).error_code).toBe("SESSION_CLOSED");
    });
  });

  describe("Auto Close (Section 9.2)", () => {
    it("auto close when all terminal", () => {
      const { sid, coord, alice } = makeSession();
      // Join, announce intent, propose and commit operation, withdraw intent
      coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));
      expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.ACTIVE);

      // Propose and commit operation
      coord.processMessage(alice.proposeOp(sid, "op-1", "i-1", "src/a.py", "patch"));
      expect(coord.getOperation("op-1")!.stateMachine.currentState).toBe(OperationState.PROPOSED);

      coord.processMessage(alice.commitOp(sid, "op-1", "i-1", "src/a.py", "patch"));
      expect(coord.getOperation("op-1")!.stateMachine.currentState).toBe(OperationState.COMMITTED);

      // Withdraw intent
      coord.processMessage(alice.withdrawIntent(sid, "i-1"));
      expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.WITHDRAWN);

      // Check auto close - should trigger
      const closeResponses = coord.checkAutoClose();
      expect(closeResponses.length).toBe(1);
      expect(closeResponses[0].message_type).toBe(MessageType.SESSION_CLOSE);
      expect((closeResponses[0].payload as any).reason).toBe("completed");
    });

    it("auto close not triggered with active intent", () => {
      const { sid, coord, alice } = makeSession();
      // Announce intent (active)
      coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));
      expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.ACTIVE);

      // Check auto close - should not trigger
      const closeResponses = coord.checkAutoClose();
      expect(closeResponses.length).toBe(0);
    });
  });

  describe("Snapshot (Section 9.3)", () => {
    it("snapshot contains all state", () => {
      const { sid, coord, alice, bob } = makeSession();
      // Build up session state
      coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));

      // Propose and commit BEFORE bob creates overlapping intent (frozen-scope enforcement)
      coord.processMessage(alice.proposeOp(sid, "op-1", "i-1", "src/a.py", "patch"));
      coord.processMessage(alice.commitOp(sid, "op-1", "i-1", "src/a.py", "patch"));

      coord.processMessage(bob.announceIntent(sid, "i-2", "Refactor", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));

      // Get snapshot
      const snap = coord.snapshot();
      expect(snap).toBeDefined();
      expect(snap.snapshot_version).toBe(2);
      expect(snap.session_id).toBe(sid);
      expect(snap.protocol_version).toBe("0.1.13");
      expect(snap.captured_at).toBeDefined();
      expect(snap.coordinator_epoch).toBeDefined();
      expect(snap.lamport_clock).toBeDefined();
      expect(snap.anti_replay).toBeDefined();
      expect(snap.anti_replay.recent_message_ids).toBeDefined();
      expect(snap.anti_replay.sender_frontier).toBeDefined();

      // Check participants
      expect(snap.participants).toBeDefined();
      expect(snap.participants.length).toBe(2);
      expect(snap.participants[0].principal_id).toBeTruthy();
      expect(snap.participants[0].display_name).toBeTruthy();
      expect(snap.participants[0].status).toBeTruthy();
      expect(snap.participants[0].is_available).toBeDefined();

      // Check intents
      expect(snap.intents).toBeDefined();
      expect(snap.intents.length).toBe(2);
      expect(snap.intents[0].intent_id).toBe("i-1");
      expect(snap.intents[0].state).toBe(IntentState.ACTIVE);
      expect(snap.intents[0].scope).toBeDefined();

      // Check operations
      expect(snap.operations).toBeDefined();
      expect(snap.operations.length).toBe(1);
      expect(snap.operations[0].op_id).toBe("op-1");
      expect(snap.operations[0].state).toBe(OperationState.COMMITTED);

      // Check conflicts
      expect(snap.conflicts).toBeDefined();
      expect(snap.conflicts.length).toBeGreaterThan(0);
      expect(snap.conflicts[0].conflict_id).toBeTruthy();
      expect(snap.conflicts[0].state).toBeDefined();
      expect(snap.conflicts[0].related_intents).toBeDefined();

      // Check session_closed flag
      expect(snap.session_closed).toBe(false);
    });
  });

  describe("Credential in Hello (Section 6.2)", () => {
    it("credential in hello", () => {
      const sid = "test-cred";
      const coord = new SessionCoordinator(sid, SecurityProfile.AUTHENTICATED, ComplianceProfile.CORE,
        30, 90, 300, "post_commit", "sha256", 0, { default_role: "contributor" });

      const credential = {
        type: "bearer_token",
        value: "token-abc123",
        issuer: "auth.example.com",
        expires_at: "2025-12-31T23:59:59Z",
      };

      const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR], [], credential);
      const responses = coord.processMessage(alice.hello(sid));

      expect(responses.length).toBe(1);
      expect(responses[0].message_type).toBe(MessageType.SESSION_INFO);

      // Verify participant was registered with credential
      const participantInfo = coord.getParticipant("agent:alice");
      expect(participantInfo).toBeDefined();
      expect(participantInfo!.principal.principal_id).toBe("agent:alice");
    });

    it("credential in hello payload", () => {
      const sid = "test-cred-payload";
      const coord = new SessionCoordinator(sid, SecurityProfile.AUTHENTICATED, ComplianceProfile.CORE,
        30, 90, 300, "post_commit", "sha256", 0, { default_role: "contributor" });

      const credential = {
        type: "mtls_fingerprint",
        value: "abcdef123456",
        issuer: "pki.example.com",
      };

      const bob = new Participant("agent:bob", "agent", "Bob", [Role.CONTRIBUTOR], [], credential);
      const helloMsg = bob.hello(sid);

      // Check that credential is in the payload
      expect((helloMsg.payload as any).credential).toBeDefined();
      expect((helloMsg.payload as any).credential.type).toBe("mtls_fingerprint");
      expect((helloMsg.payload as any).credential.value).toBe("abcdef123456");
      expect((helloMsg.payload as any).credential.issuer).toBe("pki.example.com");
    });
  });

  describe("Integration: Combine all v0.1.5 features", () => {
    it("full lifecycle with status monitoring and snapshot", () => {
      const { sid, coord, alice, bob } = makeSession();

      // Start with healthy status
      let statusMsg = coord.coordinatorStatus("heartbeat");
      expect((statusMsg[0].payload as any).session_health).toBe("healthy");
      expect((statusMsg[0].payload as any).open_conflicts).toBe(0);

      // Create overlapping intents
      coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));
      coord.processMessage(bob.announceIntent(sid, "i-2", "Refactor", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));

      // Status should now show degraded
      statusMsg = coord.coordinatorStatus("heartbeat");
      expect((statusMsg[0].payload as any).session_health).toBe("degraded");
      expect((statusMsg[0].payload as any).open_conflicts).toBeGreaterThan(0);

      // Get snapshot
      const snap1 = coord.snapshot();
      expect(snap1.intents.length).toBe(2);
      expect(snap1.conflicts.length).toBeGreaterThan(0);
      expect(snap1.session_closed).toBe(false);

      // Resolve conflict by withdrawing one intent
      const conflicts = coord.getConflicts();
      if (conflicts.length > 0) {
        const firstConflict = conflicts[0];
        coord.processMessage(bob.resolveConflict(sid, firstConflict.conflict_id, "dismissed"));
      }

      // Withdraw intents
      coord.processMessage(alice.withdrawIntent(sid, "i-1"));
      coord.processMessage(bob.withdrawIntent(sid, "i-2"));

      // Check auto close
      const closeMsg = coord.checkAutoClose();
      expect(closeMsg.length).toBe(1);
      expect(closeMsg[0].message_type).toBe(MessageType.SESSION_CLOSE);

      // Final snapshot should show closed session
      const snap2 = coord.snapshot();
      expect(snap2.session_closed).toBe(true);
    });
  });
});
