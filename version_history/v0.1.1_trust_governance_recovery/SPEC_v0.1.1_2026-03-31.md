# MPAC Specification v0.1

## 1. Status

This document defines version `0.1` of the Multi-Principal Agent Coordination Protocol (`MPAC`).

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

Participants SHOULD announce intent before committing non-trivial operations.

### 7.2 Attributable Actions

Every operation, conflict report, and resolution decision MUST be attributable to a principal.

### 7.3 Causal Context

Committed operations and conflict reports SHOULD include causal context via a watermark or equivalent reference.

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

### 8.1 Protocol-Level Ordering Constraints

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
- `ts` SHOULD use RFC 3339 / ISO 8601 UTC timestamps
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
- `vector_clock`
- `lamport_clock`
- `causal_frontier`
- `opaque`

### 12.3 Interoperability Rule

If a participant receives a watermark kind it cannot interpret, it MAY still process the message, but SHOULD treat causally sensitive judgments as partial.

### 12.4 Conflict Judgment Rule

A `CONFLICT_REPORT` SHOULD include a `based_on_watermark` field indicating the state frontier on which the judgment relied.

### 12.5 Minimal Requirement

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
- a participant SHOULD send `HELLO` when entering a session
- a receiver MAY use `HELLO` to update presence and compatibility state

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
- `rule`
- `heuristic`
- `model_inference`
- `human_report`

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

For simple binary conflicts, implementations MAY use the shorthand fields `winner` and `loser` instead of `outcome`. When both `outcome` and `winner`/`loser` are present, `outcome` takes precedence.

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
- `INTENT_ANNOUNCE` messages with overlapping scope SHOULD be accepted but participants SHOULD be warned that the scope is frozen
- the frozen state is lifted when a valid `RESOLUTION` is received for the underlying conflict
- participants MAY still send `CONFLICT_ACK`, `CONFLICT_ESCALATE`, and `RESOLUTION` messages for the frozen conflict

#### 18.6.3 Session Policy Example

```json
{
  "governance": {
    "require_arbiter": true,
    "resolution_timeout_sec": 300,
    "timeout_action": "escalate_then_freeze",
    "frozen_scope_behavior": "reject_writes"
  }
}
```

### 18.7 Resolution Causal Context

A `RESOLUTION` SHOULD include a `watermark` in the message envelope indicating the causal state known to the resolver at the time of the decision. This is critical for auditability: it allows participants to verify that the resolver had sufficient context when making the decision.

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
- `SCOPE_FROZEN`: an operation targets a scope that is frozen due to an unresolved conflict timeout (Section 18.6.2)

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
- implementations SHOULD implement replay protection by rejecting messages with duplicate `message_id` values or timestamps outside an acceptable window (RECOMMENDED: 5 minutes)
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

- formal JSON Schema definitions
- richer session negotiation and discovery protocols
- standard conflict ontology extensions
- conflict confidence scoring
- operation diff payload standards
- ownership lease semantics
- protocol conformance test suite
- session transfer and migration
- participant capability negotiation beyond HELLO
- scope normalization mechanism for cross-kind overlap detection (e.g., mapping `file_set` and `entity_set` to canonical resource URIs)
- structured assumption format for tractable syntactic contradiction detection alongside free-form text assumptions
- hierarchical vector clocks or interval tree clocks for reduced causal metadata overhead in large sessions
- session policy configurations for intent broadcast exemption on low-risk operations

Note: Security profiles and trust enforcement (Section 23), governance deadlock prevention (Sections 18.5–18.6), and participant unavailability recovery (Section 14.4) were identified as gaps in early review and have been addressed in this version of the specification.

## 30. Summary

MPAC v0.1 defines a minimal but structured protocol for multi-agent collaboration centered on:
- sessions
- intents
- operations
- conflicts
- governance
- causal context
- security and trust
- failure recovery

Its central design claim is that collaborative agent systems become more interoperable, auditable, and governable when intent, mutation, conflict, and resolution are represented as explicit protocol messages rather than hidden inside application logic. The protocol provides security profiles for deployments ranging from intra-team to cross-organizational, governance mechanisms to prevent deadlock between equal-authority principals, and recovery semantics to handle participant failure without orphaning in-flight work.

## Appendix A. Real-World Scenario Walkthroughs

The following three scenarios illustrate complete MPAC message flows in realistic settings. Each scenario shows the full sequence of messages exchanged, demonstrating how the protocol layers work together in practice.

---

### Scenario 1: Two AI Coding Agents Collaborate on a Microservice

**Setting**: A startup uses two AI coding agents — one specialized in backend logic (`agent:backend-1`) and one in database work (`agent:db-1`) — to build a new user registration endpoint. A human tech lead (`human:maya`) supervises the session.

#### Step 1 — Session join

All three participants join:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s1-001",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "human:maya", "principal_type": "human" },
  "ts": "2026-03-28T09:00:00Z",
  "payload": {
    "display_name": "Maya Chen",
    "roles": ["owner", "arbiter"],
    "capabilities": ["governance.override", "conflict.report"],
    "implementation": { "name": "acp-web-ui", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s1-002",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "agent:backend-1", "principal_type": "agent" },
  "ts": "2026-03-28T09:00:02Z",
  "payload": {
    "display_name": "Backend Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "op.commit", "conflict.report"],
    "implementation": { "name": "acp-agent-py", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s1-003",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "agent:db-1", "principal_type": "agent" },
  "ts": "2026-03-28T09:00:03Z",
  "payload": {
    "display_name": "Database Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "op.commit", "conflict.report"],
    "implementation": { "name": "acp-agent-py", "version": "0.1.0" }
  }
}
```

#### Step 2 — Intent announcement

Both agents declare what they plan to do:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s1-010",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "agent:backend-1", "principal_type": "agent" },
  "ts": "2026-03-28T09:01:00Z",
  "watermark": { "kind": "vector_clock", "value": { "maya": 1, "backend-1": 1, "db-1": 1 } },
  "payload": {
    "intent_id": "intent-api-endpoint",
    "objective": "Create POST /api/v1/register endpoint with input validation and password hashing",
    "scope": {
      "kind": "file_set",
      "resources": ["src/routes/auth.ts", "src/validators/registration.ts", "src/services/user-service.ts"]
    },
    "assumptions": [
      "Users table has columns: id, email, password_hash, created_at",
      "bcrypt is the agreed hashing algorithm",
      "Email uniqueness is enforced at the database level"
    ],
    "priority": "normal",
    "ttl_sec": 300
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s1-011",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "agent:db-1", "principal_type": "agent" },
  "ts": "2026-03-28T09:01:05Z",
  "watermark": { "kind": "vector_clock", "value": { "maya": 1, "backend-1": 2, "db-1": 1 } },
  "payload": {
    "intent_id": "intent-db-schema",
    "objective": "Create users table migration and add unique index on email",
    "scope": {
      "kind": "file_set",
      "resources": ["migrations/003_create_users.sql", "src/models/user.ts"]
    },
    "assumptions": [
      "Using PostgreSQL 15",
      "password_hash column is VARCHAR(255) for bcrypt output",
      "id column is UUID with gen_random_uuid() default"
    ],
    "priority": "normal",
    "ttl_sec": 300
  }
}
```

#### Step 3 — Conflict detection

The database agent notices an assumption mismatch after reading the backend agent's intent — the backend agent assumed `id` as a serial integer (implicit in its service code patterns), but the database agent plans UUID:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-s1-020",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "agent:db-1", "principal_type": "agent" },
  "ts": "2026-03-28T09:02:00Z",
  "watermark": { "kind": "vector_clock", "value": { "maya": 1, "backend-1": 2, "db-1": 2 } },
  "payload": {
    "conflict_id": "conf-id-type",
    "related_intents": ["intent-api-endpoint", "intent-db-schema"],
    "related_ops": [],
    "category": "assumption_contradiction",
    "severity": "high",
    "basis": {
      "kind": "model_inference",
      "rule_id": null
    },
    "based_on_watermark": { "kind": "vector_clock", "value": { "maya": 1, "backend-1": 2, "db-1": 2 } },
    "description": "Backend agent's service layer patterns imply integer auto-increment IDs, but database migration uses UUID for user.id. This will cause type mismatches in query construction and API response serialization.",
    "suggested_action": "human_review"
  }
}
```

#### Step 4 — Human resolves

Maya reviews and decides UUID is the right call:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-s1-030",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "human:maya", "principal_type": "human" },
  "ts": "2026-03-28T09:04:00Z",
  "watermark": { "kind": "vector_clock", "value": { "maya": 2, "backend-1": 2, "db-1": 3 } },
  "payload": {
    "resolution_id": "res-id-type",
    "conflict_id": "conf-id-type",
    "decision": "human_override",
    "outcome": {
      "accepted": ["intent-db-schema"],
      "rejected": [],
      "merged": ["intent-api-endpoint"]
    },
    "rationale": "Use UUID for all entity IDs per company standard. Backend agent should update its service layer to use string-typed UUIDs."
  }
}
```

#### Step 5 — Backend agent updates intent and commits

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_UPDATE",
  "message_id": "msg-s1-040",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "agent:backend-1", "principal_type": "agent" },
  "ts": "2026-03-28T09:04:30Z",
  "watermark": { "kind": "vector_clock", "value": { "maya": 3, "backend-1": 2, "db-1": 3 } },
  "payload": {
    "intent_id": "intent-api-endpoint",
    "objective": "Create POST /api/v1/register endpoint with UUID-based user IDs, input validation, and password hashing",
    "scope": {
      "kind": "file_set",
      "resources": ["src/routes/auth.ts", "src/validators/registration.ts", "src/services/user-service.ts"]
    },
    "assumptions": [
      "user.id is UUID (string type)",
      "bcrypt is the agreed hashing algorithm",
      "Email uniqueness is enforced at the database level"
    ],
    "ttl_sec": 300
  }
}
```

Both agents then commit their work:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s1-050",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "agent:db-1", "principal_type": "agent" },
  "ts": "2026-03-28T09:05:00Z",
  "watermark": { "kind": "vector_clock", "value": { "maya": 3, "backend-1": 3, "db-1": 3 } },
  "payload": {
    "op_id": "op-migration",
    "intent_id": "intent-db-schema",
    "target": "migrations/003_create_users.sql",
    "op_kind": "create",
    "state_ref_before": "sha256:empty",
    "state_ref_after": "sha256:a1b2c3d4",
    "change_ref": "sha256:migration-diff-001",
    "summary": "Created users table with UUID primary key, email (unique), password_hash, and created_at columns"
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s1-051",
  "session_id": "sess-registration-feature",
  "sender": { "principal_id": "agent:backend-1", "principal_type": "agent" },
  "ts": "2026-03-28T09:06:00Z",
  "watermark": { "kind": "vector_clock", "value": { "maya": 3, "backend-1": 3, "db-1": 4 } },
  "payload": {
    "op_id": "op-endpoint",
    "intent_id": "intent-api-endpoint",
    "target": "src/routes/auth.ts",
    "op_kind": "create",
    "state_ref_before": "sha256:empty",
    "state_ref_after": "sha256:e5f6g7h8",
    "change_ref": "sha256:endpoint-diff-001",
    "summary": "Created POST /api/v1/register with UUID user IDs, email validation, bcrypt hashing, and duplicate-email error handling"
  }
}
```

**Key takeaway**: The conflict was caught *before* any code was committed, at the intent/assumption level. Without MPAC, the agents would have written incompatible code and the mismatch would only surface at runtime or code review.

---

### Scenario 2: Multi-Agent Research Paper Writing with Scope Contention

**Setting**: A research lab uses three agents to draft a conference paper — a writing agent (`agent:writer-1`), a figure/visualization agent (`agent:viz-1`), and a citation agent (`agent:cite-1`). Two human researchers (`human:dr-patel`, `human:dr-liu`) co-supervise.

#### Step 1 — Session join (abbreviated)

All five participants send `HELLO`. Dr. Patel joins as `owner` of the Methods section, Dr. Liu as `owner` of the Results section. All three agents are `contributor` role.

#### Step 2 — Agents announce intent

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s2-010",
  "session_id": "sess-paper-draft",
  "sender": { "principal_id": "agent:writer-1", "principal_type": "agent" },
  "ts": "2026-03-28T14:00:00Z",
  "watermark": { "kind": "lamport_clock", "value": 5 },
  "payload": {
    "intent_id": "intent-methods-draft",
    "objective": "Draft the Methods section including experiment setup, dataset description, and evaluation metrics",
    "scope": {
      "kind": "entity_set",
      "entities": ["paper.sections.methods", "paper.sections.methods.subsections.*"]
    },
    "assumptions": [
      "The experiment uses the ImageNet-1K validation set",
      "Primary metric is top-1 accuracy",
      "Model architecture description belongs in Methods, not Results"
    ],
    "priority": "high",
    "ttl_sec": 600
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s2-011",
  "session_id": "sess-paper-draft",
  "sender": { "principal_id": "agent:viz-1", "principal_type": "agent" },
  "ts": "2026-03-28T14:00:10Z",
  "watermark": { "kind": "lamport_clock", "value": 6 },
  "payload": {
    "intent_id": "intent-results-figures",
    "objective": "Generate accuracy comparison bar chart and training loss curves for Results section",
    "scope": {
      "kind": "entity_set",
      "entities": ["paper.figures.fig1", "paper.figures.fig2", "paper.sections.results"]
    },
    "assumptions": [
      "Results include comparison against 3 baselines",
      "Training logs are available at /data/training_logs/",
      "Figures use the lab's standard matplotlib style"
    ],
    "priority": "normal",
    "ttl_sec": 600
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s2-012",
  "session_id": "sess-paper-draft",
  "sender": { "principal_id": "agent:cite-1", "principal_type": "agent" },
  "ts": "2026-03-28T14:00:15Z",
  "watermark": { "kind": "lamport_clock", "value": 7 },
  "payload": {
    "intent_id": "intent-citations",
    "objective": "Add inline citations and compile bibliography for Methods and Related Work sections",
    "scope": {
      "kind": "entity_set",
      "entities": ["paper.sections.methods", "paper.sections.related_work", "paper.bibliography"]
    },
    "assumptions": [
      "Citation style is NeurIPS 2026",
      "All referenced papers are available in the shared Zotero library"
    ],
    "priority": "normal",
    "ttl_sec": 600
  }
}
```

#### Step 3 — Scope overlap detected

The writing agent detects that both itself and the citation agent plan to modify the Methods section:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-s2-020",
  "session_id": "sess-paper-draft",
  "sender": { "principal_id": "agent:writer-1", "principal_type": "agent" },
  "ts": "2026-03-28T14:01:00Z",
  "watermark": { "kind": "lamport_clock", "value": 8 },
  "payload": {
    "conflict_id": "conf-methods-scope",
    "related_intents": ["intent-methods-draft", "intent-citations"],
    "related_ops": [],
    "category": "scope_overlap",
    "severity": "medium",
    "basis": { "kind": "rule", "rule_id": "scope.overlap.v1" },
    "based_on_watermark": { "kind": "lamport_clock", "value": 8 },
    "description": "Both writer-1 and cite-1 declare intent to modify paper.sections.methods. Concurrent edits risk overwriting each other's changes to the same paragraphs.",
    "suggested_action": "sequential_execution"
  }
}
```

#### Step 4 — Section owner resolves with a merge strategy

Dr. Patel, as Methods section owner, provides a resolution that allows both to proceed with ordering:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-s2-030",
  "session_id": "sess-paper-draft",
  "sender": { "principal_id": "human:dr-patel", "principal_type": "human" },
  "ts": "2026-03-28T14:03:00Z",
  "watermark": { "kind": "lamport_clock", "value": 9 },
  "payload": {
    "resolution_id": "res-methods-scope",
    "conflict_id": "conf-methods-scope",
    "decision": "merged",
    "outcome": {
      "accepted": ["intent-methods-draft", "intent-citations"],
      "rejected": [],
      "merged": []
    },
    "rationale": "Writer-1 drafts Methods first. Cite-1 waits for writer-1's OP_COMMIT on Methods before inserting citations. Both intents are valid but must execute sequentially on the shared section."
  }
}
```

#### Step 5 — Sequential execution

The writing agent commits its draft:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s2-040",
  "session_id": "sess-paper-draft",
  "sender": { "principal_id": "agent:writer-1", "principal_type": "agent" },
  "ts": "2026-03-28T14:10:00Z",
  "watermark": { "kind": "lamport_clock", "value": 10 },
  "payload": {
    "op_id": "op-methods-text",
    "intent_id": "intent-methods-draft",
    "target": "paper.sections.methods",
    "op_kind": "replace",
    "state_ref_before": "sha256:empty-methods",
    "state_ref_after": "sha256:methods-v1",
    "change_ref": "sha256:methods-diff-001",
    "summary": "Drafted complete Methods section: experiment setup with ImageNet-1K, model architecture description, training procedure, and evaluation protocol"
  }
}
```

The citation agent sees the commit and now safely operates on the updated text:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s2-041",
  "session_id": "sess-paper-draft",
  "sender": { "principal_id": "agent:cite-1", "principal_type": "agent" },
  "ts": "2026-03-28T14:12:00Z",
  "watermark": { "kind": "lamport_clock", "value": 11 },
  "payload": {
    "op_id": "op-methods-citations",
    "intent_id": "intent-citations",
    "target": "paper.sections.methods",
    "op_kind": "replace",
    "state_ref_before": "sha256:methods-v1",
    "state_ref_after": "sha256:methods-v2-cited",
    "change_ref": "sha256:cite-diff-001",
    "summary": "Inserted 12 inline citations into Methods section and added corresponding entries to bibliography"
  }
}
```

**Key takeaway**: MPAC turned a potential concurrent-edit disaster into an orderly pipeline. The `entity_set` scope kind allowed semantic resource identification beyond file paths, and the resolution established execution ordering without requiring any custom tooling.

---

### Scenario 3: Production Incident Response with Escalation

**Setting**: An e-commerce platform's monitoring service (`service:alertmanager`) detects a spike in checkout failures. Two on-call agents are activated — a diagnostics agent (`agent:diag-1`) and a hotfix agent (`agent:hotfix-1`). A human SRE (`human:jordan`) is the on-call arbiter.

#### Step 1 — Monitoring service opens the session and joins

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s3-001",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "service:alertmanager", "principal_type": "service" },
  "ts": "2026-03-28T03:15:00Z",
  "payload": {
    "display_name": "Alert Manager",
    "roles": ["observer", "contributor"],
    "capabilities": ["intent.broadcast", "conflict.report"],
    "implementation": { "name": "acp-alertmanager-plugin", "version": "0.1.0" }
  }
}
```

Agents and human join (abbreviated). Jordan joins as `arbiter`.

#### Step 2 — Diagnostics agent announces investigation

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s3-010",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "agent:diag-1", "principal_type": "agent" },
  "ts": "2026-03-28T03:16:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 1, "hotfix-1": 1, "jordan": 1 } },
  "payload": {
    "intent_id": "intent-diagnose",
    "objective": "Identify root cause of checkout failure spike starting at 03:12 UTC",
    "scope": {
      "kind": "entity_set",
      "entities": ["logs.checkout-service", "metrics.error-rate", "traces.checkout-flow"]
    },
    "assumptions": [
      "No deployments in the last 2 hours",
      "Database connections are healthy",
      "Payment gateway API is reachable"
    ],
    "priority": "high",
    "ttl_sec": 180
  }
}
```

#### Step 3 — Hotfix agent races ahead with a proposed fix

Before the diagnostics agent finishes, the hotfix agent proposes a speculative fix based on a pattern it recognizes:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s3-011",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "agent:hotfix-1", "principal_type": "agent" },
  "ts": "2026-03-28T03:16:30Z",
  "watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 2, "hotfix-1": 1, "jordan": 1 } },
  "payload": {
    "intent_id": "intent-hotfix-cache",
    "objective": "Flush and rebuild the checkout session cache — pattern matches last month's incident INC-4380",
    "scope": {
      "kind": "entity_set",
      "entities": ["service.checkout.cache", "config.cache-ttl"]
    },
    "assumptions": [
      "Root cause is stale cache entries from a TTL misconfiguration",
      "Cache flush is safe during low-traffic hours",
      "No data loss from cache invalidation"
    ],
    "priority": "high",
    "ttl_sec": 120
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_PROPOSE",
  "message_id": "msg-s3-012",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "agent:hotfix-1", "principal_type": "agent" },
  "ts": "2026-03-28T03:17:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 2, "hotfix-1": 2, "jordan": 1 } },
  "payload": {
    "op_id": "op-cache-flush",
    "intent_id": "intent-hotfix-cache",
    "target": "service.checkout.cache",
    "op_kind": "execute",
    "change_ref": "runbook:cache-flush-v2",
    "summary": "Flush checkout session cache and reset TTL to 300s (from current 3600s)"
  }
}
```

#### Step 4 — Diagnostics agent raises a conflict

The diagnostics agent's early findings suggest the problem is not cache-related:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-s3-020",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "agent:diag-1", "principal_type": "agent" },
  "ts": "2026-03-28T03:18:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 2, "hotfix-1": 3, "jordan": 1 } },
  "payload": {
    "conflict_id": "conf-wrong-root-cause",
    "related_intents": ["intent-diagnose", "intent-hotfix-cache"],
    "related_ops": ["op-cache-flush"],
    "category": "assumption_contradiction",
    "severity": "critical",
    "basis": {
      "kind": "model_inference"
    },
    "based_on_watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 2, "hotfix-1": 3, "jordan": 1 } },
    "description": "Preliminary log analysis shows checkout failures are returning HTTP 502 from payment gateway, not cache misses. Error pattern does not match INC-4380. Flushing cache will not address the root cause and may degrade performance during the incident.",
    "suggested_action": "reject_proposed_op"
  }
}
```

#### Step 5 — Diagnostics agent escalates to the human SRE

Because this is a production incident with a `critical` severity conflict, the diagnostics agent escalates:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_ESCALATE",
  "message_id": "msg-s3-021",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "agent:diag-1", "principal_type": "agent" },
  "ts": "2026-03-28T03:18:10Z",
  "watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 3, "hotfix-1": 3, "jordan": 1 } },
  "payload": {
    "conflict_id": "conf-wrong-root-cause",
    "escalate_to": "human:jordan",
    "reason": "critical_severity_production_incident",
    "context": "Hotfix agent proposes cache flush but evidence points to payment gateway 502s. Wrong remediation during incident could mask root cause and extend outage."
  }
}
```

#### Step 6 — Human SRE rejects the hotfix and redirects

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_REJECT",
  "message_id": "msg-s3-030",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "human:jordan", "principal_type": "human" },
  "ts": "2026-03-28T03:19:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 4, "hotfix-1": 3, "jordan": 1 } },
  "payload": {
    "op_id": "op-cache-flush",
    "reason": "Wrong root cause. Payment gateway is returning 502s — this is an upstream issue, not a cache problem."
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-s3-031",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "human:jordan", "principal_type": "human" },
  "ts": "2026-03-28T03:19:05Z",
  "watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 4, "hotfix-1": 3, "jordan": 2 } },
  "payload": {
    "resolution_id": "res-root-cause",
    "conflict_id": "conf-wrong-root-cause",
    "decision": "human_override",
    "outcome": {
      "accepted": ["intent-diagnose"],
      "rejected": ["intent-hotfix-cache"],
      "merged": []
    },
    "rationale": "Root cause is payment gateway 502s, not cache. Hotfix-1 should pivot to investigating payment gateway connectivity. Diag-1 should continue log analysis and check if our API keys were rotated."
  }
}
```

#### Step 7 — Hotfix agent withdraws and pivots

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_WITHDRAW",
  "message_id": "msg-s3-040",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "agent:hotfix-1", "principal_type": "agent" },
  "ts": "2026-03-28T03:19:30Z",
  "watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 4, "hotfix-1": 3, "jordan": 3 } },
  "payload": {
    "intent_id": "intent-hotfix-cache",
    "reason": "rejected_by_arbiter"
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s3-041",
  "session_id": "sess-incident-4521",
  "sender": { "principal_id": "agent:hotfix-1", "principal_type": "agent" },
  "ts": "2026-03-28T03:19:35Z",
  "watermark": { "kind": "vector_clock", "value": { "alertmanager": 1, "diag-1": 4, "hotfix-1": 4, "jordan": 3 } },
  "payload": {
    "intent_id": "intent-investigate-gateway",
    "objective": "Investigate payment gateway connectivity — check API key status, TLS cert expiry, and gateway status page",
    "scope": {
      "kind": "entity_set",
      "entities": ["service.payment-gateway", "config.payment-api-keys", "external.gateway-status"]
    },
    "assumptions": [
      "Payment gateway exposes a health endpoint",
      "API keys are stored in vault and may have been rotated"
    ],
    "priority": "high",
    "ttl_sec": 180
  }
}
```

**Key takeaway**: MPAC prevented a wrong fix from being applied to production during an active incident. The escalation path (`CONFLICT_REPORT` → `CONFLICT_ESCALATE` → `OP_REJECT` + `RESOLUTION`) gave the human SRE full context to make the right call, with a complete audit trail. The hotfix agent's speculative approach was safely caught and redirected rather than silently executed.

---

### Scenario 4: Two Teams, Six Agents, One Codebase — Cross-Team Feature Development

**Setting**: A SaaS company is building a new dashboard feature. Alice (frontend lead) has three agents — a UI component agent (`agent:alice-ui`), a state management agent (`agent:alice-state`), and a test agent (`agent:alice-test`). Bob (backend lead) also has three agents — an API agent (`agent:bob-api`), a database agent (`agent:bob-db`), and a test agent (`agent:bob-test`). Both humans serve as `owner` of their respective domains and `reviewer` of the other's. The project has a shared API contract (`api/dashboard.openapi.yaml`) that bridges both teams.

This scenario demonstrates how MPAC coordinates six concurrent agents across two team boundaries, handling cross-team dependency, parallel work within a team, and a multi-party conflict involving agents from different owners.

#### Step 1 — Everyone joins

Alice, Bob, and all six agents join the session. Abbreviated to show the key identity structure:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s4-001",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "human:alice", "principal_type": "human" },
  "ts": "2026-03-28T10:00:00Z",
  "payload": {
    "display_name": "Alice Wang",
    "roles": ["owner", "reviewer"],
    "capabilities": ["governance.override", "conflict.report", "op.reject"],
    "implementation": { "name": "acp-web-ui", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s4-002",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "human:bob", "principal_type": "human" },
  "ts": "2026-03-28T10:00:01Z",
  "payload": {
    "display_name": "Bob Martinez",
    "roles": ["owner", "reviewer"],
    "capabilities": ["governance.override", "conflict.report", "op.reject"],
    "implementation": { "name": "acp-web-ui", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s4-003",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-ui", "principal_type": "agent" },
  "ts": "2026-03-28T10:00:02Z",
  "payload": {
    "display_name": "Alice's UI Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "op.commit", "conflict.report"],
    "implementation": { "name": "acp-agent-py", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s4-004",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-state", "principal_type": "agent" },
  "ts": "2026-03-28T10:00:03Z",
  "payload": {
    "display_name": "Alice's State Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "op.commit", "conflict.report"],
    "implementation": { "name": "acp-agent-py", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s4-005",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-test", "principal_type": "agent" },
  "ts": "2026-03-28T10:00:04Z",
  "payload": {
    "display_name": "Alice's Test Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "op.commit", "conflict.report"],
    "implementation": { "name": "acp-agent-py", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s4-006",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-api", "principal_type": "agent" },
  "ts": "2026-03-28T10:00:05Z",
  "payload": {
    "display_name": "Bob's API Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "op.commit", "conflict.report"],
    "implementation": { "name": "acp-agent-py", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s4-007",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-db", "principal_type": "agent" },
  "ts": "2026-03-28T10:00:06Z",
  "payload": {
    "display_name": "Bob's Database Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "op.commit", "conflict.report"],
    "implementation": { "name": "acp-agent-py", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s4-008",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-test", "principal_type": "agent" },
  "ts": "2026-03-28T10:00:07Z",
  "payload": {
    "display_name": "Bob's Test Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "op.commit", "conflict.report"],
    "implementation": { "name": "acp-agent-py", "version": "0.1.0" }
  }
}
```

At this point, the session has 8 participants. The vector clock tracks all 8 principals.

#### Step 2 — All six agents announce intents (in parallel)

Bob's three agents announce their backend work:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s4-010",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-db", "principal_type": "agent" },
  "ts": "2026-03-28T10:01:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 1, "alice-ui": 1, "alice-state": 1, "alice-test": 1, "bob-api": 1, "bob-db": 1, "bob-test": 1 } },
  "payload": {
    "intent_id": "intent-db-tables",
    "objective": "Create dashboard_widgets and dashboard_layouts tables with foreign keys to users",
    "scope": {
      "kind": "file_set",
      "resources": ["migrations/010_dashboard_tables.sql", "src/models/dashboard.py"]
    },
    "assumptions": [
      "Widget data is JSON stored in a JSONB column",
      "Layout references widgets by UUID",
      "Soft-delete via deleted_at column"
    ],
    "priority": "high",
    "ttl_sec": 300
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s4-011",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-api", "principal_type": "agent" },
  "ts": "2026-03-28T10:01:05Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 1, "alice-ui": 1, "alice-state": 1, "alice-test": 1, "bob-api": 1, "bob-db": 2, "bob-test": 1 } },
  "payload": {
    "intent_id": "intent-api-endpoints",
    "objective": "Implement REST endpoints: GET/POST/PUT/DELETE /api/v1/dashboards and /api/v1/dashboards/{id}/widgets",
    "scope": {
      "kind": "file_set",
      "resources": ["src/routes/dashboard.py", "src/services/dashboard_service.py", "api/dashboard.openapi.yaml"]
    },
    "assumptions": [
      "OpenAPI spec is the source of truth for request/response shapes",
      "Pagination uses cursor-based approach",
      "Widget config is opaque JSON from the API's perspective"
    ],
    "priority": "high",
    "ttl_sec": 300
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s4-012",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-test", "principal_type": "agent" },
  "ts": "2026-03-28T10:01:10Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 1, "alice-ui": 1, "alice-state": 1, "alice-test": 1, "bob-api": 2, "bob-db": 2, "bob-test": 1 } },
  "payload": {
    "intent_id": "intent-backend-tests",
    "objective": "Write integration tests for dashboard API endpoints against real database",
    "scope": {
      "kind": "file_set",
      "resources": ["tests/integration/test_dashboard_api.py", "tests/fixtures/dashboard_fixtures.py"]
    },
    "assumptions": [
      "Tests run after bob-db and bob-api have committed",
      "Test database is seeded by fixtures, not production data"
    ],
    "priority": "normal",
    "ttl_sec": 600
  }
}
```

Alice's three agents announce their frontend work:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s4-013",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-ui", "principal_type": "agent" },
  "ts": "2026-03-28T10:01:15Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 1, "alice-ui": 1, "alice-state": 1, "alice-test": 1, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
  "payload": {
    "intent_id": "intent-ui-components",
    "objective": "Build DashboardGrid, WidgetCard, and AddWidgetModal React components",
    "scope": {
      "kind": "file_set",
      "resources": [
        "src/components/Dashboard/DashboardGrid.tsx",
        "src/components/Dashboard/WidgetCard.tsx",
        "src/components/Dashboard/AddWidgetModal.tsx",
        "src/components/Dashboard/index.ts"
      ]
    },
    "assumptions": [
      "Widget types: chart, table, metric, text",
      "Grid layout uses react-grid-layout",
      "API response shape matches api/dashboard.openapi.yaml"
    ],
    "priority": "high",
    "ttl_sec": 300
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s4-014",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-state", "principal_type": "agent" },
  "ts": "2026-03-28T10:01:20Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 1, "alice-ui": 2, "alice-state": 1, "alice-test": 1, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
  "payload": {
    "intent_id": "intent-state-management",
    "objective": "Create Redux slice for dashboard state: widget CRUD, layout persistence, and API integration hooks",
    "scope": {
      "kind": "file_set",
      "resources": [
        "src/store/dashboardSlice.ts",
        "src/hooks/useDashboard.ts",
        "src/api/dashboardApi.ts",
        "api/dashboard.openapi.yaml"
      ]
    },
    "assumptions": [
      "Uses RTK Query for API calls",
      "Optimistic updates for drag-and-drop layout changes",
      "API response shape matches api/dashboard.openapi.yaml"
    ],
    "priority": "high",
    "ttl_sec": 300
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s4-015",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-test", "principal_type": "agent" },
  "ts": "2026-03-28T10:01:25Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 1, "alice-ui": 2, "alice-state": 2, "alice-test": 1, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
  "payload": {
    "intent_id": "intent-frontend-tests",
    "objective": "Write component tests for DashboardGrid and WidgetCard, and integration tests for dashboard hooks",
    "scope": {
      "kind": "file_set",
      "resources": [
        "src/components/Dashboard/__tests__/DashboardGrid.test.tsx",
        "src/components/Dashboard/__tests__/WidgetCard.test.tsx",
        "src/hooks/__tests__/useDashboard.test.ts"
      ]
    },
    "assumptions": [
      "Tests run after alice-ui and alice-state have committed",
      "Uses MSW for API mocking in component tests"
    ],
    "priority": "normal",
    "ttl_sec": 600
  }
}
```

At this point, all six intents are visible to all eight participants. Every agent can see what every other agent plans to do.

#### Step 3 — Cross-team conflict: OpenAPI spec ownership

Two agents from different teams both declared intent to modify the shared API contract (`api/dashboard.openapi.yaml`) — Bob's API agent and Alice's state management agent. Alice's state agent detects this:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-s4-020",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-state", "principal_type": "agent" },
  "ts": "2026-03-28T10:02:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 1, "alice-ui": 2, "alice-state": 2, "alice-test": 2, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
  "payload": {
    "conflict_id": "conf-openapi-ownership",
    "related_intents": ["intent-api-endpoints", "intent-state-management"],
    "related_ops": [],
    "category": "scope_overlap",
    "severity": "high",
    "basis": { "kind": "rule", "rule_id": "scope.overlap.v1" },
    "based_on_watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 1, "alice-ui": 2, "alice-state": 2, "alice-test": 2, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
    "description": "Both agent:bob-api and agent:alice-state declare intent to modify api/dashboard.openapi.yaml. Concurrent edits to the shared API contract risk producing an inconsistent spec that breaks both frontend and backend.",
    "suggested_action": "human_review"
  }
}
```

#### Step 4 — Both humans negotiate a resolution

This is a cross-team conflict, so neither owner alone has authority. Bob proposes a resolution first:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-s4-030",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "human:bob", "principal_type": "human" },
  "ts": "2026-03-28T10:04:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 1, "alice-ui": 2, "alice-state": 3, "alice-test": 2, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
  "payload": {
    "resolution_id": "res-openapi-v1",
    "conflict_id": "conf-openapi-ownership",
    "decision": "merged",
    "outcome": {
      "accepted": ["intent-api-endpoints"],
      "rejected": [],
      "merged": ["intent-state-management"]
    },
    "rationale": "Proposal: bob-api owns the OpenAPI spec and writes it first. alice-state reads the committed spec as input and generates its TypeScript types from it, but does not write to the YAML. This gives backend authority over the contract while frontend consumes it."
  }
}
```

Alice's state agent disputes — it needs to add a `x-frontend-widget-types` extension to the spec that the backend wouldn't know about:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_ACK",
  "message_id": "msg-s4-031",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-state", "principal_type": "agent" },
  "ts": "2026-03-28T10:04:30Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 2, "alice-ui": 2, "alice-state": 3, "alice-test": 2, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
  "payload": {
    "conflict_id": "conf-openapi-ownership",
    "ack_type": "disputed"
  }
}
```

Alice steps in with a counter-resolution:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-s4-032",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "human:alice", "principal_type": "human" },
  "ts": "2026-03-28T10:05:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 1, "bob": 2, "alice-ui": 2, "alice-state": 4, "alice-test": 2, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
  "payload": {
    "resolution_id": "res-openapi-v2",
    "conflict_id": "conf-openapi-ownership",
    "decision": "merged",
    "outcome": {
      "accepted": ["intent-api-endpoints", "intent-state-management"],
      "rejected": [],
      "merged": []
    },
    "rationale": "Counter-proposal: bob-api writes the OpenAPI spec first (endpoints, schemas, responses). After bob-api commits, alice-state adds x-frontend-widget-types extensions to the same file. Sequential write, both contribute to the contract. The spec is a shared boundary — both teams need write access, just not concurrently."
  }
}
```

Bob acknowledges and accepts Alice's counter:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_ACK",
  "message_id": "msg-s4-033",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "human:bob", "principal_type": "human" },
  "ts": "2026-03-28T10:05:30Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 2, "alice-ui": 2, "alice-state": 4, "alice-test": 2, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
  "payload": {
    "conflict_id": "conf-openapi-ownership",
    "ack_type": "accepted"
  }
}
```

#### Step 5 — Parallel execution within teams, sequential across boundary

Now the agents execute. Within each team, independent agents work in parallel. Across the API boundary, they sequence.

**Bob's side — bob-db and bob-api work in parallel:**

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s4-040",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-db", "principal_type": "agent" },
  "ts": "2026-03-28T10:08:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 3, "alice-ui": 2, "alice-state": 4, "alice-test": 2, "bob-api": 2, "bob-db": 2, "bob-test": 2 } },
  "payload": {
    "op_id": "op-db-migration",
    "intent_id": "intent-db-tables",
    "target": "migrations/010_dashboard_tables.sql",
    "op_kind": "create",
    "state_ref_before": "sha256:empty",
    "state_ref_after": "sha256:db-mig-v1",
    "change_ref": "sha256:db-diff-001",
    "summary": "Created dashboard_widgets (UUID pk, user_id FK, widget_type, config JSONB, position, deleted_at) and dashboard_layouts (UUID pk, user_id FK, layout JSON, deleted_at) tables"
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s4-041",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-api", "principal_type": "agent" },
  "ts": "2026-03-28T10:10:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 3, "alice-ui": 2, "alice-state": 4, "alice-test": 2, "bob-api": 2, "bob-db": 3, "bob-test": 2 } },
  "payload": {
    "op_id": "op-api-openapi",
    "intent_id": "intent-api-endpoints",
    "target": "api/dashboard.openapi.yaml",
    "op_kind": "create",
    "state_ref_before": "sha256:empty",
    "state_ref_after": "sha256:openapi-v1",
    "change_ref": "sha256:openapi-diff-001",
    "summary": "Defined OpenAPI 3.1 spec: Dashboard and Widget CRUD endpoints, request/response schemas with cursor pagination, error responses"
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s4-042",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-api", "principal_type": "agent" },
  "ts": "2026-03-28T10:12:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 3, "alice-ui": 2, "alice-state": 4, "alice-test": 2, "bob-api": 3, "bob-db": 3, "bob-test": 2 } },
  "payload": {
    "op_id": "op-api-routes",
    "intent_id": "intent-api-endpoints",
    "target": "src/routes/dashboard.py",
    "op_kind": "create",
    "state_ref_before": "sha256:empty",
    "state_ref_after": "sha256:routes-v1",
    "change_ref": "sha256:routes-diff-001",
    "summary": "Implemented dashboard CRUD routes and widget sub-resource routes with service layer calls"
  }
}
```

**Alice's side — alice-ui starts immediately (no API dependency for component shells), alice-state waits for OpenAPI commit:**

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s4-050",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-ui", "principal_type": "agent" },
  "ts": "2026-03-28T10:09:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 3, "alice-ui": 2, "alice-state": 4, "alice-test": 2, "bob-api": 2, "bob-db": 3, "bob-test": 2 } },
  "payload": {
    "op_id": "op-ui-components",
    "intent_id": "intent-ui-components",
    "target": "src/components/Dashboard/DashboardGrid.tsx",
    "op_kind": "create",
    "state_ref_before": "sha256:empty",
    "state_ref_after": "sha256:grid-v1",
    "change_ref": "sha256:ui-diff-001",
    "summary": "Built DashboardGrid with react-grid-layout, WidgetCard with type-based rendering, and AddWidgetModal with widget type picker"
  }
}
```

Alice's state agent sees bob-api's OpenAPI commit arrive, and now proceeds:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s4-051",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-state", "principal_type": "agent" },
  "ts": "2026-03-28T10:13:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 3, "alice-ui": 3, "alice-state": 4, "alice-test": 2, "bob-api": 4, "bob-db": 3, "bob-test": 2 } },
  "payload": {
    "op_id": "op-state-slice",
    "intent_id": "intent-state-management",
    "target": "src/store/dashboardSlice.ts",
    "op_kind": "create",
    "state_ref_before": "sha256:empty",
    "state_ref_after": "sha256:slice-v1",
    "change_ref": "sha256:state-diff-001",
    "summary": "Created dashboardSlice with RTK Query endpoints generated from OpenAPI spec, optimistic layout update reducers, and widget CRUD actions"
  }
}
```

Alice's state agent then adds frontend extensions to the shared spec:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s4-052",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-state", "principal_type": "agent" },
  "ts": "2026-03-28T10:14:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 3, "alice-ui": 3, "alice-state": 5, "alice-test": 2, "bob-api": 4, "bob-db": 3, "bob-test": 2 } },
  "payload": {
    "op_id": "op-openapi-extensions",
    "intent_id": "intent-state-management",
    "target": "api/dashboard.openapi.yaml",
    "op_kind": "replace",
    "state_ref_before": "sha256:openapi-v1",
    "state_ref_after": "sha256:openapi-v2",
    "change_ref": "sha256:openapi-ext-diff-001",
    "summary": "Added x-frontend-widget-types extension with chart/table/metric/text type metadata for frontend code generation"
  }
}
```

#### Step 6 — Intra-team conflict: assumption mismatch within Bob's agents

Bob's test agent starts writing tests and discovers that bob-api used offset pagination in the actual implementation despite the intent stating cursor-based:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-s4-060",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-test", "principal_type": "agent" },
  "ts": "2026-03-28T10:15:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 3, "alice-ui": 3, "alice-state": 6, "alice-test": 2, "bob-api": 4, "bob-db": 3, "bob-test": 2 } },
  "payload": {
    "conflict_id": "conf-pagination-mismatch",
    "related_intents": ["intent-api-endpoints", "intent-state-management"],
    "related_ops": ["op-api-routes", "op-state-slice"],
    "category": "assumption_contradiction",
    "severity": "high",
    "basis": { "kind": "model_inference" },
    "based_on_watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 3, "alice-ui": 3, "alice-state": 6, "alice-test": 2, "bob-api": 4, "bob-db": 3, "bob-test": 2 } },
    "description": "bob-api's intent declared cursor-based pagination, but the committed routes use offset/limit parameters. alice-state's RTK Query hooks were generated assuming cursor pagination from the OpenAPI spec. The committed implementation and the spec are inconsistent — frontend API calls will fail.",
    "suggested_action": "human_review"
  }
}
```

#### Step 7 — Bob resolves within his team, triggering a cross-team fix

Bob owns the backend, so he can resolve the pagination question:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-s4-070",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "human:bob", "principal_type": "human" },
  "ts": "2026-03-28T10:17:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 3, "alice-ui": 3, "alice-state": 6, "alice-test": 2, "bob-api": 4, "bob-db": 3, "bob-test": 3 } },
  "payload": {
    "resolution_id": "res-pagination",
    "conflict_id": "conf-pagination-mismatch",
    "decision": "human_override",
    "outcome": {
      "accepted": [],
      "rejected": [],
      "merged": ["intent-api-endpoints", "intent-state-management"]
    },
    "rationale": "The spec said cursor, the implementation did offset — spec is correct. bob-api must fix routes to use cursor pagination. After bob-api commits the fix, alice-state should regenerate RTK Query hooks to confirm compatibility."
  }
}
```

Bob's API agent fixes and supersedes:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_SUPERSEDE",
  "message_id": "msg-s4-071",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-api", "principal_type": "agent" },
  "ts": "2026-03-28T10:19:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 4, "alice-ui": 3, "alice-state": 6, "alice-test": 2, "bob-api": 4, "bob-db": 3, "bob-test": 3 } },
  "payload": {
    "op_id": "op-api-routes-v2",
    "supersedes_op_id": "op-api-routes",
    "intent_id": "intent-api-endpoints",
    "target": "src/routes/dashboard.py",
    "reason": "pagination_fix_per_resolution"
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s4-072",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-api", "principal_type": "agent" },
  "ts": "2026-03-28T10:20:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 4, "alice-ui": 3, "alice-state": 6, "alice-test": 2, "bob-api": 5, "bob-db": 3, "bob-test": 3 } },
  "payload": {
    "op_id": "op-api-routes-v2",
    "intent_id": "intent-api-endpoints",
    "target": "src/routes/dashboard.py",
    "op_kind": "replace",
    "state_ref_before": "sha256:routes-v1",
    "state_ref_after": "sha256:routes-v2",
    "change_ref": "sha256:routes-fix-diff-001",
    "summary": "Fixed dashboard routes to use cursor-based pagination (after/before cursors) matching OpenAPI spec"
  }
}
```

#### Step 8 — Test agents run after all commits stabilize

Both test agents were waiting for upstream commits. Now they execute:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s4-080",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-test", "principal_type": "agent" },
  "ts": "2026-03-28T10:25:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 4, "alice-ui": 3, "alice-state": 6, "alice-test": 2, "bob-api": 6, "bob-db": 3, "bob-test": 3 } },
  "payload": {
    "op_id": "op-backend-tests",
    "intent_id": "intent-backend-tests",
    "target": "tests/integration/test_dashboard_api.py",
    "op_kind": "create",
    "state_ref_before": "sha256:empty",
    "state_ref_after": "sha256:btests-v1",
    "change_ref": "sha256:btest-diff-001",
    "summary": "Wrote 14 integration tests covering CRUD, cursor pagination, soft delete, and error cases — all passing against routes-v2"
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s4-081",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:alice-test", "principal_type": "agent" },
  "ts": "2026-03-28T10:26:00Z",
  "watermark": { "kind": "vector_clock", "value": { "alice": 2, "bob": 4, "alice-ui": 3, "alice-state": 6, "alice-test": 2, "bob-api": 6, "bob-db": 3, "bob-test": 4 } },
  "payload": {
    "op_id": "op-frontend-tests",
    "intent_id": "intent-frontend-tests",
    "target": "src/components/Dashboard/__tests__/DashboardGrid.test.tsx",
    "op_kind": "create",
    "state_ref_before": "sha256:empty",
    "state_ref_after": "sha256:ftests-v1",
    "change_ref": "sha256:ftest-diff-001",
    "summary": "Wrote 11 component tests for DashboardGrid and WidgetCard, plus 6 hook integration tests with MSW mocks matching OpenAPI v2 spec — all passing"
  }
}
```

#### Step 9 — Session wrap-up

Both teams' work is done. Agents depart:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "GOODBYE",
  "message_id": "msg-s4-090",
  "session_id": "sess-dashboard-feature",
  "sender": { "principal_id": "agent:bob-test", "principal_type": "agent" },
  "ts": "2026-03-28T10:27:00Z",
  "payload": {
    "reason": "session_complete",
    "active_intents": [],
    "intent_disposition": "withdraw"
  }
}
```

(All other agents send similar `GOODBYE` messages.)

#### Summary: What MPAC Provided in This Scenario

This scenario had **8 participants** (2 humans + 6 agents) with **6 concurrent intents** producing **10+ operations** across a shared codebase. MPAC handled:

1. **Intra-team parallelism**: Within each team, agents with non-overlapping scopes worked simultaneously (bob-db + bob-api in parallel, alice-ui started before alice-state finished).

2. **Cross-team boundary coordination**: The shared OpenAPI spec was identified as a conflict point *before* either side wrote code. The humans negotiated a sequential write protocol through the resolution mechanism.

3. **Dependency ordering without a scheduler**: Test agents declared assumptions about upstream commits and naturally waited for the right watermark state. No central scheduler was needed — causal context in watermarks provided the ordering signal.

4. **Cross-team bug detection**: Bob's test agent caught a pagination mismatch that would have broken Alice's frontend. The conflict report linked both teams' intents, making it visible to both owners.

5. **Supersession with audit trail**: When bob-api fixed the pagination, `OP_SUPERSEDE` created a clear record of what changed and why, preserving the original commit for audit.

6. **Multi-party negotiation**: The OpenAPI ownership conflict required input from both humans. Bob's initial resolution was disputed via `CONFLICT_ACK(disputed)`, Alice counter-proposed, and Bob accepted — all as structured protocol messages with full traceability.

Without MPAC, these six agents would have been black boxes to each other. The pagination bug would have surfaced as a cryptic runtime error in staging. The OpenAPI conflict would have been a merge conflict with no record of who decided what. MPAC made the coordination explicit, auditable, and recoverable.

---

### Scenario 5: Family of Four Plans a Vacation — Everyday Multi-Agent Coordination

**Setting**: The Chen family — Dad (`human:dad`), Mom (`human:mom`), and two teenagers, Lily (`human:lily`) and Max (`human:max`) — are planning a week-long trip to Japan. Each family member has a personal AI travel agent that helps research and book on their behalf: `agent:dad-travel`, `agent:mom-travel`, `agent:lily-travel`, and `agent:max-travel`. Dad and Mom are co-owners (they hold the budget and make final calls). Lily and Max are contributors (they can propose but parents approve).

This scenario shows MPAC applied outside of software engineering — to a coordination problem that every family faces: planning a trip where everyone has different preferences, a shared budget, and a shared calendar, without things falling apart.

The shared state in this session is the trip plan — a structured object containing the itinerary (day-by-day schedule), the budget ledger, and the booking list.

#### Step 1 — Family joins the planning session

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s5-001",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:dad", "principal_type": "human" },
  "ts": "2026-03-28T19:00:00Z",
  "payload": {
    "display_name": "David Chen",
    "roles": ["owner", "arbiter"],
    "capabilities": ["governance.override", "conflict.report", "op.reject"],
    "implementation": { "name": "acp-family-app", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s5-002",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:mom", "principal_type": "human" },
  "ts": "2026-03-28T19:00:01Z",
  "payload": {
    "display_name": "Wei Chen",
    "roles": ["owner", "arbiter"],
    "capabilities": ["governance.override", "conflict.report", "op.reject"],
    "implementation": { "name": "acp-family-app", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s5-003",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:lily", "principal_type": "human" },
  "ts": "2026-03-28T19:00:02Z",
  "payload": {
    "display_name": "Lily Chen",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "op.propose", "conflict.report"],
    "implementation": { "name": "acp-family-app", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s5-004",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:max", "principal_type": "human" },
  "ts": "2026-03-28T19:00:03Z",
  "payload": {
    "display_name": "Max Chen",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "op.propose", "conflict.report"],
    "implementation": { "name": "acp-family-app", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s5-005",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:dad-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:00:04Z",
  "payload": {
    "display_name": "Dad's Travel Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "op.commit", "conflict.report", "semantic.analysis"],
    "implementation": { "name": "acp-travel-agent", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s5-006",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:mom-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:00:05Z",
  "payload": {
    "display_name": "Mom's Travel Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "op.commit", "conflict.report", "semantic.analysis"],
    "implementation": { "name": "acp-travel-agent", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s5-007",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:lily-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:00:06Z",
  "payload": {
    "display_name": "Lily's Travel Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "conflict.report", "semantic.analysis"],
    "implementation": { "name": "acp-travel-agent", "version": "0.1.0" }
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "HELLO",
  "message_id": "msg-s5-008",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:max-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:00:07Z",
  "payload": {
    "display_name": "Max's Travel Agent",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "intent.update", "op.propose", "conflict.report", "semantic.analysis"],
    "implementation": { "name": "acp-travel-agent", "version": "0.1.0" }
  }
}
```

Note: Lily and Max's agents have `op.propose` but not `op.commit` — they can propose bookings but only parents can finalize them. This is MPAC governance in action.

#### Step 2 — Each agent researches and announces intent based on their human's preferences

Dad wants cultural and historical sightseeing. Mom wants good food and relaxation. Lily wants shopping and pop culture. Max wants gaming and anime. All four agents announce simultaneously:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s5-010",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:dad-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:05:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 1, "mom-travel": 1, "lily-travel": 1, "max-travel": 1 } },
  "payload": {
    "intent_id": "intent-dad-culture",
    "objective": "Plan cultural itinerary: Fushimi Inari (Day 2), Kinkaku-ji and Arashiyama (Day 3), Hiroshima day trip (Day 5)",
    "scope": {
      "kind": "entity_set",
      "entities": ["itinerary.day2.morning", "itinerary.day2.afternoon", "itinerary.day3.full", "itinerary.day5.full", "budget.activities"]
    },
    "assumptions": [
      "Trip is 7 days: Day 1 arrival, Day 7 departure",
      "Days 2-3 based in Kyoto, Days 4-6 based in Tokyo",
      "Total trip budget is $8,000 USD",
      "Hiroshima day trip uses JR Pass (already budgeted under transport)"
    ],
    "priority": "normal",
    "ttl_sec": 600
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s5-011",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:mom-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:05:05Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 2, "mom-travel": 1, "lily-travel": 1, "max-travel": 1 } },
  "payload": {
    "intent_id": "intent-mom-food",
    "objective": "Book dining experiences: Nishiki Market food tour (Day 2), kaiseki dinner in Kyoto (Day 3), Tsukiji outer market breakfast (Day 4), sushi omakase in Ginza (Day 6)",
    "scope": {
      "kind": "entity_set",
      "entities": ["itinerary.day2.lunch", "itinerary.day3.evening", "itinerary.day4.morning", "itinerary.day6.evening", "budget.dining"]
    },
    "assumptions": [
      "No seafood allergy in the family",
      "Kaiseki dinner budget: ~$300 for family of 4",
      "Omakase budget: ~$400 for family of 4",
      "Reservations need to be made 2 weeks in advance"
    ],
    "priority": "normal",
    "ttl_sec": 600
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s5-012",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:lily-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:05:10Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 2, "mom-travel": 2, "lily-travel": 1, "max-travel": 1 } },
  "payload": {
    "intent_id": "intent-lily-shopping",
    "objective": "Plan shopping and pop culture: Harajuku and Takeshita Street (Day 4), Shibuya 109 (Day 5), teamLab Borderless (Day 5 evening)",
    "scope": {
      "kind": "entity_set",
      "entities": ["itinerary.day4.afternoon", "itinerary.day5.morning", "itinerary.day5.afternoon", "itinerary.day5.evening", "budget.shopping", "budget.activities"]
    },
    "assumptions": [
      "Shopping budget for Lily: $200",
      "teamLab tickets: ~$35/person, $140 for family",
      "Days 4-6 are Tokyo days"
    ],
    "priority": "normal",
    "ttl_sec": 600
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-s5-013",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:max-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:05:15Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 2, "mom-travel": 2, "lily-travel": 2, "max-travel": 1 } },
  "payload": {
    "intent_id": "intent-max-anime",
    "objective": "Plan gaming and anime activities: Akihabara full day (Day 5), Pokémon Center Mega Tokyo (Day 4), Nintendo Tokyo in Shibuya (Day 6)",
    "scope": {
      "kind": "entity_set",
      "entities": ["itinerary.day4.afternoon", "itinerary.day5.full", "itinerary.day6.morning", "budget.shopping", "budget.activities"]
    },
    "assumptions": [
      "Shopping budget for Max: $200",
      "Akihabara needs a full day to explore properly",
      "Days 4-6 are Tokyo days"
    ],
    "priority": "normal",
    "ttl_sec": 600
  }
}
```

#### Step 3 — Conflict #1: Schedule collision between the teenagers

Mom's agent detects that Lily and Max both claimed Day 5 and Day 4 afternoon — the family travels together, so these are mutually exclusive:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-s5-020",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:mom-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:06:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 2, "mom-travel": 2, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "conflict_id": "conf-schedule-day5",
    "related_intents": ["intent-lily-shopping", "intent-max-anime"],
    "related_ops": [],
    "category": "resource_contention",
    "severity": "high",
    "basis": { "kind": "rule", "rule_id": "schedule.overlap.v1" },
    "based_on_watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 2, "mom-travel": 2, "lily-travel": 2, "max-travel": 2 } },
    "description": "Lily wants Shibuya 109 + teamLab on Day 5. Max wants Akihabara full day on Day 5. The family travels together — cannot split into two locations for a full day. Also, both claimed Day 4 afternoon (Lily: Harajuku, Max: Pokémon Center).",
    "suggested_action": "human_review"
  }
}
```

#### Step 4 — Conflict #2: Dad's plan conflicts with Lily's on Day 5

Dad's agent also notices that the Hiroshima day trip (Day 5) conflicts with both teenagers' Tokyo plans:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-s5-021",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:dad-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:06:10Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 2, "mom-travel": 3, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "conflict_id": "conf-hiroshima-vs-tokyo",
    "related_intents": ["intent-dad-culture", "intent-lily-shopping", "intent-max-anime"],
    "related_ops": [],
    "category": "semantic_goal_conflict",
    "severity": "high",
    "basis": { "kind": "model_inference" },
    "based_on_watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 2, "mom-travel": 3, "lily-travel": 2, "max-travel": 2 } },
    "description": "Dad's plan puts the family in Hiroshima for all of Day 5 (round-trip by Shinkansen). Lily and Max both have Tokyo activities planned for Day 5. The family cannot be in Hiroshima and Tokyo on the same day. This is a 3-way conflict involving 3 intents from 3 family members.",
    "suggested_action": "human_review"
  }
}
```

#### Step 5 — Conflict #3: Budget overrun detected

Mom's agent runs a budget check across all announced intents:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-s5-022",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:mom-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:07:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 3, "mom-travel": 3, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "conflict_id": "conf-budget-overrun",
    "related_intents": ["intent-dad-culture", "intent-mom-food", "intent-lily-shopping", "intent-max-anime"],
    "related_ops": [],
    "category": "resource_contention",
    "severity": "medium",
    "basis": { "kind": "heuristic" },
    "based_on_watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 3, "mom-travel": 3, "lily-travel": 2, "max-travel": 2 } },
    "description": "Preliminary budget tally across all 4 intents: activities ~$800, dining ~$900, shopping ~$400, transport (JR Pass x4) ~$1,100, accommodation (6 nights) ~$2,400, flights ~$3,200. Total: ~$8,800, exceeding the $8,000 budget by ~$800. The dining and flight categories are the largest contributors.",
    "suggested_action": "human_review"
  }
}
```

#### Step 6 — Parents resolve the schedule conflict (3-way)

Dad and Mom discuss. Mom proposes the resolution — Day 5 becomes a "split" day, and Hiroshima moves:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-s5-030",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:mom", "principal_type": "human" },
  "ts": "2026-03-28T19:15:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 1, "lily": 1, "max": 1, "dad-travel": 3, "mom-travel": 4, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "resolution_id": "res-schedule-day5",
    "conflict_id": "conf-hiroshima-vs-tokyo",
    "decision": "merged",
    "outcome": {
      "accepted": [],
      "rejected": [],
      "merged": ["intent-dad-culture", "intent-lily-shopping", "intent-max-anime"]
    },
    "rationale": "Move Hiroshima to Day 3 (swap with Kinkaku-ji, which moves to Day 2 afternoon after Fushimi Inari morning). Day 4: morning Pokémon Center together (Max happy), afternoon Harajuku together (Lily happy). Day 5: morning Akihabara together (Max), afternoon Shibuya 109 (Lily) + Nintendo Tokyo is in Shibuya Parco so Max can do both. Evening: teamLab together (everyone). This way nobody misses out."
  }
}
```

Dad confirms:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "CONFLICT_ACK",
  "message_id": "msg-s5-031",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:dad", "principal_type": "human" },
  "ts": "2026-03-28T19:15:30Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 1, "mom": 2, "lily": 1, "max": 1, "dad-travel": 3, "mom-travel": 4, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "conflict_id": "conf-hiroshima-vs-tokyo",
    "ack_type": "accepted"
  }
}
```

This also resolves the sibling schedule conflict:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-s5-032",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:mom", "principal_type": "human" },
  "ts": "2026-03-28T19:16:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 2, "mom": 2, "lily": 1, "max": 1, "dad-travel": 3, "mom-travel": 4, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "resolution_id": "res-schedule-siblings",
    "conflict_id": "conf-schedule-day5",
    "decision": "merged",
    "outcome": {
      "accepted": [],
      "rejected": [],
      "merged": ["intent-lily-shopping", "intent-max-anime"]
    },
    "rationale": "Resolved by the Day 5 restructure above. Lily and Max share Day 4 and Day 5 with alternating priority. See res-schedule-day5 for full plan."
  }
}
```

#### Step 7 — Parents resolve the budget conflict

Dad tackles the budget:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "RESOLUTION",
  "message_id": "msg-s5-033",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:dad", "principal_type": "human" },
  "ts": "2026-03-28T19:20:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 2, "mom": 3, "lily": 1, "max": 1, "dad-travel": 3, "mom-travel": 4, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "resolution_id": "res-budget",
    "conflict_id": "conf-budget-overrun",
    "decision": "merged",
    "outcome": {
      "accepted": ["intent-dad-culture", "intent-lily-shopping", "intent-max-anime"],
      "rejected": [],
      "merged": ["intent-mom-food"]
    },
    "rationale": "Drop the Ginza omakase (saves $400). Replace with a conveyor belt sushi experience in Shibuya on Day 5 evening before teamLab — still fun, budget-friendly (~$80 for family). Kids' shopping budgets stay at $200 each. Revised total: ~$8,080, close enough with some buffer from skipping small items. Mom's agent should update dining intent."
  }
}
```

#### Step 8 — All agents update intents based on resolutions

Each agent revises its plan to reflect the agreed schedule and budget:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_UPDATE",
  "message_id": "msg-s5-040",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:dad-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:22:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 3, "lily": 1, "max": 1, "dad-travel": 3, "mom-travel": 4, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "intent_id": "intent-dad-culture",
    "objective": "Plan cultural itinerary: Fushimi Inari morning + Kinkaku-ji afternoon (Day 2), Hiroshima day trip (Day 3), Meiji Shrine morning (Day 6)",
    "scope": {
      "kind": "entity_set",
      "entities": ["itinerary.day2.morning", "itinerary.day2.afternoon", "itinerary.day3.full", "itinerary.day6.morning", "budget.activities"]
    },
    "assumptions": [
      "Hiroshima moved to Day 3 per family resolution",
      "Arashiyama dropped to make room — can visit if time permits on Day 2 evening",
      "Day 6 morning free for Meiji Shrine before Nintendo Tokyo"
    ],
    "ttl_sec": 600
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_UPDATE",
  "message_id": "msg-s5-041",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:mom-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:22:05Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 3, "lily": 1, "max": 1, "dad-travel": 4, "mom-travel": 4, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "intent_id": "intent-mom-food",
    "objective": "Book dining: Nishiki Market food tour (Day 2 lunch), kaiseki dinner in Kyoto (Day 2 evening), Tsukiji breakfast (Day 4 morning), conveyor sushi in Shibuya (Day 5 evening)",
    "scope": {
      "kind": "entity_set",
      "entities": ["itinerary.day2.lunch", "itinerary.day2.evening", "itinerary.day4.morning", "itinerary.day5.evening", "budget.dining"]
    },
    "assumptions": [
      "Ginza omakase dropped per budget resolution",
      "Conveyor sushi replaces omakase (~$80 vs $400)",
      "Kaiseki moved to Day 2 evening (Kyoto night) instead of Day 3",
      "Revised dining budget: ~$580"
    ],
    "ttl_sec": 600
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_UPDATE",
  "message_id": "msg-s5-042",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:lily-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:22:10Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 3, "lily": 1, "max": 1, "dad-travel": 4, "mom-travel": 5, "lily-travel": 2, "max-travel": 2 } },
  "payload": {
    "intent_id": "intent-lily-shopping",
    "objective": "Plan shopping and pop culture: Harajuku afternoon (Day 4), Shibuya 109 afternoon (Day 5), teamLab Borderless evening (Day 5)",
    "scope": {
      "kind": "entity_set",
      "entities": ["itinerary.day4.afternoon", "itinerary.day5.afternoon", "itinerary.day5.evening", "budget.shopping", "budget.activities"]
    },
    "assumptions": [
      "Day 4 afternoon is Harajuku (shared with Max doing Pokémon Center in morning)",
      "Day 5 afternoon: Lily does Shibuya 109 while Max does Nintendo Tokyo — both in Shibuya",
      "teamLab is family evening activity"
    ],
    "ttl_sec": 600
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "INTENT_UPDATE",
  "message_id": "msg-s5-043",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:max-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:22:15Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 3, "lily": 1, "max": 1, "dad-travel": 4, "mom-travel": 5, "lily-travel": 3, "max-travel": 2 } },
  "payload": {
    "intent_id": "intent-max-anime",
    "objective": "Plan gaming and anime: Pokémon Center morning (Day 4), Akihabara morning (Day 5), Nintendo Tokyo Shibuya afternoon (Day 5)",
    "scope": {
      "kind": "entity_set",
      "entities": ["itinerary.day4.morning", "itinerary.day5.morning", "itinerary.day5.afternoon", "budget.shopping", "budget.activities"]
    },
    "assumptions": [
      "Pokémon Center Mega moved to Day 4 morning (shared day with Lily)",
      "Akihabara reduced to morning — still enough for key shops",
      "Nintendo Tokyo is in Shibuya Parco, same area as Lily's Shibuya 109"
    ],
    "ttl_sec": 600
  }
}
```

#### Step 9 — Agents propose bookings, parents approve

Now that all intents are aligned, agents start proposing concrete bookings. Since Lily and Max's agents only have `op.propose` (not `op.commit`), their bookings need parental approval:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_PROPOSE",
  "message_id": "msg-s5-050",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:mom-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:25:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 3, "lily": 1, "max": 1, "dad-travel": 4, "mom-travel": 5, "lily-travel": 3, "max-travel": 3 } },
  "payload": {
    "op_id": "op-kaiseki-reservation",
    "intent_id": "intent-mom-food",
    "target": "bookings.dining",
    "op_kind": "create",
    "change_ref": "booking:kaiseki-kikunoi-day2",
    "summary": "Reserve Kikunoi Kyoto kaiseki dinner, Day 2 (July 14), 18:30, party of 4. Cost: $280. Cancellation free until 48h before."
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_PROPOSE",
  "message_id": "msg-s5-051",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:lily-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:25:10Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 3, "lily": 1, "max": 1, "dad-travel": 4, "mom-travel": 6, "lily-travel": 3, "max-travel": 3 } },
  "payload": {
    "op_id": "op-teamlab-tickets",
    "intent_id": "intent-lily-shopping",
    "target": "bookings.activities",
    "op_kind": "create",
    "change_ref": "booking:teamlab-borderless-day5",
    "summary": "Book teamLab Borderless Azabudai, Day 5 (July 17), 18:00 entry, 4 tickets. Cost: $140 total. Non-refundable."
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_PROPOSE",
  "message_id": "msg-s5-052",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:dad-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:25:15Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 3, "lily": 1, "max": 1, "dad-travel": 4, "mom-travel": 6, "lily-travel": 4, "max-travel": 3 } },
  "payload": {
    "op_id": "op-hiroshima-tickets",
    "intent_id": "intent-dad-culture",
    "target": "bookings.transport",
    "op_kind": "create",
    "change_ref": "booking:hiroshima-shinkansen-day3",
    "summary": "Reserve Shinkansen Kyoto→Hiroshima round-trip, Day 3 (July 15), depart 08:15 arrive 09:55, return 17:30. Covered by 7-day JR Pass. Hiroshima Peace Memorial Museum tickets: $25 total for family."
  }
}
```

Mom approves all three in a batch — she commits the bookings that are within resolved intent scope:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s5-060",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:mom", "principal_type": "human" },
  "ts": "2026-03-28T19:30:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 3, "lily": 1, "max": 1, "dad-travel": 5, "mom-travel": 6, "lily-travel": 4, "max-travel": 3 } },
  "payload": {
    "op_id": "op-kaiseki-reservation",
    "intent_id": "intent-mom-food",
    "target": "bookings.dining",
    "op_kind": "create",
    "state_ref_before": "sha256:bookings-empty",
    "state_ref_after": "sha256:bookings-v1",
    "change_ref": "booking:kaiseki-kikunoi-day2",
    "summary": "Confirmed: Kikunoi kaiseki, July 14, 18:30, party of 4. $280."
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s5-061",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:mom", "principal_type": "human" },
  "ts": "2026-03-28T19:30:05Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 4, "lily": 1, "max": 1, "dad-travel": 5, "mom-travel": 6, "lily-travel": 4, "max-travel": 3 } },
  "payload": {
    "op_id": "op-teamlab-tickets",
    "intent_id": "intent-lily-shopping",
    "target": "bookings.activities",
    "op_kind": "create",
    "state_ref_before": "sha256:bookings-v1",
    "state_ref_after": "sha256:bookings-v2",
    "change_ref": "booking:teamlab-borderless-day5",
    "summary": "Confirmed: teamLab Borderless, July 17, 18:00, 4 tickets. $140."
  }
}
```

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s5-062",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "human:dad", "principal_type": "human" },
  "ts": "2026-03-28T19:30:10Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 3, "mom": 5, "lily": 1, "max": 1, "dad-travel": 5, "mom-travel": 6, "lily-travel": 4, "max-travel": 3 } },
  "payload": {
    "op_id": "op-hiroshima-tickets",
    "intent_id": "intent-dad-culture",
    "target": "bookings.transport",
    "op_kind": "create",
    "state_ref_before": "sha256:bookings-v2",
    "state_ref_after": "sha256:bookings-v3",
    "change_ref": "booking:hiroshima-shinkansen-day3",
    "summary": "Confirmed: Shinkansen Kyoto↔Hiroshima Day 3, Peace Memorial Museum. $25 + JR Pass."
  }
}
```

#### Step 10 — Final itinerary committed

After all bookings are approved, Dad's agent commits the consolidated itinerary:

```json
{
  "protocol": "MPAC",
  "version": "0.1.0",
  "message_type": "OP_COMMIT",
  "message_id": "msg-s5-070",
  "session_id": "sess-japan-trip-2026",
  "sender": { "principal_id": "agent:dad-travel", "principal_type": "agent" },
  "ts": "2026-03-28T19:35:00Z",
  "watermark": { "kind": "vector_clock", "value": { "dad": 4, "mom": 5, "lily": 1, "max": 1, "dad-travel": 5, "mom-travel": 6, "lily-travel": 4, "max-travel": 3 } },
  "payload": {
    "op_id": "op-final-itinerary",
    "intent_id": "intent-dad-culture",
    "target": "itinerary.final",
    "op_kind": "create",
    "state_ref_before": "sha256:itinerary-empty",
    "state_ref_after": "sha256:itinerary-v1",
    "change_ref": "sha256:itinerary-final-001",
    "summary": "Consolidated 7-day itinerary: Day 1 Arrive Osaka→Kyoto. Day 2 Fushimi Inari + Kinkaku-ji + Nishiki Market + kaiseki. Day 3 Hiroshima day trip. Day 4 Pokémon Center morning + Harajuku afternoon + Tsukiji breakfast. Day 5 Akihabara morning + Shibuya (109 + Nintendo Tokyo) afternoon + conveyor sushi + teamLab evening. Day 6 Meiji Shrine morning + free afternoon. Day 7 Depart. Budget: ~$8,080."
  }
}
```

#### Summary: What MPAC Provided in This Scenario

This scenario had **8 participants** (4 humans + 4 agents) planning a shared trip with **4 intents** representing each family member's preferences. MPAC handled three types of real-world coordination problems:

1. **Schedule conflicts (resource contention)**: Two teenagers wanted different activities on the same day. Dad's day trip competed with the kids' city plans. MPAC surfaced these as structured `CONFLICT_REPORT` messages *before* anything was booked, letting the family negotiate openly rather than discovering clashes after non-refundable tickets were purchased.

2. **Budget conflict (resource contention)**: All four agents independently planned activities that collectively exceeded the family budget. Mom's agent detected this by summing across all intents — something no single agent would have caught in isolation. The budget conflict was resolved by dropping one expensive dinner, a decision made by a human with full visibility into the tradeoffs.

3. **Governance through family roles**: Parents were `owner` + `arbiter`; kids were `contributor` only. The teenagers' agents could propose bookings (`op.propose`) but could not finalize them (`op.commit`). Only parents could commit. This mirrors real family dynamics — the kids have a voice in planning, but Mom and Dad hold the credit card.

4. **Intent-first planning prevents costly mistakes**: Because every agent announced intent (with assumptions and scope) before booking anything, the family caught the Hiroshima-vs-Tokyo conflict, the sibling schedule overlap, and the budget overrun all at the planning stage. Without MPAC, agents might have booked non-refundable teamLab tickets for an evening when the family was supposed to be on a Shinkansen back from Hiroshima.

5. **Multi-party resolution**: The Day 5 conflict involved three family members and required a creative compromise (morning/afternoon rotation + geographic co-location in Shibuya). The `merged` outcome let all three intents survive in modified form rather than picking a single winner.

This scenario demonstrates that MPAC is not limited to software engineering. Any situation where multiple people (each with their own AI agent) need to coordinate over shared resources — time, money, physical space — can benefit from explicit intent declaration, conflict detection, and governed resolution.
