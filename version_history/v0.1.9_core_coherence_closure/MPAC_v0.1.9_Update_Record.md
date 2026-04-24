# MPAC v0.1.9 Update Record

**Date**: 2026-04-04
**Update Name**: Core Coherence Closure
**Previous Version**: v0.1.8 (Coordination Semantics Hardening)
**Trigger**: [MPAC_v0.1.8_Gap_Analysis.md](../v0.1.8_coordination_semantics_hardening/MPAC_v0.1.8_Gap_Analysis.md) identified 2 `P0`, 3 `P1`, and 2 `P2` items that materially affect v0.1.8's internal coherence and conformance surface.
**Status**: Applied to root `SPEC.md` on 2026-04-04

---

## Overview

v0.1.9 is a **closure revision**, not a feature-expansion revision.

Its purpose is to make MPAC v0.1.x internally coherent across:

- coordinator recovery and handover
- Lamport causality rules during participant rejoin
- intent-claim lifecycle semantics
- operation lifecycle terminology
- replay protection requirements
- JSON Schema and reference-conformance artifacts

This revision keeps MPAC's application-layer coordination scope intact. It does **not** add new transport-layer ambitions such as partition diagnosis, cross-session coordination, or generalized consensus. Instead, it repairs the points where the current protocol either contradicts itself or makes stronger claims than its wire semantics can presently support.

---

## Revision Goals

1. Resolve all `P0` items from the v0.1.8 gap analysis so that coordinator recovery and participant rejoin behavior are causally coherent.
2. Resolve all `P1` items so that lifecycle and security-profile semantics are no longer internally contradictory.
3. Resolve the `P2` conformance gaps so that JSON Schema, reference implementations, and tests track the normative spec.

---

## Changes Summary

### New Protocol Elements

| Element | Type | Purpose |
|---------|------|---------|
| `sender_instance_id` | Envelope sender field | Distinguishes participant incarnations across reconnect / restart boundaries |
| `coordinator_epoch` | Envelope field | Fences stale coordinators during failover and handover |
| `anti_replay` | Snapshot object | Preserves replay-protection continuity across recovery |
| `INTENT_CLAIM_STATUS` | New message type | Makes claim approval / rejection / withdrawal explicit on the wire |
| `settled` | Lifecycle term | Separates "safe for session close" from "terminal state" in operation semantics |

### Message Count

| Version | Message Types |
|---------|---------------|
| v0.1.8 | 20 |
| v0.1.9 | 21 (`INTENT_CLAIM_STATUS` added) |

---

## Mapping from Gap Findings to Changes

| Gap Finding | Priority | Disposition in v0.1.9 | Resolution |
|-------------|----------|------------------------|------------|
| Coordinator handover lacks fencing semantics | P0 | Fixed | Add `coordinator_epoch`, update split-brain rule, persist epoch in snapshot |
| Lamport rules break on participant rejoin | P0 | Fixed | Add `sender_instance_id`, scope monotonicity per sender incarnation, define rejoin behavior |
| `INTENT_CLAIM` lifecycle only partially protocolized | P1 | Fixed | Add `INTENT_CLAIM_STATUS`, align on `TRANSFERRED`, close approval / rejection / withdrawal paths |
| Operation lifecycle terminology inconsistent | P1 | Fixed | Introduce `settled` operations; keep terminal/stable states distinct |
| Replay protection not closed over recovery | P1 | Fixed | Add `anti_replay` snapshot requirements and recovery-continuity rules |
| JSON Schema lags the spec | P2 | Fixed | Add missing schemas / enums / conditional envelope validation |
| Implementation and test coverage lag | P2 | Fixed | Add required implementation and conformance-test work items |

---

## Detailed Changes

### 1. Coordinator Epoch and Fencing [NEW / REVISED]

**Problem**: v0.1.8 uses Lamport values to break coordinator ties, but Lamport clocks are not a leader-fencing mechanism. A stale coordinator can remain visible after failover.

**Change**:

- Add `coordinator_epoch: integer` to the message envelope.
- `coordinator_epoch` is **required on all coordinator-authored messages**.
- Add `coordinator_epoch` to the coordinator snapshot format.
- Planned handover:
  - outgoing coordinator sends `COORDINATOR_STATUS` with `event: handover`
  - payload includes `successor_coordinator_id` and `next_coordinator_epoch`
  - successor assumes authority only when it begins sending coordinator-authored messages with that new epoch
- Unplanned failover:
  - standby loads snapshot
  - restores the last persisted epoch and adopts a new authority epoch before emitting new coordinator-authored messages
  - if no `next_coordinator_epoch` was supplied by handover, uses `snapshot.coordinator_epoch + 1`
  - first coordinator-authored message after assumption MUST carry the incremented epoch
- Split-brain rule:
  - participants compare `coordinator_epoch` first
  - lower epoch is always stale and MUST be rejected
  - Lamport comparison is only used if competing coordinators claim the same epoch

**Impact**:

- Fences stale coordinators without turning MPAC into a full consensus protocol
- Narrows Lamport clocks to the role they actually serve: causal ordering within an accepted coordinator epoch

---

### 2. Sender Incarnation and Rejoin-Safe Lamport Semantics [NEW / REVISED]

**Problem**: participant Lamport counters currently reset on join, but sender monotonicity is defined per sender identity. Normal rejoin paths therefore violate the monotonicity rule.

**Change**:

- Extend the envelope `sender` object with:
  - `principal_id`
  - `principal_type`
  - `sender_instance_id`
- `sender_instance_id` is a session-local incarnation identifier generated by the sender process.
- Strict Lamport monotonicity is redefined from:
  - "per `principal_id`"
  - to "per (`principal_id`, `sender_instance_id`)"
- Rejoin rules:
  - if a participant reconnects after coordinator handover **without restarting its process**, it MUST preserve both `sender_instance_id` and its Lamport counter
  - if a participant restarts, it MUST generate a new `sender_instance_id`; counter reset to `0` is then valid for the new incarnation
- Replay protection and audit references MUST treat sender incarnation as part of sender identity.

**Impact**:

- Makes monotonicity and rejoin behavior compatible
- Preserves simple Lamport rules while distinguishing true restarts from transport-level reconnections

---

### 3. `INTENT_CLAIM` Lifecycle Closure [NEW / REVISED]

**Problem**: v0.1.8 describes approval-based claim semantics and a `TRANSFERRED` state, but approval is not a first-class wire event and the reference artifacts do not align on the resulting state.

**Change**:

- Add a new message type: `INTENT_CLAIM_STATUS`
- `INTENT_CLAIM_STATUS` payload:
  - `claim_id`
  - `original_intent_id`
  - `new_intent_id` (required when approved)
  - `decision`: `approved` | `rejected` | `withdrawn`
  - `reason` (required for `rejected` / `withdrawn`)
  - `approved_by` (optional)
- Semantics:
  - only the session coordinator may send `INTENT_CLAIM_STATUS`
  - in Governance Profile sessions, a claim remains pending until the coordinator emits `approved` or `rejected`
  - in Core Profile sessions, the coordinator MAY emit `approved` automatically after the no-objection window
  - if the original owner reconnects before approval, the coordinator MUST emit `withdrawn` and restore the original intent to `ACTIVE`
  - on approval, the original intent transitions to `TRANSFERRED`, and the replacement intent becomes `ACTIVE`
- Update the normative intent state machine and all close / summary logic to include `TRANSFERRED`.
- Align reference enums and state machines with the spec.

**Impact**:

- Eliminates the current ambiguity around claim approval visibility
- Removes the spec/implementation split between `TRANSFERRED` and `WITHDRAWN`

---

### 4. Operation Lifecycle Taxonomy Cleanup [REVISED]

**Problem**: the spec currently uses "terminal" inconsistently for operations, especially around `COMMITTED` and session auto-close.

**Change**:

- Keep operation lifecycle semantics:
  - **terminal**: `REJECTED`, `ABANDONED`, `SUPERSEDED`
  - **stable non-terminal**: `COMMITTED`
- Introduce a new session-lifecycle term:
  - **settled operation** = `COMMITTED` | `REJECTED` | `ABANDONED` | `SUPERSEDED`
- Rewrite session auto-close conditions to require that all operations are **settled**, not terminal.
- Reuse this terminology in session summaries, transcript export, and interoperability guidance.

**Impact**:

- Preserves `COMMITTED -> SUPERSEDED` as a valid lifecycle path
- Removes the contradiction between lifecycle tables and session-close rules

---

### 5. Replay Protection Continuity Across Recovery [NEW / REVISED]

**Problem**: Authenticated / Verified profiles require replay protection, but the normative snapshot format does not preserve enough information to continue enforcing it after recovery.

**Change**:

- Add an `anti_replay` object to the coordinator snapshot:
  - `replay_window_sec`
  - `recent_message_ids`
  - `sender_frontier`
- `sender_frontier` records the last accepted replay-relevant state per sender incarnation:
  - timestamp
  - Lamport value
  - optional implementation-specific frontier metadata
- Recovery rule:
  - Authenticated and Verified profile implementations MUST restore `anti_replay` state before accepting new messages
- Scope clarification:
  - MPAC still does not own transport-level partition diagnosis
  - but once the spec defines replay protection as a compliance requirement, recovery continuity for that protection is also a protocol responsibility

**Impact**:

- Makes replay protection a recoverable protocol property rather than a best-effort deployment extra

---

### 6. JSON Schema Closure [REVISED]

**Problem**: v0.1.8's schemas lag the normative spec and do not fully enforce wire-level compatibility.

**Change**:

- Add payload schema for `INTENT_CLAIM_STATUS`
- Add payload schema for `OP_BATCH_COMMIT`
- Update `SESSION_INFO` schema to include required `execution_model`
- Update `PROTOCOL_ERROR` schema with all v0.1.8 and v0.1.9 error codes
- Update envelope schema:
  - add `coordinator_epoch`
  - add `sender.sender_instance_id`
  - bind `message_type` to the correct payload schema using conditional validation

**Impact**:

- Restores JSON Schema to its intended role as a machine-enforceable conformance artifact

---

### 7. Reference Implementation and Test Closure [REVISED]

**Problem**: repository artifacts currently allow silent drift between spec text, schemas, and implementations.

**Change**:

- Required reference-implementation work:
  - implement `INTENT_CLAIM_STATUS`
  - add sender-instance tracking
  - add coordinator-epoch tracking and stale-coordinator rejection
  - implement / complete `OP_BATCH_COMMIT`
  - persist and restore `anti_replay` snapshot state
- Required test additions:
  - stale coordinator rejected after epoch bump
  - equal-epoch coordinator conflict handling
  - participant rejoin without restart preserves monotonicity
  - participant restart with new sender instance is accepted
  - claim approval / rejection / withdrawal paths
  - auto-close with settled vs terminal operations
  - replay protection continuity across recovery
  - schema validation for every message type

**Impact**:

- Makes the repaired semantics executable and testable
- Reduces future drift between root `SPEC.md`, schema artifacts, and reference code

---

## Impact on Reference Implementations

### Python

- Add `sender_instance_id` generation and propagation in participant client
- Track Lamport monotonicity per sender incarnation
- Persist / restore `coordinator_epoch` and `anti_replay`
- Add `INTENT_CLAIM_STATUS` message handling
- Implement `OP_BATCH_COMMIT`

### TypeScript

- Same changes as Python
- Update type definitions for new envelope fields and new message type

### JSON Schema

- Message count: 11 payload schemas -> 13 payload schemas
- Envelope becomes message-type-aware rather than payload-agnostic

### Documentation

- Root `SPEC.md` has been merged to v0.1.9
- `MPAC_Developer_Reference.md` must be updated for:
  - new envelope fields
  - `TRANSFERRED`
  - `INTENT_CLAIM_STATUS`
  - operation `settled` terminology
  - replay checkpoint snapshot fields

---

## Release Boundary

This release keeps **all seven items above in the same revision boundary**, because they are tightly coupled:

- fencing without rejoin-safe sender semantics is incomplete
- claim closure without state-machine alignment leaves drift unresolved
- repaired spec text without schema / conformance closure will regress quickly

For that reason, v0.1.9 is best treated as a **coherence release**, not a piecemeal patch release.
