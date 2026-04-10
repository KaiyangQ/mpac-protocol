import { describe, it, expect } from "vitest";
import { v4 as uuidv4 } from "uuid";
import {
  SessionCoordinator,
  Participant,
  MessageType,
  IntentState,
  ConflictState,
  ConflictCategory,
  Severity,
  ScopeKind,
  Role,
} from "../src/index.js";

describe("Conflict Detection Test", () => {
  it("should detect and report scope overlaps", () => {
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

    // Step 1: Both participants join
    const helloA = participantA.hello(sessionId);
    const helloB = participantB.hello(sessionId);

    coordinator.processMessage(helloA);
    coordinator.processMessage(helloB);

    expect(coordinator.getParticipants().length).toBe(2);

    // Step 2: Participant A announces intent (resources: ["src/main.ts", "src/config.ts"])
    const intentAId = uuidv4();
    const intentAMsg = participantA.announceIntent(
      sessionId,
      intentAId,
      "Modify main and config",
      {
        kind: ScopeKind.FILE_SET,
        resources: ["src/main.ts", "src/config.ts"],
      }
    );

    const responsesA = coordinator.processMessage(intentAMsg);
    expect(responsesA.length).toBe(0); // First intent, no conflicts

    const intentA = coordinator.getIntent(intentAId);
    expect(intentA).toBeDefined();

    // Step 3: Participant B announces intent (resources: ["src/config.ts", "src/db.ts"]) - OVERLAP on config.ts!
    const intentBId = uuidv4();
    const intentBMsg = participantB.announceIntent(
      sessionId,
      intentBId,
      "Modify config and database",
      {
        kind: ScopeKind.FILE_SET,
        resources: ["src/config.ts", "src/db.ts"],
      }
    );

    // This should trigger auto-generation of CONFLICT_REPORT
    const responsesB = coordinator.processMessage(intentBMsg);
    expect(responsesB.length).toBe(1); // One conflict report auto-generated

    const conflictReport = responsesB[0];
    expect(conflictReport.message_type).toBe(MessageType.CONFLICT_REPORT);

    const conflictPayload = conflictReport.payload as any;
    expect(conflictPayload.category).toBe(ConflictCategory.SCOPE_OVERLAP);
    expect(conflictPayload.severity).toBe(Severity.MEDIUM);
    expect(conflictPayload.involved_principals).toContain("participant-a");
    expect(conflictPayload.involved_principals).toContain("participant-b");

    // Verify conflict registered on coordinator
    const conflicts = coordinator.getConflicts();
    expect(conflicts.length).toBe(1);

    const conflict = conflicts[0];
    expect(conflict.category).toBe(ConflictCategory.SCOPE_OVERLAP);
    expect(conflict.stateMachine.currentState).toBe(ConflictState.OPEN);

    // Step 4: Resolve conflict
    const conflictId = conflictPayload.conflict_id;
    const resolutionMsg = participantA.reportConflict(
      sessionId,
      conflictId,
      ConflictCategory.SCOPE_OVERLAP,
      Severity.MEDIUM,
      ["participant-a", "participant-b"],
      {
        kind: ScopeKind.FILE_SET,
        resources: ["src/main.ts", "src/config.ts"],
      },
      {
        kind: ScopeKind.FILE_SET,
        resources: ["src/config.ts", "src/db.ts"],
      },
      "Resolved by participant agreement"
    );

    // Process as resolution
    coordinator.processMessage(conflictReport);

    const retrievedConflict = coordinator.getConflict(conflictId);
    expect(retrievedConflict).toBeDefined();
    expect(retrievedConflict?.stateMachine.currentState).toBe(ConflictState.OPEN);

    // Manually transition to resolved
    if (retrievedConflict) {
      retrievedConflict.stateMachine.transition("ack");
      retrievedConflict.stateMachine.transition("resolve");
      retrievedConflict.stateMachine.transition("close");
      expect(retrievedConflict.stateMachine.currentState).toBe(ConflictState.CLOSED);
    }
  });

  it("should handle path normalization in scope overlap detection", () => {
    const sessionId = uuidv4();
    const coordinator = new SessionCoordinator(sessionId);

    const participantA = new Participant(
      "participant-a",
      "agent",
      "Agent A"
    );
    const participantB = new Participant(
      "participant-b",
      "agent",
      "Agent B"
    );

    // Join session
    coordinator.processMessage(participantA.hello(sessionId));
    coordinator.processMessage(participantB.hello(sessionId));

    // Intent A: files with ./ prefix
    const intentAId = uuidv4();
    const intentAMsg = participantA.announceIntent(
      sessionId,
      intentAId,
      "Modify",
      {
        kind: ScopeKind.FILE_SET,
        resources: ["./src/main.ts", "src/config.ts"],
      }
    );

    coordinator.processMessage(intentAMsg);

    // Intent B: same files, different path format, should detect overlap
    const intentBId = uuidv4();
    const intentBMsg = participantB.announceIntent(
      sessionId,
      intentBId,
      "Modify",
      {
        kind: ScopeKind.FILE_SET,
        resources: ["src/main.ts"],
      }
    );

    // Should generate conflict report due to overlap (after normalization)
    const responses = coordinator.processMessage(intentBMsg);
    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).category).toBe(
      ConflictCategory.SCOPE_OVERLAP
    );
  });
});
