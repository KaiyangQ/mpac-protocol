# MPAC v0.1.8 Gap Analysis

**Date**: 2026-04-04
**Scope**: Current shortcomings identified after the v0.1.8 coordination-semantics hardening pass
**Context**: v0.1.8 resolved three coordination-semantics gaps, but several protocol-level inconsistencies and conformance-surface gaps remain. This document records them using **Priority** (`P0`-`P3`) rather than severity language.

---

## Priority Rubric

This document uses **Priority** as a remediation-order scale, not as a synonym for severity:

- **P0**: Must be addressed before treating the current version as fully coherent for its core correctness, safety, or interoperability claims.
- **P1**: Important gap or inconsistency that should be addressed in the next revision, but does not by itself invalidate the entire protocol model.
- **P2**: Conformance, artifact, or hardening gap that weakens implementability or verification, but is not a core-model blocker.
- **P3**: Nice-to-have clarification, optimization, or future-work item.

This separation is intentional: a finding may be medium severity but still be `P0` if it blocks a core release objective, and a high-severity concern may be lower priority if it is explicitly outside the current revision scope.

---

## Summary

| Priority | Count | Themes |
|----------|-------|--------|
| P0 | 2 | Coordinator failover correctness, Lamport rejoin correctness |
| P1 | 3 | Intent-claim closure, lifecycle consistency, replay-protection closure |
| P2 | 2 | JSON Schema lag, implementation/test coverage lag |
| P3 | 0 | None currently recorded |

---

## P0-1: Coordinator Handover Still Lacks Fencing Semantics

**Affected Sections**: 7.7, 8.1.1.4, 12.7, 14.6

### Problem

v0.1.8 claims a coordinator-serialized total order and a single-coordinator invariant, but coordinator failover still relies on comparing Lamport clock values during split-brain handling.

This is not a sufficient fencing mechanism:

1. A stale coordinator can continue emitting messages after failover.
2. A stale coordinator may still carry a higher Lamport value than the replacement coordinator.
3. Participants have no protocol-level epoch / term / lease / fencing token with which to reject an old leader deterministically.

As a result, the protocol currently mixes two claims that are not yet fully compatible:

- "exactly one logical coordinator"
- "participants can safely recover via handover / failover using the current wire semantics alone"

### Why This Is P0

This gap directly affects MPAC's central correctness claim: that authoritative mutation order is coordinator-serialized. If coordinator ownership cannot be fenced at the protocol level, then the total-order guarantee can be violated exactly in the recovery path where the protocol says it remains safe.

### Recommendation

- Add a monotonic `coordinator_epoch` / `term` field to `COORDINATOR_STATUS`, `SESSION_INFO`, and the coordinator snapshot.
- Require all participants to reject messages from coordinators with stale epochs, regardless of Lamport value.
- State explicitly that Lamport clocks order events **within** an accepted coordinator epoch; they are not a replacement for leader fencing.
- If protocol-level fencing is intentionally out of scope, then the handover section should explicitly delegate failover safety to external consensus infrastructure and narrow MPAC's claim accordingly.

---

## P0-2: Lamport Rules Are Not Closed Under Participant Rejoin

**Affected Sections**: 8.1.1.4, 12.7, 14.1, 14.2

### Problem

The current Lamport rules require a participant to initialize its local counter to `0` when joining a session, while also requiring Lamport values from the same sender to be strictly monotonically increasing.

This becomes inconsistent in a normal recovery path:

1. A participant joins with `HELLO`.
2. The coordinator fails over or hands over.
3. The participant is required to re-send `HELLO` to re-establish presence.
4. The participant may now emit Lamport values that are lower than its own earlier messages, even though the `sender.principal_id` is unchanged.

Without an incarnation concept, implementations are forced into incompatible behaviors:

- treat the participant as a logically new sender
- reject the rejoined sender as replay / non-monotonic
- silently waive the monotonicity rule during recovery

### Why This Is P0

This is not an edge case; it is on the protocol's normal coordinator-recovery path. A causal-order rule that breaks during standard rejoin behavior is a core correctness issue, not just a hardening issue.

### Recommendation

- Introduce a session-local sender incarnation identifier, or
- require participants to restore their prior Lamport counter on rejoin, or
- scope strict monotonicity to `(principal_id, incarnation_id)` rather than `principal_id` alone.

The spec should define one of these paths explicitly rather than leaving it to implementation policy.

---

## P1-1: `INTENT_CLAIM` Lifecycle Is Only Partially Protocolized

**Affected Sections**: 14.7.4, 15.6.1, 9.6.1
**Affected Artifacts**: `ref-impl/python/mpac/models.py`, `ref-impl/typescript/src/models.ts`, `ref-impl/python/mpac/coordinator.py`

### Problem

v0.1.8 defines an approval-based `INTENT_CLAIM` flow and introduces the `TRANSFERRED` intent state, but the lifecycle is still not fully closed:

1. The spec describes approval / no-objection semantics for claims, but there is no explicit wire-level approval or rejection message dedicated to claim disposition.
2. `TRANSFERRED` is part of the normative intent lifecycle, yet the reference-model enums do not include it.
3. The reference coordinator currently terminates the original intent as `WITHDRAWN`, creating divergence between spec semantics and executable semantics.

This means two implementations can both claim to support `INTENT_CLAIM` while disagreeing on:

- whether approval is explicit or implicit
- whether the original intent ends as `TRANSFERRED` or `WITHDRAWN`
- whether auto-close logic should treat claimed intents distinctly from withdrawn intents

### Why This Is P1

This gap affects an important recovery path and is already producing spec/implementation drift, but it does not undermine the entire protocol in the same way as stale-coordinator acceptance or broken causal rules.

### Recommendation

- Fully protocolize claim disposition:
  - either add an explicit claim approval / rejection message, or
  - define claim approval as a coordinator-generated authoritative state transition with exact wire-visible consequences.
- Align the normative state machine, auto-close conditions, and reference enums on `TRANSFERRED`.
- Add conformance tests for claim approval, rejection, reconnect-before-approval, and post-claim lifecycle accounting.

---

## P1-2: Operation Lifecycle Terminology Is Internally Inconsistent

**Affected Sections**: 9.6.1, 16.6.1

### Problem

The current spec uses incompatible terminology for operation end states:

1. Session auto-close conditions treat `COMMITTED`, `REJECTED`, and `ABANDONED` as terminal.
2. The normative operation lifecycle table states that terminal states are `REJECTED`, `ABANDONED`, and `SUPERSEDED`, while `COMMITTED` is a stable state that can later transition to `SUPERSEDED`.

This creates observable ambiguity:

- one implementation may auto-close with committed operations still eligible for later supersession
- another may wait until all supersession opportunities are exhausted
- summary / archival tooling may count final states differently

### Why This Is P1

This is a real normative contradiction and will create cross-implementation divergence, but it is localized and can be repaired with a narrow clarification.

### Recommendation

- Define the canonical operation state taxonomy once:
  - terminal states
  - stable non-terminal states
  - allowed outgoing transitions
- Reuse that taxonomy in session-close logic, summaries, and interoperability guidance.
- Make the lifecycle table the single source of truth and rewrite Section 9.6.1 to reference it directly.

---

## P1-3: Replay Protection Requirements Are Not Closed Over Recovery

**Affected Sections**: 8.1.1.2, 8.1.1.3, 23.1.2 / 23.1.3
**Affected Artifacts**: snapshot format, recovery semantics

### Problem

The security profiles require replay protection, including rejection of duplicate `message_id` values and timestamps outside an acceptable window. However, the normative coordinator snapshot format does not include anti-replay state such as:

- recently-seen message IDs
- replay-window checkpoints
- sender-specific acceptance windows

After recovery, an implementation can restore the session state but still lack the protocol-defined information needed to continue enforcing replay protection consistently.

This also creates an internal scope mismatch:

- the security profile states replay protection as a MUST
- the v0.1.8 update record scopes replay protection after recovery out as "infrastructure-layer"

### Why This Is P1

The protocol can still function, but its current responsibility boundary is not internally clean. Implementers cannot tell whether replay continuity across recovery is mandatory protocol behavior or deployment-specific hardening.

### Recommendation

- Either include minimum anti-replay checkpoint state in the normative snapshot, or
- explicitly redefine replay protection as a deployment contract rather than a protocol-compliance requirement across recovery boundaries.

The spec should not simultaneously require and scope out the same guarantee.

---

## P2-1: JSON Schema and Wire-Level Conformance Artifacts Lag the Normative Spec

**Affected Artifacts**:
- `ref-impl/schema/envelope.schema.json`
- `ref-impl/schema/messages/session_info.schema.json`
- `ref-impl/schema/messages/protocol_error.schema.json`
- missing `OP_BATCH_COMMIT` payload schema

### Problem

The machine-readable conformance surface has fallen behind the current spec:

1. `OP_BATCH_COMMIT` is part of the v0.1.8 message set, but is not present in the reference schema set.
2. `SESSION_INFO` requires `execution_model` in the spec, but the payload schema does not require or model it.
3. `PROTOCOL_ERROR` schema does not include several error codes added by later revisions.
4. The envelope schema does not bind `message_type` to the appropriate payload schema, so structurally invalid combinations can still validate as long as `payload` is an object.

### Why This Is P2

This gap weakens machine-enforceable interoperability and makes conformance tooling less trustworthy, but it does not by itself redefine protocol semantics.

### Recommendation

- Add / update schemas for all v0.1.8 message types and error codes.
- Use `oneOf` / conditional schema logic to bind `message_type` to the corresponding payload schema.
- Add a schema-validation test suite so update records and repository artifacts cannot drift silently.

---

## P2-2: Reference Implementation and Test Coverage Still Lag Several Normative Commitments

**Affected Artifacts**:
- `README.md`
- `ref-impl/python/tests/`
- `ref-impl/typescript/tests/`
- reference coordinators and participants

### Problem

Several important behaviors remain unimplemented or unverified in the repository, even though the spec now treats them as normative or near-normative:

1. `OP_BATCH_COMMIT` remains uncovered in both implementation and tests.
2. No focused split-brain / fencing tests exist for coordinator handover.
3. No replay-protection continuity tests exist across snapshot recovery.
4. No tests verify sender-side Lamport monotonicity across rejoin / handover.
5. The repository currently allows spec / schema / implementation drift to survive version bumps.

### Why This Is P2

These are conformance-surface gaps rather than new protocol-design failures, but they materially increase the chance of hidden divergence between the written spec and executable behavior.

### Recommendation

- Add targeted tests for:
  - coordinator epoch / fencing behavior
  - participant rejoin monotonicity
  - replay protection across recovery
  - `OP_BATCH_COMMIT`
  - `INTENT_CLAIM` end-state alignment
- Update coverage statements in `README.md` to distinguish:
  - normative spec status
  - reference implementation status
  - schema / conformance status

---

## Priority Assessment

| Finding | Priority | Reason for Priority |
|---------|----------|--------------------|
| Coordinator handover lacks fencing semantics | P0 | Undermines single-coordinator invariant and authoritative total order |
| Lamport rules are not closed under participant rejoin | P0 | Breaks causal rules on a normal recovery path |
| `INTENT_CLAIM` lifecycle only partially protocolized | P1 | Important recovery path remains underspecified and drift-prone |
| Operation lifecycle terminology inconsistent | P1 | Normative contradiction affects auto-close and archival behavior |
| Replay protection not closed over recovery | P1 | Security-profile requirement boundary remains internally inconsistent |
| JSON Schema lag | P2 | Weakens machine-enforceable interoperability |
| Implementation / test coverage lag | P2 | Increases risk of silent spec / artifact divergence |

---

## Suggested Next Revision Boundary

If the goal of the next revision is **core coherence** rather than feature expansion, the highest-leverage scope would be:

1. Close the two `P0` items first.
2. Then resolve the three `P1` inconsistencies in the lifecycle and security boundary.
3. Treat the `P2` items as the conformance pass that makes the repaired spec mechanically verifiable.

That ordering preserves the historical use of priority in MPAC version history: core-release blockers first, important but non-blocking gaps second, and conformance / hardening follow-through third.
