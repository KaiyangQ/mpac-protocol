import { describe, it, expect } from "vitest";
import { v4 as uuidv4 } from "uuid";
import {
  SessionCoordinator,
  Participant,
  MessageType,
  IntentState,
  OperationState,
  ScopeKind,
  Role,
} from "../src/index.js";

describe("Happy Path Test", () => {
  it("should handle complete workflow with two participants", () => {
    const sessionId = uuidv4();

    // Create coordinator
    const coordinator = new SessionCoordinator(sessionId);

    // Create two participants
    const participantA = new Participant(
      "participant-a",
      "agent",
      "Agent A",
      [Role.CONTRIBUTOR],
      ["read", "write"]
    );

    const participantB = new Participant(
      "participant-b",
      "agent",
      "Agent B",
      [Role.CONTRIBUTOR],
      ["read", "write"]
    );

    // Step 1: Both participants send HELLO
    const helloA = participantA.hello(sessionId);
    const helloB = participantB.hello(sessionId);

    expect(helloA.message_type).toBe(MessageType.HELLO);
    expect(helloB.message_type).toBe(MessageType.HELLO);

    // Coordinator processes HELLO messages
    const responseA = coordinator.processMessage(helloA);
    const responseB = coordinator.processMessage(helloB);

    expect(responseA.length).toBe(1);
    expect(responseB.length).toBe(1);

    const sessionInfoA = responseA[0];
    const sessionInfoB = responseB[0];

    expect(sessionInfoA.message_type).toBe(MessageType.SESSION_INFO);
    expect(sessionInfoB.message_type).toBe(MessageType.SESSION_INFO);

    // Process SESSION_INFO by participants
    participantA.processMessage(sessionInfoA);
    participantB.processMessage(sessionInfoB);

    // Verify participants registered
    expect(coordinator.getParticipants().length).toBe(2);
    expect(coordinator.getParticipant("participant-a")).toBeDefined();
    expect(coordinator.getParticipant("participant-b")).toBeDefined();

    // Step 2: Participant A announces intent (resources: ["src/main.ts"])
    const intentAId = uuidv4();
    const intentAMsg = participantA.announceIntent(
      sessionId,
      intentAId,
      "Modify main.ts",
      {
        kind: ScopeKind.FILE_SET,
        resources: ["src/main.ts"],
      }
    );

    expect(intentAMsg.message_type).toBe(MessageType.INTENT_ANNOUNCE);

    const responsesA = coordinator.processMessage(intentAMsg);
    expect(responsesA.length).toBe(0); // No conflicts yet

    // Verify intent registered and auto-activated
    const intentA = coordinator.getIntent(intentAId);
    expect(intentA).toBeDefined();
    expect(intentA?.objective).toBe("Modify main.ts");
    expect(intentA?.stateMachine.currentState).toBe(IntentState.ACTIVE);

    // Step 3: Participant B announces intent (resources: ["src/utils.ts"]) - no overlap
    const intentBId = uuidv4();
    const intentBMsg = participantB.announceIntent(
      sessionId,
      intentBId,
      "Modify utils.ts",
      {
        kind: ScopeKind.FILE_SET,
        resources: ["src/utils.ts"],
      }
    );

    const responsesB = coordinator.processMessage(intentBMsg);
    expect(responsesB.length).toBe(0); // No conflicts (different files)

    // Verify intent registered
    const intentB = coordinator.getIntent(intentBId);
    expect(intentB).toBeDefined();
    expect(intentB?.objective).toBe("Modify utils.ts");

    // Step 4: Participant A proposes operation
    const opAId = uuidv4();
    const proposeMsg = participantA.proposeOp(
      sessionId,
      opAId,
      intentAId,
      "src/main.ts",
      "write"
    );

    expect(proposeMsg.message_type).toBe(MessageType.OP_PROPOSE);

    coordinator.processMessage(proposeMsg);

    // Verify operation registered in PROPOSED state
    const opA = coordinator.getOperation(opAId);
    expect(opA).toBeDefined();
    expect(opA?.stateMachine.currentState).toBe(OperationState.PROPOSED);

    // Step 5: Participant A commits operation
    const commitMsg = participantA.commitOp(
      sessionId,
      opAId,
      intentAId,
      "src/main.ts",
      "write",
      "state-v1",
      "state-v2"
    );

    expect(commitMsg.message_type).toBe(MessageType.OP_COMMIT);

    coordinator.processMessage(commitMsg);

    // Verify operation is now COMMITTED
    const opACommitted = coordinator.getOperation(opAId);
    expect(opACommitted?.stateMachine.currentState).toBe(OperationState.COMMITTED);

    // Verify watermarks are being incremented (Lamport clock)
    const clockA = participantA.getClockValue();
    const clockB = participantB.getClockValue();
    expect(clockA).toBeGreaterThan(0);
    expect(clockB).toBeGreaterThan(0);
  });
});
