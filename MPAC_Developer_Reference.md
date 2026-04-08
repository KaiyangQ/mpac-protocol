# MPAC v0.1.13 Developer Reference

Technical reference for implementers. This document is organized around data structures, defining all modules, fields, enum values, state machines, and cross-module reference relationships.

**Conventions**: R = Required, O = Optional, C = Conditionally required (depends on the value of other fields)

---

## 1. Core Data Objects

All MPAC messages and state are composed of the following core data objects. Understanding the reference relationships between them is fundamental to implementing the protocol.

### 1.1 Principal (Participant Identity)

Describes a subject participating in a session.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `principal_id` | string | R | Unique identifier. Recommended format: `{type}:{name}`, e.g., `agent:alice-coder-1` |
| `principal_type` | string | R | Enum: `human` / `agent` / `service` |
| `display_name` | string | O | Human-readable name |
| `roles` | string[] | O | List of roles, see [Enum: Roles](#61-roles) |
| `capabilities` | string[] | O | List of capabilities, see [Enum: Capabilities](#62-capabilities) |

**Referenced by**: The `sender` field of Message Envelope, the `original_principal_id` of INTENT_CLAIM, the `escalate_to` of CONFLICT_ESCALATE

---

### 1.2 Message Envelope

The outer wrapper for all MPAC messages. Every message, regardless of type, must have this structure.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `protocol` | string | R | Fixed value `"MPAC"` |
| `version` | string | R | Protocol version, e.g., `"0.1.13"` |
| `message_type` | string | R | Message type, see [Message Type Catalog](#2-message-type-catalog) |
| `message_id` | string | R | Unique message ID, must be unique across the system |
| `session_id` | string | R | ID of the owning session -> associated with [Session](#13-session) |
| `sender` | object | R | Sender info, structured as `{ principal_id, principal_type, sender_instance_id }`. The `sender_instance_id` identifies this sender's process instance/incarnation within the session -> associated with [Principal](#11-principal-participant-identity) |
| `ts` | string | R | RFC 3339 UTC timestamp, e.g., `"2026-04-02T10:00:00Z"` |
| `payload` | object | R | Message body; structure varies by `message_type` |
| `watermark` | Watermark | O | Causal context, see [Watermark](#14-watermark-causal-watermark) |
| `in_reply_to` | string | O | Target `message_id` being replied to |
| `trace_id` | string | O | Distributed tracing ID |
| `policy_ref` | string | O | Policy reference |
| `signature` | string | O | Message signature (used in Authenticated/Verified profiles) |
| `coordinator_epoch` | integer | C | Required only for coordinator-authored messages. Coordinator authoritative epoch, used for failover/handover fencing |
| `extensions` | object | O | Extension fields, format: `{ "vendor.name": { ... } }` |

**Key constraints**:
- The `watermark` for `OP_COMMIT`, `CONFLICT_REPORT`, and `RESOLUTION` is **MUST** (although the field is optional at the envelope level, these three message types mandate it)
- Under Authenticated/Verified profiles, `message_id` is used for replay detection; the coordinator will reject duplicate values; after recovery, the same replay-protection policy must continue to be enforced
- Lamport monotonicity is evaluated per `(sender.principal_id, sender.sender_instance_id)` sender incarnation pair, not just by `principal_id`
- All coordinator-authored messages must carry `coordinator_epoch`; when determining coordinator authority, receivers compare epoch first, then compare Lamport watermarks within the same epoch

---

### 1.3 Session

A Session is not a message but a state container, configured via session metadata.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | R | Unique identifier |
| `protocol_version` | string | R | MPAC version |
| `security_profile` | string | R | Enum: `open` / `authenticated` / `verified` |
| `compliance_profile` | string | O | Enum: `core` / `governance` / `semantic` |
| `execution_model` | string | R | Enum: `pre_commit` / `post_commit`. Declares the execution model of this session, see [Section 7.8] |
| `governance_policy` | object | O | Governance configuration, see [Governance Policy](#15-governance-policy) |
| `liveness_policy` | object | O | Liveness configuration, see [Liveness Policy](#16-liveness-policy) |
| `resource_registry` | object | O | Resource registry, see [Resource Registry](#17-resource-registry) |
| `state_ref_format` | string | O | Format declaration for state_ref, e.g., `"sha256"` / `"git_hash"` / `"monotonic_version"` |

**Note**: Session is not transmitted directly in messages. It is exposed to participants via the `SESSION_INFO` message payload.

---

### 1.4 Watermark (Causal Watermark)

Expresses "when I sent this message, I was already aware of the following prior state."

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `kind` | string | R | Enum: `lamport_clock` (MUST support) / `vector_clock` / `causal_frontier` / `opaque` |
| `value` | any | R | Type determined by kind: `lamport_clock` -> integer, `vector_clock` -> `{ participant: clock }` object, others -> string |
| `lamport_value` | integer | O | When kind is not `lamport_clock`, SHOULD provide this field as a fallback comparison value |

**Comparison semantics** (`lamport_clock`):
- `a < b` -> a happened-before b
- `a == b` or incomparable -> concurrent or indeterminate

**Referenced by**: The `watermark` field of Message Envelope, the `based_on_watermark` field of CONFLICT_REPORT

---

### 1.5 Governance Policy

Session-level configuration controlling conflict resolution and permission behavior.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `require_arbiter` | boolean | `false` | MUST be true under Governance profile |
| `resolution_timeout_sec` | integer | `300` | Timeout in seconds for unresolved conflicts; 0 = disabled |
| `timeout_action` | string | `"escalate_then_freeze"` | Action taken on timeout |
| `frozen_scope_behavior` | string | `"reject_writes_and_intents"` | Rejection policy for frozen scopes |
| `frozen_scope_phase_1_sec` | integer | `60` | Duration of Phase 1 (normal resolution) |
| `frozen_scope_phase_2_sec` | integer | `240` | Duration of Phase 2 (auto-escalation + priority bypass) |
| `frozen_scope_phase_3_action` | string | `"first_committer_wins"` | Phase 3 fallback action |
| `frozen_scope_disable_phase_3` | boolean | `false` | Whether to disable Phase 3 automatic fallback. `true` = scope remains frozen indefinitely until manually resolved (not recommended) |
| `intent_expiry_grace_sec` | integer | `30` | Grace period before associated proposals are auto-rejected after intent expiry |

---

### 1.6 Liveness Policy

Session-level configuration controlling heartbeat and unavailability detection.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `heartbeat_interval_sec` | integer | `30` | Heartbeat send interval |
| `unavailability_timeout_sec` | integer | `90` | Duration of no messages before declaring unavailability |
| `orphaned_intent_action` | string | `"suspend"` | How to handle intents when participant becomes unavailable |
| `orphaned_proposal_action` | string | `"abandon"` | How to handle proposals when participant becomes unavailable |
| `intent_claim_approval` | string | `"governance"` | Approval method for INTENT_CLAIM |
| `intent_claim_grace_period_sec` | integer | `30` | Grace period before auto-approval of claims under Core profile |
| `backend_health_policy` | object | O | AI model backend health monitoring policy | |

---

### 1.7 Resource Registry

Optional session-level configuration. Maps different scope kind representations to unified canonical URIs.

```
resource_registry.mappings[] -> each entry contains:
  canonical_uri: string        -> Canonical resource URI
  aliases[]:                   -> Alias list
    kind: string               -> Scope kind
    value: string              -> Resource identifier under that kind
```

**Purpose**: When participants in a session use different scope kinds (e.g., one uses `file_set` while another uses `entity_set`), the registry enables the coordinator to determine whether they refer to the same resource.

---

### 1.8 Scope

Describes the target resource set of an intent or operation. This is the core input for conflict detection.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `kind` | string | R | Enum: `file_set` / `resource_path` / `task_set` / `query` / `entity_set` / `custom` |
| `resources` | string[] | C | Required when kind = `file_set`. Array of file paths |
| `pattern` | string | C | Required when kind = `resource_path`. Glob pattern |
| `task_ids` | string[] | C | Required when kind = `task_set`. Array of task IDs |
| `expression` | string | C | Required when kind = `query`. Query expression |
| `language` | string | C | Required when kind = `query`. Query language identifier |
| `entities` | string[] | C | Required when kind = `entity_set`. Array of entity names |
| `canonical_uris` | string[] | O | Canonical resource URIs. MUST for cross-kind sessions under Authenticated/Verified profiles |
| `extensions` | object | O | Implementation-specific extensions |

**Overlap determination rules**:

| Kind | Algorithm | Level |
|------|-----------|-------|
| `file_set` | Normalize paths (remove `./`, collapse `//`, strip trailing `/`), then exact string match; take set intersection | MUST |
| `entity_set` | Exact string match; take set intersection | MUST |
| `task_set` | Exact string match; take set intersection | MUST |
| `resource_path` | Minimum support for `*` and `**` glob matching | SHOULD |
| `query` / `custom` | Conservative assumption: possible overlap | Default behavior |
| Cross-kind | Determine via `canonical_uris` or resource registry; if neither is available, conservatively assume overlap | MUST NOT assume non-overlap solely based on different kinds |

**Referenced by**: The `scope` field of INTENT_ANNOUNCE / INTENT_UPDATE / INTENT_CLAIM

---

### 1.9 Basis (Conflict Detection Basis)

Describes how a conflict was detected.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `kind` | string | R | Enum: `rule` / `heuristic` / `model_inference` / `semantic_match` / `human_report` |
| `rule_id` | string | O | Rule identifier when kind = `rule` |
| `matcher` | string | O | Matcher identifier when kind = `semantic_match` |
| `match_type` | string | O | Match result when kind = `semantic_match`: `contradictory` / `equivalent` / `uncertain` |
| `confidence` | number | O | Confidence score between 0.0 and 1.0. Values below the threshold (default 0.7) should be treated as `uncertain` |
| `matched_pair` | object | O | `{ left: { source_intent_id, content }, right: { source_intent_id, content } }` |
| `explanation` | string | O | Human-readable explanation of the match |

**Referenced by**: The `basis` field of CONFLICT_REPORT

---

### 1.10 Outcome (Resolution Outcome)

Describes the specific decision result of a RESOLUTION.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `accepted` | string[] | O | List of accepted intent/operation IDs |
| `rejected` | string[] | O | List of rejected intent/operation IDs |
| `merged` | string[] | O | List of merged intent/operation IDs |
| `rollback` | string | C | **MUST be provided** when the rejected list contains operations in COMMITTED state. Value is a reference to the compensating OP_COMMIT or `"not_required"` |

**Referenced by**: The `outcome` field of RESOLUTION

---

## 2. Message Type Catalog

MPAC v0.1.13 has 21 message types, distributed across six categories: Session / Intent / Operation / Conflict / Governance / Error.

| Layer | Message Type | Direction | Core Profile | Governance Profile |
|-------|-------------|-----------|-------------|-------------------|
| Session | `HELLO` | Participant -> Coordinator | ✅ | ✅ |
| Session | `SESSION_INFO` | Coordinator -> Participant | ✅ | ✅ |
| Session | `SESSION_CLOSE` | Coordinator -> All | ✅ | ✅ |
| Session | `COORDINATOR_STATUS` | Coordinator -> All | ✅ | ✅ |
| Session | `HEARTBEAT` | Participant -> All | ✅ | ✅ |
| Session | `GOODBYE` | Participant -> All | ✅ | ✅ |
| Intent | `INTENT_ANNOUNCE` | Participant -> All | ✅ | ✅ |
| Intent | `INTENT_UPDATE` | Participant -> All | | ✅ |
| Intent | `INTENT_WITHDRAW` | Participant -> All | | ✅ |
| Intent | `INTENT_CLAIM` | Participant -> Coordinator | | ✅ |
| Intent | `INTENT_CLAIM_STATUS` | Coordinator -> All | | ✅ |
| Operation | `OP_PROPOSE` | Participant -> Coordinator | | ✅ |
| Operation | `OP_COMMIT` | Participant -> All | ✅ | ✅ |
| Operation | `OP_REJECT` | Reviewer/Coordinator -> Participant | | ✅ |
| Operation | `OP_SUPERSEDE` | Participant -> All | | ✅ |
| Operation | `OP_BATCH_COMMIT` | Participant -> Coordinator | ✅ | ✅ |
| Conflict | `CONFLICT_REPORT` | Detector -> All | ✅ | ✅ |
| Conflict | `CONFLICT_ACK` | Participant -> All | | ✅ |
| Conflict | `CONFLICT_ESCALATE` | Participant -> Arbiter | | ✅ |
| Governance | `RESOLUTION` | Arbiter/Owner -> All | ✅ | ✅ |
| Error | `PROTOCOL_ERROR` | Any -> Any | ✅ | ✅ |

---

## 3. Message Payload Detailed Definitions

### 3.1 HELLO

Join a session, declaring identity and capabilities.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `display_name` | string | R | Human-readable name | |
| `roles` | string[] | R | Requested role list | -> [Roles Enum](#61-roles) |
| `capabilities` | string[] | R | Supported capability list | -> [Capabilities Enum](#62-capabilities) |
| `implementation` | object | O | `{ name: string, version: string }` | |
| `credential` | object | C | Required under Authenticated/Verified profiles. `{ type: string, value: string, issuer?: string, expires_at?: string }` | -> [Security Profile](#63-security-profile) |
| `backend` | object | O | Agent's AI model backend dependency | |

**Follow-up**: Upon receiving this, the coordinator MUST reply with SESSION_INFO.

---

### 3.2 SESSION_INFO

The coordinator's response to HELLO, carrying session configuration and compatibility check results.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `session_id` | string | R | Session ID | -> [Session](#13-session) |
| `protocol_version` | string | R | Protocol version | |
| `security_profile` | string | R | Security level | -> [Security Profile Enum](#63-security-profile) |
| `compliance_profile` | string | R | Compliance level | -> [Compliance Profile Enum](#64-compliance-profile) |
| `execution_model` | string | R | Enum: `pre_commit` / `post_commit`. Declares the session's execution model | -> Execution Model (Section 8.2) |
| `watermark_kind` | string | R | Baseline watermark type | -> [Watermark](#14-watermark-causal-watermark) |
| `state_ref_format` | string | R | state_ref format | -> `state_ref_before/after` in OP_COMMIT |
| `governance_policy` | object | O | Governance configuration | -> [Governance Policy](#15-governance-policy) |
| `liveness_policy` | object | O | Liveness configuration | -> [Liveness Policy](#16-liveness-policy) |
| `participant_count` | integer | O | Current participant count | |
| `granted_roles` | string[] | R | Actually granted roles (may differ from HELLO request) | -> [Roles Enum](#61-roles) |
| `identity_verified` | boolean | O | Whether participant credentials have been verified. Required under Authenticated/Verified profiles | -> [Security Profile](#63-security-profile) |
| `identity_method` | string | O | Credential type used for verification, e.g., `bearer_token` / `mtls_fingerprint` | |
| `identity_issuer` | string | O | Identity provider or CA that issued the credential, e.g., `https://auth.example.com`. Related to Authenticated/Verified profiles | -> Spec §23.1.4 |
| `compatibility_errors` | string[] | O | List of detected incompatibilities | |

**Envelope requirement**: As a coordinator-authored message, the Message Envelope of `SESSION_INFO` MUST include `coordinator_epoch`.

**Compatibility note**: For legacy implementations prior to v0.1.7, if a `SESSION_INFO` without `execution_model` is received, the receiver MUST treat it as `post_commit`.

---

### 3.3 HEARTBEAT

Maintains liveness and publishes status summaries.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `status` | string | R | Enum: `idle` / `working` / `blocked` / `awaiting_review` / `offline` | |
| `active_intent_id` | string | O | Currently active intent ID | -> `intent_id` of INTENT_ANNOUNCE |
| `summary` | string | O | Human-readable activity summary | |
| `backend_health` | object | O | Backend provider health status | |

**Frequency**: SHOULD be sent every 30 seconds. No messages for 90 consecutive seconds -> declared unavailable.

---

### 3.4 GOODBYE

Leave a session.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `reason` | string | R | Enum: `user_exit` / `session_complete` / `error` / `timeout` | |
| `active_intents` | string[] | O | List of intent IDs still active at departure | -> `intent_id` of INTENT_ANNOUNCE |
| `intent_disposition` | string | O | Enum: `withdraw` / `transfer` / `expire`. Default: `withdraw` | |

**Transfer mechanism**: When `intent_disposition` = `transfer`, the coordinator SHOULD transition the departing participant's active intents to `SUSPENDED`, making them claimable by other participants via `INTENT_CLAIM` (§14.7.4). The specific claim solicitation mechanism is implementation-defined.

---

### 3.5 INTENT_ANNOUNCE

Declares planned work to be performed. **Under Governance Profile, MUST be sent before OP_PROPOSE/OP_COMMIT.**

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `intent_id` | string | R | Unique identifier | Referenced by OP_PROPOSE/OP_COMMIT/CONFLICT_REPORT |
| `objective` | string | R | Human-readable objective description | |
| `scope` | Scope | R | Target resource set | -> [Scope](#18-scope) |
| `assumptions` | string[] | O | Important implicit dependencies. Default: `[]` | Used by semantic_match for contradiction detection |
| `priority` | string | O | Enum: `low` / `normal` / `high` / `critical`. Default: `normal` | |
| `ttl_sec` | integer | O | Wall-clock seconds; coordinator determines expiry based on received_at. Default: `300` | |
| `parent_intent_id` | string | O | Parent intent ID (hierarchical relationship) | -> `intent_id` of another intent |
| `supersedes_intent_id` | string | O | ID of the intent superseded by this one | -> `intent_id` of another intent |

---

### 3.6 INTENT_UPDATE

Modifies properties of an active intent.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `intent_id` | string | R | ID of the intent to update | -> `intent_id` of INTENT_ANNOUNCE |
| `objective` | string | O | New objective | |
| `scope` | Scope | O | New scope | -> [Scope](#18-scope) |
| `assumptions` | string[] | O | New assumption list | |
| `ttl_sec` | integer | O | New TTL | |

**Constraint**: At least one field besides `intent_id` must be provided.

**Scope expansion re-check**: When the `scope` field is updated and the new scope is **strictly larger** than the original scope (covering resources not declared in the original `INTENT_ANNOUNCE`), the coordinator SHOULD re-perform overlap detection on the expanded portion and SHOULD generate a `CONFLICT_REPORT` if new overlaps are found. This prevents participants from circumventing conflict detection through incremental updates.

---

### 3.7 INTENT_WITHDRAW

Cancels an active intent.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `intent_id` | string | R | ID of the intent to cancel | -> `intent_id` of INTENT_ANNOUNCE |
| `reason` | string | O | Cancellation reason | |

**Side effect**: Triggers the Intent Expiry Cascade (Section 15.7); associated pending proposals are automatically rejected.

---

### 3.8 INTENT_CLAIM

Claims a suspended intent from an unavailable participant.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `claim_id` | string | R | Unique identifier for the claim | |
| `original_intent_id` | string | R | The suspended intent being claimed | -> Must be an intent in SUSPENDED state |
| `original_principal_id` | string | R | Principal ID of the original intent owner | -> [Principal](#11-principal-participant-identity) |
| `new_intent_id` | string | R | Newly created intent ID | |
| `objective` | string | R | Objective of the new intent | |
| `scope` | Scope | R | New scope (must be equal to or narrower than the original scope) | -> [Scope](#18-scope) |
| `justification` | string | O | Justification for the claim | |

**Race condition rules**:
- First-claim-wins; subsequent claims receive a `CLAIM_CONFLICT` error
- A claim does not take effect until the coordinator issues `INTENT_CLAIM_STATUS(decision=approved)`
- If the original participant reconnects before approval -> the coordinator MUST issue `INTENT_CLAIM_STATUS(decision=withdrawn)`, and the original intent is restored to `ACTIVE`

---

### 3.8.1 INTENT_CLAIM_STATUS

The coordinator's authoritative disposition of an `INTENT_CLAIM`. Used to explicitly indicate whether a claim has been approved, rejected, or withdrawn due to the original owner's recovery.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `claim_id` | string | R | The claim ID being disposed | -> `claim_id` of INTENT_CLAIM |
| `original_intent_id` | string | R | The suspended intent that was claimed | -> `intent_id` of INTENT_ANNOUNCE |
| `new_intent_id` | string | C | Required when `decision=approved`: ID of the replacement intent | -> `intent_id` of INTENT_ANNOUNCE |
| `decision` | string | R | Enum: `approved` / `rejected` / `withdrawn` | |
| `reason` | string | C | Required when `decision=rejected` or `withdrawn` | |
| `approved_by` | string | C | Required under Governance Profile when `decision=approved`: principal ID of the approver | -> [Principal](#11-principal-participant-identity) |

**Semantics**:
- Only the session coordinator can send `INTENT_CLAIM_STATUS`
- `approved`: The original intent enters `TRANSFERRED`; the new intent enters `ACTIVE`
- Under Governance Profile, `approved` must include `approved_by`; under Core Profile, if the coordinator auto-approves via a no-objection policy, this may be omitted
- `rejected`: The original intent remains `SUSPENDED`, unless other rules change it
- `withdrawn`: Indicates the original owner recovered before approval completed; the original intent returns to `ACTIVE`, and the new intent must not be activated

---

### 3.9 OP_PROPOSE

Proposes a change pending approval (used under Governance Profile).

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `op_id` | string | R | Unique operation identifier | Referenced by OP_COMMIT/OP_REJECT/CONFLICT_REPORT |
| `intent_id` | string | O | Associated intent ID | -> `intent_id` of INTENT_ANNOUNCE |
| `target` | string | R | Resource being modified | |
| `op_kind` | string | R | Change type, e.g., `replace` / `insert` / `delete` / `patch` | |
| `change_ref` | string | O | Reference to the change content (e.g., hash of the diff blob) | |
| `summary` | string | O | Human-readable summary | |

---

### 3.10 OP_COMMIT

Declares that a change has been committed to shared state.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `op_id` | string | R | Unique operation identifier | |
| `intent_id` | string | O (Governance: R) | Associated intent ID | -> `intent_id` of INTENT_ANNOUNCE |
| `target` | string | R | Resource being modified | |
| `op_kind` | string | R | Change type | |
| `state_ref_before` | string | R | State reference before the change (format determined by the session's `state_ref_format`) | |
| `state_ref_after` | string | R | State reference after the change | |
| `change_ref` | string | O | Reference to the change content | |
| `summary` | string | O | Human-readable summary | |

**Key logic**: If the receiver's local state does not match `state_ref_before`, it SHOULD mark the operation as `causally_unverifiable` and not base conflict judgments on this operation.

---

### 3.11 OP_REJECT

Rejects a proposed operation.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `op_id` | string | R | ID of the rejected operation | -> `op_id` of OP_PROPOSE |
| `reason` | string | R | Rejection reason (e.g., `policy_violation` / `intent_terminated` / `participant_unavailable` / `frozen_scope_fallback`) | |

---

### 3.12 OP_SUPERSEDE

Replaces a previously committed operation with a new one.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `op_id` | string | R | New operation ID | |
| `supersedes_op_id` | string | R | ID of the operation being superseded | -> Must be an operation in COMMITTED state |
| `intent_id` | string | O | Associated intent ID | -> `intent_id` of INTENT_ANNOUNCE |
| `target` | string | R | Target resource | |
| `reason` | string | O | Reason for superseding | |

---

### 3.13 CONFLICT_REPORT

Publishes a structured conflict determination.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `conflict_id` | string | R | Unique conflict identifier | Referenced by CONFLICT_ACK/ESCALATE/RESOLUTION |
| `related_intents` | string[] | O | List of related intent IDs. Default: `[]` | -> `intent_id` of INTENT_ANNOUNCE |
| `related_ops` | string[] | O | List of related operation IDs. Default: `[]` | -> `op_id` of OP_PROPOSE/OP_COMMIT |
| `category` | string | R | Conflict category | -> [Conflict Category Enum](#65-conflict-category) |
| `severity` | string | R | Severity level | -> [Severity Enum](#66-severity) |
| `basis` | Basis | R | Detection basis | -> [Basis](#19-basis-conflict-detection-basis) |
| `based_on_watermark` | Watermark | R | Causal state at the time of determination | -> [Watermark](#14-watermark-causal-watermark) |
| `description` | string | R | Human-readable description | |
| `suggested_action` | string | O | Suggested next step | |

**Constraint**: At least one of `related_intents` and `related_ops` must be non-empty.

---

### 3.14 CONFLICT_ACK

Acknowledges receipt of a conflict report.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `conflict_id` | string | R | ID of the acknowledged conflict | -> `conflict_id` of CONFLICT_REPORT |
| `ack_type` | string | R | Enum: `seen` / `accepted` / `disputed` | |

---

### 3.15 CONFLICT_ESCALATE

Escalates a conflict to a higher-authority resolver.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `conflict_id` | string | R | ID of the escalated conflict | -> `conflict_id` of CONFLICT_REPORT |
| `escalate_to` | string | R | Principal ID of the escalation target | -> [Principal](#11-principal-participant-identity), typically an owner/arbiter |
| `reason` | string | R | Reason for escalation | |
| `context` | string | O | Additional context for the resolver | |

---

### 3.16 RESOLUTION

Makes a ruling on a conflict.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `resolution_id` | string | R | Unique resolution identifier | |
| `conflict_id` | string | R | ID of the conflict being resolved | -> `conflict_id` of CONFLICT_REPORT |
| `decision` | string | R | Resolution type | -> [Decision Enum](#67-decision) |
| `outcome` | Outcome | O | Structured result | -> [Outcome](#110-outcome-resolution-outcome) |
| `rationale` | string | R | Human-readable rationale for the ruling | |

**Envelope requirement**: MUST include `watermark`. Under Authenticated/Verified profiles, a RESOLUTION missing a watermark will be rejected.

**Concurrent resolution rules** (Section 18.4): For multiple RESOLUTIONs with the same `conflict_id`, the coordinator MUST first filter for "legitimate resolvers of the current authority phase," then accept only the first valid resolution among them (by coordinator receipt order). After escalation to `ESCALATED`, the owner no longer inherently retains resolution authority; priority goes to the `escalate_to` target / arbiter explicitly authorized by session policy / coordinator system resolution.

---

### 3.17 PROTOCOL_ERROR

Protocol-level signaling error.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `error_code` | string | R | Error code | -> [Error Code Enum](#68-error-code) |
| `refers_to` | string | O | `message_id` of the message that triggered the error | -> `message_id` of Message Envelope |
| `description` | string | R | Human-readable error description | |

---

### 3.18 SESSION_CLOSE

Closes a session. Only the coordinator may send this.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `reason` | string | R | Enum: `completed` / `timeout` / `policy` / `coordinator_shutdown` / `manual` | |
| `final_lamport_clock` | integer | R | Final Lamport clock value of the session | -> [Watermark](#14-watermark-causal-watermark) |
| `summary` | object | O | Session completion summary (Section 9.6.2) | |
| `active_intents_disposition` | string | O | How to handle remaining active intents. Enum: `withdraw_all` / `expire_all`. Default: `withdraw_all` | |
| `transcript_ref` | string | O | Exported session transcript URI or reference (Section 9.6.3) | |

**Side effects**: Upon receipt, participants MUST stop sending business messages (except `GOODBYE`). Subsequent messages receive a `SESSION_CLOSED` error. Before closing, the coordinator SHOULD persist a final state snapshot.

---

### 3.19 COORDINATOR_STATUS

Coordinator heartbeat and status broadcast, serving as both a coordinator liveness signal and a foundation for failure recovery.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `event` | string | R | Enum: `heartbeat` / `recovered` / `handover` / `assumed` / `authorization` / `backend_alert` | |
| `coordinator_id` | string | R | Principal ID of the coordinator sending this message | -> [Principal](#11-principal-participant-identity) |
| `session_health` | string | R | Enum: `healthy` / `degraded` / `recovering` | |
| `active_participants` | integer | O | Current number of available participants | |
| `open_conflicts` | integer | O | Number of unresolved conflicts | |
| `snapshot_lamport_clock` | integer | O | Lamport clock value of the latest persisted snapshot | -> [Watermark](#14-watermark-causal-watermark) |
| `successor_coordinator_id` | string | C | Required when `event` = `handover`: principal ID of the successor | -> [Principal](#11-principal-participant-identity) |
| `next_coordinator_epoch` | integer | C | Required when `event` = `handover`: epoch the successor will use | |
| `authorized_op_id` | string | C | Required when `event` = `authorization`: the authorized operation ID | |
| `authorized_batch_id` | string | O | Optional when `event` = `authorization`: batch ID the operation belongs to | |
| `authorized_by` | string | C | Required when `event` = `authorization`: principal ID of the authorizer | -> [Principal](#11-principal-participant-identity) |
| `affected_principal` | string | O | When `event` = `backend_alert`: the affected principal ID | -> [Principal](#11-principal-participant-identity) |
| `backend_detail` | object | O | When `event` = `backend_alert`: detailed backend status information | |

**Frequency**: MUST be sent at least every `heartbeat_interval_sec`. Participants that receive no messages for `2 x heartbeat_interval_sec` -> declare coordinator unavailable (Section 8.1.1.1).

**Envelope requirements**:
- The Message Envelope of all `COORDINATOR_STATUS` messages MUST include `coordinator_epoch`
- `COORDINATOR_STATUS` SHOULD carry a Lamport watermark; when two coordinators claim the same epoch, the watermark serves as a tie-breaker

**Event details**:
- `recovered`: Participants SHOULD re-send `HELLO`; if the local process has not restarted, they SHOULD retain the original `sender_instance_id` and local Lamport counter
- `handover`: Must include both `successor_coordinator_id` and `next_coordinator_epoch`
- `assumed`: Indicates the new coordinator has taken over at the declared epoch and can accept new `HELLO` messages
- `authorization`: Under `pre_commit` mode, the coordinator authorizes a proposed operation for execution. Upon receipt, the proposer MAY execute the mutation and issue a completion declaration. Must include `authorized_op_id` and `authorized_by`; if the operation belongs to a batch, also includes `authorized_batch_id`
- `backend_alert`: An AI model backend failure or switch has occurred. Must include `affected_principal` and `backend_detail`

**Split-brain protection**: If a participant receives coordinator-authored messages from two different coordinators within the same session, it MUST first compare `coordinator_epoch`, rejecting messages from the lower epoch; if both epochs are equal, compare Lamport watermarks, rejecting messages from the coordinator with the lower Lamport value, and SHOULD send `PROTOCOL_ERROR` (`error_code`: `COORDINATOR_CONFLICT`) to both.

---

### 3.20 OP_BATCH_COMMIT

Multi-target batch operation. Packages multiple OP_COMMIT-style changes into a single logical batch.

| Field | Type | Required | Description | Reference |
|-------|------|----------|-------------|-----------|
| `batch_id` | string | R | Unique batch identifier | |
| `intent_id` | string | O (Governance: R) | Associated intent ID | -> `intent_id` of INTENT_ANNOUNCE |
| `atomicity` | string | R | Enum: `all_or_nothing` / `best_effort` | |
| `operations` | object[] | R | List of operations; see structure below | |
| `summary` | string | O | Human-readable batch summary | |

**operations[] item structure**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `op_id` | string | R | Unique operation identifier |
| `target` | string | R | Target resource |
| `op_kind` | string | R | Change type |
| `state_ref_before` | string | R | State reference before change |
| `state_ref_after` | string | R | State reference after change |
| `change_ref` | string | O | Change content reference |

**Batch semantics**: `OP_BATCH_COMMIT` is treated as a single logical unit for conflict detection / governance; Scope = union of all targets. In `all_or_nothing` mode, any single operation failure causes the entire batch to fail; in `best_effort` mode, each entry has an independent lifecycle and can partially succeed.

**Pre-commit model**: Upon receipt, the coordinator first performs scope checking, conflict detection, and governance validation; explicit authorization follows before participants can execute; authorization itself does not equate to the batch being `COMMITTED`; after execution completes, a second `OP_BATCH_COMMIT` with the same `batch_id` must be sent as a completion declaration.
**Pre-commit disambiguation**: The coordinator distinguishes between an initial request and a completion declaration by checking whether the same `batch_id` already exists. If `batch_id` does not exist -> initial request, each entry enters `PROPOSED`. If `batch_id` is already registered and authorized -> completion declaration, each authorized entry transitions to `COMMITTED`. This logic is consistent with the pre-commit disambiguation rules for `OP_COMMIT`.
**Post-commit model**: The participant has already executed all changes; OP_BATCH_COMMIT serves as a post-hoc declaration.

---

## 4. Entity Relationship Diagram

The diagram below shows the reference relationships between all core entities. Arrows indicate "references/associates with."

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              SESSION                                     │
│  session_id, security_profile, governance_policy, liveness_policy        │
│                                                                          │
│  ┌──────────┐   SESSION_INFO    ┌─────────────┐                        │
│  │Coordinator│ ────────────────→ │ Participant  │                        │
│  │ (service) │ ←──── HELLO ──── │ (Principal)  │                        │
│  └─────┬─────┘                  └──────┬───────┘                        │
│        │                               │                                 │
└────────┼───────────────────────────────┼─────────────────────────────────┘
         │ Manages/executes              │ Sends
         ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           INTENT LAYER                                   │
│                                                                          │
│  INTENT_ANNOUNCE ──┐                                                    │
│    intent_id ◄─────┼──── Referenced by:                                 │
│    scope ───────────┼──→ Scope object                                   │
│    ttl_sec          │    (input for conflict detection)                  │
│                     │                                                    │
│  INTENT_UPDATE ─────┤ intent_id → references INTENT_ANNOUNCE            │
│  INTENT_WITHDRAW ───┤ intent_id → references INTENT_ANNOUNCE            │
│  INTENT_CLAIM ──────┘ original_intent_id → references SUSPENDED intent  │
│                       new_intent_id → creates new intent                │
│                       original_principal_id → references Principal       │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ intent_id
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         OPERATION LAYER                                  │
│                                                                          │
│  OP_PROPOSE ────┐                                                       │
│    op_id ◄──────┼──── Referenced by:                                    │
│    intent_id ───┼──→ INTENT_ANNOUNCE (optional; required under Gov.)    │
│    target       │                                                        │
│                 │                                                        │
│  OP_COMMIT ─────┤ op_id, intent_id → same as above                     │
│    state_ref_before ──→ State before change (format per session)        │
│    state_ref_after ───→ State after change                              │
│                 │                                                        │
│  OP_REJECT ─────┤ op_id → references OP_PROPOSE                        │
│  OP_SUPERSEDE ──┘ supersedes_op_id → references COMMITTED operation     │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ op_id, intent_id
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         CONFLICT LAYER                                   │
│                                                                          │
│  CONFLICT_REPORT ──┐                                                    │
│    conflict_id ◄───┼──── Referenced by:                                 │
│    related_intents ┼──→ intent_id of INTENT_ANNOUNCE (array)            │
│    related_ops ────┼──→ op_id of OP_PROPOSE/OP_COMMIT (array)           │
│    basis ──────────┼──→ Basis object                                    │
│    based_on_watermark → Watermark object                                │
│                    │                                                     │
│  CONFLICT_ACK ─────┤ conflict_id → references CONFLICT_REPORT          │
│  CONFLICT_ESCALATE ┤ conflict_id → references CONFLICT_REPORT          │
│                    │ escalate_to → references Principal                  │
└────────────────────┼─────────────────────────────────────────────────────┘
                     │ conflict_id
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        GOVERNANCE LAYER                                  │
│                                                                          │
│  RESOLUTION                                                              │
│    resolution_id                                                         │
│    conflict_id ────→ conflict_id of CONFLICT_REPORT                     │
│    outcome ────────→ Outcome object                                     │
│      accepted[] ──→ intent_id / op_id                                   │
│      rejected[] ──→ intent_id / op_id                                   │
│      merged[] ────→ intent_id / op_id                                   │
│      rollback ────→ Compensating OP_COMMIT reference or "not_required"  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Key Reference Chain Summary

| Source Field | -> Target Field | Relationship |
|-------------|-----------------|--------------|
| OP_PROPOSE.`intent_id` | -> INTENT_ANNOUNCE.`intent_id` | Which intent the operation belongs to |
| OP_COMMIT.`intent_id` | -> INTENT_ANNOUNCE.`intent_id` | Same as above |
| OP_REJECT.`op_id` | -> OP_PROPOSE.`op_id` | Which proposal is rejected |
| OP_SUPERSEDE.`supersedes_op_id` | -> OP_COMMIT.`op_id` | Which committed operation is superseded |
| CONFLICT_REPORT.`related_intents[]` | -> INTENT_ANNOUNCE.`intent_id` | Which intents the conflict involves |
| CONFLICT_REPORT.`related_ops[]` | -> OP_PROPOSE/OP_COMMIT.`op_id` | Which operations the conflict involves |
| CONFLICT_ACK.`conflict_id` | -> CONFLICT_REPORT.`conflict_id` | Which conflict is acknowledged |
| CONFLICT_ESCALATE.`conflict_id` | -> CONFLICT_REPORT.`conflict_id` | Which conflict is escalated |
| CONFLICT_ESCALATE.`escalate_to` | -> Principal.`principal_id` | Who the conflict is escalated to |
| RESOLUTION.`conflict_id` | -> CONFLICT_REPORT.`conflict_id` | Which conflict is resolved |
| RESOLUTION.`outcome.accepted/rejected[]` | -> `intent_id` or `op_id` | Entities involved in the resolution outcome |
| INTENT_CLAIM.`original_intent_id` | -> INTENT_ANNOUNCE.`intent_id` | Which suspended intent is being claimed |
| INTENT_CLAIM.`original_principal_id` | -> Principal.`principal_id` | Original intent owner |
| INTENT_CLAIM_STATUS.`claim_id` | -> INTENT_CLAIM.`claim_id` | Which claim is being disposed |
| INTENT_CLAIM_STATUS.`original_intent_id` | -> INTENT_ANNOUNCE.`intent_id` | The suspended intent that was claimed |
| INTENT_CLAIM_STATUS.`new_intent_id` | -> INTENT_ANNOUNCE.`intent_id` | New intent activated after claim approval |
| INTENT_ANNOUNCE.`parent_intent_id` | -> INTENT_ANNOUNCE.`intent_id` | Intent hierarchical relationship |
| INTENT_ANNOUNCE.`supersedes_intent_id` | -> INTENT_ANNOUNCE.`intent_id` | Intent supersession relationship |
| OP_BATCH_COMMIT.`intent_id` | -> INTENT_ANNOUNCE.`intent_id` | Which intent the batch operation belongs to |
| OP_BATCH_COMMIT.`operations[].op_id` | -> Unique identifier of each operation | Individual operations within the batch |
| SESSION_CLOSE.`final_lamport_clock` | -> Watermark (lamport) | Session's final Lamport clock value |
| COORDINATOR_STATUS.`coordinator_id` | -> Principal.`principal_id` | Identity of the sending coordinator |
| COORDINATOR_STATUS.`successor_coordinator_id` | -> Principal.`principal_id` | Successor during handover |
| COORDINATOR_STATUS.`authorized_op_id` | -> OP_PROPOSE.`op_id` | Operation authorized in an authorization event |
| COORDINATOR_STATUS.`authorized_by` | -> Principal.`principal_id` | Authorizer in an authorization event |
| COORDINATOR_STATUS.`snapshot_lamport_clock` | -> Watermark (lamport) | Causal watermark at snapshot time |
| HEARTBEAT.`active_intent_id` | -> INTENT_ANNOUNCE.`intent_id` | Currently active intent |
| GOODBYE.`active_intents[]` | -> INTENT_ANNOUNCE.`intent_id` | Active intents at departure |
| Message Envelope.`in_reply_to` | -> Message Envelope.`message_id` | Message reply chain |

---

## 5. State Machines

### 5.1 Intent State Machine

```text
DRAFT -> ANNOUNCED -> ACTIVE -> SUPERSEDED
DRAFT -> ANNOUNCED -> ACTIVE -> EXPIRED
DRAFT -> ANNOUNCED -> WITHDRAWN
ACTIVE -> SUSPENDED -> ACTIVE           (participant reconnects)
ACTIVE -> SUSPENDED -> TRANSFERRED      (intent claimed by another participant)
ACTIVE -> SUSPENDED                     (owner departs with intent_disposition: transfer)
```

| Path | Description |
|------|-------------|
| DRAFT -> ANNOUNCED -> ACTIVE | `DRAFT` / `ANNOUNCED` are conceptual phases for understanding; the canonical state machine enters `ACTIVE` after the participant successfully sends `INTENT_ANNOUNCE` |
| ACTIVE -> EXPIRED / WITHDRAWN / SUPERSEDED | When an intent enters a terminal state, it triggers the Intent Expiry Cascade |
| ACTIVE -> SUSPENDED -> ACTIVE | After the owner recovers, FROZEN operations referencing it are restored to PROPOSED |
| ACTIVE -> SUSPENDED -> TRANSFERRED | After a claim is approved, the original intent is closed and the new intent is activated |

**Canonical state transition table** (Section 15.6.1, authoritative reference):

| # | From State | To State | Trigger Message/Event | Guard Condition | Action |
|---|-----------|----------|----------------------|----------------|--------|
| 1 | (none) | ACTIVE | `INTENT_ANNOUNCE` received | Sender is a registered participant | Register intent, start TTL timer |
| 2 | ACTIVE | ACTIVE | `INTENT_UPDATE` received | Sender = intent owner | Update fields, optionally reset TTL |
| 3 | ACTIVE | WITHDRAWN | `INTENT_WITHDRAW` received | Sender = intent owner | Trigger Expiry Cascade |
| 4 | ACTIVE | EXPIRED | TTL expired | Coordinator wall-clock check | Trigger Expiry Cascade |
| 5 | ACTIVE | SUPERSEDED | `INTENT_ANNOUNCE` with `supersedes_intent_id` | New intent from same owner | Trigger Expiry Cascade |
| 6 | ACTIVE | SUSPENDED | Owner unavailability detected | Section 14.7.1 | Freeze PROPOSED operations referencing it; retain scope for conflict detection |
| 6b | ACTIVE | SUSPENDED | Owner departs with `intent_disposition`: `transfer` | GOODBYE from owner (§14.4) | Freeze referencing operations; intent becomes claimable via INTENT_CLAIM |
| 7 | SUSPENDED | ACTIVE | Owner reconnects (`HELLO` or `HEARTBEAT` resumes) | Original owner re-authenticated | Unfreeze referencing operations; notify of changes during offline period |
| 8 | SUSPENDED | TRANSFERRED | `INTENT_CLAIM_STATUS` received (`decision = approved`) | Claim approved per governance rules | Original intent closed; new intent created as ACTIVE |
| 9 | SUSPENDED | EXPIRED | TTL expired while suspended | Coordinator wall-clock check | Trigger Expiry Cascade |

**Supplement**: `INTENT_CLAIM_STATUS(rejected)` does not change the original intent's `SUSPENDED` state; `INTENT_CLAIM_STATUS(withdrawn)` returns the original intent to `ACTIVE`.

---

### 5.2 Operation State Machine

```
                When INTENT is active
   ┌────────────────────────────────────────┐
   │                                        │
   │  ┌──────────────┐    OP_COMMIT    ┌──────────────┐    OP_SUPERSEDE   ┌──────────────┐
   │  │   PROPOSED   │ ─────────────→ │  COMMITTED   │ ────────────────→│  SUPERSEDED  │
   │  └──┬──┬──┬─────┘                └──────────────┘                   └──────────────┘
   │     │  │  │
   │     │  │  │  OP_REJECT / intent_terminated / frozen_scope_fallback
   │     │  │  └──────────────────────────────────────────→ ┌──────────────┐
   │     │  │                                                │   REJECTED   │
   │     │  │                                                └──────────────┘
   │     │  │  Sender unavailable
   │     │  └─────────────────────────────────────────────→ ┌──────────────┐
   │     │                                                   │  ABANDONED   │
   │     │  Referenced intent enters SUSPENDED                └──────────────┘
   │     └────────────────────────────────────────────────→ ┌──────────────┐
   │                                                        │   FROZEN     │──→ PROPOSED (intent recovers)
   │                                                        └──────┬───────┘
   │                                                               │ Intent terminal state
   │                                                               ▼
   │                                                        ┌──────────────┐
   │                                                        │   REJECTED   │
   └────────────────────────────────────────────────────────└──────────────┘
```

| Transition | Trigger Condition |
|-----------|-------------------|
| PROPOSED -> COMMITTED | Change has been applied to shared state |
| PROPOSED -> REJECTED | Reviewer rejects / referenced intent enters `EXPIRED` / `WITHDRAWN` / `SUPERSEDED` / `TRANSFERRED` / frozen scope Phase 3 fallback |
| PROPOSED -> ABANDONED | Sender declared unavailable |
| PROPOSED -> FROZEN | Referenced intent enters SUSPENDED |
| FROZEN -> PROPOSED | Referenced intent recovers to ACTIVE |
| FROZEN -> REJECTED | Referenced intent transitions from SUSPENDED to `EXPIRED` / `WITHDRAWN` / `SUPERSEDED` / `TRANSFERRED` |
| COMMITTED -> SUPERSEDED | Superseded by OP_SUPERSEDE |

**Canonical state transition table** (Section 16.6.1, authoritative reference):

| # | From State | To State | Trigger Message/Event | Guard Condition | Action |
|---|-----------|----------|----------------------|----------------|--------|
| 1 | (none) | PROPOSED | OP_PROPOSE | Sender registered; referenced intent (if any) is valid | Register operation |
| 2 | (none) | COMMITTED | OP_COMMIT (post_commit) | Sender registered; state_refs valid | Record state change |
| 3 | (none) | PROPOSED | OP_COMMIT (pre_commit, legacy path) | New `op_id`; treated only as a pending authorization request | Register pending authorization operation |
| 4 | PROPOSED | PROPOSED | Coordinator authorization (pre_commit) | Scope check passed; no blocking conflicts | Record authorization and notify participant to execute |
| 5 | PROPOSED | COMMITTED | OP_COMMIT (pre_commit, completion declaration) | Proposal authorized and change applied | Record state_ref_after |
| 6 | PROPOSED | REJECTED | OP_REJECT / referenced intent enters `EXPIRED` / `WITHDRAWN` / `SUPERSEDED` / `TRANSFERRED` / frozen scope Phase 3 fallback | | Notify sender |
| 7 | PROPOSED | ABANDONED | Sender unavailable | Heartbeat timeout | |
| 8 | PROPOSED | FROZEN | Referenced intent enters SUSPENDED | | |
| 9 | FROZEN | PROPOSED | Referenced intent recovers to ACTIVE | | |
| 10 | FROZEN | REJECTED | Referenced intent transitions from SUSPENDED to `EXPIRED` / `WITHDRAWN` / `SUPERSEDED` / `TRANSFERRED` | | |
| 11 | COMMITTED -> SUPERSEDED | OP_SUPERSEDE | Superseded operation must be in COMMITTED state | Record supersession chain |
| 12 | (none) | per-entry | OP_BATCH_COMMIT | post_commit: process directly per `atomicity`; pre_commit: initial submission enters PROPOSED, send same `batch_id` again after authorization as completion declaration | scope = union of targets; batch treated as single logical unit for conflict detection / governance |

**Terminology alignment**: `REJECTED` / `ABANDONED` / `SUPERSEDED` are terminal states for operations; `COMMITTED` is a stable state, not a terminal state. For session lifecycle purposes, `COMMITTED` / `REJECTED` / `ABANDONED` / `SUPERSEDED` are collectively called **settled**.

---

### 5.3 Conflict State Machine

```text
OPEN -> ACKED -> RESOLVED -> CLOSED
OPEN -> RESOLVED -> CLOSED
OPEN -> ESCALATED -> RESOLVED -> CLOSED
ACKED -> ESCALATED -> RESOLVED -> CLOSED
OPEN / ACKED / ESCALATED -> DISMISSED    (all related entities terminated)
OPEN -> CLOSED                           (Phase 3 policy_override fallback)
```

| Transition | Trigger Condition |
|-----------|-------------------|
| OPEN -> ACKED | `CONFLICT_ACK` received |
| OPEN -> RESOLVED | Legitimate resolver of the current authority phase sends `RESOLUTION` directly |
| OPEN -> ESCALATED | `CONFLICT_ESCALATE` received |
| ACKED -> ESCALATED | `CONFLICT_ESCALATE` received |
| OPEN / ACKED / ESCALATED -> DISMISSED | All related entities terminated (auto-dismiss) |
| ACKED / ESCALATED -> RESOLVED | `RESOLUTION` received |
| OPEN -> CLOSED | Frozen scope Phase 3 fallback triggered; coordinator generates `policy_override` |
| RESOLVED -> CLOSED | Resolution execution completed |

**Auto-dismiss trigger condition**: All `related_intents` are in terminal states (EXPIRED/WITHDRAWN/SUPERSEDED/TRANSFERRED) AND all `related_ops` are in terminal states (REJECTED/ABANDONED/SUPERSEDED).

**Canonical state transition table** (Section 17.8.1, authoritative reference):

| # | From State | To State | Trigger Message/Event | Guard Condition | Action |
|---|-----------|----------|----------------------|----------------|--------|
| 1 | (none) | OPEN | CONFLICT_REPORT | Basis valid; at least one of related_intents/ops is non-empty | Notify all participants |
| 2 | OPEN | ACKED | `CONFLICT_ACK` received (`ack_type: seen` or `accepted`) | Acknowledger is a related participant | Record acknowledgment |
| 3 | OPEN | ESCALATED | `CONFLICT_ESCALATE` received | Escalation target has authority | Notify escalation target |
| 4 | OPEN | RESOLVED | `RESOLUTION` received | Resolver has authority for current authority phase (owner / arbiter / coordinator) | Execute outcome; release frozen scope |
| 5 | OPEN | DISMISSED | All related entities terminated | Auto-dismiss condition met | Coordinator generates system RESOLUTION with `decision: dismissed`; release frozen scope |
| 6 | OPEN | CLOSED | Frozen scope Phase 3 fallback | Phase 2 timeout exceeded | Coordinator generates `policy_override`; execute first-committer-wins by coordinator receipt order |
| 7 | ACKED | ESCALATED | `CONFLICT_ESCALATE` received | Escalation target has authority | Notify escalation target |
| 8 | ACKED | RESOLVED | `RESOLUTION` received | Resolver has authority for current authority phase | Execute outcome; release frozen scope |
| 9 | ACKED | DISMISSED | All related entities terminated | Auto-dismiss condition met | Coordinator generates system RESOLUTION; release frozen scope |
| 10 | ESCALATED | RESOLVED | `RESOLUTION` received | Resolver = `escalate_to`, or arbiter explicitly authorized by session policy, or coordinator system resolution | Execute outcome; release frozen scope |
| 11 | ESCALATED | DISMISSED | All related entities terminated | Auto-dismiss condition met | Coordinator generates system RESOLUTION; release frozen scope |
| 12 | RESOLVED | CLOSED | Resolution execution completed | Outcome actions executed | Archive / audit |

---

### 5.4 Cross-State-Machine Interaction Rules

Defines causal propagation between state machines (introduced in v0.1.4, canonical state transition tables added in v0.1.7).

```
Intent terminal state ────┬──→ Associated PROPOSED operations auto-reject (or reject after grace period)
(EXPIRED/WITHDRAWN/       │
 SUPERSEDED /
 TRANSFERRED)             └──→ If this is the last active related entity of a conflict → Conflict auto-dismiss
                                   └──→ Release frozen scope

Intent SUSPENDED ────────────→ Associated PROPOSED operations → FROZEN

Intent recovers to ACTIVE ──→ Associated FROZEN operations → PROPOSED

Participant unavailable ─────→ Intent → SUSPENDED
                              → Participant's PROPOSED operations → ABANDONED
```

---

## 6. Enum Registry

### 6.1 Roles

| Value | Permissions |
|-------|------------|
| `observer` | Read-only, no decision-making authority |
| `contributor` | Can submit intents and operations |
| `reviewer` | Can approve/reject OP_PROPOSE |
| `owner` | Can resolve conflicts, override contributor operations |
| `arbiter` | Highest resolution authority, can resolve any conflict and override any participant |

### 6.2 Capabilities

| Value | Description |
|-------|-------------|
| `intent.broadcast` | Can send INTENT_ANNOUNCE |
| `intent.update` | Can send INTENT_UPDATE |
| `intent.withdraw` | Can send INTENT_WITHDRAW |
| `intent.claim` | Can send INTENT_CLAIM |
| `op.propose` | Can send OP_PROPOSE |
| `op.commit` | Can send OP_COMMIT |
| `op.reject` | Can send OP_REJECT |
| `op.batch_commit` | Can send OP_BATCH_COMMIT |
| `conflict.report` | Can send CONFLICT_REPORT |
| `conflict.ack` | Can send CONFLICT_ACK |
| `governance.vote` | Can participate in governance voting |
| `governance.override` | Can send override RESOLUTION |
| `causality.vector_clock` | Supports vector_clock watermarks |
| `causality.lamport_clock` | Supports lamport_clock watermarks (MUST support) |
| `semantic.analysis` | Supports semantic conflict detection |

### 6.3 Security Profile

| Value | Authentication | Signing | Auditing | Use Case |
|-------|---------------|---------|----------|----------|
| `open` | None | None | SHOULD | Internal teams / development environments |
| `authenticated` | MUST (OAuth/mTLS/API Key) | SHOULD (MAC or digital signature) | MUST | Cross-team collaboration |
| `verified` | MUST (X.509 certificate chain) | MUST (digital signature) | MUST (tamper-proof logging) | Cross-organization high-risk scenarios |

**Authenticated / Verified enforcement requirements (Section 23.1.2-23.1.5):**
- **Role policy evaluation**: The coordinator must evaluate `requested_roles` from HELLO against the `role_policy`, granting only roles that pass the policy check. `SESSION_INFO.granted_roles` reflects actually granted roles, not requested roles. Under Open profile with no policy, roles are granted as-is; under Authenticated/Verified with no policy, since the policy is a MUST requirement, `AUTHORIZATION_FAILED` is returned to reject joining (no longer falls back to `["participant"]`). `max_count` constraint counts exclude the principal currently joining (to avoid rejecting rejoins).
- **Replay protection**: The coordinator must reject duplicate `message_id` values (returning `REPLAY_DETECTED`). Additionally, it should check message timestamp drift: deviations exceeding `replay_window` (RECOMMENDED: 5 minutes) should also be rejected. Protection state must persist across coordinator recovery (via the `anti_replay` checkpoint in snapshots).

### 6.4 Compliance Profile

| Value | Required Message Types | Additional Requirements |
|-------|----------------------|------------------------|
| `core` | HELLO, SESSION_INFO, SESSION_CLOSE, COORDINATOR_STATUS, GOODBYE, HEARTBEAT, INTENT_ANNOUNCE, OP_COMMIT, OP_BATCH_COMMIT, CONFLICT_REPORT, RESOLUTION, PROTOCOL_ERROR | Lamport clock rules, consistency model semantics; sessions only allow `post_commit` |
| `governance` | core + INTENT_UPDATE, INTENT_WITHDRAW, INTENT_CLAIM, INTENT_CLAIM_STATUS, OP_PROPOSE, OP_REJECT, OP_SUPERSEDE, CONFLICT_ACK, CONFLICT_ESCALATE | Must designate an arbiter; intent-before-action is MUST; `pre_commit` can only be enabled under this profile; progressive degradation |
| `semantic` | governance + semantic conflict reporting | Supports basis.kind = model_inference |

### 6.5 Conflict Category

| Value | Description |
|-------|-------------|
| `scope_overlap` | Two intents/operations have overlapping scopes |
| `concurrent_write` | Concurrent writes to the same resource |
| `semantic_goal_conflict` | Semantic-level goal conflict |
| `assumption_contradiction` | Contradiction between assumptions |
| `policy_violation` | Violation of session policy |
| `authority_conflict` | Authority conflict |
| `dependency_breakage` | Dependency relationship broken |
| `resource_contention` | Resource contention |

### 6.6 Severity

`info` < `low` < `medium` < `high` < `critical`

### 6.7 Decision

| Value | Description |
|-------|-------------|
| `approved` | Approved |
| `rejected` | Rejected |
| `dismissed` | Dismissed (conflict deemed invalid or obsolete) |
| `human_override` | Human override |
| `policy_override` | Policy override |
| `merged` | Merged resolution |

### 6.8 Error Code

| Value | Description | Trigger Scenario |
|-------|-------------|-----------------|
| `MALFORMED_MESSAGE` | Message format error or missing required fields | Parse failure |
| `UNKNOWN_MESSAGE_TYPE` | Unknown message_type | Unsupported message type |
| `INVALID_REFERENCE` | Referenced a nonexistent session/intent/operation/conflict | Reference target not found |
| `VERSION_MISMATCH` | Incompatible protocol version | Version mismatch in HELLO |
| `CAPABILITY_UNSUPPORTED` | Message requires a capability the receiver does not support | Missing capability |
| `AUTHORIZATION_FAILED` | Sender lacks sufficient permissions | Role mismatch |
| `PARTICIPANT_UNAVAILABLE` | Participant unavailability detected | Heartbeat timeout |
| `RESOLUTION_TIMEOUT` | Conflict resolution timeout | Exceeded resolution_timeout_sec |
| `SCOPE_FROZEN` | Target scope is frozen | Operation/intent hits a frozen region |
| `CLAIM_CONFLICT` | INTENT_CLAIM target already claimed by another | Concurrent claims |
| `COORDINATOR_CONFLICT` | Coordinator conflict (split-brain detected) | Multiple coordinator instances detected |
| `STATE_DIVERGENCE` | State divergence (discovered after recovery) | State inconsistency after snapshot + audit log replay |
| `SESSION_CLOSED` | Session already closed | Business message received after SESSION_CLOSE |
| `CREDENTIAL_REJECTED` | Credential verification failed | Credential in HELLO not accepted |
| `REPLAY_DETECTED` | Duplicate message rejected | Duplicate `message_id` detected under Authenticated/Verified profile (Section 23.1.2) |
| `RESOLUTION_CONFLICT` | Duplicate resolution for the same conflict | Second RESOLUTION received for an already-resolved conflict (Section 18.4) |
| `CAUSAL_GAP` | Causal gap signal | Participant detects missed messages via watermark (Section 12.8) |
| `INTENT_BACKOFF` | Intent backoff cooldown in effect | Premature re-announce of the same scope after conflict-driven rejection (Section 15.3.1) |
| `BACKEND_SWITCH_DENIED` | Backend switch denied | Unable to switch to the requested AI model backend |

---

## 7. Protocol Ordering Constraints

Message ordering rules that must be followed during implementation:

| Constraint | Rule | Behavior on Violation |
|-----------|------|----------------------|
| **Session-first** | HELLO must be the first message a participant sends in a session | Reject or defer processing of non-HELLO messages |
| **Session-info-before-activity** | Participants should not send business messages before receiving SESSION_INFO | Coordinator does not process business messages before SESSION_INFO |
| **Intent-before-operation** | The intent_id referenced by OP_PROPOSE/OP_COMMIT must already exist | May buffer/warn/reject (PROTOCOL_ERROR) |
| **Conflict-before-resolution** | The conflict_id referenced by RESOLUTION must already exist | Reject resolutions for unknown conflicts |
| **Causal consistency** | Messages carrying a watermark should not be considered authoritative statements about events outside the watermark's coverage | Mark out-of-scope judgments as partial |

---

## 8. Version-Specific Protocol Semantics

### v0.1.7 Additions

### 8.1 Consistency Model (Section 7.7)

MPAC adopts a **coordinator-serialized total order**:

- **Normal mode**: The coordinator is the sole ordering authority; all messages are assigned Lamport clock values by the coordinator before broadcast; all participants see the same total message order.
- **Degraded mode** (coordinator unavailable): Participants MUST NOT execute new mutations; they may continue reading and maintaining heartbeats.
- **After recovery**: Consistent state is rebuilt via snapshot + audit log replay. State divergence is resolved through the governance layer.

MPAC **does not provide** linearizability. It provides coordinator-serialized total order + causal context annotations.

### 8.2 Execution Model (Section 7.8)

Sessions MUST declare `execution_model` in SESSION_INFO:

| Model | OP_COMMIT Semantics | Use Case |
|-------|---------------------|----------|
| `pre_commit` | OP_PROPOSE -> coordinator authorization -> participant executes -> OP_COMMIT; authorization itself does not equate to COMMITTED | High-coordination scenarios, pre-write checks; only available under Governance Profile |
| `post_commit` | Participant executes change first -> OP_COMMIT serves as post-hoc declaration | Low-latency scenarios, post-hoc coordination |

**Pre-commit flow**: OP_PROPOSE -> coordinator performs scope check + conflict detection + governance validation -> explicit authorization -> participant executes -> OP_COMMIT.
If an `OP_COMMIT` is sent first for backward compatibility with legacy implementations, it can only be treated as a "pending authorization request" in a `pre_commit` session, entering `PROPOSED` first; it cannot be directly treated as committed.
**Post-commit flow**: Participant executes directly -> OP_COMMIT (with state_ref_before/after) -> coordinator performs post-hoc conflict detection.
**Compatibility default**: If a legacy implementation returns `SESSION_INFO` without `execution_model`, the receiver MUST default to `post_commit`.

### 8.3 Lamport Clock Maintenance Rules (Section 12.7)

7 canonical rules:

| # | Rule | Description |
|---|------|-------------|
| 1 | Initialization | Each sender incarnation starts from 0 when creating a new `sender_instance_id`; retains the existing value when the same process reconnects. Coordinator starts from 0 at session creation, or continues from snapshot value during recovery |
| 2 | Send rule | Increment clock before sending a message (clock++) |
| 3 | Receive rule | Upon receiving a message: clock = max(local, received) + 1 |
| 4 | Coordinator authority | The coordinator's Lamport value is authoritative; participants SHOULD report if their local value exceeds the coordinator's |
| 5 | Snapshot persistence | Coordinator snapshots MUST include the current Lamport value; continue from snapshot value after recovery |
| 6 | Monotonicity | Lamport values for the same sender incarnation (identified by `(principal_id, sender_instance_id)`) MUST be strictly increasing; MUST NOT regress |
| 7 | Reconnection rule | When re-sending `HELLO` after handover/recovery, participants whose process has not restarted MUST retain their `sender_instance_id` and local Lamport counter; if the process has restarted, a new `sender_instance_id` must be generated |

### 8.4 Frozen Scope Three-Phase Progressive Degradation (Section 18.6.2.1)

Replaces the legacy binary strategy of "wait 30 minutes then reject all":

| Phase | Time Window | Behavior |
|-------|-------------|----------|
| Phase 1 | 0 - phase_1_sec (default 60s) | Normal resolution flow: participants negotiate or arbiter resolves |
| Phase 2 | phase_1_sec - (phase_1 + phase_2) (default 60-300s) | Auto-escalation + priority bypass: high-priority intents may bypass the freeze |
| Phase 3 | > (phase_1 + phase_2) (default 300s+) | First-committer-wins: select the first winning commit by coordinator receipt order |

### 8.5 Coordinator Accountability (Section 23.1.3.1, Verified profile only)

- Coordinator MUST sign all outgoing messages
- Participants MUST verify coordinator signatures
- All coordinator operations are recorded in a tamper-proof log
- Independent auditing is supported

### v0.1.8 Additions

#### 8.6 Concurrent RESOLUTION Race Rules (Section 18.4)

Multiple RESOLUTIONs for the same `conflict_id` -> the coordinator first determines "whether the sender is a legitimate resolver of the current authority phase," then accepts only the first valid resolution among them (by coordinator receipt order); subsequent ones are rejected with `RESOLUTION_CONFLICT`.

- After `ESCALATED`, it is no longer "first-come-first-served"; priority switches to `escalate_to` / arbiter explicitly authorized by session policy / coordinator system resolution
- Consistent with the first-claim-wins model of INTENT_CLAIM (Section 14.7.4)
- Ordering basis: coordinator receipt order, not message `ts` timestamp

#### 8.7 Intent Re-Announce Backoff (Section 15.3.1)

Prevents livelock: after an intent is rejected due to a scope overlap conflict, re-announcing the same/overlapping scope SHOULD follow exponential backoff.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `intent_backoff_initial_sec` | `30` | Initial backoff wait time |
| `intent_backoff_max_sec` | `300` | Maximum backoff duration |
| `intent_backoff_multiplier` | `2` | Multiplier for each backoff |

- Coordinator MAY enforce backoff by rejecting premature re-announces with `INTENT_BACKOFF`
- **Does not apply to**: Re-announce after TTL expiry, re-announce after voluntary withdraw, announce with a different scope

#### 8.8 Causal Gap Detection and Behavior (Section 12.8)

Behavioral specification when participants detect missed messages via watermarks:

| Behavior | Level | Description |
|----------|-------|-------------|
| Still update Lamport clock | MUST | `counter = max(local, received) + 1` |
| Do not make conflict judgments or resolutions | SHOULD NOT | Judgments based on incomplete causal context may be incorrect |
| Send `CAUSAL_GAP` to coordinator | MAY | Request state synchronization (mechanism is implementation-defined) |
| Continue non-causal-sensitive operations | MAY | E.g., HEARTBEAT, INTENT_UPDATE, etc. |

### v0.1.9-v0.1.12 Additions / Revisions

#### 8.9 Coordinator Epoch Fencing

- All coordinator-authored messages must carry `coordinator_epoch`
- During handover, the successor epoch is explicitly declared via `next_coordinator_epoch`
- Split-brain detection compares epoch first, then uses Lamport watermark as a tie-breaker within the same epoch

#### 8.10 Sender Incarnation and Secure Reconnection

- `sender_instance_id` explicitly distinguishes different processes/restart incarnations of the same principal
- Lamport monotonicity and sender-frontier replay checks are evaluated per `(principal_id, sender_instance_id)`
- After coordinator handover/recovery, participants whose process has not restarted must retain their original `sender_instance_id` and local Lamport counter when re-sending `HELLO`

#### 8.11 Explicit Claim Disposition and Replay Recovery Closure

- New `INTENT_CLAIM_STATUS` makes `approved` / `rejected` / `withdrawn` explicit protocol events
- Successfully claimed original intents enter `TRANSFERRED`
- Replay protection under Authenticated/Verified profiles must persist across coordinator recovery; snapshots need to retain sufficient anti-replay checkpoints

#### 8.12 Execution and Governance Closure

- `pre_commit` now explicitly requires Governance Profile; Core Profile sessions can only use `post_commit`
- In `pre_commit`, coordinator authorization no longer equates to `COMMITTED`; the actual transition to `COMMITTED` still requires the proposer to execute and then send `OP_COMMIT`
- Concurrent `RESOLUTION` changed to "first-resolution-wins within the current authority phase": after escalation, priority goes to `escalate_to` / explicitly authorized arbiter
- Intent terminal state set for conflict auto-dismiss now includes `TRANSFERRED`
- Under Governance Profile, claim approval must record `approved_by`

#### 8.13 Examples and Schema Alignment (v0.1.12)

- All example messages in Section 28 now include `sender.sender_instance_id` and correct `version`
- `SESSION_INFO` payload table adds `identity_issuer` (Optional), consistent with §23.1.4 credential exchange response
- `SESSION_CLOSE` summary example aligned with the detailed structure in §9.6.2
- `COORDINATOR_STATUS` `heartbeat_interval_sec` cross-reference corrected to §14.7.5
- `OP_BATCH_COMMIT` adds pre-commit disambiguation rule: coordinator uses `batch_id` existence to distinguish initial submission vs. completion declaration
- `INTENT_UPDATE` scope expansion triggers coordinator re-check for conflict detection
- `GOODBYE` `transfer` disposition explicitly follows the `SUSPENDED` -> `INTENT_CLAIM` path
- Semantic Profile (§20.3) marked as v0.1.x placeholder

#### 8.14 Backend Health Monitoring (v0.1.13)

- `HELLO` payload adds `backend` field (Optional), declaring the Agent's AI model backend dependency
- `HEARTBEAT` payload adds `backend_health` field (Optional), reporting backend provider health status
- `COORDINATOR_STATUS` `event` enum adds `backend_alert`, used by the coordinator to notify Agents of backend failures or switches
- `COORDINATOR_STATUS` adds `affected_principal` and `backend_detail` fields, providing affected party and detailed information during backend alerts
- `Liveness Policy` adds `backend_health_policy` field (Optional), controlling backend health monitoring and failover strategy
- New error code `BACKEND_SWITCH_DENIED`, indicating inability to switch to the requested AI model backend

---

## 9. Implementation Checklist

Quick reference table for developers implementing MPAC:

**Basics (all profiles):**
- [ ] All messages are wrapped in a Message Envelope with all 8 required fields present
- [ ] All messages include `sender_instance_id` in the `sender` field
- [ ] HELLO is sent as the first message; after receiving SESSION_INFO, validate compatibility
- [ ] SESSION_INFO includes the `execution_model` field (R)
- [ ] All coordinator-authored messages carry `coordinator_epoch`
- [ ] Support `lamport_clock` watermark generation, comparison, and lamport_value fallback
- [ ] Lamport clock follows all 7 maintenance rules (Section 12.7)
- [ ] Enforce strict Lamport monotonicity per `(principal_id, sender_instance_id)`
- [ ] OP_COMMIT includes state_ref_before and state_ref_after
- [ ] Envelopes for OP_COMMIT / CONFLICT_REPORT / RESOLUTION include watermark
- [ ] Scope overlap uses MUST-level algorithms for file_set / entity_set / task_set
- [ ] Intent terminal states trigger auto-reject of associated PROPOSED operations (Section 15.7)
- [ ] Auto-dismiss conflicts when all related entities are terminated (Section 17.9)
- [ ] TTL is determined by coordinator based on received_at + ttl_sec wall-clock
- [ ] RESOLUTION rejecting COMMITTED operations MUST include the rollback field
- [ ] Heartbeat interval <= 30 seconds; unavailability timeout = 90 seconds
- [ ] GOODBYE declares active_intents and intent_disposition
- [ ] Support SESSION_CLOSE and COORDINATOR_STATUS message handling
- [ ] Support OP_BATCH_COMMIT (both all_or_nothing and best_effort modes)

**Execution model:**
- [ ] Core Profile sessions only use `post_commit`
- [ ] Sessions declaring `pre_commit` must also declare Governance Profile
- [ ] Pre-commit: OP_PROPOSE -> coordinator explicit authorization -> execute -> OP_COMMIT
- [ ] Post-commit: execute -> OP_COMMIT (post-hoc declaration)
- [ ] Select the correct flow based on SESSION_INFO.execution_model
- [ ] In `pre_commit`, authorization alone does not transition the operation to `COMMITTED`
- [ ] `OP_BATCH_COMMIT` follows the same execution_model semantics as `OP_COMMIT`

**Frozen scope three-phase degradation:**
- [ ] Phase 1: Normal resolution flow (default 0-60s)
- [ ] Phase 2: Auto-escalation + priority bypass (default 60-300s)
- [ ] Phase 3: First-committer-wins fallback (default 300s+)

**Coordinator failure recovery:**
- [ ] Periodically send COORDINATOR_STATUS and independently persist state snapshots
- [ ] Support snapshot + audit log replay recovery
- [ ] Snapshots retain at minimum `snapshot_version: 2`, `coordinator_epoch`, `lamport_clock`, and `anti_replay` checkpoint
- [ ] After recovery, restore the anti-replay checkpoint first, then accept new post-recovery messages
- [ ] Participants retain `sender_instance_id` and Lamport counter during reconnection without process restart
- [ ] Split-brain detection follows "epoch first, then Lamport tie-break"

**Concurrent resolution, claim disposition, and livelock prevention (v0.1.8+ / v0.1.12):**
- [ ] Coordinator executes first-resolution-wins only within the "legitimate resolvers of the current authority phase" set
- [ ] Support `INTENT_CLAIM_STATUS` and correctly handle `approved` / `rejected` / `withdrawn`
- [ ] `INTENT_CLAIM_STATUS(approved)` transitions the original intent to `TRANSFERRED`
- [ ] Under Governance Profile, `INTENT_CLAIM_STATUS(approved)` must include `approved_by`
- [ ] Intent re-announce backoff: follow exponential backoff for re-announces of the same scope after conflict-driven rejection
- [ ] Causal gap detection: do not emit CONFLICT_REPORT or RESOLUTION during watermark jumps; may send `CAUSAL_GAP`

**v0.1.12 alignment items:**
- [ ] `OP_BATCH_COMMIT` pre-commit disambiguation: coordinator uses `batch_id` existence to distinguish initial submission vs. completion declaration
- [ ] `INTENT_UPDATE` scope expansion triggers overlap re-check
- [ ] `GOODBYE` with `intent_disposition: "transfer"` transitions intents to `SUSPENDED`, making them claimable via `INTENT_CLAIM`
- [ ] `SESSION_INFO` response may optionally include `identity_issuer`

**Security / compliance:**
- [ ] Authenticated profile: credential exchange (Section 23.1.4), identity binding
- [ ] Authenticated / Verified profile: **Role policy evaluation** — `requested_roles` in HELLO must be checked against `role_policy`; `SESSION_INFO.granted_roles` reflects actually granted roles (Section 23.1.5). Without a `role_policy`, return `AUTHORIZATION_FAILED` to reject joining. `max_count` counting excludes the principal currently joining.
- [ ] Authenticated / Verified profile: **Replay protection** — reject duplicate `message_id` (return `REPLAY_DETECTED`); also check message timestamp drift (RECOMMENDED: 5-minute window). Anti-replay checkpoint is persisted to snapshots; continue enforcing the same policy after recovery (Section 23.1.2)
- [ ] Verified profile: coordinator signs all messages, tamper-proof logging, independent auditing
