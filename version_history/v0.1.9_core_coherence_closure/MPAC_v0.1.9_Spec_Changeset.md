# MPAC v0.1.9 Spec Changeset (Draft)

**Date**: 2026-04-04
**Status**: Applied changeset reference for the implemented v0.1.9 revision
**Companion Document**: [MPAC_v0.1.9_Update_Record.md](./MPAC_v0.1.9_Update_Record.md)

---

## Purpose

This document translates the v0.1.9 update record into concrete spec deltas. It complements the full `SPEC_v0.1.9` snapshot and identifies the exact field-, message-, and rule-level changes that were merged into the root spec.

---

## 1. Envelope Changes

### 1.1 Sender Object

Add a new required field to the envelope `sender` object:

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `sender_instance_id` | string | R | Session-local sender incarnation identifier. Stable across reconnect-to-new-coordinator if the sender process survives; regenerated if the sender process restarts. |

### 1.2 Coordinator Epoch

Add a new envelope field:

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `coordinator_epoch` | integer | C | Required on coordinator-authored messages. Monotonic fencing epoch used to reject stale coordinators. |

### 1.3 Envelope Semantics

Add normative rules:

1. Participants MUST treat `(sender.principal_id, sender.sender_instance_id)` as the sender identity for Lamport monotonicity and replay tracking.
2. Participants MUST reject coordinator-authored messages whose `coordinator_epoch` is lower than the highest accepted epoch for the session.
3. Lamport ordering MUST NOT be used to prefer a stale coordinator from a lower epoch over an accepted coordinator from a higher epoch.

---

## 2. Snapshot Format Changes

### 2.1 Required Snapshot Fields

Extend the coordinator snapshot with:

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `coordinator_epoch` | integer | R | Current accepted coordinator epoch for the session |
| `anti_replay` | object | C | Required in Authenticated / Verified profiles; checkpoint needed to resume replay protection after recovery |

### 2.2 `anti_replay` Object

Recommended minimum structure:

```json
{
  "anti_replay": {
    "replay_window_sec": 300,
    "recent_message_ids": [
      "msg-101",
      "msg-102"
    ],
    "sender_frontier": {
      "agent:alice|inst-01": {
        "last_ts": "2026-04-04T17:10:00Z",
        "last_lamport": 57
      }
    }
  }
}
```

Normative requirement:

- Implementations MAY use a different internal representation, but the persisted checkpoint MUST preserve enough information to enforce the same replay-acceptance policy after recovery.

---

## 3. Coordinator Recovery and Handover Changes

### 3.1 Planned Handover

Revise the handover rule:

1. Outgoing coordinator sends `COORDINATOR_STATUS` with:
   - `event: handover`
   - `successor_coordinator_id`
   - `next_coordinator_epoch`
   - envelope `coordinator_epoch = current_epoch`
2. Successor loads transferred state.
3. Successor begins authority only when it emits coordinator-authored messages with `coordinator_epoch = next_coordinator_epoch`.

### 3.2 Unplanned Failover

Revise the failover rule:

1. Standby loads the most recent snapshot.
2. Standby restores the last persisted epoch and adopts a new authority epoch before emitting any new coordinator-authored message.
3. If no `next_coordinator_epoch` was supplied by planned handover, standby uses `snapshot.coordinator_epoch + 1`.
4. Standby restores Lamport clock and anti-replay checkpoint.
5. Standby's first authoritative coordinator message MUST carry the new epoch.

### 3.3 Split-Brain Rule

Replace the current single-step Lamport comparison rule with:

1. Compare `coordinator_epoch` first.
2. Lower epoch is always stale and MUST be rejected.
3. If epochs are equal and two coordinators still appear, compare Lamport value.
4. Equal epoch plus conflicting coordinators MUST generate `COORDINATOR_CONFLICT`.

---

## 4. Lamport Rules Changes

### 4.1 Initialization Rule

Replace "participant initializes Lamport counter to 0 upon join" with:

- a sender incarnation initializes its Lamport counter to `0` when a new `sender_instance_id` is created
- reconnecting with the same `sender_instance_id` MUST preserve the existing Lamport counter

### 4.2 Monotonicity Rule

Replace "strictly monotonic per sender" with:

- strictly monotonic per (`principal_id`, `sender_instance_id`)

### 4.3 Rejoin Rule

Add:

1. If a participant re-sends `HELLO` after coordinator handover but its process has not restarted, it MUST reuse the same `sender_instance_id` and continue its Lamport counter.
2. If a participant restarts, it MUST generate a new `sender_instance_id`; Lamport reset is then valid for the new incarnation.

---

## 5. New Message Type: `INTENT_CLAIM_STATUS`

### 5.1 Payload Schema

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `claim_id` | string | R | Claim being decided |
| `original_intent_id` | string | R | Suspended intent targeted by the claim |
| `new_intent_id` | string | C | Required when `decision = approved` |
| `decision` | string | R | One of: `approved`, `rejected`, `withdrawn` |
| `reason` | string | C | Required when `decision = rejected` or `withdrawn` |
| `approved_by` | string | O | Principal whose approval authorized the claim |

### 5.2 Semantics

1. Only the session coordinator MAY send `INTENT_CLAIM_STATUS`.
2. A claim is not effective until the coordinator emits `decision = approved`.
3. On approval:
   - original suspended intent -> `TRANSFERRED`
   - replacement intent -> `ACTIVE`
4. On rejection:
   - original intent remains `SUSPENDED` unless another rule changes it
5. On withdrawal:
   - original owner has resumed before approval
   - original intent returns to `ACTIVE`
   - replacement intent MUST NOT become active

---

## 6. Intent Lifecycle Changes

### 6.1 Intent States

Add / enforce:

| State | Meaning |
|-------|---------|
| `TRANSFERRED` | Original intent was superseded by an approved claim from another participant |

### 6.2 Auto-Close and Summary Logic

Every place that currently enumerates terminal intent states MUST include:

- `WITHDRAWN`
- `EXPIRED`
- `SUPERSEDED`
- `TRANSFERRED`

Reference implementations must expose `TRANSFERRED` in both Python and TypeScript enums.

---

## 7. Operation Lifecycle Terminology Changes

### 7.1 Canonical Taxonomy

Define:

- **terminal**: `REJECTED`, `ABANDONED`, `SUPERSEDED`
- **stable**: `COMMITTED`
- **settled**: `COMMITTED`, `REJECTED`, `ABANDONED`, `SUPERSEDED`

### 7.2 Session Close Rule

Rewrite auto-close condition from:

- "all operations are terminal"

to:

- "all operations are settled"

This avoids conflicting with the valid `COMMITTED -> SUPERSEDED` transition.

---

## 8. Security Profile Changes

### 8.1 Replay Protection Continuity

Add to Authenticated / Verified profile requirements:

1. Replay protection MUST survive coordinator recovery.
2. Implementations MUST restore anti-replay checkpoint state before admitting new messages after recovery.
3. Snapshot persistence in these profiles MUST include the minimum checkpoint needed to continue duplicate-message rejection across the configured replay window.

### 8.2 Sender Identity

Clarify:

- authenticated sender identity is the triple:
  - `principal_id`
  - `sender_instance_id`
  - credential binding

This prevents ambiguity between a genuine process restart and a replay / monotonicity violation from the same long-lived sender incarnation.

---

## 9. JSON Schema Changes

### 9.1 Envelope Schema

Required updates:

- add `sender.sender_instance_id`
- add `coordinator_epoch`
- add `INTENT_CLAIM_STATUS` to `message_type`
- bind each `message_type` to the correct payload schema using conditional validation

### 9.2 Message Schemas

Required new / updated files:

- `messages/intent_claim_status.schema.json` (new)
- `messages/op_batch_commit.schema.json` (new)
- `messages/session_info.schema.json` (update `execution_model`)
- `messages/protocol_error.schema.json` (update error-code enum)

---

## 10. Error-Code Changes

No new error code is strictly required for v0.1.9 if `INTENT_CLAIM_STATUS` handles claim disposition explicitly.

However, the following existing behavior should be clarified:

- `CLAIM_CONFLICT` remains the correct response when a second claim loses first-claim-wins
- `COORDINATOR_CONFLICT` remains the correct response for same-epoch competing coordinators

Optional clarification:

- add `STALE_COORDINATOR_EPOCH` only if explicit stale-epoch diagnostics are desired instead of silent rejection + `COORDINATOR_CONFLICT`

---

## 11. Conformance Work Required

Minimum required tests for the v0.1.9 merge:

1. stale coordinator rejected after epoch increase
2. equal-epoch coordinator conflict resolved deterministically
3. reconnect with same sender instance preserves Lamport monotonicity
4. restart with new sender instance is accepted with counter reset
5. `INTENT_CLAIM_STATUS` approved / rejected / withdrawn paths
6. original claimed intent ends as `TRANSFERRED`, not `WITHDRAWN`
7. operations "settled" logic governs auto-close
8. replay protection survives snapshot recovery
9. schema validation covers every message type including `OP_BATCH_COMMIT`

---

## Suggested Merge Order into Root `SPEC.md`

1. Envelope and snapshot changes
2. Coordinator recovery / handover changes
3. Lamport monotonicity and rejoin changes
4. `INTENT_CLAIM_STATUS` and `TRANSFERRED`
5. Operation taxonomy cleanup
6. Security-profile replay continuity
7. JSON Schema and conformance updates

This order minimizes cross-reference churn while updating the root spec.
