# MPAC v0.1.11 Spec Changeset

**Base**: SPEC v0.1.10 (2026-04-04)
**Target**: SPEC v0.1.11 (2026-04-04)
**Archived snapshot**: `version_history/v0.1.11_example_and_schema_alignment/SPEC_v0.1.11_2026-04-04.md`

---

## Field-Level and Rule-Level Changes

### Section 1 — Status
- Version bumped: `0.1.10` → `0.1.11`

### Section 11.1 — Envelope Structure Example
- `version` field updated: `"0.1.10"` → `"0.1.11"` (via global version bump)

### Section 13.1 — `SESSION_INFO` Payload Table
- **Added field**: `identity_issuer` (string, Optional) — "Identity provider or certificate authority that issued the verified credential. Relevant in Authenticated/Verified profiles (Section 23.1.4)"
- Inserted between `identity_method` and `compatibility_errors`

### Section 14.4 — `GOODBYE` Semantics
- **Expanded** `transfer` disposition: coordinator SHOULD transition departing participant's active intents to `SUSPENDED`, making them eligible for `INTENT_CLAIM` per Section 14.7.4

### Section 14.5 — `SESSION_CLOSE` Payload Example
- **Replaced** simplified summary with detailed structure matching Section 9.6.2:
  - Added: `completed_intents`, `expired_intents`, `withdrawn_intents`, `committed_operations`, `rejected_operations`, `abandoned_operations`, `resolved_conflicts`, `total_participants`
  - Removed: `total_resolutions`

### Section 14.6 — `COORDINATOR_STATUS` Semantics
- **Fixed cross-reference**: `(Section 14.3)` → `(Section 14.7.5)` for `heartbeat_interval_sec`

### Section 15.4 — `INTENT_UPDATE` Semantics
- **Added** semantics block with two rules:
  1. At least one field besides `intent_id` SHOULD be present
  2. Scope expansion SHOULD trigger conflict re-evaluation by coordinator

### Section 16.8 — `OP_BATCH_COMMIT` Semantics
- **Added** "Pre-commit disambiguation" bullet: coordinator distinguishes initial vs completion `OP_BATCH_COMMIT` by checking whether `batch_id` already exists

### Section 20.3 — Semantic Profile
- **Added** placeholder note: "The Semantic Profile is a placeholder in v0.1.x"

### Section 28.1 — Example `HELLO`
- `version`: `"0.1.0"` → `"0.1.11"`
- `sender`: added `"sender_instance_id": "inst-a1"`

### Section 28.2 — Example `INTENT_ANNOUNCE`
- `version`: `"0.1.0"` → `"0.1.11"`
- `sender`: added `"sender_instance_id": "inst-a1"`

### Section 28.3 — Example `OP_COMMIT`
- `version`: `"0.1.0"` → `"0.1.11"`
- `sender`: added `"sender_instance_id": "inst-a1"`

### Section 28.4 — Example `CONFLICT_REPORT`
- `version`: `"0.1.0"` → `"0.1.11"`
- `sender`: added `"sender_instance_id": "inst-b1"`

### Section 28.5 — Example `RESOLUTION`
- `version`: `"0.1.0"` → `"0.1.11"`
- `sender`: added `"sender_instance_id": "inst-h1"`

### Section 15.6.1 — Intent State Transition Table
- **Added row**: `ACTIVE → SUSPENDED` when owner departs with `intent_disposition`: `transfer` (GOODBYE from owner, Section 14.4). This makes the GOODBYE transfer path a normative state transition, complementing the existing `ACTIVE → SUSPENDED` row for unavailability detection.

### Section 17.8.1 — Conflict State Transition Table
- **Terminology fix**: "current conflict phase" → "current authority phase" in guard conditions for `OPEN → RESOLVED` and `ACKED → RESOLVED` transitions, aligning with the terminology used in Section 18.4 concurrent resolution rule.

### Section 29 — Recommended Future Work (Note)
- Updated "addressed across" range: `v0.1.1–v0.1.10` → `v0.1.1–v0.1.11`
- Added v0.1.11 items to the addressed list

### Section 30 — Summary
- Version reference updated: `v0.1.10` → `v0.1.11` (via global version bump)

---

## What Did NOT Change

- **Message types**: Still 21. No new message types added.
- **State machines**: Intent transition table gained one row (GOODBYE transfer → SUSPENDED). Conflict and Operation tables unchanged in structure. No new states added.
- **Wire format**: No new required fields. `identity_issuer` was already in use; only the payload table was updated.
- **Security/compliance profiles**: No requirement changes (Semantic Profile note is informational).
- **Error codes**: No additions or removals.
