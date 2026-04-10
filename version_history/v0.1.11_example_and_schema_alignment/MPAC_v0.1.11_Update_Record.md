# MPAC v0.1.11 Update Record — Example and Schema Alignment

**Date**: 2026-04-04
**Base version**: v0.1.10
**New version**: v0.1.11
**Revision type**: Closure — documentation alignment and minor normative clarifications

---

## Motivation

A systematic review of the v0.1.10 root spec identified a class of issues where example messages, payload schema tables, and cross-references had fallen behind normative requirements introduced in v0.1.9–v0.1.10. Additionally, several edge-case behaviors (scope expansion via INTENT_UPDATE, GOODBYE transfer disposition, OP_BATCH_COMMIT pre-commit disambiguation) lacked explicit specification, creating interoperability ambiguity. This revision closes those gaps without expanding the protocol's feature scope.

---

## Changes

### 1. Section 28 — Example Messages: Add `sender_instance_id` and Update Version

**Problem**: All five example messages in Section 28 (HELLO, INTENT_ANNOUNCE, OP_COMMIT, CONFLICT_REPORT, RESOLUTION) omitted the `sender.sender_instance_id` field, which Section 11.2 declares as MUST. The `version` field was `"0.1.0"`, inconsistent with the current spec version.

**Fix**:
- Added `sender_instance_id` to every sender object in Sections 28.1–28.5
- Updated `version` to `"0.1.11"` in all example envelopes

**Impact**: Documentation only. No wire format or state machine change.

### 2. Section 13.1 — `SESSION_INFO` Payload: Add `identity_issuer`

**Problem**: Section 23.1.4 showed `identity_issuer` in the credential exchange response example, but the normative payload table in Section 13.1 did not list the field.

**Fix**: Added `identity_issuer` (type: string, optional) to the `SESSION_INFO` payload table with description referencing Section 23.1.4.

**Impact**: Payload schema completeness. The field was already in use; this makes the schema table authoritative.

### 3. Section 14.5 — `SESSION_CLOSE` Summary Alignment

**Problem**: The `SESSION_CLOSE` example in Section 14.5 used a simplified summary structure (`total_intents`, `total_operations`, `total_conflicts`, `total_resolutions`, `duration_sec`), while Section 9.6.2 defined a detailed structure with per-state breakdowns (`completed_intents`, `expired_intents`, `committed_operations`, etc.).

**Fix**: Updated the Section 14.5 example to match the detailed structure defined in Section 9.6.2.

**Impact**: Documentation alignment. The Section 9.6.2 structure was already normative; this removes ambiguity.

### 4. Section 14.6 — `COORDINATOR_STATUS` Cross-Reference Fix

**Problem**: The semantics for `COORDINATOR_STATUS` referenced "Section 14.3" for `heartbeat_interval_sec`, but 14.3 defines the `HEARTBEAT` message. The actual configuration lives in Section 14.7.5 (liveness policy).

**Fix**: Changed cross-reference from `(Section 14.3)` to `(Section 14.7.5)`.

**Impact**: Cross-reference correctness only.

### 5. Section 16.8 — `OP_BATCH_COMMIT` Pre-Commit Disambiguation Rule

**Problem**: In pre-commit model, `OP_BATCH_COMMIT` serves dual purposes: initial request-to-commit and post-execution completion declaration. The spec did not explicitly state how the coordinator distinguishes between the two.

**Fix**: Added a "Pre-commit disambiguation" bullet to Section 16.8 semantics: the coordinator checks whether a pending batch with the same `batch_id` already exists. New `batch_id` → initial request (entries enter PROPOSED). Known authorized `batch_id` → completion declaration (entries transition to COMMITTED). Explicitly parallels the `OP_COMMIT` disambiguation in Section 16.6.1.

**Impact**: Normative clarification. Reduces implementation ambiguity for pre-commit batch workflows.

### 6. Section 15.4 — `INTENT_UPDATE` Scope Expansion Conflict Re-Evaluation

**Problem**: `INTENT_UPDATE` allowed unrestricted scope changes, including expansion beyond the original `INTENT_ANNOUNCE` scope. This could bypass conflict detection: an agent could announce a narrow scope, establish itself, then silently expand into contested territory.

**Fix**: Added semantics to Section 15.4: when scope is updated and the new scope is strictly larger, the coordinator SHOULD re-evaluate the expanded scope for overlap with other active intents and SHOULD generate a `CONFLICT_REPORT` for any newly overlapping portion.

**Impact**: SHOULD-level normative addition. Does not break existing implementations that already ignore scope changes, but provides clear guidance for correct behavior.

### 7. Section 14.4 — `GOODBYE` Transfer Disposition Mechanism

**Problem**: The `intent_disposition: "transfer"` value in `GOODBYE` was described as "requires session coordinator support" without specifying the actual mechanism.

**Fix**: Added clarification that the coordinator SHOULD transition the departing participant's active intents to `SUSPENDED` upon receiving `GOODBYE` with `intent_disposition: "transfer"`, making them eligible for `INTENT_CLAIM` by other participants per Section 14.7.4. The specific mechanism for soliciting claims is implementation-defined.

**Impact**: SHOULD-level normative addition. Connects the GOODBYE transfer path to the existing INTENT_CLAIM infrastructure.

### 8. Section 20.3 — Semantic Profile Placeholder Note

**Problem**: The Semantic Profile definition was three lines, far less detailed than Core and Governance Profiles, without any indication that this was intentional.

**Fix**: Added a note: "The Semantic Profile is a placeholder in v0.1.x. Its requirements are intentionally minimal; a detailed specification will be provided in a future version."

**Impact**: Documentation clarity only.

---

### 9. Section 15.6.1 — Intent State Transition Table: GOODBYE Transfer Row

**Problem**: The GOODBYE transfer semantics added in change #7 (Section 14.4) introduced a SHOULD-level `ACTIVE → SUSPENDED` path, but the normative state transition table in Section 15.6.1 did not include this transition. Since Section 15.6.1 states "any transition not listed is invalid and MUST be rejected", the GOODBYE transfer path was technically forbidden by the state machine.

**Fix**: Added a new row to the Intent State Transition Table: `ACTIVE → SUSPENDED` when owner departs with `intent_disposition`: `transfer` (triggered by coordinator upon receiving GOODBYE from the intent owner).

**Impact**: Normative state machine addition. One new row in the Intent lifecycle table.

### 10. Sections 17.8.1, 18.4 — Terminology Unification: "authority phase"

**Problem**: The Conflict State Transition Table (Section 17.8.1) used "current conflict phase" in guard conditions, while Section 18.4 (concurrent resolution rule) used "current authority phase". These refer to the same concept but the inconsistent terminology could cause confusion.

**Fix**: Replaced all occurrences of "current conflict phase" with "current authority phase" in the state transition table guard conditions.

**Impact**: Terminology alignment only. No semantic change.

---

## Summary

This revision makes zero changes to message types or wire format. It adds one row to the Intent state transition table (GOODBYE transfer → SUSPENDED) and closes 10 documentation, normative-clarification, and terminology gaps, ensuring that examples, payload tables, cross-references, state machine tables, and edge-case behaviors are consistent with the normative requirements established in v0.1.9–v0.1.10.
