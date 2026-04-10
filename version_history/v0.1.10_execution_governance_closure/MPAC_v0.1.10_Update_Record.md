# MPAC v0.1.10 Update Record

**Date**: 2026-04-04
**Update Name**: Execution and Governance Closure
**Previous Version**: v0.1.9 (Core Coherence Closure)
**Trigger**: Static protocol review of v0.1.9 identified residual closure gaps in pre-commit semantics, profile requirements, escalation authority, conflict auto-dismiss rules, and claim-approval auditability.
**Status**: Applied to root `SPEC.md` on 2026-04-04

---

## Overview

v0.1.10 is a **closure revision**, not a feature-expansion revision.

Its purpose is to make MPAC v0.1.x internally coherent at the protocol level after the v0.1.9 coherence pass. This revision does not add new message types, new transport responsibilities, or new coordination layers. Instead, it tightens the remaining normative gaps around:

- execution-model semantics
- profile compatibility requirements
- escalation-stage authority and arbiter finality
- conflict auto-dismiss cross-state-machine alignment
- governance approval attribution

The result is still a `v0.1.x` release rather than a `v0.2.0` feature branch, because the work narrows ambiguity rather than expanding scope.

---

## Revision Goals

1. Close the remaining ambiguity in `pre_commit` without adding new wire types.
2. Ensure the compliance-profile matrix is self-consistent.
3. Preserve deterministic conflict resolution without weakening arbiter authority after escalation.
4. Align conflict dismissal rules with the intent lifecycle defined elsewhere in the spec.
5. Make governance-mediated claim transfer audit-complete.

---

## Changes Summary

### Message Count

| Version | Message Types |
|---------|---------------|
| v0.1.9 | 21 |
| v0.1.10 | 21 (unchanged) |

### Normative Closure Areas

| Area | Revision |
|------|----------|
| Execution model | `pre_commit` now cleanly separates authorization from commit completion |
| Compliance profiles | Core sessions are limited to `post_commit`; `pre_commit` requires Governance Profile |
| Conflict resolution authority | First-resolution-wins now applies within the current authority phase |
| Conflict auto-dismiss | `TRANSFERRED` now counts as a terminal intent state |
| Claim approval auditability | Governance approvals must record `approved_by` |
| Decision registry | `deferred` removed from `RESOLUTION.decision` |

---

## Mapping from Gap Findings to Changes

| Gap Finding | Priority | Disposition in v0.1.10 | Resolution |
|-------------|----------|------------------------|------------|
| Core Profile and `pre_commit` were not closed as a valid profile combination | P1 | Fixed | Require `post_commit` for Core sessions; require Governance Profile for `pre_commit` |
| `pre_commit` conflated authorization with completed execution | P1 | Fixed | Make authorization explicit but non-committing; `COMMITTED` occurs only after the proposer declares execution completion |
| First-resolution-wins could override arbiter finality after escalation | P1 | Fixed | Scope resolver ordering to the conflict's current authority phase |
| `RESOLUTION.decision = deferred` had no state-machine meaning | P1 | Fixed | Remove `deferred` from the decision registry |
| Conflict auto-dismiss omitted `TRANSFERRED` | P1 | Fixed | Add `TRANSFERRED` to the terminal intent set used by auto-dismiss |
| Governance claim approvals could be unattributed | P2 | Fixed | Require `approved_by` on Governance Profile `INTENT_CLAIM_STATUS(approved)` |

---

## Detailed Changes

### 1. Execution-Model Closure [REVISED]

**Problem**: v0.1.9 still allowed a reading in which coordinator confirmation immediately made an operation `COMMITTED`, even though execution had not yet occurred.

**Change**:

- Rewrite Section 7.8 so that:
  - `pre_commit` means "authorization before execution"
  - authorization itself does **not** transition an operation to `COMMITTED`
  - `COMMITTED` is reached only when the proposer later declares the executed mutation via `OP_COMMIT`
- Preserve a backward-compatible path in which an initial `OP_COMMIT` may still be accepted as a request-to-commit in `pre_commit` sessions, but only as a `PROPOSED` operation
- Clarify that `OP_BATCH_COMMIT` follows the same two-step pattern in `pre_commit`

**Impact**:

- Eliminates the protocol-level ambiguity between "permission granted" and "mutation completed"
- Keeps v0.1.x backward-compatible without inventing a new message type

---

### 2. Profile Matrix Closure [REVISED]

**Problem**: v0.1.9 allowed sessions to advertise `pre_commit` even though the minimal Core Profile does not include the governance messages needed to run that flow safely.

**Change**:

- Add a normative rule that Core Profile sessions MUST use `post_commit`
- Add a normative rule that sessions declaring `pre_commit` MUST also declare Governance Profile compliance

**Impact**:

- Prevents protocol-valid but capability-incomplete session configurations
- Makes profile negotiation self-consistent

---

### 3. Escalation-Phase Authority Closure [REVISED]

**Problem**: v0.1.9's unconditional first-resolution-wins rule allowed an `owner` to race an escalated conflict and potentially defeat the arbiter's intended finality.

**Change**:

- Narrow the concurrent-resolution rule so that ordering applies only among resolvers authorized for the conflict's current authority phase
- Before escalation, ordinary `owner` / `arbiter` / coordinator rules apply
- After escalation, only:
  - the `escalate_to` target
  - an arbiter explicitly allowed by session policy for that conflict class
  - coordinator system-generated outcomes
  may resolve the conflict

**Impact**:

- Keeps deterministic ordering
- Preserves the meaning of escalation as an authority shift rather than only a notification

---

### 4. Cross-State-Machine Terminal Alignment [REVISED]

**Problem**: intent lifecycle rules already treated `TRANSFERRED` as terminal, but conflict auto-dismiss did not.

**Change**:

- Update the conflict auto-dismiss rule to include `TRANSFERRED` in the terminal intent set

**Impact**:

- Aligns conflict lifecycle behavior with the intent state machine
- Avoids stale conflicts surviving after a successful claim transfer

---

### 5. Governance Claim Auditability [REVISED]

**Problem**: governance-mediated claim approval could occur without a required record of who approved it.

**Change**:

- Change `INTENT_CLAIM_STATUS.approved_by` from optional to conditionally required for Governance Profile approvals
- Clarify that Core Profile coordinator auto-approval may omit `approved_by`

**Impact**:

- Makes claim transfer attributable in governance-governed sessions
- Improves audit completeness without changing message count

---

## Out of Scope

v0.1.10 intentionally does **not** attempt to solve broader future-version topics such as:

- richer scope expressiveness
- transport-level replay / key-distribution redesign
- cross-session coordination
- new batch-specific proposal message types
- general rollback protocol extensions

Those remain appropriate for a later `v0.2.x` revision rather than this closure pass.
