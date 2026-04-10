import { describe, it, expect } from "vitest";
import { SessionCoordinator } from "../src/coordinator.js";
import { Participant } from "../src/participant.js";
import {
  SecurityProfile,
  ComplianceProfile,
  Role,
  ScopeKind,
  IntentState,
  OperationState,
  MessageType,
} from "../src/models.js";

function makeSession() {
  const sessionId = "test-expiry-session";
  const coordinator = new SessionCoordinator(
    sessionId,
    SecurityProfile.OPEN,
    ComplianceProfile.CORE,
    0 // no grace period
  );

  const alice = new Participant(
    "agent:alice",
    "agent",
    "Alice",
    [Role.CONTRIBUTOR],
    ["intent.broadcast", "op.propose", "op.commit"]
  );
  const bob = new Participant(
    "agent:bob",
    "agent",
    "Bob",
    [Role.CONTRIBUTOR],
    ["intent.broadcast", "op.propose", "op.commit"]
  );

  coordinator.processMessage(alice.hello(sessionId));
  coordinator.processMessage(bob.hello(sessionId));

  return { sessionId, coordinator, alice, bob };
}

describe("Intent Expiry Cascade (Section 15.7)", () => {
  it("expires an intent after TTL elapses", () => {
    const { sessionId, coordinator, alice } = makeSession();

    const intentEnv = alice.announceIntent(
      sessionId,
      "intent-1",
      "Fix auth",
      { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] }
    );
    (intentEnv.payload as any).ttl_sec = 60;
    coordinator.processMessage(intentEnv);

    const intent = coordinator.getIntent("intent-1")!;
    expect(intent.stateMachine.currentState).toBe(IntentState.ACTIVE);
    expect(intent.expires_at).toBeDefined();

    // Not expired yet at +30s
    coordinator.checkExpiry(intent.received_at + 30_000);
    expect(intent.stateMachine.currentState).toBe(IntentState.ACTIVE);

    // Expired at +61s
    coordinator.checkExpiry(intent.received_at + 61_000);
    expect(intent.stateMachine.currentState).toBe(IntentState.EXPIRED);
  });

  it("auto-rejects PROPOSED operations when intent expires", () => {
    const { sessionId, coordinator, alice } = makeSession();

    const intentEnv = alice.announceIntent(
      sessionId,
      "intent-2",
      "Fix auth",
      { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] }
    );
    (intentEnv.payload as any).ttl_sec = 60;
    coordinator.processMessage(intentEnv);

    const opEnv = alice.proposeOp(
      sessionId,
      "op-1",
      "intent-2",
      "src/auth.py",
      "patch"
    );
    coordinator.processMessage(opEnv);

    const op = coordinator.getOperation("op-1")!;
    expect(op.stateMachine.currentState).toBe(OperationState.PROPOSED);

    const intent = coordinator.getIntent("intent-2")!;
    const responses = coordinator.checkExpiry(intent.received_at + 61_000);

    expect(op.stateMachine.currentState).toBe(OperationState.REJECTED);

    const rejects = responses.filter(
      (r) => r.message_type === MessageType.OP_REJECT
    );
    expect(rejects.length).toBe(1);
    expect((rejects[0].payload as any).op_id).toBe("op-1");
    expect((rejects[0].payload as any).reason).toBe("intent_terminated");
  });

  it("does NOT affect COMMITTED operations (Rule 4)", () => {
    const { sessionId, coordinator, alice } = makeSession();

    const intentEnv = alice.announceIntent(
      sessionId,
      "intent-3",
      "Fix auth",
      { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] }
    );
    (intentEnv.payload as any).ttl_sec = 60;
    coordinator.processMessage(intentEnv);

    const commitEnv = alice.commitOp(
      sessionId,
      "op-2",
      "intent-3",
      "src/auth.py",
      "patch",
      "sha:a",
      "sha:b"
    );
    coordinator.processMessage(commitEnv);

    const op = coordinator.getOperation("op-2")!;
    expect(op.stateMachine.currentState).toBe(OperationState.COMMITTED);

    const intent = coordinator.getIntent("intent-3")!;
    const responses = coordinator.checkExpiry(intent.received_at + 61_000);

    // Op still committed
    expect(op.stateMachine.currentState).toBe(OperationState.COMMITTED);
    const rejects = responses.filter(
      (r) => r.message_type === MessageType.OP_REJECT
    );
    expect(rejects.length).toBe(0);
  });

  it("INTENT_WITHDRAW triggers cascade", () => {
    const { sessionId, coordinator, alice } = makeSession();

    const intentEnv = alice.announceIntent(
      sessionId,
      "intent-4",
      "Fix auth",
      { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] }
    );
    coordinator.processMessage(intentEnv);

    const opEnv = alice.proposeOp(
      sessionId,
      "op-3",
      "intent-4",
      "src/auth.py",
      "patch"
    );
    coordinator.processMessage(opEnv);

    const withdrawEnv = alice.withdrawIntent(sessionId, "intent-4");
    const responses = coordinator.processMessage(withdrawEnv);

    const intent = coordinator.getIntent("intent-4")!;
    expect(intent.stateMachine.currentState).toBe(IntentState.WITHDRAWN);

    const op = coordinator.getOperation("op-3")!;
    expect(op.stateMachine.currentState).toBe(OperationState.REJECTED);

    const rejects = responses.filter(
      (r) => r.message_type === MessageType.OP_REJECT
    );
    expect(rejects.length).toBe(1);
  });

  it("proposing on a terminated intent is immediately rejected", () => {
    const { sessionId, coordinator, alice } = makeSession();

    const intentEnv = alice.announceIntent(
      sessionId,
      "intent-5",
      "Fix auth",
      { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] }
    );
    coordinator.processMessage(intentEnv);

    const withdrawEnv = alice.withdrawIntent(sessionId, "intent-5");
    coordinator.processMessage(withdrawEnv);

    const opEnv = alice.proposeOp(
      sessionId,
      "op-4",
      "intent-5",
      "src/auth.py",
      "patch"
    );
    const responses = coordinator.processMessage(opEnv);

    const op = coordinator.getOperation("op-4")!;
    expect(op.stateMachine.currentState).toBe(OperationState.REJECTED);

    const rejects = responses.filter(
      (r) => r.message_type === MessageType.OP_REJECT
    );
    expect(rejects.length).toBe(1);
    expect((rejects[0].payload as any).reason).toBe("intent_terminated");
  });
});
