import { describe, it, expect } from "vitest";
import { SessionCoordinator } from "../src/coordinator.js";
import { Participant } from "../src/participant.js";
import {
  SecurityProfile, ComplianceProfile, Role, ScopeKind,
  IntentState, OperationState, MessageType,
} from "../src/models.js";

function makeSession() {
  const sid = "test-uc";
  const coord = new SessionCoordinator(
    sid, SecurityProfile.OPEN, ComplianceProfile.CORE, 0, 10
  );
  const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
  const bob = new Participant("agent:bob", "agent", "Bob", [Role.CONTRIBUTOR]);
  coord.processMessage(alice.hello(sid));
  coord.processMessage(bob.hello(sid));
  return { sid, coord, alice, bob };
}

describe("INTENT_UPDATE (Section 15.4)", () => {
  it("updates objective", () => {
    const { sid, coord, alice } = makeSession();
    coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["a.py"] }));
    coord.processMessage(alice.updateIntent(sid, "i-1", { objective: "Fix v2" }));
    expect(coord.getIntent("i-1")!.objective).toBe("Fix v2");
  });

  it("extends TTL", () => {
    const { sid, coord, alice } = makeSession();
    const env = alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["a.py"] });
    (env.payload as any).ttl_sec = 60;
    coord.processMessage(env);
    const old = coord.getIntent("i-1")!.expires_at!;
    coord.processMessage(alice.updateIntent(sid, "i-1", { ttl_sec: 300 }));
    expect(coord.getIntent("i-1")!.expires_at!).toBeGreaterThan(old);
  });

  it("scope change detects new overlap", () => {
    const { sid, coord, alice, bob } = makeSession();
    coord.processMessage(alice.announceIntent(sid, "i-a", "Fix models", { kind: ScopeKind.FILE_SET, resources: ["models.py"] }));
    coord.processMessage(bob.announceIntent(sid, "i-b", "Fix auth", { kind: ScopeKind.FILE_SET, resources: ["auth.py"] }));
    // No conflict yet
    expect(coord.getConflicts().length).toBe(0);
    // Alice expands scope
    const res = coord.processMessage(alice.updateIntent(sid, "i-a", { scope: { kind: ScopeKind.FILE_SET, resources: ["models.py", "auth.py"] } }));
    expect(res.length).toBe(1);
    expect(res[0].message_type).toBe(MessageType.CONFLICT_REPORT);
  });

  it("non-owner update is ignored", () => {
    const { sid, coord, alice, bob } = makeSession();
    coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["a.py"] }));
    coord.processMessage(bob.updateIntent(sid, "i-1", { objective: "Hijack" }));
    expect(coord.getIntent("i-1")!.objective).toBe("Fix");
  });
});

describe("INTENT_CLAIM (Section 14.5.4)", () => {
  it("claims a suspended intent", () => {
    const { sid, coord, alice, bob } = makeSession();
    const scope = { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] };
    coord.processMessage(alice.announceIntent(sid, "i-a", "Fix", scope as any));
    coord.processMessage(alice.proposeOp(sid, "op-1", "i-a", "src/auth.py", "patch"));

    // Alice goes unavailable
    coord.getParticipant("agent:alice")!.last_seen = Date.now() - 11_000;
    coord.checkLiveness();
    expect(coord.getIntent("i-a")!.stateMachine.currentState).toBe(IntentState.SUSPENDED);

    // Bob claims
    const responses = coord.processMessage(bob.claimIntent(sid, "claim-1", "i-a", "agent:alice", "i-b", "Continue", scope as any));
    const statusMessages = responses.filter((message) => message.message_type === MessageType.INTENT_CLAIM_STATUS);
    expect(statusMessages.length).toBe(1);
    expect((statusMessages[0].payload as any).decision).toBe("approved");
    expect(coord.getIntent("i-a")!.stateMachine.currentState).toBe(IntentState.TRANSFERRED);
    expect(coord.getIntent("i-b")!.stateMachine.currentState).toBe(IntentState.ACTIVE);
    expect(coord.getIntent("i-b")!.principal_id).toBe("agent:bob");
  });

  it("rejects claim on non-suspended intent", () => {
    const { sid, coord, alice, bob } = makeSession();
    const scope = { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] };
    coord.processMessage(alice.announceIntent(sid, "i-a", "Fix", scope as any));
    const res = coord.processMessage(bob.claimIntent(sid, "c-1", "i-a", "agent:alice", "i-b", "Steal", scope as any));
    expect(res.length).toBe(1);
    expect(res[0].message_type).toBe(MessageType.PROTOCOL_ERROR);
    expect((res[0].payload as any).error_code).toBe("INVALID_REFERENCE");
  });

  it("rejects duplicate claim", () => {
    const { sid, coord, alice, bob } = makeSession();
    const charlie = new Participant("agent:charlie", "agent", "Charlie", [Role.CONTRIBUTOR]);
    coord.processMessage(charlie.hello(sid));

    const scope = { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] };
    coord.processMessage(alice.announceIntent(sid, "i-a", "Fix", scope as any));
    coord.getParticipant("agent:alice")!.last_seen = Date.now() - 11_000;
    coord.checkLiveness();

    coord.processMessage(bob.claimIntent(sid, "c-1", "i-a", "agent:alice", "i-b", "Continue", scope as any));
    const res = coord.processMessage(charlie.claimIntent(sid, "c-2", "i-a", "agent:alice", "i-c", "Also", scope as any));
    expect(res.length).toBe(1);
    expect((res[0].payload as any).error_code).toBe("CLAIM_CONFLICT");
  });

  it("reconnection before claim restores intent", () => {
    const { sid, coord, alice } = makeSession();
    const scope = { kind: ScopeKind.FILE_SET, resources: ["src/auth.py"] };
    coord.processMessage(alice.announceIntent(sid, "i-a", "Fix", scope as any));
    coord.getParticipant("agent:alice")!.last_seen = Date.now() - 11_000;
    coord.checkLiveness();
    expect(coord.getIntent("i-a")!.stateMachine.currentState).toBe(IntentState.SUSPENDED);
    coord.processMessage(alice.hello(sid));
    expect(coord.getIntent("i-a")!.stateMachine.currentState).toBe(IntentState.ACTIVE);
  });
});
