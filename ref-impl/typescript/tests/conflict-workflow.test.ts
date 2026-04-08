import { describe, it, expect } from "vitest";
import { SessionCoordinator } from "../src/coordinator.js";
import { Participant } from "../src/participant.js";
import {
  SecurityProfile, ComplianceProfile, Role, ScopeKind,
  ConflictState, MessageType,
} from "../src/models.js";

function makeConflictSession() {
  const sid = "test-cw";
  const coord = new SessionCoordinator(
    sid, SecurityProfile.OPEN, ComplianceProfile.CORE, 0, 90, 60
  );
  const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
  const bob = new Participant("agent:bob", "agent", "Bob", [Role.OWNER]);
  const arbiter = new Participant("human:arbiter", "human", "Arbiter", ["arbiter" as Role]);
  coord.processMessage(alice.hello(sid));
  coord.processMessage(bob.hello(sid));
  coord.processMessage(arbiter.hello(sid));

  coord.processMessage(alice.announceIntent(sid, "i-a", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] }));
  const res = coord.processMessage(bob.announceIntent(sid, "i-b", "Refactor", { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] }));
  expect(res.length).toBe(1);
  const conflictId = (res[0].payload as any).conflict_id;
  return { sid, coord, alice, bob, arbiter, conflictId };
}

describe("Conflict Workflow (Section 17-18)", () => {
  it("CONFLICT_ACK transitions OPEN → ACKED", () => {
    const { sid, coord, alice, conflictId } = makeConflictSession();
    coord.processMessage(alice.ackConflict(sid, conflictId));
    expect(coord.getConflict(conflictId)!.stateMachine.currentState).toBe(ConflictState.ACKED);
  });

  it("CONFLICT_ESCALATE transitions to ESCALATED", () => {
    const { sid, coord, alice, conflictId } = makeConflictSession();
    coord.processMessage(alice.escalateConflict(sid, conflictId, "human:arbiter", "need help"));
    const c = coord.getConflict(conflictId)!;
    expect(c.stateMachine.currentState).toBe(ConflictState.ESCALATED);
    expect(c.escalated_to).toBe("human:arbiter");
  });

  it("arbiter resolves ESCALATED conflict → CLOSED", () => {
    const { sid, coord, alice, arbiter, conflictId } = makeConflictSession();
    coord.processMessage(alice.escalateConflict(sid, conflictId, "human:arbiter", "need help"));
    coord.processMessage(arbiter.resolveConflict(sid, conflictId, "approved", "Alice wins"));
    expect(coord.getConflict(conflictId)!.stateMachine.currentState).toBe(ConflictState.CLOSED);
  });

  it("resolution timeout auto-escalates to arbiter", () => {
    const { sid, coord, conflictId } = makeConflictSession();
    const c = coord.getConflict(conflictId)!;
    c.created_at = Date.now() - 61_000;
    const responses = coord.checkResolutionTimeouts();
    expect(c.stateMachine.currentState).toBe(ConflictState.ESCALATED);
    const escalates = responses.filter(r => r.message_type === MessageType.CONFLICT_ESCALATE);
    expect(escalates.length).toBe(1);
  });

  it("ACK → RESOLVE → CLOSED flow", () => {
    const { sid, coord, alice, bob, conflictId } = makeConflictSession();
    coord.processMessage(alice.ackConflict(sid, conflictId));
    coord.processMessage(bob.resolveConflict(sid, conflictId, "merged"));
    expect(coord.getConflict(conflictId)!.stateMachine.currentState).toBe(ConflictState.CLOSED);
  });

  it("dismiss from ESCALATED", () => {
    const { sid, coord, alice, arbiter, conflictId } = makeConflictSession();
    coord.processMessage(alice.escalateConflict(sid, conflictId, "human:arbiter", "need help"));
    coord.processMessage(arbiter.resolveConflict(sid, conflictId, "dismissed"));
    expect(coord.getConflict(conflictId)!.stateMachine.currentState).toBe(ConflictState.DISMISSED);
  });
});
