import { describe, it, expect } from "vitest";
import { SessionCoordinator } from "../src/coordinator.js";
import { Participant } from "../src/participant.js";
import {
  SecurityProfile, ComplianceProfile, Role, ScopeKind,
  IntentState, OperationState, MessageType,
} from "../src/models.js";

function makeSession(unavailabilityTimeoutSec = 10) {
  const sid = "test-liveness";
  const coord = new SessionCoordinator(
    sid, SecurityProfile.OPEN, ComplianceProfile.CORE, 0, unavailabilityTimeoutSec
  );
  const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
  const bob = new Participant("agent:bob", "agent", "Bob", [Role.CONTRIBUTOR]);
  coord.processMessage(alice.hello(sid));
  coord.processMessage(bob.hello(sid));
  return { sid, coord, alice, bob };
}

describe("Liveness Detection (Section 14)", () => {
  it("heartbeat updates status", () => {
    const { sid, coord, alice } = makeSession();
    coord.processMessage(alice.heartbeat(sid, "working"));
    const info = coord.getParticipant("agent:alice")!;
    expect(info.status).toBe("working");
    expect(info.is_available).toBe(true);
  });

  it("detects unavailable participant after timeout", () => {
    const { sid, coord, alice } = makeSession(10);
    const info = coord.getParticipant("agent:alice")!;
    info.last_seen = Date.now() - 11_000;
    const responses = coord.checkLiveness();
    expect(info.is_available).toBe(false);
    const errors = responses.filter(r => r.message_type === MessageType.PROTOCOL_ERROR);
    expect(errors.length).toBe(1);
    expect((errors[0].payload as any).error_code).toBe("PARTICIPANT_UNAVAILABLE");
  });

  it("suspends intents on unavailability", () => {
    const { sid, coord, alice } = makeSession(10);
    coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));
    expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.ACTIVE);
    coord.getParticipant("agent:alice")!.last_seen = Date.now() - 11_000;
    coord.checkLiveness();
    expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.SUSPENDED);
  });

  it("abandons proposals on unavailability", () => {
    const { sid, coord, alice } = makeSession(10);
    coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));
    coord.processMessage(alice.proposeOp(sid, "op-1", "i-1", "src/a.py", "patch"));
    expect(coord.getOperation("op-1")!.stateMachine.currentState).toBe(OperationState.PROPOSED);
    coord.getParticipant("agent:alice")!.last_seen = Date.now() - 11_000;
    coord.checkLiveness();
    expect(coord.getOperation("op-1")!.stateMachine.currentState).toBe(OperationState.ABANDONED);
  });

  it("reconnection restores suspended intents", () => {
    const { sid, coord, alice } = makeSession(10);
    coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));
    coord.getParticipant("agent:alice")!.last_seen = Date.now() - 11_000;
    coord.checkLiveness();
    expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.SUSPENDED);
    coord.processMessage(alice.heartbeat(sid, "idle"));
    expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.ACTIVE);
  });

  it("goodbye withdraws intents", () => {
    const { sid, coord, alice } = makeSession();
    coord.processMessage(alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] }));
    coord.processMessage(alice.goodbye(sid));
    expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.WITHDRAWN);
    expect(coord.getParticipant("agent:alice")!.is_available).toBe(false);
  });

  it("goodbye with expire keeps intents active", () => {
    const { sid, coord, alice } = makeSession();
    const env = alice.announceIntent(sid, "i-1", "Fix", { kind: ScopeKind.FILE_SET, resources: ["src/a.py"] });
    (env.payload as any).ttl_sec = 120;
    coord.processMessage(env);
    coord.processMessage(alice.goodbye(sid, "user_exit", undefined, "expire"));
    expect(coord.getIntent("i-1")!.stateMachine.currentState).toBe(IntentState.ACTIVE);
  });
});
