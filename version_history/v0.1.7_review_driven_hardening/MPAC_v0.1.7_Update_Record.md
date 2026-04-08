# MPAC v0.1.7 Update Record

**Date**: 2026-04-03
**Trigger**: Independent deep technical review (simulating SOSP/OSDI-level scrutiny) identified foundational gaps in execution semantics, consistency guarantees, atomicity, and coordinator trust. After cross-referencing with version history (v0.1–v0.1.6), the review was calibrated: 2 findings were genuinely new, 3 were known-and-deferred items promoted to this version at the user's request.

---

## Changes Summary

### New Sections

| Section | Title | What it adds |
|---------|-------|-------------|
| 7.7 | Consistency Model | Explicit declaration: coordinator-serialized total order during normal operation, no mutations during degraded mode, governance-level reconciliation on recovery. States MPAC does NOT provide linearizability. |
| 7.8 | Execution Model | Disambiguates OP_COMMIT: `pre_commit` (request to commit, coordinator confirms before mutation) vs `post_commit` (notification of completed mutation). Sessions MUST declare in SESSION_INFO. |
| 12.7 | Lamport Clock Maintenance Rules | Six normative rules: initialization, send rule (increment before send), receive rule (max + 1), coordinator authority, snapshot persistence, monotonicity enforcement. |
| 15.6.1 | Intent State Transition Table | Normative table: 9 transitions, guard conditions, actions, triggered-by. Replaces informal ASCII diagram as the authoritative reference. |
| 16.6.1 | Operation State Transition Table | Normative table: 12 transitions including OP_BATCH_COMMIT entry, pre/post-commit model variants. |
| 16.8 | `OP_BATCH_COMMIT` | New message type for atomic multi-target operations. `all_or_nothing` and `best_effort` atomicity modes. Scope = union of targets. |
| 17.8.1 | Conflict State Transition Table | Normative table: 11 transitions including frozen scope Phase 3 fallback path. |
| 18.6.2.1 | Frozen Scope Progressive Degradation | Replaces binary "wait 30 min then reject all" with three-phase degradation: Phase 1 (normal resolution, 0–60s), Phase 2 (auto-escalate + priority bypass, 60–300s), Phase 3 (first-committer-wins, 300s+). |
| 23.1.3.1 | Coordinator Accountability | Verified profile: coordinator MUST sign all messages, participants MUST verify, coordinator actions in tamper-evident log, independent audit capability. |

### Modified Sections

| Section | Change |
|---------|--------|
| 1 | Version bumped to 0.1.7 |
| 13 | Added `OP_BATCH_COMMIT` to core message types list (19 → 20 types) |
| 13.1 | Added `OP_BATCH_COMMIT` payload schema table; added `execution_model` field to `SESSION_INFO` payload |
| 14.2 | SESSION_INFO example updated with `execution_model: "pre_commit"` |
| 19.1 | Added `op.batch_commit` capability |
| 20.1 | Core Profile now requires `OP_BATCH_COMMIT`, Lamport clock rules, consistency model semantics |
| 20.2 | Governance Profile adds progressive degradation reference, pre-commit model recommendation |
| 26 | Interoperability guidance items 17–20 added (execution model, Lamport rules, batch commit, coordinator accountability) |
| 29 | Removed "atomic multi-target operations" from future work (now addressed). Added compact envelope, scope-based subscription, session sharding. |
| 30 | Summary rewritten for v0.1.7 features |

---

## Mapping from Review Findings to Changes

| Review Finding | Severity | Disposition | Resolution |
|---|---|---|---|
| OP_COMMIT semantic ambiguity (pre-commit vs post-commit) | Critical (new finding) | **Fixed in v0.1.7** | Section 7.8: execution model declaration |
| Consistency model undeclared | High (new finding) | **Fixed in v0.1.7** | Section 7.7: explicit consistency guarantees |
| No atomic multi-target operations (OP_BATCH) | High (known, was deferred to v0.2) | **Promoted to v0.1.7** | Section 16.8: OP_BATCH_COMMIT |
| Coordinator trust over-concentration | Medium-High (partially addressed in v0.1.5) | **Promoted to v0.1.7** | Section 23.1.3.1: coordinator accountability |
| Frozen scope "wait then reject all" | Medium (known, was accepted tradeoff) | **Promoted to v0.1.7** | Section 18.6.2.1: progressive degradation |
| Lamport clock rules not specified | Medium (new finding) | **Fixed in v0.1.7** | Section 12.7: six normative rules |
| State machines not formalized | Medium (new finding) | **Fixed in v0.1.7** | Sections 15.6.1, 16.6.1, 17.8.1 |

---

## Impact on Reference Implementations

### Python (ref-impl/python/)
- New message handler needed: `OP_BATCH_COMMIT`
- Coordinator must implement pre-commit confirmation flow
- Lamport clock send/receive rules must be verified against Section 12.7
- Frozen scope handler must implement 3-phase degradation
- New state transition: OP_BATCH_COMMIT → per-entry COMMITTED/PROPOSED
- Coordinator accountability: sign all outgoing messages in Verified profile

### TypeScript (ref-impl/typescript/)
- Same changes as Python implementation
- SESSION_INFO must include `execution_model` field
- State machine implementations should be verified against normative transition tables

### JSON Schema (ref-impl/schema/)
- New schema needed: `op_batch_commit.schema.json`
- Updated: `session_info.schema.json` (add `execution_model` field)
- Updated: `envelope.schema.json` (add `OP_BATCH_COMMIT` to message type enum)
