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
  ConflictState,
  MessageType,
} from "../src/models.js";

function makeConflictingSession() {
  const sessionId = "test-dismiss-session";
  const coordinator = new SessionCoordinator(
    sessionId,
    SecurityProfile.OPEN,
    ComplianceProfile.CORE,
    0
  );

  const alice = new Participant(
    "agent:alice",
    "agent",
    "Alice",
    [Role.CONTRIBUTOR],
    ["intent.broadcast", "op.propose"]
  );
  const bob = new Participant(
    "agent:bob",
    "agent",
    "Bob",
    [Role.CONTRIBUTOR],
    ["intent.broadcast", "op.propose"]
  );

  coordinator.processMessage(alice.hello(sessionId));
  coordinator.processMessage(bob.hello(sessionId));

  // Alice: auth.py + middleware.py (with TTL)
  const intentA = alice.announceIntent(sessionId, "intent-alice", "Fix auth", {
    kind: ScopeKind.FILE_SET,
    resources: ["src/auth.py", "src/middleware.py"],
  });
  (intentA.payload as any).ttl_sec = 120;
  coordinator.processMessage(intentA);

  // Bob: auth.py + models.py (with TTL) — overlaps on auth.py
  const intentB = bob.announceIntent(
    sessionId,
    "intent-bob",
    "Refactor auth",
    {
      kind: ScopeKind.FILE_SET,
      resources: ["src/auth.py", "src/models.py"],
    }
  );
  (intentB.payload as any).ttl_sec = 120;
  const responses = coordinator.processMessage(intentB);

  expect(responses.length).toBe(1);
  expect(responses[0].message_type).toBe(MessageType.CONFLICT_REPORT);
  const conflictId = (responses[0].payload as any).conflict_id;

  return { sessionId, coordinator, alice, bob, conflictId };
}

describe("Conflict Auto-Dismissal (Section 17.9)", () => {
  it("auto-dismisses when both intents expire", () => {
    const { coordinator, conflictId } = makeConflictingSession();

    const conflict = coordinator.getConflict(conflictId)!;
    expect(conflict.stateMachine.currentState).toBe(ConflictState.OPEN);

    const intentAlice = coordinator.getIntent("intent-alice")!;
    const responses = coordinator.checkExpiry(intentAlice.received_at + 121_000);

    expect(
      coordinator.getIntent("intent-alice")!.stateMachine.currentState
    ).toBe(IntentState.EXPIRED);
    expect(
      coordinator.getIntent("intent-bob")!.stateMachine.currentState
    ).toBe(IntentState.EXPIRED);

    expect(conflict.stateMachine.currentState).toBe(ConflictState.DISMISSED);

    const resolutions = responses.filter(
      (r) => r.message_type === MessageType.RESOLUTION
    );
    expect(resolutions.length).toBe(1);
    expect((resolutions[0].payload as any).decision).toBe("dismissed");
    expect((resolutions[0].payload as any).rationale).toBe(
      "all_related_entities_terminated"
    );
  });

  it("auto-dismisses when one withdrawn + one expired", () => {
    const { sessionId, coordinator, alice, conflictId } =
      makeConflictingSession();

    // Alice withdraws
    const withdrawEnv = alice.withdrawIntent(sessionId, "intent-alice");
    coordinator.processMessage(withdrawEnv);

    expect(
      coordinator.getIntent("intent-alice")!.stateMachine.currentState
    ).toBe(IntentState.WITHDRAWN);

    // Conflict still open (Bob is active)
    const conflict = coordinator.getConflict(conflictId)!;
    expect(conflict.stateMachine.isTerminal()).toBe(false);

    // Bob's intent expires
    const intentBob = coordinator.getIntent("intent-bob")!;
    coordinator.checkExpiry(intentBob.received_at + 121_000);

    expect(conflict.stateMachine.currentState).toBe(ConflictState.DISMISSED);
  });

  it("does NOT dismiss if a committed op exists", () => {
    // Custom setup: commit op BEFORE bob creates the conflict (frozen-scope enforcement)
    const sessionId = "test-dismiss-committed";
    const coordinator = new SessionCoordinator(
      sessionId,
      SecurityProfile.OPEN,
      ComplianceProfile.CORE,
      0
    );
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    const bob = new Participant("agent:bob", "agent", "Bob", [Role.CONTRIBUTOR]);
    coordinator.processMessage(alice.hello(sessionId));
    coordinator.processMessage(bob.hello(sessionId));

    const intentA = alice.announceIntent(sessionId, "intent-alice", "Fix auth", {
      kind: ScopeKind.FILE_SET,
      resources: ["src/auth.py", "src/middleware.py"],
    });
    (intentA.payload as any).ttl_sec = 120;
    coordinator.processMessage(intentA);

    // Commit BEFORE conflict exists
    const commitEnv = alice.commitOp(sessionId, "op-alice-1", "intent-alice", "src/auth.py", "patch", "sha:a", "sha:b");
    coordinator.processMessage(commitEnv);

    // Bob announces → creates conflict
    const intentB = bob.announceIntent(sessionId, "intent-bob", "Refactor auth", {
      kind: ScopeKind.FILE_SET,
      resources: ["src/auth.py", "src/models.py"],
    });
    (intentB.payload as any).ttl_sec = 120;
    const responses = coordinator.processMessage(intentB);
    expect(responses.length).toBe(1);
    const conflictId = (responses[0].payload as any).conflict_id;

    // Manually add the op to conflict's related_ops
    const conflict = coordinator.getConflict(conflictId)!;
    conflict.related_ops.push("op-alice-1");

    // Both intents expire
    const intentAlice = coordinator.getIntent("intent-alice")!;
    coordinator.checkExpiry(intentAlice.received_at + 121_000);

    expect(coordinator.getIntent("intent-alice")!.stateMachine.currentState).toBe(IntentState.EXPIRED);
    expect(coordinator.getIntent("intent-bob")!.stateMachine.currentState).toBe(IntentState.EXPIRED);

    // But conflict NOT dismissed (committed op)
    expect(conflict.stateMachine.isTerminal()).toBe(false);
  });

  it("dismisses when all related ops are rejected", () => {
    // Custom setup: propose op BEFORE bob creates the conflict
    const sessionId = "test-dismiss-rejected";
    const coordinator = new SessionCoordinator(
      sessionId,
      SecurityProfile.OPEN,
      ComplianceProfile.CORE,
      0
    );
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    const bob = new Participant("agent:bob", "agent", "Bob", [Role.CONTRIBUTOR]);
    coordinator.processMessage(alice.hello(sessionId));
    coordinator.processMessage(bob.hello(sessionId));

    const intentA = alice.announceIntent(sessionId, "intent-alice", "Fix auth", {
      kind: ScopeKind.FILE_SET,
      resources: ["src/auth.py", "src/middleware.py"],
    });
    (intentA.payload as any).ttl_sec = 120;
    coordinator.processMessage(intentA);

    // Propose BEFORE conflict exists
    const proposeEnv = alice.proposeOp(sessionId, "op-alice-2", "intent-alice", "src/auth.py", "patch");
    coordinator.processMessage(proposeEnv);

    // Bob announces → creates conflict
    const intentB = bob.announceIntent(sessionId, "intent-bob", "Refactor auth", {
      kind: ScopeKind.FILE_SET,
      resources: ["src/auth.py", "src/models.py"],
    });
    (intentB.payload as any).ttl_sec = 120;
    const responses = coordinator.processMessage(intentB);
    expect(responses.length).toBe(1);
    const conflictId = (responses[0].payload as any).conflict_id;

    // Track op in conflict
    const conflict = coordinator.getConflict(conflictId)!;
    conflict.related_ops.push("op-alice-2");

    // Both intents expire → op auto-rejected → conflict auto-dismissed
    const intentAlice = coordinator.getIntent("intent-alice")!;
    coordinator.checkExpiry(intentAlice.received_at + 121_000);

    expect(coordinator.getOperation("op-alice-2")!.stateMachine.currentState).toBe(OperationState.REJECTED);
    expect(conflict.stateMachine.currentState).toBe(ConflictState.DISMISSED);
  });

  it("does NOT dismiss with only partial intent termination", () => {
    const { sessionId, coordinator, alice, conflictId } =
      makeConflictingSession();

    // Only Alice withdraws
    const withdrawEnv = alice.withdrawIntent(sessionId, "intent-alice");
    coordinator.processMessage(withdrawEnv);

    const conflict = coordinator.getConflict(conflictId)!;
    expect(conflict.stateMachine.isTerminal()).toBe(false);

    // Check at current time (Bob still active)
    const intentAlice = coordinator.getIntent("intent-alice")!;
    coordinator.checkExpiry(intentAlice.received_at);
    expect(conflict.stateMachine.isTerminal()).toBe(false);
  });
});
