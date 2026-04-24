# MPAC v0.1.10 Spec Changeset

**Date**: 2026-04-04
**Status**: Applied changeset reference for the implemented v0.1.10 revision
**Companion Document**: [MPAC_v0.1.10_Update_Record.md](./MPAC_v0.1.10_Update_Record.md)

---

## Purpose

This document translates the v0.1.10 update record into concrete spec deltas. It complements the archived `SPEC_v0.1.10_2026-04-04.md` snapshot and identifies the rule-level changes merged into the root spec.

---

## 1. Execution Model Changes

### 1.1 Section 7.8 Rewrite

Revise `pre_commit` so that:

1. Authorization happens before execution.
2. Authorization alone does **not** move the operation to `COMMITTED`.
3. `COMMITTED` is reached only when the proposer later declares the executed mutation via `OP_COMMIT`.
4. Initial `OP_COMMIT` in `pre_commit` remains permitted only as a backward-compatible request path; it enters `PROPOSED`, not `COMMITTED`.

### 1.2 Profile Gate

Add normative profile rules:

- Core Profile sessions MUST use `post_commit`
- Sessions declaring `pre_commit` MUST also declare Governance Profile compliance

---

## 2. Operation Lifecycle Changes

### 2.1 Operation Model Text

Clarify that an operation in `pre_commit` MAY remain `PROPOSED` after authorization and becomes `COMMITTED` only when execution completion is declared.

### 2.2 `OP_COMMIT` Purpose Text

Keep the canonical meaning:

- `OP_COMMIT` declares a committed mutation

Add the backward-compatible exception:

- in `pre_commit`, an initial `OP_COMMIT` MAY be accepted as a request-to-commit, but only as a `PROPOSED` operation

### 2.3 State Transition Table

Replace the old pre-commit rows:

- `(none) -> PROPOSED` on initial `OP_COMMIT` in `pre_commit`
- `PROPOSED -> PROPOSED` on coordinator authorization
- `PROPOSED -> COMMITTED` on completion `OP_COMMIT` after authorization

### 2.4 Batch Commit Clarification

Revise `OP_BATCH_COMMIT` semantics so that:

- post-commit batch submission is still an immediate commit declaration
- pre-commit batch submission first enters `PROPOSED`
- after authorization, the proposer emits a completion `OP_BATCH_COMMIT` for the same `batch_id`

---

## 3. Claim Approval Attribution Changes

### 3.1 Payload Table

Change:

| Field | Old | New |
|-------|-----|-----|
| `approved_by` | Optional | Conditionally required when `decision = approved` in Governance Profile sessions |

### 3.2 Claim Semantics

Add:

- Governance Profile `INTENT_CLAIM_STATUS(approved)` MUST include `approved_by`
- Core Profile coordinator auto-approval MAY omit `approved_by`

---

## 4. Conflict Resolution Authority Changes

### 4.1 Conflict State Table

Revise `RESOLUTION` guards so that:

- `OPEN` / `ACKED`: resolver must be authorized for the current conflict phase
- `ESCALATED`: resolver must be the escalation target, a session-policy-authorized arbiter, or the coordinator issuing a system-generated outcome

### 4.2 Concurrent Resolution Rule

Replace unconditional role-agnostic first-resolution-wins with:

1. Filter by current-phase authority first
2. Reject out-of-phase resolvers
3. Apply first-resolution-wins only among resolvers authorized for the current phase

---

## 5. Auto-Dismiss and Decision Registry Changes

### 5.1 Auto-Dismiss Terminal Intent Set

Add `TRANSFERRED` to the terminal intent set used by conflict auto-dismiss.

### 5.2 Decision Registry

Remove `deferred` from:

- `RESOLUTION` payload table
- recommended `decision` value list

Reason:

- the spec had no conflict-state-machine semantics for a deferred resolution

---

## 6. Compliance Profile Changes

### 6.1 Core Profile

Add:

- `post_commit` execution model only

### 6.2 Governance Profile

Revise:

- `pre_commit` support remains available, but only under Governance Profile compliance

---

## 7. Version and Summary Updates

Update:

- root spec version from `0.1.9` to `0.1.10`
- example `protocol_version` / envelope `version` literals to `0.1.10`
- closing summary text to reflect execution/governance closure and phase-scoped resolver authority
