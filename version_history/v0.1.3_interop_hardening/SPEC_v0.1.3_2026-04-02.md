# MPAC Specification v0.1.3

## 1. Status

This document defines version `0.1.3` of the Multi-Principal Agent Coordination Protocol (`MPAC`).

Status of this document:
- Draft
- Experimental
- Not yet stable for production interoperability
- Intended for reference implementations, research prototypes, and early ecosystem discussion

This version defines the minimal protocol semantics required for multi-human, multi-agent collaboration over shared tasks and shared state.

## 2. Introduction

The Multi-Principal Agent Coordination Protocol (`MPAC`) is an application-layer protocol for coordinating agents that serve **multiple independent principals** — distinct humans, organizations, or stakeholders with potentially conflicting goals — operating within a shared session.

### 2.1 Positioning

Existing protocols address different layers of the agent ecosystem:

- **MCP** (Model Context Protocol) standardizes agent-to-tool communication: how a single agent discovers and invokes tools.
- **A2A** (Agent-to-Agent Protocol) standardizes agent-to-agent communication under a single controlling principal: how one orchestrator delegates tasks to other agents it trusts.

MPAC addresses the layer that neither MCP nor A2A covers: **multi-principal coordination**. When multiple independent stakeholders — each with their own agents acting on their behalf — need to collaborate over shared state, new problems arise that single-principal architectures are not designed to handle:

- **Intent conflict detection**: Two agents, serving different principals, may announce incompatible plans over the same resources.
- **Cross-principal governance**: Decisions about shared resources require authority models that span principal boundaries — not just delegation within a single trust domain.
- **Causal accountability**: When outcomes affect multiple principals, every operation must carry traceable causal context so that responsibility can be attributed across organizational lines.

These are scenarios that A2A does not architecturally support, because A2A assumes a single orchestrating principal with full authority over all participating agents.

### 2.2 What MPAC Standardizes

MPAC standardizes:
- participant identity and presence
- pre-execution intent announcement
- operation proposal and commit semantics
- causal context metadata
- conflict reporting
- governance and resolution workflows

### 2.3 Typical Use Cases

MPAC is designed for settings where multiple agents — serving different principals — may act concurrently, where actions may depend on incomplete information, and where cross-principal accountability and coordination are required.

Typical use cases include:
- collaborative software engineering across team boundaries
- multi-stakeholder document editing and knowledge work
- cross-organizational research workflows
- multi-party planning and orchestration systems
- human-in-the-loop decision systems with competing interests
- family or group coordination where each member has their own agent

MPAC does not define a specific user interface, storage engine, transport protocol, model provider, or execution runtime.

## 3. Design Goals

MPAC has the following goals:

1. Interoperability
Different agent systems should be able to coordinate through a shared message model.

2. Explicit coordination
Agents should announce intent before acting when possible.

3. Causal traceability
Operations, judgments, and conflicts should indicate the causal context they were based on.

4. Structured conflict handling
Conflicts should be represented as first-class protocol objects rather than implicit side effects.

5. Human-governed collaboration
The protocol should support human override, escalation, and policy-based authority.

6. Extensibility
The protocol should allow optional features and implementation-specific extensions without breaking core interoperability.

## 4. Non-Goals

MPAC is not intended to be:

- a transport protocol like TCP or QUIC
- a replacement for CRDTs, OT, or version control systems
- a standard UI protocol
- a standard tool execution protocol
- a single conflict-detection algorithm
- a single security framework
- a single storage format

MPAC defines coordination semantics, not the full underlying runtime.

## 5. Terminology

The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", and "MAY" in this document are to be interpreted as described in RFC 2119 style specifications.

### 5.1 Principal

A principal is an accountable actor participating in a collaboration session.

Principal types include:
- human
- agent
- service

### 5.2 Participant

A participant is a principal currently joined to a session.

### 5.3 Session

A session is a bounded collaboration context in which participants coordinate over shared state.

### 5.4 Intent

An intent is a structured pre-execution declaration of a planned action.

### 5.5 Operation

An operation is a structured mutation proposal or committed change against shared state.

### 5.6 Conflict

A conflict is a structured claim that two or more intents, operations, assumptions, or policies are incompatible or potentially incompatible.

### 5.7 Watermark

A watermark is a causal completeness marker describing what known state a message, judgment, or decision was based on.

### 5.8 Governance

Governance is the authority model that determines who may approve, reject, override, or resolve contested actions.

## 6. Protocol Model

MPAC is an application-layer coordination protocol with five logical layers:

1. Session Layer
Membership, presence, capabilities, and liveness.

2. Intent Layer
Pre-execution coordination via declared goals, scope, and assumptions.

3. Operation Layer
Proposals, commits, rejection, and supersession of mutations.

4. Conflict Layer
Conflict reporting, acknowledgment, escalation, and resolution.

5. Governance Layer
Authority, policy, and final decision-making.

Implementations MAY merge these layers internally, but their externally visible semantics SHOULD remain distinct.

## 7. Shared Principles

### 7.1 Intent Before Action

In sessions using the Governance Profile (Section 20.2), participants MUST announce intent via `INTENT_ANNOUNCE` before issuing `OP_PROPOSE` or `OP_COMMIT`, unless explicitly exempted by session policy. In Core Profile sessions, participants SHOULD announce intent before committing non-trivial operations.

Operations submitted without a corresponding active intent SHOULD be flagged as `uncoordinated` by the session coordinator. Implementations MAY apply lower priority or additional governance scrutiny to uncoordinated operations.

### 7.2 Attributable Actions

Every operation, conflict report, and resolution decision MUST be attributable to a principal.

### 7.3 Causal Context

`OP_COMMIT`, `CONFLICT_REPORT`, and `RESOLUTION` messages MUST include causal context via a watermark in the message envelope. Other message types SHOULD include causal context when available.

### 7.4 Human Override

Implementations SHOULD support governance policies in which a human principal may serve as final arbiter for selected conflict classes.

### 7.5 Transport Independence

MPAC semantics MUST NOT depend on a single transport mechanism.

### 7.6 Algorithm Independence

MPAC conflict objects MUST be interoperable regardless of whether they were produced by deterministic rules, heuristics, model inference, or human review.

## 8. Transport Binding

MPAC is transport-independent.

Possible transport bindings include:
- WebSocket
- HTTP request/response with polling
- message queue
- event bus
- local shared storage
- peer-to-peer messaging
- append-only logs

Transport responsibilities include:
- message delivery
- ordering guarantees if any
- retry behavior
- authentication channels if any

MPAC responsibilities include:
- message meaning
- state transitions
- causal metadata
- governance semantics

Transport is responsible for delivery.
MPAC is responsible for meaning.

### 8.1 Session Coordinator

Many MPAC features — including heartbeat-based unavailability detection (Section 14.4), sender identity binding (Section 23.3), frozen scope enforcement (Section 18.6), and tamper-evident logging (Section 23.1.3) — require a component with a unified view of session state and the authority to enforce protocol-level decisions.

MPAC defines this component as the **session coordinator**. A session coordinator is a `service`-type principal responsible for:
- maintaining the authoritative session state (participant roster, intent registry, conflict state)
- enforcing message ordering constraints (Section 8.2)
- performing liveness detection and unavailability transitions (Section 14.4)
- validating sender identity binding in Authenticated and Verified profiles (Section 23.1)
- maintaining audit logs

Every session MUST have exactly one logical session coordinator. The coordinator MAY be implemented as a dedicated server, a message broker, or a designated participant, but its responsibilities MUST NOT be split across multiple independent components without a consensus mechanism.

In deployments where a centralized coordinator is unavailable, implementations MUST provide an equivalent distributed mechanism (e.g., consensus protocol) that satisfies the same guarantees. The specifics of such mechanisms are outside the scope of MPAC.

Note: MPAC remains transport-independent. The session coordinator is a logical role, not a transport requirement. It MAY be co-located with a WebSocket server, message broker, or any other infrastructure component.

### 8.2 Protocol-Level Ordering Constraints

While message delivery order is a transport concern, MPAC imposes the following semantic ordering constraints that implementations MUST respect regardless of transport:

1. **Session-first**: A participant MUST send `HELLO` before any other message type in a session. Receivers SHOULD reject or defer non-`HELLO` messages from unknown participants.

2. **Intent-before-operation**: An `OP_PROPOSE` or `OP_COMMIT` that references an `intent_id` SHOULD only be processed after the corresponding `INTENT_ANNOUNCE` has been received. If the referenced intent is unknown, the receiver MAY:
   - buffer the operation until the intent arrives
   - process it with a warning
   - reject it with a `PROTOCOL_ERROR`

3. **Conflict-before-resolution**: A `RESOLUTION` MUST reference a previously reported `conflict_id`. Receivers SHOULD reject resolutions for unknown conflicts.

4. **Causal consistency**: If a message carries a watermark, receivers SHOULD NOT treat it as authoritative about events beyond what the watermark claims to have observed.

These constraints define the semantic contract. Implementations are free to enforce them strictly or permissively based on session policy.

## 9. Sessions

### 9.1 Session Definition

A session represents a collaboration boundary.

A session SHOULD define:
- session identifier
- protocol version
- participant set
- shared state reference
- governance policy reference
- supported capabilities
- optional transport binding metadata

### 9.2 Session Creation

MPAC does not mandate a single session creation mechanism. However, implementations MUST support at least one of the following approaches:

1. **Explicit creation**: A principal sends a `SESSION_CREATE` request to a session coordinator or broker, which allocates a `session_id` and returns it.
2. **Implicit creation**: The first `HELLO` message referencing a previously unknown `session_id` causes the receiver to initialize a new session context.
3. **Out-of-band provisioning**: A session is created via external configuration, CLI, or administrative API, and the `session_id` is distributed to participants through a separate channel.

Regardless of the creation method, the resulting session MUST satisfy the requirements in Section 9.3.

### 9.3 Session Discovery

MPAC v0.1 does not define a standard session discovery mechanism.

Implementations MAY support discovery through:
- a session registry or directory service
- a well-known endpoint or broadcast channel
- invitation links or tokens
- out-of-band communication

Future versions MAY define a standard discovery protocol.

### 9.4 Session Requirements

A session MUST have:
- a unique `session_id`
- a declared MPAC protocol version
- at least one governing authority model

A session SHOULD also declare:
- a security profile (Section 23.1); defaults to Open if not specified
- at least one `arbiter`-role participant when multiple `owner`-role principals are present (Section 18.5)
- a liveness policy for unavailability detection (Section 14.4.5); defaults apply if not specified

### 9.5 Shared State

MPAC does not require a particular shared-state model.

Shared state MAY be:
- a file set
- a document graph
- a task graph
- a database snapshot
- a tool state machine
- a simulation state

MPAC messages MUST reference shared state in a way meaningful to participants in the session.

## 10. Participant Identity

Each participant MUST have a stable session-visible identifier.

### 10.1 Principal Object

A principal SHOULD be represented as:

```json
{
  "principal_id": "agent:alice-coder-1",
  "principal_type": "agent",
  "display_name": "Alice Coder",
  "roles": ["contributor"],
  "capabilities": ["intent.broadcast", "op.commit", "conflict.report"]
}
```

### 10.2 Principal Types

Recognized principal types in MPAC v0.1:
- `human`
- `agent`
- `service`

Future versions MAY add additional types.

### 10.3 Roles

Roles are governance-facing labels. Recommended roles:
- `observer`
- `contributor`
- `reviewer`
- `owner`
- `arbiter`

Implementations MAY define additional roles.

## 11. Message Envelope

All MPAC messages MUST be wrapped in a common envelope.

### 11.1 Envelope Structure

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "7c5f3d51-fd2b-4e89-8a5e-55f72dbf32ab",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:alice-coder-1",
    "principal_type": "agent"
  },
  "ts": "2026-03-27T18:00:00Z",
  "watermark": {
    "kind": "vector_clock",
    "value": {
      "alice": 3,
      "bob": 5
    }
  },
  "payload": {}
}
```

### 11.2 Required Envelope Fields

Every MPAC message MUST include:
- `protocol`
- `version`
- `message_type`
- `message_id`
- `session_id`
- `sender`
- `ts`
- `payload`

### 11.3 Optional Envelope Fields

An MPAC message MAY include:
- `watermark`
- `in_reply_to`
- `trace_id`
- `policy_ref`
- `signature`
- `extensions`

### 11.4 Envelope Semantics

- `protocol` MUST be `MPAC`
- `version` MUST identify the MPAC message format version
- `message_id` MUST be unique within practical system scope
- `ts` MUST use RFC 3339 / ISO 8601 UTC timestamps
- `watermark` SHOULD describe the causal state known to the sender at send time

## 12. Watermarks and Causality

### 12.1 Purpose

A watermark expresses what prior state was known when a participant produced:
- an operation
- a conflict report
- a resolution decision
- any other causally sensitive message

### 12.2 Allowed Watermark Kinds

MPAC v0.1 recognizes the following watermark kinds:
- `lamport_clock` **(baseline — MUST support)**
- `vector_clock`
- `causal_frontier`
- `opaque`

### 12.3 Baseline Watermark Kind

All MPAC implementations MUST support `lamport_clock` as the baseline watermark kind. A Lamport clock watermark value is a single non-negative integer. Comparison semantics: if watermark A has value `a` and watermark B has value `b`, then `a < b` implies A happened-before B; `a == b` or incomparable values imply concurrent or indeterminate ordering.

Implementations MAY additionally support other watermark kinds (`vector_clock`, `causal_frontier`, `opaque`). When two participants in a session use different watermark kinds, both MUST be able to fall back to `lamport_clock` for causal comparison. Implementations SHOULD include a `lamport_value` field alongside any non-`lamport_clock` watermark to enable this fallback:

```json
{
  "watermark": {
    "kind": "vector_clock",
    "value": { "alice": 3, "bob": 5 },
    "lamport_value": 8
  }
}
```

### 12.4 Interoperability Rule

If a participant receives a watermark kind it cannot interpret, it MUST fall back to the `lamport_value` field for causal comparison. If `lamport_value` is absent and the kind is uninterpretable, the participant SHOULD treat causally sensitive judgments (conflict detection, resolution validation) as partial and MAY request the sender to re-transmit with a `lamport_clock` watermark.

### 12.5 Conflict Judgment Rule

A `CONFLICT_REPORT` MUST include a `based_on_watermark` field indicating the state frontier on which the judgment relied.

### 12.6 Minimal Requirement

MPAC does not require all implementations to use the same causal algorithm.
MPAC requires only that causally relevant messages carry an explicit causal reference when possible.

## 13. Core Message Types

MPAC v0.1 defines the following core message types:

- `HELLO`
- `HEARTBEAT`
- `GOODBYE`
- `INTENT_ANNOUNCE`
- `INTENT_UPDATE`
- `INTENT_WITHDRAW`
- `INTENT_CLAIM`
- `OP_PROPOSE`
- `OP_COMMIT`
- `OP_REJECT`
- `OP_SUPERSEDE`
- `CONFLICT_REPORT`
- `CONFLICT_ACK`
- `CONFLICT_ESCALATE`
- `RESOLUTION`
- `PROTOCOL_ERROR`

Implementations MAY support a subset, subject to compliance profile rules.

### 13.1 Payload Schema Reference

This section defines the required and optional fields for each message type's payload. Field requirement levels: **R** = required (MUST be present), **O** = optional (MAY be omitted).

#### `HELLO` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `display_name` | string | R | Human-readable participant name |
| `roles` | string[] | R | Requested roles (Section 10.3) |
| `capabilities` | string[] | R | Supported capabilities (Section 19.1) |
| `implementation` | object | O | `{ "name": string, "version": string }` |

#### `HEARTBEAT` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `status` | string | R | One of: `idle`, `working`, `blocked`, `awaiting_review`, `offline` |
| `active_intent_id` | string | O | Currently active intent |
| `summary` | string | O | Human-readable activity summary |

#### `GOODBYE` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `reason` | string | R | One of: `user_exit`, `session_complete`, `error`, `timeout` |
| `active_intents` | string[] | O | List of the departing participant's active intent IDs |
| `intent_disposition` | string | O | One of: `withdraw`, `transfer`, `expire`. Default: `withdraw` |

#### `INTENT_ANNOUNCE` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `intent_id` | string | R | Unique intent identifier |
| `objective` | string | R | Human-readable description of planned work |
| `scope` | Scope object | R | Expected target set (Section 15.2) |
| `assumptions` | string[] | O | Important unstated dependencies. Default: `[]` |
| `priority` | string | O | One of: `low`, `normal`, `high`, `critical`. Default: `normal` |
| `ttl_sec` | integer | O | Time-to-live in wall-clock seconds. Default: `300` |
| `parent_intent_id` | string | O | Parent intent if hierarchically related |
| `supersedes_intent_id` | string | O | Intent this one replaces |

#### `INTENT_UPDATE` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `intent_id` | string | R | Intent to update |
| `objective` | string | O | Updated objective |
| `scope` | Scope object | O | Updated scope |
| `assumptions` | string[] | O | Updated assumptions |
| `ttl_sec` | integer | O | Updated TTL |

At least one field besides `intent_id` SHOULD be present.

#### `INTENT_WITHDRAW` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `intent_id` | string | R | Intent to withdraw |
| `reason` | string | O | Reason for withdrawal |

#### `INTENT_CLAIM` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `claim_id` | string | R | Unique claim identifier |
| `original_intent_id` | string | R | Suspended intent being claimed |
| `original_principal_id` | string | R | Principal who owned the original intent |
| `new_intent_id` | string | R | New intent that will replace the original |
| `objective` | string | R | Objective of the new intent |
| `scope` | Scope object | R | Scope (must be equal to or narrower than original) |
| `justification` | string | O | Reason for claiming |

#### `OP_PROPOSE` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `op_id` | string | R | Unique operation identifier |
| `intent_id` | string | O | Associated intent |
| `target` | string | R | Resource being mutated |
| `op_kind` | string | R | Mutation type (e.g., `replace`, `insert`, `delete`, `patch`) |
| `change_ref` | string | O | Reference to the proposed change content |
| `summary` | string | O | Human-readable summary |

#### `OP_COMMIT` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `op_id` | string | R | Unique operation identifier |
| `intent_id` | string | O | Associated intent (MUST in Governance Profile) |
| `target` | string | R | Resource being mutated |
| `op_kind` | string | R | Mutation type |
| `state_ref_before` | string | R | State reference before mutation |
| `state_ref_after` | string | R | State reference after mutation |
| `change_ref` | string | O | Reference to the change content |
| `summary` | string | O | Human-readable summary |

#### `OP_REJECT` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `op_id` | string | R | Operation being rejected |
| `reason` | string | R | Rejection reason |

#### `OP_SUPERSEDE` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `op_id` | string | R | New operation identifier |
| `supersedes_op_id` | string | R | Previously committed operation being superseded |
| `intent_id` | string | O | Associated intent |
| `target` | string | R | Resource being targeted |
| `reason` | string | O | Reason for supersession |

#### `CONFLICT_REPORT` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `conflict_id` | string | R | Unique conflict identifier |
| `related_intents` | string[] | O | Related intent IDs. Default: `[]` |
| `related_ops` | string[] | O | Related operation IDs. Default: `[]` |
| `category` | string | R | Conflict category (Section 17.5) |
| `severity` | string | R | Severity level (Section 17.6) |
| `basis` | object | R | Detection basis (Section 17.7) |
| `based_on_watermark` | Watermark | R | Causal state when conflict was detected |
| `description` | string | R | Human-readable conflict description |
| `suggested_action` | string | O | Recommended next step |

At least one of `related_intents` or `related_ops` MUST be non-empty.

#### `CONFLICT_ACK` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `conflict_id` | string | R | Conflict being acknowledged |
| `ack_type` | string | R | One of: `seen`, `accepted`, `disputed` |

#### `CONFLICT_ESCALATE` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `conflict_id` | string | R | Conflict being escalated |
| `escalate_to` | string | R | Principal ID of escalation target |
| `reason` | string | R | Reason for escalation |
| `context` | string | O | Additional context for the escalation target |

#### `RESOLUTION` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `resolution_id` | string | R | Unique resolution identifier |
| `conflict_id` | string | R | Conflict being resolved |
| `decision` | string | R | One of: `approved`, `rejected`, `dismissed`, `human_override`, `policy_override`, `merged`, `deferred` |
| `outcome` | Outcome | O | Structured outcome (see below) |
| `rationale` | string | R | Human-readable explanation |

Outcome object:

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `accepted` | string[] | O | Intent/operation IDs accepted |
| `rejected` | string[] | O | Intent/operation IDs rejected |
| `merged` | string[] | O | Intent/operation IDs merged |
| `rollback` | string | O | `"not_required"` or reference to compensating operation |

#### `PROTOCOL_ERROR` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `error_code` | string | R | Error code (Section 22.1) |
| `refers_to` | string | O | `message_id` of the problematic message |
| `description` | string | R | Human-readable error description |

#### Scope Object

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `kind` | string | R | Scope kind (Section 15.2) |
| `resources` | string[] | C | Required when `kind` = `file_set` |
| `pattern` | string | C | Required when `kind` = `resource_path` |
| `task_ids` | string[] | C | Required when `kind` = `task_set` |
| `expression` | string | C | Required when `kind` = `query` |
| `language` | string | C | Required when `kind` = `query` |
| `entities` | string[] | C | Required when `kind` = `entity_set` |
| `canonical_uris` | string[] | O | Canonical resource URIs (Section 15.2.2) |
| `extensions` | object | O | Implementation-specific data |

(**C** = conditionally required, based on `kind` value)

#### Watermark Object

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `kind` | string | R | Watermark kind (Section 12.2) |
| `value` | any | R | Kind-specific value (integer for `lamport_clock`, object for `vector_clock`, string for others) |
| `lamport_value` | integer | O | Lamport clock fallback value. SHOULD be present when `kind` is not `lamport_clock` (Section 12.3) |

## 14. Session Layer Messages

### 14.1 `HELLO`

Purpose:
- join a session
- advertise identity
- advertise capabilities

Payload:

```json
{
  "display_name": "Alice",
  "roles": ["contributor"],
  "capabilities": [
    "intent.broadcast",
    "op.commit",
    "conflict.report"
  ],
  "implementation": {
    "name": "acp-ref-js",
    "version": "0.1.0"
  }
}
```

Semantics:
- a participant MUST send `HELLO` as its first message when entering a session
- a receiver MUST use `HELLO` to register the participant; messages from unregistered participants (other than `HELLO`) MUST be rejected with a `PROTOCOL_ERROR` (`error_code`: `INVALID_REFERENCE`)

### 14.2 `HEARTBEAT`

Purpose:
- maintain liveness
- publish lightweight activity summary

Payload:

```json
{
  "status": "idle",
  "active_intent_id": "intent-123",
  "summary": "reviewing train.py"
}
```

Recommended `status` values:
- `idle`
- `working`
- `blocked`
- `awaiting_review`
- `offline`

Timing guidance:
- participants SHOULD send `HEARTBEAT` at least once every 30 seconds while active in a session
- implementations SHOULD consider a participant as potentially unavailable if no `HEARTBEAT` has been received for 3 consecutive expected intervals (default: 90 seconds)
- sessions MAY override these defaults via session configuration
- a participant whose status is `offline` is exempt from heartbeat timing expectations

### 14.3 `GOODBYE`

Purpose:
- cleanly leave a session

Payload:

```json
{
  "reason": "user_exit",
  "active_intents": ["intent-123"],
  "intent_disposition": "withdraw"
}
```

Semantics:
- a departing participant SHOULD include a list of their active intent identifiers in the `active_intents` field
- the `intent_disposition` field indicates what should happen to active intents upon departure

Recommended `intent_disposition` values:
- `withdraw`: all active intents are implicitly withdrawn (equivalent to sending `INTENT_WITHDRAW` for each)
- `transfer`: active intents are offered for adoption by another participant (requires session coordinator support)
- `expire`: active intents retain their existing TTL and expire naturally

If `intent_disposition` is omitted, implementations SHOULD default to `withdraw`.

In-flight proposed operations (`OP_PROPOSE` without a corresponding `OP_COMMIT` or `OP_REJECT`) from a departing participant SHOULD be treated as abandoned. Implementations MAY automatically reject them or leave them for governance review.

Recommended `reason` values:
- `user_exit`
- `session_complete`
- `error`
- `timeout`

### 14.4 Participant Unavailability and Recovery

When a participant becomes unavailable without sending `GOODBYE` (e.g., crash, network partition, or unresponsive process), the session faces orphaned intents, in-flight proposals, and ambiguous scope locks. This section defines the detection mechanism and required recovery behaviors.

#### 14.4.1 Unavailability Detection

A participant is considered **unavailable** when no `HEARTBEAT` or any other message has been received from them for the duration specified by the session's liveness timeout (default: 90 seconds per Section 14.2). The session coordinator or any participant with governance authority MAY declare a participant unavailable.

When unavailability is detected, implementations SHOULD broadcast a system-level notification to all remaining participants. The recommended format is a `PROTOCOL_ERROR` with `error_code`: `PARTICIPANT_UNAVAILABLE` and the `refers_to` field set to the unavailable participant's last known `message_id`.

#### 14.4.2 Orphaned Intent Handling

When a participant is detected as unavailable, their active intents MUST be transitioned to a `SUSPENDED` state:

1. **SUSPENDED state**: A suspended intent remains visible to all participants but is not actionable — no new `OP_PROPOSE` or `OP_COMMIT` may reference a suspended intent. The scope declared by suspended intents SHOULD still be considered occupied for conflict detection purposes (to prevent silent overwrite of in-progress work).

2. **Transition trigger**: The transition to `SUSPENDED` SHOULD occur automatically upon unavailability detection. Implementations SHOULD generate a synthetic `INTENT_UPDATE` or equivalent audit record marking the state change, attributed to the system or session coordinator rather than the unavailable participant.

3. **Recovery**: If the unavailable participant reconnects (sends a new `HELLO` or resumes `HEARTBEAT`), their suspended intents SHOULD automatically transition back to `ACTIVE`. The participant SHOULD be notified of any state changes that occurred during their absence.

#### 14.4.3 Abandoned Operation Handling

In-flight `OP_PROPOSE` messages from the unavailable participant that have no corresponding `OP_COMMIT` or `OP_REJECT` MUST be marked as `ABANDONED` after the liveness timeout expires:

1. **ABANDONED state**: An abandoned proposal is no longer eligible for commit. It is retained for audit purposes but does not block other operations on the same target.

2. **Automatic marking**: Implementations SHOULD automatically transition orphaned proposals to `ABANDONED` state. This transition SHOULD generate an audit record.

3. **Governance override**: A participant with `owner` or `arbiter` role MAY explicitly reject an orphaned proposal via `OP_REJECT` (with `reason`: `participant_unavailable`) instead of waiting for automatic abandonment, if faster resolution is needed.

#### 14.4.4 `INTENT_CLAIM`

Purpose:
- allow a participant to claim the scope of a suspended intent from an unavailable participant, enabling work to continue

Payload:

```json
{
  "claim_id": "claim-001",
  "original_intent_id": "intent-123",
  "original_principal_id": "agent:alice-coder-1",
  "new_intent_id": "intent-456",
  "objective": "Continue training stability tuning (claimed from unavailable agent)",
  "scope": {
    "kind": "file_set",
    "resources": ["train.py", "config.yaml"]
  },
  "justification": "Original agent unavailable for >90 seconds; work must continue to meet deadline"
}
```

Semantics:
- `INTENT_CLAIM` MUST reference a suspended intent via `original_intent_id`
- the claiming participant SHOULD declare a new `new_intent_id` that inherits or narrows the scope of the original intent
- `INTENT_CLAIM` is subject to governance approval: in sessions using the Governance profile, a participant with `owner` or `arbiter` role MUST approve the claim before the new intent becomes active. In Core profile sessions, the claim is automatically approved after a configurable grace period (default: 30 seconds) if no objection is raised
- upon approval, the original suspended intent transitions to `TRANSFERRED` state and the new intent becomes `ACTIVE`
- if the original participant reconnects before the claim is approved, the claim SHOULD be automatically withdrawn and the original intent restored to `ACTIVE`
- **concurrent claims**: if multiple participants submit `INTENT_CLAIM` for the same suspended intent, the session coordinator MUST accept only the first claim received (first-claim-wins) and reject subsequent claims with a `PROTOCOL_ERROR` (`error_code`: `CLAIM_CONFLICT`). The ordering is determined by the session coordinator's receipt order

#### 14.4.5 Session Policy for Unavailability

Sessions MAY configure unavailability behavior through session policy:

```json
{
  "liveness": {
    "heartbeat_interval_sec": 30,
    "unavailability_timeout_sec": 90,
    "orphaned_intent_action": "suspend",
    "orphaned_proposal_action": "abandon",
    "intent_claim_approval": "governance",
    "intent_claim_grace_period_sec": 30
  }
}
```

## 15. Intent Layer

### 15.1 Intent Model

An intent SHOULD include:
- intent identifier
- objective
- expected scope
- assumptions
- priority
- time-to-live
- optional parent or superseded intent relation

### 15.2 Scope Object

The scope object describes the expected target set of an intent or operation.

A scope MUST include:
- `kind`: the type of scope

Recommended `kind` values:
- `file_set`: a list of file paths (`resources` is an array of strings)
- `resource_path`: a hierarchical resource path or glob pattern (`pattern` is a string)
- `task_set`: a set of task identifiers (`task_ids` is an array of strings)
- `query`: a query expression against shared state (`expression` is a string, `language` identifies the query language)
- `entity_set`: a set of named entities such as database tables, API endpoints, or config keys (`entities` is an array of strings)
- `custom`: an implementation-specific scope kind (contents defined by the implementation under `extensions`)

Implementations MAY define additional scope kinds. Unknown scope kinds SHOULD be treated as opaque but preserved for audit purposes.

### 15.2.1 Scope Overlap Determination

Scope overlap is the foundation of conflict detection. To ensure interoperable conflict judgments, MPAC defines mandatory overlap rules for common scope kinds and a fallback mechanism for others.

#### 15.2.1.1 Mandatory Overlap Rules

For the following scope kinds, implementations MUST use the specified overlap determination algorithm:

**`file_set`**: Two `file_set` scopes overlap if and only if the set intersection of their `resources` arrays is non-empty. Before comparison, resource paths MUST be normalized: leading `./` removed, consecutive `/` collapsed, trailing `/` removed. Comparison is case-sensitive byte-level string matching on the normalized paths.

**`entity_set`**: Two `entity_set` scopes overlap if and only if the set intersection of their `entities` arrays is non-empty. Comparison is case-sensitive exact string matching.

**`task_set`**: Two `task_set` scopes overlap if and only if the set intersection of their `task_ids` arrays is non-empty. Comparison is case-sensitive exact string matching.

#### 15.2.1.2 Best-Effort Overlap Rules

For the following scope kinds, overlap determination is implementation-dependent, but implementations SHOULD apply at least the specified minimum logic:

**`resource_path`**: Implementations SHOULD support at minimum the glob operators `*` (match any sequence within a path segment) and `**` (match any sequence of path segments). Two `resource_path` scopes SHOULD be considered overlapping if either pattern matches any resource that the other pattern also matches.

**`query`** and **`custom`**: Overlap determination for these kinds is outside the scope of MPAC v0.1. Implementations SHOULD treat two scopes of these kinds as potentially overlapping (conservative default) unless canonical URIs (Section 15.2.2) are available to determine otherwise.

#### 15.2.1.3 Cross-Kind Overlap

When two scopes have different `kind` values, implementations MUST NOT assume they are non-overlapping based on kind mismatch alone. Cross-kind overlap MUST be determined via canonical URIs (Section 15.2.2) or the session resource registry (Section 15.2.3). If neither is available, implementations SHOULD treat cross-kind scopes as potentially overlapping when their scope descriptions appear to reference similar resources, and MAY use `semantic_match` (Section 17.7.1) to make this determination.

### 15.2.2 Canonical Resource URIs

Different scope kinds may refer to the same underlying resource using different representations (e.g., `file_set ["src/routes/auth.ts"]` and `entity_set ["api.auth.routes"]`). When scope kinds differ, overlap detection based on kind-specific fields alone will fail to identify true overlaps.

To enable cross-kind overlap detection, scope objects SHOULD include a `canonical_uris` field when the session involves participants using heterogeneous scope kinds. In sessions where all participants use the same scope kind, `canonical_uris` is optional. The field is an array of canonical resource identifiers that the scope covers, independent of representation.

```json
{
  "kind": "file_set",
  "resources": ["src/routes/auth.ts"],
  "canonical_uris": ["resource://myproject/src/routes/auth.ts"]
}
```

```json
{
  "kind": "entity_set",
  "entities": ["api.auth.routes"],
  "canonical_uris": ["resource://myproject/src/routes/auth.ts"]
}
```

When `canonical_uris` is present on two scope objects, overlap detection SHOULD compute the set intersection of their canonical URI arrays. A non-empty intersection indicates scope overlap regardless of differing `kind` values.

URI format requirements:
- canonical URIs SHOULD use the format `resource://{namespace}/{path}`, where `{namespace}` identifies the project, repository, or organizational boundary, and `{path}` identifies the specific resource
- implementations MAY use other URI schemes (e.g., `https://`, `urn:`) as long as they are consistent within a session
- canonical URIs MUST be treated as case-sensitive opaque strings for comparison purposes

When `canonical_uris` is absent, implementations SHOULD fall back to kind-specific comparison (e.g., string matching within the same `kind`) or to semantic matching via `model_inference` (Section 17.7).

### 15.2.3 Session Resource Registry

For sessions where participants use heterogeneous scope kinds, implementations MAY provide a **resource registry** — a session-level mapping from various scope representations to canonical URIs.

The registry MAY be declared in session metadata:

```json
{
  "resource_registry": {
    "mappings": [
      {
        "canonical_uri": "resource://myproject/src/routes/auth.ts",
        "aliases": [
          { "kind": "file_set", "value": "src/routes/auth.ts" },
          { "kind": "entity_set", "value": "api.auth.routes" },
          { "kind": "resource_path", "value": "src/routes/auth.*" }
        ]
      }
    ]
  }
}
```

When a resource registry is present, implementations SHOULD automatically resolve scope entries to canonical URIs using the registry mappings, even if the participant did not explicitly include `canonical_uris` in their scope object.

The resource registry is optional. Sessions with homogeneous scope kinds (all participants using `file_set`, for example) do not need it.

### 15.3 `INTENT_ANNOUNCE`

Purpose:
- declare planned work before execution

Payload:

```json
{
  "intent_id": "intent-123",
  "objective": "Tune training stability",
  "scope": {
    "kind": "file_set",
    "resources": ["train.py", "config.yaml"]
  },
  "assumptions": [
    "hidden_dim remains 256",
    "scheduler should remain cosine"
  ],
  "priority": "normal",
  "ttl_sec": 120
}
```

Semantics:
- participants SHOULD announce intent before non-trivial work
- intent scope SHOULD describe the expected target set
- assumptions SHOULD capture important unstated dependencies

### 15.4 `INTENT_UPDATE`

Purpose:
- revise an existing active intent

Payload:

```json
{
  "intent_id": "intent-123",
  "objective": "Tune training stability and scheduler warmup",
  "scope": {
    "kind": "file_set",
    "resources": ["train.py", "config.yaml"]
  },
  "assumptions": [
    "scheduler may be adjusted if loss spikes"
  ],
  "ttl_sec": 180
}
```

### 15.5 `INTENT_WITHDRAW`

Purpose:
- cancel an active intent

Payload:

```json
{
  "intent_id": "intent-123",
  "reason": "superseded_by_human_instruction"
}
```

### 15.6 Intent Lifecycle

The recommended intent state machine is:

```text
DRAFT -> ANNOUNCED -> ACTIVE -> SUPERSEDED
DRAFT -> ANNOUNCED -> ACTIVE -> EXPIRED
DRAFT -> ANNOUNCED -> WITHDRAWN
ACTIVE -> SUSPENDED -> ACTIVE           (participant reconnects)
ACTIVE -> SUSPENDED -> TRANSFERRED      (intent claimed by another participant)
```

MPAC does not require a `DRAFT` message on the wire.
It is included here as a conceptual lifecycle state.

The `SUSPENDED` and `TRANSFERRED` states support recovery from participant unavailability (Section 14.4). An intent enters `SUSPENDED` when its owner becomes unavailable, and transitions to `TRANSFERRED` when another participant successfully claims it via `INTENT_CLAIM`.

## 16. Operation Layer

### 16.1 Operation Model

An operation represents a proposed or committed mutation to shared state.

An operation SHOULD include:
- operation identifier
- associated intent identifier if any
- target resource
- operation kind
- state reference before
- state reference after
- change reference
- summary

### 16.2 `OP_PROPOSE`

Purpose:
- declare a pending mutation before commit in governance modes that require review

Payload:

```json
{
  "op_id": "op-456",
  "intent_id": "intent-123",
  "target": "train.py",
  "op_kind": "replace",
  "change_ref": "sha256:diffblob-001",
  "summary": "Adjust optimizer settings"
}
```

### 16.3 `OP_COMMIT`

Purpose:
- declare that a mutation has been committed into shared state

Payload:

```json
{
  "op_id": "op-456",
  "intent_id": "intent-123",
  "target": "train.py",
  "op_kind": "replace",
  "state_ref_before": "sha256:old-state",
  "state_ref_after": "sha256:new-state",
  "change_ref": "sha256:diffblob-001",
  "summary": "Adjust optimizer settings"
}
```

Additional requirements:
- `state_ref_before` MUST be present in `OP_COMMIT` messages. It SHOULD be a content-addressable identifier (e.g., a SHA-256 hash of the target's content before mutation) or a version identifier meaningful to the shared state backend. The format is implementation-defined but MUST be consistent within a session.
- `state_ref_after` MUST be present in `OP_COMMIT` messages, using the same format as `state_ref_before`.
- When a receiver processes an `OP_COMMIT` and cannot verify that its local view of the target matches `state_ref_before`, it SHOULD mark the operation as `causally_unverifiable` in its local state and SHOULD NOT use this operation as a basis for conflict judgments until the local state is synchronized. The `causally_unverifiable` marker is a local processing hint, not a protocol-level state.

### 16.4 `OP_REJECT`

Purpose:
- reject a proposed operation

Payload:

```json
{
  "op_id": "op-456",
  "reason": "policy_violation"
}
```

### 16.5 `OP_SUPERSEDE`

Purpose:
- explicitly mark a previously committed operation as superseded by a newer operation

Payload:

```json
{
  "op_id": "op-789",
  "supersedes_op_id": "op-456",
  "intent_id": "intent-123",
  "target": "train.py",
  "reason": "revised_approach"
}
```

Semantics:
- the `supersedes_op_id` field MUST reference a previously committed operation
- the superseded operation's lifecycle state transitions to `SUPERSEDED`
- implementations SHOULD retain the superseded operation for audit purposes
- if no explicit `OP_SUPERSEDE` is sent, an operation MAY be implicitly superseded when a new `OP_COMMIT` targets the same resource with a `state_ref_before` matching the superseded operation's `state_ref_after`

### 16.6 Operation Lifecycle

```text
PROPOSED -> COMMITTED
PROPOSED -> REJECTED
PROPOSED -> ABANDONED          (sender unavailable, per Section 14.4.3)
COMMITTED -> SUPERSEDED
```

### 16.7 Operation Attribution

Every committed operation MUST be attributable to a sender principal.

### 16.8 Scope Consistency

If an operation is associated with an intent, implementations SHOULD be able to determine whether the operation falls within the declared scope of that intent.

## 17. Conflict Layer

### 17.1 Conflict Model

A conflict is a structured object describing a compatibility problem or potential compatibility problem.

A conflict SHOULD include:
- conflict identifier
- related intents and/or operations
- category
- severity
- detection basis
- causal basis
- description
- recommended action

### 17.2 `CONFLICT_REPORT`

Purpose:
- publish a structured incompatibility judgment

Payload:

```json
{
  "conflict_id": "conf-789",
  "related_intents": ["intent-123", "intent-222"],
  "related_ops": ["op-456", "op-999"],
  "category": "scope_overlap",
  "severity": "high",
  "basis": {
    "kind": "rule",
    "rule_id": "scope.overlap.v1"
  },
  "based_on_watermark": {
    "kind": "vector_clock",
    "value": {
      "alice": 4,
      "bob": 5
    }
  },
  "description": "Two agents intend to modify overlapping regions of train.py",
  "suggested_action": "human_review"
}
```

### 17.3 `CONFLICT_ACK`

Purpose:
- acknowledge receipt or recognition of a conflict

Payload:

```json
{
  "conflict_id": "conf-789",
  "ack_type": "seen"
}
```

Recommended `ack_type` values:
- `seen`
- `accepted`
- `disputed`

### 17.4 `CONFLICT_ESCALATE`

Purpose:
- escalate an unresolved conflict to a higher authority (typically a human arbiter or owner)

Payload:

```json
{
  "conflict_id": "conf-789",
  "escalate_to": "human:alice",
  "reason": "automated_resolution_failed",
  "context": "Both agents hold valid assumptions; human judgment required"
}
```

Semantics:
- a participant or automated system SHOULD send `CONFLICT_ESCALATE` when a conflict cannot be resolved at the current authority level
- the `escalate_to` field SHOULD reference a principal with sufficient governance authority (typically `owner` or `arbiter` role)
- upon escalation, the conflict lifecycle state transitions to `ESCALATED`
- the escalation target SHOULD respond with a `RESOLUTION` message

### 17.5 Conflict Categories

Recommended categories in MPAC v0.1:
- `scope_overlap`
- `concurrent_write`
- `semantic_goal_conflict`
- `assumption_contradiction`
- `policy_violation`
- `authority_conflict`
- `dependency_breakage`
- `resource_contention`

Implementations MAY define additional categories.

### 17.6 Severity Levels

Recommended severity values:
- `info`
- `low`
- `medium`
- `high`
- `critical`

### 17.7 Detection Basis

The `basis.kind` field SHOULD indicate how the conflict was detected.

Recommended values:
- `rule`: deterministic rule match (e.g., two scopes sharing a file path)
- `heuristic`: non-deterministic but non-model-based detection (e.g., budget threshold exceeded)
- `model_inference`: general model-based detection (e.g., LLM identified a potential issue)
- `semantic_match`: a specialized form of model-based detection where a semantic matcher compared two assumptions or scope descriptions and found a contradiction or equivalence (see Section 17.7.1)
- `human_report`: a human participant identified the conflict

### 17.7.1 Semantic Match Basis

When `basis.kind` is `semantic_match`, the `basis` object SHOULD include additional fields that describe the matching result. This enables downstream resolvers to assess confidence and understand what was matched.

```json
{
  "basis": {
    "kind": "semantic_match",
    "matcher": "implementation-defined-matcher-id",
    "match_type": "contradictory",
    "confidence": 0.87,
    "matched_pair": {
      "left": {
        "source_intent_id": "intent-123",
        "content": "scheduler should remain cosine"
      },
      "right": {
        "source_intent_id": "intent-456",
        "content": "we plan to switch to linear warmup"
      }
    },
    "explanation": "Both assumptions constrain the learning rate scheduler parameter with incompatible values"
  }
}
```

Field definitions:
- `matcher`: an implementation-defined identifier for the semantic matching engine used (e.g., a model name, service endpoint, or algorithm identifier). This is informational and aids audit and trust calibration.
- `match_type`: the semantic relationship detected. Recommended values:
  - `contradictory`: the two items assert incompatible claims
  - `equivalent`: the two items assert the same claim in different words (useful for scope deduplication)
  - `uncertain`: the matcher cannot determine the relationship with sufficient confidence
- `confidence`: a value between 0.0 and 1.0 indicating the matcher's confidence in the `match_type` assessment. Implementations SHOULD treat low-confidence results (below a session-configurable threshold, recommended default: 0.7) as `uncertain` regardless of `match_type`.
- `matched_pair`: the specific pair of items that were compared, with references to their source intents. Both `left` and `right` SHOULD include `source_intent_id` and `content` (the original text or scope representation).
- `explanation`: a human-readable explanation of why the match was classified as it was. This field is RECOMMENDED for auditability.

Implementations SHOULD NOT auto-resolve conflicts detected with `basis.kind = semantic_match` and `confidence` below the session threshold. Such conflicts SHOULD be escalated to a human participant for review.

The semantic matching algorithm itself is explicitly outside the scope of MPAC. Implementations MAY use embedding similarity, LLM inference, rule-based NLP, or any other technique. MPAC standardizes only the output format, ensuring that different implementations' matching results are interoperable within the conflict resolution pipeline.

### 17.8 Conflict Lifecycle

```text
OPEN -> ACKED -> RESOLVED -> CLOSED
OPEN -> DISMISSED
OPEN -> ESCALATED -> RESOLVED -> CLOSED
```

MPAC v0.1 does not require all lifecycle transitions to be explicitly represented as separate messages.
It requires that conflict state be representable and auditable.

## 18. Governance Layer

### 18.1 Purpose

Governance determines who may:
- approve or reject operations
- resolve conflicts
- override automated decisions
- assign ownership
- freeze or reopen scope

### 18.2 Authority Roles

Governance authority roles are the same as participant roles defined in Section 10.3: `observer`, `contributor`, `reviewer`, `owner`, and `arbiter`. Authority semantics are layered on top of these roles as follows:

- `observer`: no decision authority; may view session state
- `contributor`: may propose and commit operations within their scope
- `reviewer`: may approve or reject proposed operations
- `owner`: may resolve conflicts and override contributor actions within owned scope
- `arbiter`: may resolve any conflict and override any participant; typically reserved for human principals in high-risk decisions

### 18.3 Governance Principles

1. Role-awareness
Participants SHOULD know which roles have decision authority.

2. Override clarity
Override actions SHOULD be explicit and attributable.

3. Finality policy
Sessions SHOULD define whether some decisions are final or revisitable.

4. Human priority
For high-risk or high-severity conflicts, sessions SHOULD be able to designate human principals as final arbiters.

### 18.4 `RESOLUTION`

Purpose:
- resolve, dismiss, or override a conflict or contested operation

Payload:

```json
{
  "resolution_id": "res-111",
  "conflict_id": "conf-789",
  "decision": "human_override",
  "outcome": {
    "accepted": ["intent-123"],
    "rejected": ["intent-222"],
    "merged": []
  },
  "rationale": "Alice owns training pipeline changes in this session"
}
```

The `outcome` object SHOULD contain:
- `accepted`: array of intent or operation identifiers that are accepted as-is
- `rejected`: array of intent or operation identifiers that are rejected
- `merged`: array of intent or operation identifiers whose partial contributions are incorporated into a combined result

All three fields are optional. At least one SHOULD be present.

When a `RESOLUTION` rejects an operation that is already in `COMMITTED` state (i.e., the mutation has already been applied to shared state), the resolver SHOULD accompany the resolution with a compensating `OP_COMMIT` that reverses the effect, or include an explicit `"rollback": "not_required"` field in the `outcome` to indicate that no state reversal is needed. MPAC does not define shared state rollback semantics — this is the responsibility of the application layer — but the protocol requires that the resolution makes its rollback expectation explicit for auditability.

Recommended `decision` values:
- `approved`
- `rejected`
- `dismissed`
- `human_override`
- `policy_override`
- `merged`
- `deferred`

### 18.5 Arbiter Designation

Sessions in which multiple principals hold `owner` roles SHOULD designate at least one participant with the `arbiter` role at session creation time. The arbiter serves as the final decision authority when owners reach an impasse.

Arbiter designation requirements:

1. **Governance profile sessions**: Sessions that declare MPAC Governance Profile compliance (Section 20.2) MUST designate at least one `arbiter` at session creation. If no arbiter is designated, the session coordinator SHOULD emit a warning and MAY refuse to create the session.

2. **Arbiter qualifications**: The arbiter SHOULD be a `human` principal or a `service` principal with explicit organizational authority. Agent principals MAY serve as arbiter only if the session policy explicitly permits it.

3. **Arbiter availability**: If the designated arbiter leaves the session (via `GOODBYE` or unavailability detection per Section 14.4), participants SHOULD either designate a replacement arbiter or acknowledge that deadlock resolution may require out-of-band intervention.

4. **Multiple arbiters**: Sessions MAY designate multiple arbiters. When multiple arbiters are present and disagree, the session policy SHOULD define a precedence rule (e.g., first-responder wins, or a specific arbiter is designated as primary).

### 18.6 Resolution Timeout and Deadlock Prevention

To prevent governance deadlock — situations where a conflict remains unresolved because equal-authority principals cannot reach agreement — sessions SHOULD define timeout-based escalation policies.

#### 18.6.1 Resolution Timeout

Sessions MAY specify a `resolution_timeout_sec` in session policy. When a `CONFLICT_REPORT` or `CONFLICT_ESCALATE` has been pending without a corresponding `RESOLUTION` for longer than this timeout:

1. If an arbiter is designated, the conflict SHOULD be automatically escalated to the arbiter via a system-generated `CONFLICT_ESCALATE` message.

2. If no arbiter is designated or the arbiter is unavailable, the session SHOULD enter a **frozen state** for the conflicted scope: operations targeting the scope of the unresolved conflict MUST be rejected until the conflict is resolved. Other non-conflicting operations MAY continue normally.

3. The timeout event SHOULD be visible to all participants (e.g., via a `PROTOCOL_ERROR` with `error_code`: `RESOLUTION_TIMEOUT` or an implementation-specific notification).

Recommended default: `resolution_timeout_sec: 300` (5 minutes). Sessions MAY override this value. A value of `0` disables timeout-based escalation.

#### 18.6.2 Frozen Scope

When a scope enters frozen state due to resolution timeout:

- `OP_PROPOSE` and `OP_COMMIT` messages targeting resources within the frozen scope MUST be rejected with a `PROTOCOL_ERROR` (`error_code`: `SCOPE_FROZEN`)
- `INTENT_ANNOUNCE` messages whose scope is fully contained within the frozen scope MUST be rejected with a `PROTOCOL_ERROR` (`error_code`: `SCOPE_FROZEN`). `INTENT_ANNOUNCE` messages with partially overlapping scope SHOULD be accepted but participants MUST be warned that the overlapping portion is frozen
- the frozen state is lifted when a valid `RESOLUTION` is received for the underlying conflict
- participants MAY still send `CONFLICT_ACK`, `CONFLICT_ESCALATE`, and `RESOLUTION` messages for the frozen conflict

#### 18.6.2.1 Frozen Scope Fallback

To prevent indefinite freezing when no arbiter is available, sessions SHOULD define a `frozen_scope_timeout_sec` in session policy (recommended default: 1800 seconds / 30 minutes). When a frozen scope exceeds this timeout without resolution:

1. The conflicting operations that triggered the freeze SHOULD be automatically rejected (`OP_REJECT` with `reason`: `frozen_scope_timeout`)
2. The underlying conflict SHOULD be transitioned to `CLOSED` with a system-generated `RESOLUTION` (`decision`: `rejected`, `rationale`: `frozen_scope_timeout_exceeded`)
3. The frozen scope is released, and participants may re-propose operations

This fallback prevents a single unavailable arbiter from permanently blocking progress. Sessions MAY disable this fallback by setting `frozen_scope_timeout_sec: 0`.

#### 18.6.3 Session Policy Example

```json
{
  "governance": {
    "require_arbiter": true,
    "resolution_timeout_sec": 300,
    "timeout_action": "escalate_then_freeze",
    "frozen_scope_behavior": "reject_writes_and_intents",
    "frozen_scope_timeout_sec": 1800
  }
}
```

### 18.7 Resolution Causal Context

A `RESOLUTION` MUST include a `watermark` in the message envelope indicating the causal state known to the resolver at the time of the decision. This is critical for auditability: it allows participants to verify that the resolver had sufficient context when making the decision. Resolutions without a watermark SHOULD be rejected by implementations operating under the Authenticated or Verified security profile.

### 18.8 Governance Auditability

A `RESOLUTION` MUST be attributable to the sender.
Implementations SHOULD retain enough history to reconstruct who resolved what and why.

## 19. Capability Advertisement

Participants SHOULD advertise capabilities during `HELLO`.

### 19.1 Recommended Capability Names

- `intent.broadcast`
- `intent.update`
- `intent.withdraw`
- `intent.claim`
- `op.propose`
- `op.commit`
- `op.reject`
- `conflict.report`
- `conflict.ack`
- `governance.vote`
- `governance.override`
- `causality.vector_clock`
- `causality.lamport_clock`
- `semantic.analysis`

### 19.2 Capability Rule

Participants MUST NOT assume features that were not advertised unless the session defines them as mandatory.

## 20. Compliance Profiles

MPAC v0.1 defines lightweight compliance profiles.

### 20.1 MPAC Core Profile

An implementation is MPAC Core compliant if it supports:
- `HELLO`
- `GOODBYE`
- `HEARTBEAT`
- `INTENT_ANNOUNCE`
- `OP_COMMIT`
- `CONFLICT_REPORT`
- `RESOLUTION`
- `PROTOCOL_ERROR`

### 20.2 MPAC Governance Profile

Adds:
- role-aware authority
- escalation support (`CONFLICT_ESCALATE`)
- override semantics
- operation rejection support (`OP_REJECT`)
- operation supersession (`OP_SUPERSEDE`)
- arbiter designation (Section 18.5) — sessions MUST designate at least one arbiter
- resolution timeout support (Section 18.6)
- intent claim support (`INTENT_CLAIM`) for unavailability recovery (Section 14.4)

### 20.3 MPAC Semantic Profile

Adds:
- semantic conflict reporting
- `basis.kind = model_inference`
- causal confidence handling or equivalent

Implementations SHOULD declare which profiles they support.

## 21. Extensions

### 21.1 Extension Mechanism

Implementations MAY add custom fields under:
- `payload.extensions`
- `sender.extensions`
- `watermark.extensions`

### 21.2 Forward Compatibility

Unknown extension fields SHOULD be ignored unless explicitly marked mandatory by session policy.

### 21.3 Namespacing

Implementations SHOULD namespace vendor-specific extensions to avoid collision.

Example:

```json
{
  "extensions": {
    "vendor.example": {
      "confidence": 0.83
    }
  }
}
```

## 22. Error Handling

### 22.1 `PROTOCOL_ERROR`

MPAC v0.1 defines a lightweight error message for signaling protocol-level problems that do not fit into the conflict or operation rejection categories.

Purpose:
- signal that a received message is malformed, unprocessable, or violates protocol constraints

Payload:

```json
{
  "error_code": "MALFORMED_MESSAGE",
  "refers_to": "msg-010",
  "description": "Missing required field: payload.intent_id"
}
```

Recommended `error_code` values:
- `MALFORMED_MESSAGE`: the referenced message could not be parsed or is missing required fields
- `UNKNOWN_MESSAGE_TYPE`: the `message_type` is not recognized and session policy does not allow ignoring it
- `INVALID_REFERENCE`: the message references a nonexistent session, intent, operation, or conflict
- `VERSION_MISMATCH`: the protocol version is incompatible
- `CAPABILITY_UNSUPPORTED`: the message requires a capability the receiver does not support
- `AUTHORIZATION_FAILED`: the sender lacks the authority for the attempted action
- `PARTICIPANT_UNAVAILABLE`: a participant has been detected as unavailable (Section 14.4.1)
- `RESOLUTION_TIMEOUT`: a conflict resolution has exceeded the configured timeout (Section 18.6.1)
- `SCOPE_FROZEN`: an operation or intent targets a scope that is frozen due to an unresolved conflict timeout (Section 18.6.2)
- `CLAIM_CONFLICT`: an `INTENT_CLAIM` targets a suspended intent that has already been claimed by another participant (Section 14.4.4)

Semantics:
- the `refers_to` field SHOULD reference the `message_id` of the problematic message when available
- `PROTOCOL_ERROR` is informational; it does not mandate any specific recovery behavior
- implementations SHOULD NOT send `PROTOCOL_ERROR` for messages that are merely unexpected but processable (e.g., unknown extension fields)

### 22.2 Other Error Signaling

Implementations MAY also express protocol-level issues by:
- rejecting an operation with `OP_REJECT`
- publishing a `CONFLICT_REPORT`
- using transport-level error signaling
- using implementation-specific extension messages

## 23. Security and Trust Considerations

MPAC does not assume all participants are fully trusted. Different deployment environments have vastly different trust requirements: an intra-team session between agents built by the same organization may need minimal authentication, while a cross-organizational session involving competing stakeholders may require message signing with certificate chains.

### 23.1 Security Profiles

MPAC v0.1 defines three security profiles. Sessions MUST declare which security profile they operate under. Implementations SHOULD support at least the Open profile, and SHOULD support the Authenticated profile for any cross-principal deployment.

#### 23.1.1 Open Profile

Intended for intra-team or development environments where all participants share a single trust domain.

Requirements:
- principal identifiers MUST be unique within the session
- message envelopes MUST include all required fields per Section 11.2
- implementations SHOULD retain message logs for the session duration

No authentication or message signing is required. This profile is NOT RECOMMENDED for cross-organizational deployments.

#### 23.1.2 Authenticated Profile

Intended for cross-team or cross-organizational deployments where participants need identity assurance but operate within a shared governance framework.

Requirements:
- all requirements of the Open profile
- principal identity MUST be verified through an authentication mechanism before a participant's `HELLO` is accepted. Acceptable mechanisms include: OAuth 2.0 tokens, mutual TLS (mTLS), API keys issued by a session coordinator, or equivalent identity verification
- sessions MUST reject `HELLO` messages from principals whose identity cannot be verified
- implementations MUST bind each `sender` field to the authenticated identity, preventing principal impersonation
- the `signature` envelope field (Section 11.3) SHOULD be populated with a message authentication code (MAC) or digital signature on every message
- implementations MUST implement replay protection by rejecting messages with duplicate `message_id` values or timestamps outside an acceptable window (RECOMMENDED: 5 minutes)
- role assertions in `HELLO` messages MUST be validated by the session coordinator against the session's role policy before the participant is admitted. Participants MUST NOT be granted roles they are not authorized for, regardless of what they declare in `HELLO`
- audit trail logs MUST be retained for at least the session duration and SHOULD be retained for a configurable period after session completion

#### 23.1.3 Verified Profile

Intended for high-stakes cross-organizational deployments where participants may have adversarial interests and full cryptographic accountability is required.

Requirements:
- all requirements of the Authenticated profile
- every message MUST carry a digital signature in the `signature` envelope field, using a key bound to the sender's authenticated identity
- implementations MUST verify message signatures before processing; messages with invalid or missing signatures MUST be rejected with a `PROTOCOL_ERROR` (`error_code`: `AUTHORIZATION_FAILED`)
- implementations MUST maintain a tamper-evident log (e.g., hash chain or Merkle tree) of all messages in the session. The log integrity mechanism SHOULD be declared in session metadata
- `RESOLUTION` messages MUST carry both a valid signature and a watermark; resolutions without causal context SHOULD be rejected
- principal authentication MUST use certificate-based identity (X.509 certificates or equivalent) with a verifiable chain of trust
- implementations SHOULD support key rotation without session interruption

### 23.2 Session Security Declaration

Sessions SHOULD declare their security profile in session metadata. The recommended format is:

```json
{
  "session_id": "sess-001",
  "security_profile": "authenticated",
  "security_config": {
    "auth_mechanism": "mTLS",
    "replay_window_sec": 300,
    "audit_retention_days": 90
  }
}
```

If no security profile is declared, implementations SHOULD default to the Open profile and SHOULD emit a warning if cross-organizational principals are detected.

### 23.3 Trust Boundary Enforcement

Regardless of security profile, the following trust principles apply:

1. **Principal isolation**: An agent's messages MUST only claim the `principal_id` that was authenticated at session join. Implementations MUST reject messages where the `sender.principal_id` does not match the authenticated identity.

2. **Scope honoring**: Implementations SHOULD detect and flag operations that fall outside the scope declared in the sender's active intent. While this is not a security violation per se, undeclared scope mutations in cross-principal sessions SHOULD be logged and MAY trigger a `CONFLICT_REPORT` with category `policy_violation`.

3. **Governance authority verification**: Before processing a `RESOLUTION`, `OP_REJECT`, or `CONFLICT_ESCALATE`, implementations SHOULD verify that the sender holds a role with sufficient authority (per Section 18.2). Messages from principals lacking the required role SHOULD be rejected with a `PROTOCOL_ERROR` (`error_code`: `AUTHORIZATION_FAILED`).

4. **Watermark integrity**: In the Verified security profile, watermark values MUST be consistent with the sender's observed message history. Implementations MAY cross-check watermark claims against the tamper-evident log and flag inconsistencies as a `CONFLICT_REPORT` with category `policy_violation`.

### 23.4 General Security Considerations

Beyond the security profiles, implementations SHOULD consider:
- session-scoped authorization that limits participant capabilities to their declared roles
- rate limiting to prevent denial-of-service through message flooding
- message size limits to prevent resource exhaustion
- secure transport (TLS 1.3 or equivalent) for all message delivery channels
- credential and key material storage following platform security best practices
- end-to-end encryption of message payloads in deployments where the session coordinator or transport intermediaries are not fully trusted. In such deployments, participants SHOULD encrypt payload contents using recipient-specific keys, leaving only the envelope fields (which the coordinator needs for routing and ordering) in plaintext

## 24. Privacy Considerations

Messages MAY contain:
- user identity
- inferred intent
- operational history
- conflict rationale
- assumptions or planning details

Implementations SHOULD provide policy controls for:
- retention duration
- visibility scope
- redaction
- access auditing

## 25. Versioning

### 25.1 Protocol Version

The `version` field in the envelope identifies the MPAC message format version.

### 25.2 Compatibility Rule

Minor or patch evolution SHOULD preserve backward compatibility where feasible.

### 25.3 Unknown Message Types

Receivers SHOULD ignore unknown message types unless the session policy marks them mandatory.

## 26. Reference Interoperability Guidance

To maximize interoperability, implementations SHOULD:

1. Use stable principal identifiers
2. Emit explicit `INTENT_ANNOUNCE` before substantial work
3. Attach causal context to operations and conflict reports
4. Use standardized conflict categories when possible
5. Keep governance decisions attributable and auditable
6. Advertise supported capabilities at session join
7. Preserve protocol semantics independent of transport
8. Declare a security profile appropriate to the deployment's trust boundaries (Section 23.1)
9. Designate at least one arbiter in multi-owner sessions (Section 18.5)
10. Implement unavailability detection and orphaned intent recovery (Section 14.4)
11. Include `canonical_uris` in scope objects when participants use heterogeneous scope kinds (Section 15.2.1)
12. Use the `semantic_match` basis kind with standardized output format for assumption contradiction detection (Section 17.7.1)
13. Support `lamport_clock` as the baseline watermark kind and include `lamport_value` in non-lamport watermarks (Section 12.3)
14. Use the mandatory scope overlap rules for `file_set`, `entity_set`, and `task_set` (Section 15.2.1.1)
15. Require `state_ref_before` and `state_ref_after` in all `OP_COMMIT` messages (Section 16.3)
16. Validate role assertions against session policy in Authenticated and Verified profiles (Section 23.1.2)

## 27. Example Minimal Flow

A minimal MPAC collaboration flow may look like this:

1. Agent A sends `HELLO`
2. Agent B sends `HELLO`
3. Agent A sends `INTENT_ANNOUNCE`
4. Agent B sends `INTENT_ANNOUNCE`
5. Agent A commits work with `OP_COMMIT`
6. Agent B detects overlap and sends `CONFLICT_REPORT`
7. Human reviewer sends `RESOLUTION`
8. Agents continue from the resolved state

This flow illustrates that MPAC treats coordination and conflict handling as explicit protocol objects rather than implicit application behavior.

## 28. Example Messages

### 28.1 Example `HELLO`

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-001",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:alice-coder-1",
    "principal_type": "agent"
  },
  "ts": "2026-03-27T18:00:00Z",
  "payload": {
    "display_name": "Alice",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "op.commit", "conflict.report"],
    "implementation": {
      "name": "acp-ref-js",
      "version": "0.1.0"
    }
  }
}
```

### 28.2 Example `INTENT_ANNOUNCE`

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-010",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:alice-coder-1",
    "principal_type": "agent"
  },
  "ts": "2026-03-27T18:01:00Z",
  "watermark": {
    "kind": "vector_clock",
    "value": {
      "alice": 1,
      "bob": 0
    }
  },
  "payload": {
    "intent_id": "intent-123",
    "objective": "Tune training stability",
    "scope": {
      "kind": "file_set",
      "resources": ["train.py", "config.yaml"]
    },
    "assumptions": [
      "hidden_dim remains 256",
      "scheduler should remain cosine"
    ],
    "priority": "normal",
    "ttl_sec": 120
  }
}
```

### 28.3 Example `OP_COMMIT`

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-020",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:alice-coder-1",
    "principal_type": "agent"
  },
  "ts": "2026-03-27T18:02:00Z",
  "watermark": {
    "kind": "vector_clock",
    "value": {
      "alice": 2,
      "bob": 1
    }
  },
  "payload": {
    "op_id": "op-456",
    "intent_id": "intent-123",
    "target": "train.py",
    "op_kind": "replace",
    "state_ref_before": "sha256:old-state",
    "state_ref_after": "sha256:new-state",
    "change_ref": "sha256:diffblob-001",
    "summary": "Adjust optimizer settings"
  }
}
```

### 28.4 Example `CONFLICT_REPORT`

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-030",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:bob-review-1",
    "principal_type": "agent"
  },
  "ts": "2026-03-27T18:02:10Z",
  "watermark": {
    "kind": "vector_clock",
    "value": {
      "alice": 2,
      "bob": 2
    }
  },
  "payload": {
    "conflict_id": "conf-789",
    "related_intents": ["intent-123", "intent-222"],
    "related_ops": ["op-456", "op-999"],
    "category": "scope_overlap",
    "severity": "high",
    "basis": {
      "kind": "rule",
      "rule_id": "scope.overlap.v1"
    },
    "based_on_watermark": {
      "kind": "vector_clock",
      "value": {
        "alice": 2,
        "bob": 2
      }
    },
    "description": "Two agents intend to modify overlapping regions of train.py",
    "suggested_action": "human_review"
  }
}
```

### 28.5 Example `RESOLUTION`

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-040",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "human:alice",
    "principal_type": "human"
  },
  "ts": "2026-03-27T18:03:00Z",
  "watermark": {
    "kind": "vector_clock",
    "value": {
      "alice": 4,
      "bob": 2
    }
  },
  "payload": {
    "resolution_id": "res-111",
    "conflict_id": "conf-789",
    "decision": "human_override",
    "outcome": {
      "accepted": ["intent-123"],
      "rejected": ["intent-222"],
      "merged": []
    },
    "rationale": "Alice owns training pipeline changes in this session"
  }
}
```

## 29. Recommended Future Work

The following areas are explicitly deferred from MPAC v0.1 and may be addressed in future versions:

- formal JSON Schema files (machine-readable) corresponding to the payload schema tables in Section 13.1
- richer session negotiation and discovery protocols, including capability compatibility verification at join time
- standard conflict ontology extensions
- conflict confidence scoring
- operation diff payload standards
- atomic multi-target operations (batch mutations spanning multiple resources in a single logical operation)
- ownership lease semantics
- protocol conformance test suite
- session transfer and migration
- participant capability negotiation beyond HELLO
- session-level resource registry auto-population and discovery mechanisms
- standard assumption ontology or vocabulary for common domains (to improve `semantic_match` accuracy across implementations)
- hierarchical vector clocks or interval tree clocks for reduced causal metadata overhead in large sessions
- integration architecture guidance for deployments combining MPAC with MCP (agent-to-tool) and A2A (agent-to-agent) protocols
- end-to-end payload encryption specification for deployments with untrusted coordinators

Note: Security profiles and trust enforcement (Section 23), governance deadlock prevention (Sections 18.5–18.6), participant unavailability recovery (Section 14.4), semantic interoperability foundations (Sections 15.2.1–15.2.3, 17.7.1), payload schema tables (Section 13.1), scope overlap standardization (Section 15.2.1), baseline watermark interoperability (Section 12.3), session coordinator role (Section 8.1), and frozen scope fallback (Section 18.6.2.1) were identified as gaps in review and have been addressed in this version of the specification.

## 30. Summary

MPAC v0.1.3 defines a minimal but structured protocol for multi-agent collaboration centered on:
- sessions and session coordination
- intents with mandatory pre-execution declaration (Governance Profile)
- operations with required state references
- conflicts with standardized scope overlap rules
- governance with deadlock prevention and frozen scope fallback
- causal context with baseline watermark interoperability
- security and trust with role assertion verification
- failure recovery with concurrent claim resolution

Its central design claim is that collaborative agent systems become more interoperable, auditable, and governable when intent, mutation, conflict, and resolution are represented as explicit protocol messages rather than hidden inside application logic. The protocol provides security profiles for deployments ranging from intra-team to cross-organizational, governance mechanisms to prevent deadlock between equal-authority principals, recovery semantics to handle participant failure without orphaning in-flight work, semantic interoperability mechanisms (canonical resource URIs and standardized semantic matching output) to enable cross-kind scope overlap detection and assumption contradiction identification, and payload schema definitions to ensure cross-implementation field-level compatibility.

