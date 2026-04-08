/**
 * Adversarial / negative-path tests for v0.1.12 runtime enforcement gaps.
 *
 * Covers 6 enforcement rules:
 * 1. HELLO-first gate
 * 2. Credential validation
 * 3. Resolution authority
 * 4. Frozen-scope enforcement
 * 5. Batch atomicity rollback
 * 6. Error codes: CAUSAL_GAP and INTENT_BACKOFF
 */
import { describe, it, expect } from "vitest";
import { SessionCoordinator } from "../src/coordinator.js";
import { Participant } from "../src/participant.js";
import {
  SecurityProfile,
  ComplianceProfile,
  Role,
  ScopeKind,
  MessageType,
  IntentState,
  ConflictState,
  OperationState,
  ErrorCode,
  CoordinatorEvent,
} from "../src/models.js";

// ============================================================================
//  1. HELLO-first gate
// ============================================================================

describe("HELLO-first gate", () => {
  it("rejects INTENT_ANNOUNCE from unregistered sender", () => {
    const coord = new SessionCoordinator("test-hello-gate");
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);

    const msg = alice.announceIntent("test-hello-gate", "intent-1", "Fix", {
      kind: ScopeKind.FILE_SET,
      resources: ["src/main.py"],
    });
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect(responses[0].message_type).toBe(MessageType.PROTOCOL_ERROR);
    expect((responses[0].payload as any).error_code).toBe("INVALID_REFERENCE");
  });

  it("rejects HEARTBEAT from unregistered sender", () => {
    const coord = new SessionCoordinator("test-hello-gate-hb");
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);

    const msg = alice.heartbeat("test-hello-gate-hb", "idle");
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("INVALID_REFERENCE");
  });

  it("rejects GOODBYE from unregistered sender", () => {
    const coord = new SessionCoordinator("test-hello-gate-bye");
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);

    const msg = alice.goodbye("test-hello-gate-bye", "user_exit");
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("INVALID_REFERENCE");
  });

  it("GOODBYE cannot affect other principal's intents", () => {
    const sid = "test-goodbye-ownership";
    const coord = new SessionCoordinator(sid);
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    const bob = new Participant("agent:bob", "agent", "Bob", [Role.CONTRIBUTOR]);

    coord.processMessage(alice.hello(sid));
    coord.processMessage(bob.hello(sid));

    coord.processMessage(
      alice.announceIntent(sid, "intent-alice", "Fix", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/main.py"],
      })
    );
    expect(coord.getIntent("intent-alice")!.stateMachine.currentState).toBe(
      IntentState.ACTIVE
    );

    // Bob sends GOODBYE with alice's intent in active_intents
    const msg = bob.goodbye(sid, "user_exit");
    (msg.payload as any).active_intents = ["intent-alice"];
    coord.processMessage(msg);

    // Alice's intent should NOT be affected
    expect(coord.getIntent("intent-alice")!.stateMachine.currentState).toBe(
      IntentState.ACTIVE
    );
  });

  it("allows HELLO from unregistered sender", () => {
    const coord = new SessionCoordinator("test-hello-gate-ok");
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);

    const responses = coord.processMessage(alice.hello("test-hello-gate-ok"));

    expect(responses.length).toBe(1);
    expect(responses[0].message_type).toBe(MessageType.SESSION_INFO);
  });

  it("allows registered sender to announce intent", () => {
    const coord = new SessionCoordinator("test-hello-gate-post");
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);

    coord.processMessage(alice.hello("test-hello-gate-post"));
    const msg = alice.announceIntent("test-hello-gate-post", "intent-1", "Fix", {
      kind: ScopeKind.FILE_SET,
      resources: ["src/main.py"],
    });
    const responses = coord.processMessage(msg);

    const authErrors = responses.filter(
      (r) =>
        r.message_type === MessageType.PROTOCOL_ERROR &&
        (r.payload as any).error_code === "AUTHORIZATION_FAILED"
    );
    expect(authErrors.length).toBe(0);
  });
});

// ============================================================================
//  2. Credential validation
// ============================================================================

describe("Credential validation", () => {
  it("rejects HELLO without credential in authenticated profile", () => {
    const coord = new SessionCoordinator(
      "test-cred-auth",
      SecurityProfile.AUTHENTICATED
    );
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);

    const responses = coord.processMessage(alice.hello("test-cred-auth"));

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("CREDENTIAL_REJECTED");
  });

  it("rejects HELLO without credential in verified profile", () => {
    const coord = new SessionCoordinator(
      "test-cred-verified",
      SecurityProfile.VERIFIED
    );
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);

    const responses = coord.processMessage(alice.hello("test-cred-verified"));

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("CREDENTIAL_REJECTED");
  });

  it("accepts HELLO with valid credential in authenticated profile", () => {
    const coord = new SessionCoordinator(
      "test-cred-ok",
      SecurityProfile.AUTHENTICATED,
      ComplianceProfile.CORE,
      30, 90, 300, "post_commit", "sha256", 0,
      { default_role: "contributor" },
    );
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);

    const msg = alice.hello("test-cred-ok");
    (msg.payload as any).credential = {
      type: "bearer_token",
      value: "tok-abc123",
    };
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect(responses[0].message_type).toBe(MessageType.SESSION_INFO);
  });

  it("allows HELLO without credential in open profile", () => {
    const coord = new SessionCoordinator("test-cred-open", SecurityProfile.OPEN);
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);

    const responses = coord.processMessage(alice.hello("test-cred-open"));

    expect(responses.length).toBe(1);
    expect(responses[0].message_type).toBe(MessageType.SESSION_INFO);
  });
});

// ============================================================================
//  3. Resolution authority
// ============================================================================

describe("Resolution authority", () => {
  function makeConflict(sid = "test-res-auth") {
    const coord = new SessionCoordinator(sid);
    const alice = new Participant("agent:alice", "agent", "Alice", [
      Role.CONTRIBUTOR,
    ]);
    const bob = new Participant("agent:bob", "agent", "Bob", [
      Role.CONTRIBUTOR,
    ]);
    const owner = new Participant("human:owner", "human", "Owner", [
      Role.OWNER,
    ]);
    const arbiter = new Participant("human:arbiter", "human", "Arbiter", [
      Role.ARBITER,
    ]);

    coord.processMessage(alice.hello(sid));
    coord.processMessage(bob.hello(sid));
    coord.processMessage(owner.hello(sid));
    coord.processMessage(arbiter.hello(sid));

    coord.processMessage(
      alice.announceIntent(sid, "intent-a", "Fix", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/auth.py"],
      })
    );
    const responses = coord.processMessage(
      bob.announceIntent(sid, "intent-b", "Refactor", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/auth.py"],
      })
    );

    const conflictId = (responses[0].payload as any).conflict_id;
    return { coord, alice, bob, owner, arbiter, conflictId };
  }

  it("contributor cannot resolve pre-escalation conflict", () => {
    const { coord, alice, conflictId } = makeConflict();
    const responses = coord.processMessage(
      alice.resolveConflict("test-res-auth", conflictId, "dismissed")
    );

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe(
      "AUTHORIZATION_FAILED"
    );
  });

  it("owner can resolve pre-escalation conflict", () => {
    const { coord, owner, conflictId } = makeConflict();
    const responses = coord.processMessage(
      owner.resolveConflict("test-res-auth", conflictId, "dismissed")
    );

    expect(responses).toEqual([]);
    expect(
      coord.getConflict(conflictId)!.stateMachine.isTerminal()
    ).toBe(true);
  });

  it("arbiter can resolve pre-escalation conflict", () => {
    const { coord, arbiter, conflictId } = makeConflict();
    const responses = coord.processMessage(
      arbiter.resolveConflict("test-res-auth", conflictId, "dismissed")
    );

    expect(responses).toEqual([]);
    expect(
      coord.getConflict(conflictId)!.stateMachine.isTerminal()
    ).toBe(true);
  });

  it("post-escalation: only escalate_to target can resolve", () => {
    const { coord, alice, owner, arbiter, conflictId } = makeConflict();

    coord.processMessage(
      alice.escalateConflict(
        "test-res-auth",
        conflictId,
        "human:arbiter",
        "need help"
      )
    );

    // Owner cannot resolve post-escalation
    const ownerResponse = coord.processMessage(
      owner.resolveConflict("test-res-auth", conflictId, "dismissed")
    );
    expect(ownerResponse.length).toBe(1);
    expect((ownerResponse[0].payload as any).error_code).toBe(
      "AUTHORIZATION_FAILED"
    );

    // Arbiter can
    const arbiterResponse = coord.processMessage(
      arbiter.resolveConflict("test-res-auth", conflictId, "approved")
    );
    expect(arbiterResponse).toEqual([]);
    expect(
      coord.getConflict(conflictId)!.stateMachine.currentState
    ).toBe(ConflictState.CLOSED);
  });
});

// ============================================================================
//  4. Frozen-scope enforcement
// ============================================================================

describe("Frozen-scope enforcement", () => {
  /**
   * Create a session with a frozen scope (conflict that has timed out).
   * Per Section 18.6.2, scopes only enter frozen state after resolution_timeout_sec
   * expires, not immediately on conflict creation.
   */
  function makeFrozenSession(sid = "test-frozen") {
    // Short resolution timeout (1 second)
    const coord = new SessionCoordinator(
      sid,
      SecurityProfile.OPEN,
      ComplianceProfile.CORE,
      0, // intentExpiryGraceSec
      90, // unavailabilityTimeoutSec
      1, // resolutionTimeoutSec = 1 second
    );
    const alice = new Participant("agent:alice", "agent", "Alice", [
      Role.OWNER,
    ]);
    const bob = new Participant("agent:bob", "agent", "Bob", [
      Role.CONTRIBUTOR,
    ]);

    coord.processMessage(alice.hello(sid));
    coord.processMessage(bob.hello(sid));

    coord.processMessage(
      alice.announceIntent(sid, "intent-a", "Fix", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/auth.py"],
      })
    );
    const responses = coord.processMessage(
      bob.announceIntent(sid, "intent-b", "Refactor", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/auth.py"],
      })
    );

    const conflictId = (responses[0].payload as any).conflict_id;

    // Trigger resolution timeout — no arbiter, so scope enters frozen state
    const conflict = coord.getConflict(conflictId)!;
    conflict.created_at = Date.now() - 2000;
    coord.checkResolutionTimeouts();
    expect(conflict.scope_frozen).toBe(true);

    return { coord, alice, bob, conflictId };
  }

  it("conflict without timeout does NOT freeze scope", () => {
    const sid = "test-no-freeze";
    const coord = new SessionCoordinator(sid);
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.OWNER]);
    const bob = new Participant("agent:bob", "agent", "Bob", [Role.CONTRIBUTOR]);

    coord.processMessage(alice.hello(sid));
    coord.processMessage(bob.hello(sid));

    coord.processMessage(
      alice.announceIntent(sid, "intent-a", "Fix", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/auth.py"],
      })
    );
    coord.processMessage(
      bob.announceIntent(sid, "intent-b", "Refactor", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/auth.py"],
      })
    );

    // Operations should still be allowed (scope not frozen yet)
    const msg = alice.commitOp(sid, "op-1", "intent-a", "src/auth.py", "patch", "sha:a", "sha:b");
    const responses = coord.processMessage(msg);

    const frozenErrors = responses.filter(
      (r) =>
        r.message_type === MessageType.PROTOCOL_ERROR &&
        (r.payload as any).error_code === "SCOPE_FROZEN"
    );
    expect(frozenErrors.length).toBe(0);
  });

  it("blocks new intent fully contained in frozen scope", () => {
    const { coord } = makeFrozenSession();
    const charlie = new Participant("agent:charlie", "agent", "Charlie", [
      Role.CONTRIBUTOR,
    ]);
    coord.processMessage(charlie.hello("test-frozen"));

    const msg = charlie.announceIntent("test-frozen", "intent-c", "Also fix", {
      kind: ScopeKind.FILE_SET,
      resources: ["src/auth.py"],
    });
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("SCOPE_FROZEN");
  });

  it("accepts partially overlapping intent with warning", () => {
    const { coord } = makeFrozenSession();
    const charlie = new Participant("agent:charlie", "agent", "Charlie", [
      Role.CONTRIBUTOR,
    ]);
    coord.processMessage(charlie.hello("test-frozen"));

    // Partially overlaps: src/auth.py is frozen, src/utils.py is not
    const msg = charlie.announceIntent("test-frozen", "intent-c", "Mixed scope", {
      kind: ScopeKind.FILE_SET,
      resources: ["src/auth.py", "src/utils.py"],
    });
    const responses = coord.processMessage(msg);

    // Intent should be registered (accepted)
    expect(coord.getIntent("intent-c")).toBeDefined();

    // Should include a SCOPE_FROZEN warning
    const frozenWarnings = responses.filter(
      (r) =>
        r.message_type === MessageType.PROTOCOL_ERROR &&
        (r.payload as any).error_code === "SCOPE_FROZEN"
    );
    expect(frozenWarnings.length).toBe(1);
    expect((frozenWarnings[0].payload as any).description).toContain("Warning");
  });

  it("blocks propose on frozen scope", () => {
    const { coord, alice } = makeFrozenSession();

    const msg = alice.proposeOp(
      "test-frozen",
      "op-1",
      "intent-a",
      "src/auth.py",
      "patch"
    );
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("SCOPE_FROZEN");
  });

  it("blocks commit on frozen scope", () => {
    const { coord, alice } = makeFrozenSession();

    const msg = alice.commitOp(
      "test-frozen",
      "op-1",
      "intent-a",
      "src/auth.py",
      "patch",
      "sha:a",
      "sha:b"
    );
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("SCOPE_FROZEN");
  });

  it("allows operations on non-overlapping scope", () => {
    const { coord, alice } = makeFrozenSession();

    // Different file
    coord.processMessage(
      alice.announceIntent("test-frozen", "intent-c", "Fix utils", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/utils.py"],
      })
    );
    const msg = alice.commitOp(
      "test-frozen",
      "op-1",
      "intent-c",
      "src/utils.py",
      "patch",
      "sha:a",
      "sha:b"
    );
    const responses = coord.processMessage(msg);

    const frozenErrors = responses.filter(
      (r) =>
        r.message_type === MessageType.PROTOCOL_ERROR &&
        (r.payload as any).error_code === "SCOPE_FROZEN"
    );
    expect(frozenErrors.length).toBe(0);
  });

  it("blocks batch commit on frozen scope", () => {
    const { coord, alice } = makeFrozenSession();

    const msg = alice.batchCommitOp(
      "test-frozen",
      "batch-frozen",
      [
        {
          op_id: "op-batch-1",
          target: "src/auth.py",
          op_kind: "patch",
          state_ref_before: "sha:a",
          state_ref_after: "sha:b",
        },
      ],
      "all_or_nothing",
      "intent-a",
    );
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("SCOPE_FROZEN");
  });

  it("blocks batch commit with per-entry intent_id on frozen scope", () => {
    const { coord, alice } = makeFrozenSession();

    // Batch with no top-level intentId, only per-entry intent_id
    const msg = alice.batchCommitOp(
      "test-frozen",
      "batch-bypass",
      [
        {
          op_id: "op-bypass-1",
          intent_id: "intent-a", // per-entry intent_id
          target: "src/auth.py",
          op_kind: "patch",
          state_ref_before: "sha:a",
          state_ref_after: "sha:b",
        },
      ],
      "all_or_nothing",
      undefined, // no top-level intentId
    );
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("SCOPE_FROZEN");
  });

  it("blocks batch commit with no intent_id anywhere by target", () => {
    const { coord, alice } = makeFrozenSession();

    const msg = alice.batchCommitOp(
      "test-frozen",
      "batch-no-intent",
      [
        {
          op_id: "op-no-intent-1",
          target: "src/auth.py",
          op_kind: "patch",
          state_ref_before: "sha:a",
          state_ref_after: "sha:b",
        },
      ],
      "all_or_nothing",
      undefined, // no top-level intentId
    );
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("SCOPE_FROZEN");
  });

  it("blocks propose with no intent_id by target", () => {
    const { coord, alice } = makeFrozenSession();

    // Build a propose with no intent_id
    const msg = alice.proposeOp("test-frozen", "op-no-intent", "intent-a", "src/auth.py", "patch");
    delete (msg.payload as any).intent_id;
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("SCOPE_FROZEN");
  });

  it("blocks commit with no intent_id by target", () => {
    const { coord, alice } = makeFrozenSession();

    const msg = alice.commitOp("test-frozen", "op-no-intent", "intent-a", "src/auth.py", "patch", "sha:a", "sha:b");
    delete (msg.payload as any).intent_id;
    const responses = coord.processMessage(msg);

    expect(responses.length).toBe(1);
    expect((responses[0].payload as any).error_code).toBe("SCOPE_FROZEN");
  });

  it("preserves scope_frozen through snapshot/recovery", () => {
    const { coord, alice, conflictId } = makeFrozenSession();

    // Verify scope is frozen
    expect(coord.getConflict(conflictId)!.scope_frozen).toBe(true);

    // Take snapshot and recover
    const snapshot = coord.snapshot();
    const coord2 = new SessionCoordinator("test-frozen-recovered");
    coord2.recoverFromSnapshot(snapshot);

    // Verify scope_frozen is preserved after recovery
    expect(coord2.getConflict(conflictId)!.scope_frozen).toBe(true);

    // Operations on frozen scope should still be blocked after recovery
    const msg = alice.commitOp(
      "test-frozen-recovered",
      "op-recover",
      "intent-a",
      "src/auth.py",
      "patch",
      "sha:a",
      "sha:b",
    );
    const responses = coord2.processMessage(msg);
    const frozenErrors = responses.filter(
      (r) =>
        r.message_type === MessageType.PROTOCOL_ERROR &&
        (r.payload as any).error_code === "SCOPE_FROZEN"
    );
    expect(frozenErrors.length).toBe(1);
  });

  it("unfreezes scope after conflict resolution", () => {
    const { coord, alice, conflictId } = makeFrozenSession();

    // Resolve conflict (alice is owner)
    coord.processMessage(
      alice.resolveConflict("test-frozen", conflictId, "dismissed")
    );
    expect(coord.getConflict(conflictId)!.stateMachine.isTerminal()).toBe(true);

    // Propose should now work
    const msg = alice.proposeOp(
      "test-frozen",
      "op-1",
      "intent-a",
      "src/auth.py",
      "patch"
    );
    const responses = coord.processMessage(msg);

    const frozenErrors = responses.filter(
      (r) =>
        r.message_type === MessageType.PROTOCOL_ERROR &&
        (r.payload as any).error_code === "SCOPE_FROZEN"
    );
    expect(frozenErrors.length).toBe(0);
  });
});

// ============================================================================
//  5. Batch atomicity rollback
// ============================================================================

describe("Batch atomicity rollback", () => {
  it("all_or_nothing cleans up registered ops on failure", () => {
    const sid = "test-batch-rollback";
    const coord = new SessionCoordinator(sid);
    const alice = new Participant("agent:alice", "agent", "Alice", [
      Role.CONTRIBUTOR,
    ]);

    coord.processMessage(alice.hello(sid));
    coord.processMessage(
      alice.announceIntent(sid, "intent-a", "Fix", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/auth.py"],
      })
    );

    const responses = coord.processMessage(
      alice.batchCommitOp(
        sid,
        "batch-bad",
        [
          {
            op_id: "op-good",
            target: "src/auth.py",
            op_kind: "patch",
            state_ref_before: "sha:a",
            state_ref_after: "sha:b",
          },
          {
            op_id: "op-bad",
            intent_id: "intent-nonexistent", // mismatched intent
            target: "src/auth.py",
            op_kind: "patch",
            state_ref_before: "sha:c",
            state_ref_after: "sha:d",
          },
        ],
        "all_or_nothing",
        "intent-a",
      )
    );

    expect(responses.length).toBe(1);
    expect(responses[0].message_type).toBe(MessageType.OP_REJECT);

    // Good op should NOT remain registered
    expect(coord.getOperation("op-good")).toBeUndefined();
  });
});

// ============================================================================
//  6. Error codes
// ============================================================================

describe("Error codes: CAUSAL_GAP and INTENT_BACKOFF", () => {
  it("CAUSAL_GAP is a valid ErrorCode", () => {
    expect(ErrorCode.CAUSAL_GAP).toBe("CAUSAL_GAP");
  });

  it("INTENT_BACKOFF is a valid ErrorCode", () => {
    expect(ErrorCode.INTENT_BACKOFF).toBe("INTENT_BACKOFF");
  });

  it("authorization is a valid CoordinatorEvent", () => {
    expect(CoordinatorEvent.AUTHORIZATION).toBe("authorization");
  });

  it("all 17 spec error codes are present", () => {
    const expected = [
      "MALFORMED_MESSAGE",
      "UNKNOWN_MESSAGE_TYPE",
      "INVALID_REFERENCE",
      "VERSION_MISMATCH",
      "CAPABILITY_UNSUPPORTED",
      "AUTHORIZATION_FAILED",
      "PARTICIPANT_UNAVAILABLE",
      "RESOLUTION_TIMEOUT",
      "SCOPE_FROZEN",
      "CLAIM_CONFLICT",
      "RESOLUTION_CONFLICT",
      "COORDINATOR_CONFLICT",
      "STATE_DIVERGENCE",
      "SESSION_CLOSED",
      "CREDENTIAL_REJECTED",
      "CAUSAL_GAP",
      "INTENT_BACKOFF",
    ];
    const actual = Object.values(ErrorCode);
    for (const code of expected) {
      expect(actual).toContain(code);
    }
  });
});
