import { describe, it, expect } from "vitest";
import { SessionCoordinator } from "../src/coordinator.js";
import { Participant } from "../src/participant.js";
import {
  MessageType,
  SecurityProfile,
  ComplianceProfile,
  IntentState,
  OperationState,
  ConflictState,
  Role,
  ScopeKind,
} from "../src/models.js";
import { OperationStateMachine } from "../src/state-machines.js";

const SESSION = "test-v016";

function makeCoordinator() {
  return new SessionCoordinator(SESSION);
}

function makeParticipant(name: string) {
  return new Participant(
    `agent:${name}`, "agent", name,
    [Role.CONTRIBUTOR],
    ["intent.broadcast", "op.propose", "op.commit"]
  );
}

function joinAndAnnounce(coord: SessionCoordinator, p: Participant, intentId: string, files: string[]) {
  const hello = p.hello(SESSION);
  coord.processMessage(hello);
  const intent = p.announceIntent(SESSION, intentId, "work on files", {
    kind: ScopeKind.FILE_SET, resources: files,
  });
  coord.processMessage(intent);
}

function commitOp(coord: SessionCoordinator, p: Participant, opId: string, intentId: string, target: string) {
  const msg = p.commitOp(SESSION, opId, intentId, target, "replace", "sha256:aaa", "sha256:bbb");
  coord.processMessage(msg);
}

// ================================================================
// OP_SUPERSEDE tests
// ================================================================

describe("OP_SUPERSEDE", () => {
  it("supersedes a committed op", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    joinAndAnnounce(coord, alice, "intent-1", ["src/main.py"]);
    commitOp(coord, alice, "op-1", "intent-1", "src/main.py");

    const msg = alice.supersedeOp(SESSION, "op-2", "op-1", "src/main.py", "intent-1", "revised");
    const responses = coord.processMessage(msg);

    expect(coord.getOperation("op-1")!.stateMachine.currentState).toBe(OperationState.SUPERSEDED);
    expect(coord.getOperation("op-2")!.stateMachine.currentState).toBe(OperationState.COMMITTED);
    expect(responses.length).toBe(0);
  });

  it("rejects supersede of non-existent op", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    joinAndAnnounce(coord, alice, "intent-1", ["src/main.py"]);

    const msg = alice.supersedeOp(SESSION, "op-2", "op-ghost", "src/main.py");
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("INVALID_REFERENCE");
  });

  it("rejects supersede of non-committed op", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    joinAndAnnounce(coord, alice, "intent-1", ["src/main.py"]);

    const propose = alice.proposeOp(SESSION, "op-1", "intent-1", "src/main.py", "replace");
    coord.processMessage(propose);

    const msg = alice.supersedeOp(SESSION, "op-2", "op-1", "src/main.py");
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).description).toContain("not COMMITTED");
  });

  it("supports chain of supersessions", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    joinAndAnnounce(coord, alice, "intent-1", ["src/main.py"]);
    commitOp(coord, alice, "op-1", "intent-1", "src/main.py");

    coord.processMessage(alice.supersedeOp(SESSION, "op-2", "op-1", "src/main.py"));
    coord.processMessage(alice.supersedeOp(SESSION, "op-3", "op-2", "src/main.py"));

    expect(coord.getOperation("op-1")!.stateMachine.currentState).toBe(OperationState.SUPERSEDED);
    expect(coord.getOperation("op-2")!.stateMachine.currentState).toBe(OperationState.SUPERSEDED);
    expect(coord.getOperation("op-3")!.stateMachine.currentState).toBe(OperationState.COMMITTED);
  });

  it("state machine supports COMMITTED -> SUPERSEDED", () => {
    const sm = new OperationStateMachine(OperationState.PROPOSED);
    sm.transition("commit");
    sm.transition("supersede");
    expect(sm.currentState).toBe(OperationState.SUPERSEDED);
    expect(sm.isTerminal()).toBe(true);
  });
});

// ================================================================
// Fault Recovery tests
// ================================================================

describe("Fault Recovery", () => {
  it("snapshot + recover restores participants and intents", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    joinAndAnnounce(coord, alice, "intent-1", ["src/main.py"]);

    const snap = coord.snapshot();
    const coord2 = makeCoordinator();
    coord2.recoverFromSnapshot(snap);

    expect(coord2.getParticipant("agent:Alice")).toBeDefined();
    expect(coord2.getIntent("intent-1")).toBeDefined();
    expect(coord2.getIntent("intent-1")!.stateMachine.currentState).toBe(IntentState.ACTIVE);
  });

  it("snapshot + recover restores operations", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    joinAndAnnounce(coord, alice, "intent-1", ["src/main.py"]);
    commitOp(coord, alice, "op-1", "intent-1", "src/main.py");

    const snap = coord.snapshot();
    const coord2 = makeCoordinator();
    coord2.recoverFromSnapshot(snap);

    expect(coord2.getOperation("op-1")).toBeDefined();
    expect(coord2.getOperation("op-1")!.stateMachine.currentState).toBe(OperationState.COMMITTED);
  });

  it("snapshot + recover restores conflicts", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    const bob = makeParticipant("Bob");
    joinAndAnnounce(coord, alice, "intent-a", ["src/main.py"]);
    joinAndAnnounce(coord, bob, "intent-b", ["src/main.py"]);

    const snap = coord.snapshot();
    const coord2 = makeCoordinator();
    coord2.recoverFromSnapshot(snap);

    expect(coord2.getConflicts().length).toBe(1);
    expect(coord2.getConflicts()[0].stateMachine.currentState).toBe(ConflictState.OPEN);
  });

  it("snapshot + recover preserves session closed state", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    joinAndAnnounce(coord, alice, "intent-1", ["src/main.py"]);
    coord.closeSession("manual");

    const snap = coord.snapshot();
    const coord2 = makeCoordinator();
    coord2.recoverFromSnapshot(snap);

    // Session should be closed - try sending a message
    const bob = makeParticipant("Bob");
    const hello = bob.hello(SESSION);
    const responses = coord2.processMessage(hello);
    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("SESSION_CLOSED");
  });

  it("audit log records messages", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    coord.processMessage(alice.hello(SESSION));

    const log = coord.getAuditLog();
    expect(log.length).toBe(1);
    expect(log[0].message_type).toBe(MessageType.HELLO);
  });

  it("replay audit log after snapshot", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    const bob = makeParticipant("Bob");

    joinAndAnnounce(coord, alice, "intent-a", ["src/main.py"]);
    const snap = coord.snapshot();

    // Commit BEFORE bob creates conflict (frozen-scope enforcement)
    commitOp(coord, alice, "op-1", "intent-a", "src/main.py");
    joinAndAnnounce(coord, bob, "intent-b", ["src/main.py"]);

    const msgsAfterSnap = coord.getAuditLog().slice(2);

    const coord2 = makeCoordinator();
    coord2.recoverFromSnapshot(snap);
    coord2.replayAuditLog(msgsAfterSnap);

    expect(coord2.getParticipant("agent:Bob")).toBeDefined();
    expect(coord2.getIntent("intent-b")).toBeDefined();
    expect(coord2.getOperation("op-1")).toBeDefined();
    expect(coord2.getOperation("op-1")!.stateMachine.currentState).toBe(OperationState.COMMITTED);
  });

  it("recover superseded operation state", () => {
    const coord = makeCoordinator();
    const alice = makeParticipant("Alice");
    joinAndAnnounce(coord, alice, "intent-1", ["src/main.py"]);
    commitOp(coord, alice, "op-1", "intent-1", "src/main.py");
    coord.processMessage(alice.supersedeOp(SESSION, "op-2", "op-1", "src/main.py"));

    const snap = coord.snapshot();
    const coord2 = makeCoordinator();
    coord2.recoverFromSnapshot(snap);

    expect(coord2.getOperation("op-1")!.stateMachine.currentState).toBe(OperationState.SUPERSEDED);
    expect(coord2.getOperation("op-2")!.stateMachine.currentState).toBe(OperationState.COMMITTED);
  });
});
