# MPAC Specification v0.1.14

## 1. Status

This document defines version `0.1.14` of the Multi-Principal Agent Coordination Protocol (`MPAC`).

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

### 7.7 Consistency Model

MPAC provides different consistency guarantees depending on coordinator availability:

1. **Coordinator-available (normal operation)**: The session coordinator serializes all state-mutating messages (`OP_COMMIT`, `OP_BATCH_COMMIT`, `RESOLUTION`, `INTENT_CLAIM` approval, state transitions). This provides a **total order** over all state mutations within a session. Participants observe a consistent, linearized sequence of state changes. The coordinator's Lamport clock serves as the authoritative ordering mechanism.

2. **Coordinator-unavailable (degraded operation)**: When participants detect coordinator unavailability (Section 8.1.1.1), the protocol enters degraded mode. In this mode, participants MUST NOT perform state-mutating operations (no `OP_COMMIT`, no `OP_BATCH_COMMIT`, no `RESOLUTION`). Read-only and non-conflicting local activities (e.g., planning, analysis) MAY continue. No consistency guarantee is provided for local activities performed during degraded mode.

3. **Coordinator recovery (reconciliation)**: Upon coordinator recovery (Section 8.1.1.3), the coordinator reconstructs authoritative state from its last snapshot plus audit log replay. If any participant performed state mutations during the coordinator's absence (violating rule 2), the coordinator MUST detect the divergence via `STATE_DIVERGENCE` and the session MUST reconcile before resuming normal operation. Reconciliation requires governance-level resolution — the protocol does not automatically merge divergent states.

MPAC does NOT provide linearizability in the strict distributed systems sense, because participants may observe state changes with transport-dependent delay. MPAC provides **coordinator-serialized total order**: all mutations are ordered by the coordinator, and participants eventually observe the same order. This is analogous to a single-leader replication model.

### 7.8 Execution Model

MPAC defines two execution models for operations. Sessions MUST declare which execution model they use in `SESSION_INFO` (via the `execution_model` field). The two models MUST NOT be mixed within a single session.

1. **Pre-commit model** (`execution_model`: `pre_commit`): The mutation is NOT applied to shared state until the session coordinator explicitly authorizes execution. The canonical flow is `OP_PROPOSE` -> coordinator validation / review -> authorization -> proposer executes -> `OP_COMMIT`. Authorization alone does **not** transition the operation to `COMMITTED`; the operation becomes `COMMITTED` only when the proposer later declares the executed mutation via `OP_COMMIT`. For backward compatibility, implementations MAY accept an initial `OP_COMMIT` as the request-to-commit step in pre-commit sessions; when they do, that message MUST enter the `PROPOSED` lifecycle state and MUST NOT be treated as an already-applied mutation. This model REQUIRES Governance Profile compliance because it depends on proposal / rejection semantics and explicit authority handling. It is RECOMMENDED for Governance Profile sessions and cross-organizational deployments where mutations must be reviewed before taking effect.

2. **Post-commit model** (`execution_model`: `post_commit`): The agent applies the mutation to shared state first, then declares the completed mutation via `OP_COMMIT`. In this model, `OP_COMMIT` is a **notification of a completed mutation**. The `state_ref_before` and `state_ref_after` fields reflect the actual state change that has already occurred. If a conflict is later detected, resolution may require a **compensating operation** (a new `OP_COMMIT` that reverses the effect). This model is suitable for Core Profile sessions and intra-team deployments where agents are trusted to act independently.

Key implications:
- In pre-commit model, `OP_REJECT` prevents the mutation from occurring because execution authorization was denied before the mutation was declared as committed. In post-commit model, `OP_REJECT` signals that the already-applied mutation is contested and may require rollback.
- In pre-commit model, authorization MUST be explicit, attributable, and tied to a specific `op_id` or `batch_id`, but MUST NOT by itself transition the operation to `COMMITTED`. The exact authorization carrier MAY be implementation-defined, but it MUST unambiguously identify the authorized proposal and MUST be generated by the coordinator or another actor whose authority is mediated by the coordinator. In post-commit model, no prior authorization is required.
- `OP_BATCH_COMMIT` (Section 16.8) follows the same execution model as `OP_COMMIT`: in pre-commit model a batch MUST NOT be applied before coordinator authorization; in post-commit model the batch message declares an already-executed batch.
- Core Profile sessions MUST use `post_commit`. Sessions that declare `pre_commit` MUST also declare Governance Profile compliance.
- If no `execution_model` is declared in `SESSION_INFO`, implementations MUST default to `post_commit` for backward compatibility with MPAC versions prior to v0.1.7.

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

Many MPAC features — including heartbeat-based unavailability detection (Section 14.7), sender identity binding (Section 23.3), frozen scope enforcement (Section 18.6), and tamper-evident logging (Section 23.1.3) — require a component with a unified view of session state and the authority to enforce protocol-level decisions.

MPAC defines this component as the **session coordinator**. A session coordinator is a `service`-type principal responsible for:
- maintaining the authoritative session state (participant roster, intent registry, conflict state)
- enforcing message ordering constraints (Section 8.2)
- performing liveness detection and unavailability transitions (Section 14.7)
- validating sender identity binding in Authenticated and Verified profiles (Section 23.1)
- maintaining audit logs

Every session MUST have exactly one logical session coordinator. The coordinator MAY be implemented as a dedicated server, a message broker, or a designated participant, but its responsibilities MUST NOT be split across multiple independent components without a consensus mechanism.

In deployments where a centralized coordinator is unavailable, implementations MUST provide an equivalent distributed mechanism (e.g., consensus protocol) that satisfies the same guarantees. The specifics of such mechanisms are outside the scope of MPAC.

Note: MPAC remains transport-independent. The session coordinator is a logical role, not a transport requirement. It MAY be co-located with a WebSocket server, message broker, or any other infrastructure component.

#### 8.1.1 Coordinator Fault Recovery

The session coordinator is a single logical point of authority. If the coordinator becomes unavailable, all coordinator-dependent functions — including liveness detection (Section 14.7), frozen scope enforcement (Section 18.6), sender identity binding (Section 23.3), and intent expiry cascade (Section 15.7) — cease to operate.

##### 8.1.1.1 Coordinator Liveness

The coordinator MUST periodically broadcast a `COORDINATOR_STATUS` message (Section 14.6) to all participants at a configurable interval (default: same as `heartbeat_interval_sec`). This message serves as the coordinator's own liveness signal and carries a summary of session health.

Participants MUST detect coordinator unavailability through the absence of `COORDINATOR_STATUS` messages for a duration exceeding `2 × heartbeat_interval_sec`. Upon detection, participants MUST:
- suspend all conflict-sensitive operations (operations whose scope overlaps with any active intent from another participant)
- continue read-only or non-conflicting activities
- attempt reconnection at regular intervals
- NOT unilaterally transition intents, operations, or conflicts — these state transitions remain coordinator-exclusive

##### 8.1.1.2 State Snapshot

The coordinator MUST persist session state to durable storage at least once per heartbeat interval. The state snapshot MUST include the following components:

```json
{
  "snapshot_version": 2,
  "session_id": "sess-001",
  "protocol_version": "0.1.14",
  "captured_at": "2026-04-03T12:00:00Z",
  "coordinator_epoch": 4,
  "lamport_clock": 42,
  "anti_replay": {
    "replay_window_sec": 300,
    "recent_message_ids": ["msg-101", "msg-102"],
    "sender_frontier": {
      "agent:alice|inst-01": {
        "last_ts": "2026-04-03T11:59:30Z",
        "last_lamport": 41
      }
    }
  },
  "participants": [
    {
      "principal_id": "agent:alice",
      "display_name": "Alice",
      "roles": ["contributor"],
      "status": "working",
      "is_available": true,
      "last_seen": "2026-04-03T11:59:30Z"
    }
  ],
  "intents": [
    {
      "intent_id": "intent-001",
      "principal_id": "agent:alice",
      "state": "ACTIVE",
      "scope": { "kind": "file_set", "resources": ["auth.py"] },
      "expires_at": "2026-04-03T12:05:00Z"
    }
  ],
  "operations": [
    {
      "op_id": "op-001",
      "intent_id": "intent-001",
      "state": "PROPOSED",
      "target": "auth.py"
    }
  ],
  "conflicts": [
    {
      "conflict_id": "conf-001",
      "state": "OPEN",
      "related_intents": ["intent-001", "intent-002"],
      "related_ops": []
    }
  ],
  "governance_policy": {},
  "liveness_policy": {}
}
```

The snapshot format is a JSON object. Implementations MAY extend it with additional fields but MUST preserve the fields listed above. Implementations SHOULD use a write-ahead or atomic write mechanism to prevent snapshot corruption.

The coordinator MUST initialize `coordinator_epoch` to `1` at session creation. Authenticated and Verified profile implementations MUST persist enough anti-replay checkpoint state in `anti_replay` to continue enforcing the same replay-protection policy after recovery. Implementations MAY use a different internal representation, but the persisted snapshot MUST preserve enough information to restore duplicate-message rejection and sender-frontier checks across the configured replay window.

##### 8.1.1.3 Coordinator Recovery

Upon restart, the coordinator MUST:

1. Load the most recent valid state snapshot
2. Restore `coordinator_epoch` from the snapshot and adopt a new authority epoch before emitting any new coordinator-authored messages. If a planned handover supplied `next_coordinator_epoch`, the recovering coordinator MUST use that value. Otherwise, it MUST set `coordinator_epoch = snapshot.coordinator_epoch + 1`
3. Restore anti-replay checkpoint state before accepting new post-recovery messages in Authenticated or Verified profile sessions
4. If a tamper-evident audit log is available (Section 23.1.3), replay any messages logged after the snapshot's `captured_at` timestamp to reconstruct the current state
5. Broadcast a `COORDINATOR_STATUS` message with `event`: `recovered` to all participants at their last-known transport addresses
6. Accept `HELLO` messages from reconnecting participants and reconcile their state against the recovered snapshot — if a participant's local state diverges from the snapshot (e.g., they committed an operation during the coordinator's absence), the coordinator SHOULD emit a `PROTOCOL_ERROR` with `error_code`: `STATE_DIVERGENCE` and include the divergent message IDs for manual or governance-level resolution

Participants that reconnect after coordinator recovery without restarting their own process SHOULD preserve the same `sender.sender_instance_id` and continue their Lamport counter (Section 12.7). A participant that has restarted MAY generate a new `sender_instance_id`, in which case Lamport monotonicity is evaluated for the new sender incarnation rather than the prior one.

##### 8.1.1.4 Coordinator Handover

When a coordinator needs to be replaced (planned maintenance, failover to standby), the handover process is:

1. **Planned handover**: The outgoing coordinator broadcasts a `COORDINATOR_STATUS` message with `event`: `handover`, `successor_coordinator_id`, and `next_coordinator_epoch` identifying the new coordinator and the epoch it will assume. The outgoing coordinator MUST transfer the latest state snapshot to the successor through an implementation-defined mechanism. The successor coordinator MUST begin sending coordinator-authored messages only with `coordinator_epoch = next_coordinator_epoch`, and MUST broadcast a `COORDINATOR_STATUS` with `event`: `assumed` upon taking over. Participants MUST re-send `HELLO` to the new coordinator to re-establish session presence. Participants whose process has not restarted MUST preserve their `sender.sender_instance_id` and local Lamport counter when doing so.

2. **Unplanned failover**: If the outgoing coordinator does not send a handover message (crash), a standby coordinator MAY assume the role after detecting the primary's absence for `2 × heartbeat_interval_sec`. The standby MUST load the most recent shared state snapshot, restore anti-replay checkpoint state if required by the session's security profile, and follow the recovery procedure in Section 8.1.1.3. Participants detect the new coordinator through receipt of `COORDINATOR_STATUS` from a different `sender.principal_id` or from a higher `coordinator_epoch`.

3. **Split-brain prevention**: At any given time, only one coordinator MAY broadcast `COORDINATOR_STATUS` for a session. If a participant receives coordinator-authored messages from two different coordinators within the same session, it MUST compare `coordinator_epoch` first. Messages from the coordinator with the lower epoch are stale and MUST be rejected. If both coordinators claim the same epoch, the participant MUST compare their Lamport watermark values when present, reject messages from the coordinator with the lower Lamport value, and SHOULD send a `PROTOCOL_ERROR` with `error_code`: `COORDINATOR_CONFLICT` to both coordinators. Implementations using consensus-based replication (e.g., Raft, Paxos) MAY use their consensus mechanism instead of equal-epoch Lamport comparison, but MUST ensure the single-coordinator invariant.

Implementations MAY additionally support hot standby or consensus-based replication for zero-downtime failover, but the specifics of such mechanisms are outside the scope of MPAC. The protocol requires only that the single-coordinator invariant is maintained and that state transfer follows the snapshot format defined in Section 8.1.1.2.

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
- a liveness policy for unavailability detection (Section 14.7.5); defaults apply if not specified

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

### 9.6 Session Completion and Close

A session has a defined beginning (HELLO → SESSION_INFO) and a defined end (SESSION_CLOSE). This section defines the conditions under which a session ends and the required behaviors.

#### 9.6.1 Session Close Conditions

A session MAY be closed under any of the following conditions:

1. **Manual close**: A participant with `owner` or `arbiter` role requests session close through an implementation-defined mechanism. The coordinator sends `SESSION_CLOSE` with `reason`: `manual`.

2. **Auto-close on completion**: When all of the following conditions are met, the coordinator MAY automatically close the session:
   - all intents are in a terminal state (EXPIRED, WITHDRAWN, SUPERSEDED, or TRANSFERRED)
   - all operations are in a settled state (`COMMITTED`, `REJECTED`, `ABANDONED`, or `SUPERSEDED`; see Section 16.6.1)
   - all conflicts are CLOSED or DISMISSED
   - no participants have `status`: `working` or `blocked`

   Auto-close is opt-in. Sessions MAY configure `auto_close: true` in session policy. When enabled, the coordinator SHOULD wait a grace period (default: 60 seconds) after conditions are met before closing, to allow participants to announce new intents.

3. **Session TTL**: Sessions MAY configure a `session_ttl_sec` in session policy. When the session's elapsed time exceeds this value, the coordinator MUST send `SESSION_CLOSE` with `reason`: `timeout`. Recommended default: no TTL (sessions are open-ended).

4. **Coordinator shutdown**: If the coordinator is shutting down and no successor is available for handover (Section 8.1.1.4), it MUST send `SESSION_CLOSE` with `reason`: `coordinator_shutdown` before terminating.

#### 9.6.2 Session Summary

The `SESSION_CLOSE` message SHOULD include a `summary` object providing aggregate statistics for the session:

```json
{
  "total_intents": 8,
  "completed_intents": 5,
  "expired_intents": 2,
  "withdrawn_intents": 1,
  "total_operations": 12,
  "committed_operations": 9,
  "rejected_operations": 2,
  "abandoned_operations": 1,
  "total_conflicts": 3,
  "resolved_conflicts": 3,
  "total_participants": 4,
  "duration_sec": 3600
}
```

#### 9.6.3 Session Transcript and Audit Export

For compliance and auditability, implementations SHOULD support exporting a complete session transcript. The transcript is an ordered array of all `MessageEnvelope` objects exchanged during the session, sorted by Lamport clock value (with `(sender.principal_id, sender.sender_instance_id)` as the tiebreaker).

The transcript format:

```json
{
  "session_id": "sess-001",
  "protocol_version": "0.1.14",
  "exported_at": "2026-04-03T12:00:00Z",
  "security_profile": "authenticated",
  "participants": [ /* Principal objects */ ],
  "messages": [ /* MessageEnvelope objects in causal order */ ],
  "final_snapshot": { /* State snapshot per Section 8.1.1.2 */ }
}
```

Implementations operating under the Authenticated or Verified security profile (Section 23.1) MUST retain the session transcript for at least the duration configured in `audit_retention_days`. The transcript MAY be stored in the coordinator's durable storage or exported to an external audit system.

#### 9.6.4 Session Policy for Lifecycle

```json
{
  "lifecycle": {
    "auto_close": false,
    "auto_close_grace_sec": 60,
    "session_ttl_sec": 0,
    "transcript_export": true,
    "audit_retention_days": 90
  }
}
```

A `session_ttl_sec` value of `0` disables session TTL (session is open-ended). An `audit_retention_days` value of `0` means retain for session duration only.

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
  "version": "0.1.14",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "7c5f3d51-fd2b-4e89-8a5e-55f72dbf32ab",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:alice-coder-1",
    "principal_type": "agent",
    "sender_instance_id": "inst-01"
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

The `sender` object MUST include:
- `principal_id`
- `principal_type`
- `sender_instance_id`

### 11.3 Optional Envelope Fields

An MPAC message MAY include:
- `watermark`
- `in_reply_to`
- `trace_id`
- `policy_ref`
- `signature`
- `coordinator_epoch`
- `extensions`

### 11.4 Envelope Semantics

- `protocol` MUST be `MPAC`
- `version` MUST identify the MPAC message format version
- `message_id` MUST be unique within practical system scope
- `ts` MUST use RFC 3339 / ISO 8601 UTC timestamps
- `sender.sender_instance_id` MUST identify the sender's session-local process incarnation; Lamport monotonicity and sender-frontier replay checks apply per `(sender.principal_id, sender.sender_instance_id)` pair
- `coordinator_epoch` is conditionally required on coordinator-authored messages. It MUST be monotonically increasing across crash recovery and handover events, and receivers MUST prefer higher accepted epochs over lower ones when evaluating coordinator authority
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

### 12.7 Lamport Clock Maintenance Rules

Since `lamport_clock` is the mandatory baseline watermark kind (Section 12.3), all MPAC implementations MUST maintain a Lamport clock according to the following rules:

1. **Initialization**: Each sender incarnation MUST initialize a local Lamport counter to `0` when a new `sender.sender_instance_id` is created. A participant that reconnects without restarting its process MUST preserve its existing `sender_instance_id` and Lamport counter. The session coordinator MUST initialize its Lamport counter to `0` upon session creation, or restore it from the most recent snapshot upon recovery (Section 8.1.1.3).

2. **Send rule**: Before sending any message, the participant MUST increment its local counter by 1: `counter = counter + 1`. The resulting value MUST be used as the `lamport_value` (or the `value` field when `watermark.kind` is `lamport_clock`) in the outgoing message's watermark.

3. **Receive rule**: Upon receiving a message with a Lamport clock value `received_value`, the participant MUST update its local counter: `counter = max(counter, received_value) + 1`.

4. **Coordinator authority**: The session coordinator's Lamport counter is the authoritative session-global counter. When the coordinator processes a message (e.g., confirming an `OP_COMMIT`, broadcasting a state transition), it applies the receive rule, then the send rule for its outgoing message. The coordinator's counter value in outgoing messages establishes the definitive causal ordering for the session.

5. **Snapshot persistence**: The coordinator MUST include its current Lamport counter value in every state snapshot (Section 8.1.1.2, field `lamport_clock`). Upon recovery, the coordinator MUST restore the counter from the snapshot and then apply the receive rule for each replayed audit log entry.

6. **Monotonicity**: Lamport clock values in messages from the same sender incarnation MUST be strictly monotonically increasing. A sender incarnation is identified by the pair `(sender.principal_id, sender.sender_instance_id)`. A receiver that detects a non-monotonic Lamport value from the same sender incarnation (a value less than or equal to a previously received value from that same pair) SHOULD treat it as a potential replay or ordering violation and MAY reject the message with a `PROTOCOL_ERROR` (`error_code`: `MALFORMED_MESSAGE`).

7. **Rejoin rule**: If a participant re-sends `HELLO` after coordinator handover or recovery without restarting its process, it MUST preserve both `sender.sender_instance_id` and its local Lamport counter. If the participant has restarted, it MUST generate a new `sender_instance_id`; in that case, counter reset to `0` is valid for the new sender incarnation.

### 12.8 Causal Gap Detection and Behavior

A participant detects a **causal gap** when it receives a message whose watermark references causal state that the participant has not yet observed. For example, if a participant's local Lamport counter is at 10 and it receives a message with `lamport_value` 15, the gap between 10 and 15 suggests that the participant has missed intermediate messages.

When a causal gap is detected, the participant:

1. MUST still apply the Lamport clock receive rule (Section 12.7, rule 3) — the local counter advances to `max(local, received) + 1` regardless of the gap.

2. SHOULD NOT issue `CONFLICT_REPORT` or `RESOLUTION` messages based on incomplete causal context. A conflict judgment made without awareness of intermediate messages may be incorrect (e.g., a conflict may have already been resolved by a message the participant hasn't seen).

3. MAY send a `PROTOCOL_ERROR` with `error_code`: `CAUSAL_GAP` to the session coordinator to signal that its causal state is incomplete. The `refers_to` field SHOULD reference the `message_id` of the message that revealed the gap. The coordinator MAY respond with a state synchronization mechanism (implementation-defined — e.g., replaying missed messages from the audit log, or sending a state snapshot).

4. MAY continue non-causally-sensitive activities (e.g., sending `HEARTBEAT`, updating its own intent's objective or TTL) while the gap persists.

Causal gap detection is best-effort. Participants using `lamport_clock` watermarks can detect gaps heuristically (via non-consecutive values from the coordinator), but cannot determine precisely which messages were missed. Participants using `vector_clock` watermarks can detect gaps with per-participant granularity. The protocol does not require gap detection — it requires that participants who detect gaps behave conservatively with respect to causally-sensitive judgments.

## 13. Core Message Types

MPAC v0.1 defines the following core message types:

- `HELLO`
- `SESSION_INFO`
- `HEARTBEAT`
- `GOODBYE`
- `SESSION_CLOSE`
- `COORDINATOR_STATUS`
- `INTENT_ANNOUNCE`
- `INTENT_UPDATE`
- `INTENT_WITHDRAW`
- `INTENT_DEFERRED` *(v0.1.14+)*
- `INTENT_CLAIM`
- `INTENT_CLAIM_STATUS`
- `OP_PROPOSE`
- `OP_COMMIT`
- `OP_BATCH_COMMIT`
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
| `credential` | object | C | Required in Authenticated/Verified profiles (Section 23.1.4). `{ "type": string, "value": string, "issuer"?: string, "expires_at"?: string }` |
| `backend` | object | O | Agent's AI model backend dependency. `{ "model_id": string, "provider": string }`. `model_id` uses `provider/model` format (e.g., `anthropic/claude-sonnet-4.6`). `provider` is the provider slug (e.g., `anthropic`, `openai`, `google`). See Section 14.3.1 |

#### `SESSION_INFO` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `session_id` | string | R | Session identifier |
| `protocol_version` | string | R | MPAC version the session is operating under |
| `security_profile` | string | R | One of: `open`, `authenticated`, `verified` |
| `compliance_profile` | string | R | One of: `core`, `governance`, `semantic` |
| `watermark_kind` | string | R | Session's baseline watermark kind (Section 12.2) |
| `execution_model` | string | R | One of: `pre_commit`, `post_commit` (Section 7.8) |
| `state_ref_format` | string | R | Format used for `state_ref_before`/`state_ref_after` (e.g., `sha256`, `git_hash`, `monotonic_version`) |
| `governance_policy` | object | O | Session governance configuration (Section 18.6.3) |
| `liveness_policy` | object | O | Session liveness configuration (Section 14.7.5) |
| `participant_count` | integer | O | Current number of active participants |
| `granted_roles` | string[] | R | Roles actually granted to the joining participant (may differ from requested) |
| `identity_verified` | boolean | O | Whether the participant's credential was verified. Required in Authenticated/Verified profiles (Section 23.1.4) |
| `identity_method` | string | O | Credential type used for verification (e.g., `bearer_token`, `mtls_fingerprint`) |
| `identity_issuer` | string | O | Identity provider or certificate authority that issued the verified credential (e.g., `https://auth.example.com`). Relevant in Authenticated/Verified profiles (Section 23.1.4) |
| `compatibility_errors` | string[] | O | List of incompatibilities detected. Default: `[]` |

#### `HEARTBEAT` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `status` | string | R | One of: `idle`, `working`, `blocked`, `awaiting_review`, `offline` |
| `active_intent_id` | string | O | Currently active intent |
| `summary` | string | O | Human-readable activity summary |
| `backend_health` | object | O | Backend provider health status (Section 14.3.1). Contains: `model_id` (string, R), `provider_status` (string, R: `operational` / `degraded` / `down` / `unknown`), `status_detail` (string, O), `checked_at` (date-time, R), `alternatives` (array, O), `switched_from` (string, O), `switch_reason` (string, O: `provider_down` / `provider_degraded` / `manual` / `cost_optimization`) |

#### `GOODBYE` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `reason` | string | R | One of: `user_exit`, `session_complete`, `error`, `timeout` |
| `active_intents` | string[] | O | List of the departing participant's active intent IDs |
| `intent_disposition` | string | O | One of: `withdraw`, `transfer`, `expire`. Default: `withdraw` |

#### `SESSION_CLOSE` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `reason` | string | R | One of: `completed`, `timeout`, `policy`, `coordinator_shutdown`, `manual` |
| `final_lamport_clock` | integer | R | Final Lamport clock value for the session |
| `summary` | object | O | Session completion summary (Section 9.6.2) |
| `active_intents_disposition` | string | O | How remaining active intents are handled. One of: `withdraw_all`, `expire_all`. Default: `withdraw_all` |
| `transcript_ref` | string | O | URI or reference to the exported session transcript (Section 9.6.3) |

#### `COORDINATOR_STATUS` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `event` | string | R | One of: `heartbeat`, `recovered`, `handover`, `assumed`, `authorization`, `backend_alert` |
| `coordinator_id` | string | R | Principal ID of the coordinator sending this message |
| `session_health` | string | R | One of: `healthy`, `degraded`, `recovering` |
| `active_participants` | integer | O | Number of currently available participants |
| `open_conflicts` | integer | O | Number of unresolved conflicts |
| `snapshot_lamport_clock` | integer | O | Lamport clock value of the latest persisted snapshot |
| `successor_coordinator_id` | string | C | Required when `event` = `handover`: principal ID of the successor coordinator |
| `next_coordinator_epoch` | integer | C | Required when `event` = `handover`: epoch the successor coordinator will assume |
| `authorized_op_id` | string | C | Required when `event` = `authorization`: operation ID being authorized for commit |
| `authorized_batch_id` | string | O | Present when `event` = `authorization` and the operation belongs to a batch |
| `authorized_by` | string | C | Required when `event` = `authorization`: principal ID of the authorizing coordinator |
| `affected_principal` | string | C | Required when `event` = `backend_alert`: principal ID of the agent whose backend is affected |
| `backend_detail` | object | C | Required when `event` = `backend_alert`: `{ "model_id": string, "provider_status": string, "status_detail"?: string, "alternatives"?: array }` (Section 14.3.1) |

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

#### `INTENT_DEFERRED` Payload *(v0.1.14+)*

Two shapes share this message type. Active deferrals carry the full record; lifecycle follow-ups carry only the disposition.

**Active form** (sent by the deferring participant; coordinator re-broadcasts with `principal_id` filled in):

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `deferral_id` | string | R | Sender-chosen unique id |
| `principal_id` | string | C | Filled in by the coordinator on broadcast; clients SHOULD omit when sending |
| `scope` | Scope object | R | The scope the sender was about to claim before deciding to yield |
| `reason` | string | O | Free-form rationale (e.g. `"yielded_to_active_editor"`) |
| `observed_intent_ids` | string[] | O | Intent ids the sender saw on the scope |
| `observed_principals` | string[] | O | Principal ids the sender saw working on the scope |
| `ttl_sec` | number | O | TTL in seconds; default 60 |
| `expires_at` | string | C | ISO timestamp; coordinator MUST add this on rebroadcast based on `received_at + ttl_sec` |

**Resolution form** (emitted only by the coordinator):

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `deferral_id` | string | R | Deferral being resolved |
| `principal_id` | string | R | Original deferring principal |
| `status` | string | R | `"resolved"` (observed intents terminated / principal announced) or `"expired"` (TTL fired) |
| `reason` | string | O | Free-form, e.g. `"observed_intents_terminated"`, `"principal_announced"`, `"ttl"` |

See Section 15.5.1 for full semantics, including the three-axis cleanup rule.

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

#### `INTENT_CLAIM_STATUS` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `claim_id` | string | R | Claim being decided |
| `original_intent_id` | string | R | Suspended intent targeted by the claim |
| `new_intent_id` | string | C | Required when `decision` = `approved` |
| `decision` | string | R | One of: `approved`, `rejected`, `withdrawn` |
| `reason` | string | C | Required when `decision` = `rejected` or `withdrawn` |
| `approved_by` | string | C | Required when `decision` = `approved` in Governance Profile sessions; identifies the principal whose approval authorized the claim |

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

#### `OP_BATCH_COMMIT` Payload

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `batch_id` | string | R | Unique batch identifier |
| `intent_id` | string | O | Associated intent (MUST in Governance Profile) |
| `atomicity` | string | R | One of: `all_or_nothing`, `best_effort` |
| `operations` | array | R | Array of batch operation entries (see below) |
| `summary` | string | O | Human-readable summary of the batch |

Batch operation entry:

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `op_id` | string | R | Unique operation identifier for this entry |
| `target` | string | R | Resource being mutated |
| `op_kind` | string | R | Mutation type |
| `state_ref_before` | string | R | State reference before mutation |
| `state_ref_after` | string | R | State reference after mutation |
| `change_ref` | string | O | Reference to the change content |

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
| `decision` | string | R | One of: `approved`, `rejected`, `dismissed`, `human_override`, `policy_override`, `merged` |
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
  },
  "backend": {
    "model_id": "anthropic/claude-sonnet-4.6",
    "provider": "anthropic"
  }
}
```

Semantics:
- a participant MUST send `HELLO` as its first message when entering a session
- a receiver MUST use `HELLO` to register the participant; messages from unregistered participants (other than `HELLO`) MUST be rejected with a `PROTOCOL_ERROR` (`error_code`: `INVALID_REFERENCE`)
- a participant MAY include a `backend` field declaring the AI model backend it depends on; this field is informational and does not affect session admission

### 14.2 `SESSION_INFO`

Purpose:
- respond to a `HELLO` with the session's configuration, enabling the joining participant to verify compatibility before proceeding

Payload:

```json
{
  "session_id": "sess-001",
  "protocol_version": "0.1.14",
  "security_profile": "authenticated",
  "compliance_profile": "governance",
  "execution_model": "pre_commit",
  "watermark_kind": "lamport_clock",
  "state_ref_format": "sha256",
  "governance_policy": {
    "require_arbiter": true,
    "resolution_timeout_sec": 300,
    "intent_expiry_grace_sec": 30
  },
  "liveness_policy": {
    "heartbeat_interval_sec": 30,
    "unavailability_timeout_sec": 90,
    "backend_health_policy": {
      "enabled": true,
      "check_source": "https://aistatus.cc/api/check",
      "check_interval_sec": 60,
      "on_degraded": "warn",
      "on_down": "suspend_and_claim",
      "auto_switch": "allowed",
      "allowed_providers": ["anthropic", "openai", "google"]
    }
  },
  "participant_count": 3,
  "granted_roles": ["contributor"],
  "compatibility_errors": []
}
```

Semantics:
- the session coordinator MUST send `SESSION_INFO` in response to every valid `HELLO` message. A participant is not fully admitted to the session until it has received `SESSION_INFO`.
- `granted_roles` contains the roles actually granted to the participant, which MAY differ from the roles requested in `HELLO` (e.g., if the participant requested `arbiter` but is not authorized for it per Section 23.1.2)
- the coordinator SHOULD populate `compatibility_errors` with any detected incompatibilities between the participant's advertised capabilities and the session's requirements. Examples include: the participant does not support the session's `watermark_kind`, or the participant does not advertise a capability required by the session's compliance profile
- if `compatibility_errors` is non-empty, the coordinator SHOULD still admit the participant (to allow graceful degradation), but the participant SHOULD evaluate the errors and MAY choose to send `GOODBYE` (reason: `error`) if the incompatibilities are unacceptable
- in the Authenticated and Verified security profiles (Section 23.1), `SESSION_INFO` MUST only be sent after the participant's identity has been verified
- coordinator-authored `SESSION_INFO` messages MUST include the current `coordinator_epoch` in the message envelope

### 14.3 `HEARTBEAT`

Purpose:
- maintain liveness
- publish lightweight activity summary
- report backend AI model health status (optional)

Payload:

```json
{
  "status": "idle",
  "active_intent_id": "intent-123",
  "summary": "reviewing train.py",
  "backend_health": {
    "model_id": "anthropic/claude-sonnet-4.6",
    "provider_status": "operational",
    "status_detail": null,
    "checked_at": "2026-04-07T10:30:00Z",
    "alternatives": []
  }
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

#### 14.3.1 Backend Health Monitoring

When a session's `liveness_policy` includes `backend_health_policy` with `enabled: true`, participants that declared a `backend` in their `HELLO` message SHOULD include `backend_health` in their `HEARTBEAT` messages.

**Health check data source:** Agents SHOULD query the status API specified in `backend_health_policy.check_source` (default: `https://aistatus.cc/api/check`) at the interval specified by `check_interval_sec` (default: 60 seconds). The `provider_status` field aligns with the aistatus.cc provider status values:
- `operational`: provider is fully available
- `degraded`: provider is experiencing partial issues (e.g., elevated error rates)
- `down`: provider is experiencing a major outage
- `unknown`: status cannot be determined

**Coordinator behavior on status change:** When the coordinator receives a `HEARTBEAT` with `backend_health.provider_status` other than `operational`, it SHOULD evaluate the session's `backend_health_policy`:
- `on_degraded` / `on_down` = `ignore`: no action taken
- `on_degraded` / `on_down` = `warn`: the coordinator MUST broadcast a `COORDINATOR_STATUS` message with `event: backend_alert`, including `affected_principal` and `backend_detail`
- `on_degraded` / `on_down` = `suspend_and_claim`: the coordinator MUST broadcast the alert AND transition the affected agent's active intents to `SUSPENDED` state (Section 14.7.2), enabling other agents to claim them via `INTENT_CLAIM` (Section 14.7.4)

**Model switching governance:** When an agent switches to a different backend model (indicated by `backend_health.switched_from` being present), the coordinator MUST validate the switch against the session's `backend_health_policy`:
- `auto_switch` = `allowed`: the switch is accepted; the coordinator updates its record of the agent's backend and MAY broadcast a `COORDINATOR_STATUS(event=backend_alert)` notification
- `auto_switch` = `notify_first`: the agent MUST NOT switch until the coordinator acknowledges; the agent SHOULD send an `INTENT_UPDATE` indicating the planned switch, and wait for coordinator confirmation
- `auto_switch` = `forbidden`: the switch is rejected; the coordinator MUST send a `PROTOCOL_ERROR` with `error_code: BACKEND_SWITCH_DENIED`
- `allowed_providers`: if present, the coordinator MUST verify that the new model's provider is in the whitelist; if not, the switch MUST be rejected with `PROTOCOL_ERROR(BACKEND_SWITCH_DENIED)`. The `allowed_providers` list is configured by the session creator (principal/user), not by the protocol

**Protocol vs. implementation boundary:** The protocol defines the signaling mechanism (health reporting, alert broadcasting, switch governance) and the coordinator's enforcement rules. The protocol does NOT prescribe which alternative model to choose, when to trigger a switch, or whether to switch back after recovery — these are implementation-level decisions.

### 14.4 `GOODBYE`

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
- `transfer`: active intents are offered for adoption by another participant (requires session coordinator support). The coordinator SHOULD transition the departing participant's active intents to `SUSPENDED` upon receiving `GOODBYE` with `intent_disposition`: `transfer`, making them eligible for `INTENT_CLAIM` by other participants per Section 14.7.4. The specific mechanism for soliciting claims is implementation-defined
- `expire`: active intents retain their existing TTL and expire naturally

If `intent_disposition` is omitted, implementations SHOULD default to `withdraw`.

In-flight proposed operations (`OP_PROPOSE` without a corresponding `OP_COMMIT` or `OP_REJECT`) from a departing participant SHOULD be treated as abandoned. Implementations MAY automatically reject them or leave them for governance review.

Recommended `reason` values:
- `user_exit`
- `session_complete`
- `error`
- `timeout`

### 14.5 `SESSION_CLOSE`

Purpose:
- formally end a session
- communicate final state to all participants
- trigger session transcript archival

Payload:

```json
{
  "reason": "completed",
  "final_lamport_clock": 127,
  "summary": {
    "total_intents": 8,
    "completed_intents": 5,
    "expired_intents": 2,
    "withdrawn_intents": 1,
    "total_operations": 12,
    "committed_operations": 9,
    "rejected_operations": 2,
    "abandoned_operations": 1,
    "total_conflicts": 3,
    "resolved_conflicts": 3,
    "total_participants": 4,
    "duration_sec": 3600
  },
  "active_intents_disposition": "withdraw_all",
  "transcript_ref": "archive://sess-001/transcript.json"
}
```

Semantics:
- only the session coordinator MAY send `SESSION_CLOSE`
- upon receiving `SESSION_CLOSE`, participants MUST cease sending any messages to the session except `GOODBYE` (as a courtesy acknowledgment)
- any message received for a closed session MUST be rejected with a `PROTOCOL_ERROR` (`error_code`: `SESSION_CLOSED`)
- `active_intents_disposition` determines how remaining active intents are handled: `withdraw_all` immediately withdraws all active intents; `expire_all` leaves them to expire naturally per their TTL
- the coordinator SHOULD persist the final state snapshot (Section 8.1.1.2) before sending `SESSION_CLOSE`
- session auto-close conditions are defined in Section 9.6.1

### 14.6 `COORDINATOR_STATUS`

Purpose:
- signal coordinator liveness to all participants
- communicate session health and coordinator lifecycle events (recovery, handover)

Payload:

```json
{
  "event": "heartbeat",
  "coordinator_id": "service:coordinator-1",
  "session_health": "healthy",
  "active_participants": 3,
  "open_conflicts": 1,
  "snapshot_lamport_clock": 42
}
```

Semantics:
- the coordinator MUST broadcast `COORDINATOR_STATUS` at least once per `heartbeat_interval_sec` (Section 14.7.5)
- every `COORDINATOR_STATUS` message MUST include `coordinator_epoch` in the message envelope
- `COORDINATOR_STATUS` SHOULD include a Lamport watermark; when two coordinators claim the same epoch, participants use that watermark as the tie-breaker per Section 8.1.1.4
- participants MUST track coordinator liveness; absence of `COORDINATOR_STATUS` for `2 × heartbeat_interval_sec` indicates coordinator unavailability (Section 8.1.1.1)
- `event` values:
  - `heartbeat`: routine liveness signal
  - `recovered`: coordinator has restarted and recovered state from snapshot (Section 8.1.1.3); participants SHOULD re-send `HELLO` and preserve `sender_instance_id` if their process has not restarted
  - `handover`: coordinator is transferring authority to `successor_coordinator_id` at `next_coordinator_epoch` (Section 8.1.1.4); participants SHOULD prepare to reconnect
  - `assumed`: a new coordinator has taken over and is ready to accept messages at the advertised epoch; participants MUST re-send `HELLO`
  - `authorization`: coordinator has approved a proposed operation for commit in `pre_commit` execution model sessions (Section 7.8); the proposer MAY proceed to execute the mutation and declare completion. Requires `authorized_op_id` and `authorized_by`; `authorized_batch_id` is present when the operation belongs to an `OP_BATCH_COMMIT`
  - `backend_alert`: a participant's AI model backend has changed status (degraded, down, or recovered). Requires `affected_principal` and `backend_detail` (Section 14.3.1). The coordinator emits this event based on `backend_health_policy` evaluation of incoming `HEARTBEAT` data

### 14.7 Participant Unavailability and Recovery

When a participant becomes unavailable without sending `GOODBYE` (e.g., crash, network partition, or unresponsive process), the session faces orphaned intents, in-flight proposals, and ambiguous scope locks. This section defines the detection mechanism and required recovery behaviors.

#### 14.7.1 Unavailability Detection

A participant is considered **unavailable** when no `HEARTBEAT` or any other message has been received from them for the duration specified by the session's liveness timeout (default: 90 seconds per Section 14.3). The session coordinator or any participant with governance authority MAY declare a participant unavailable.

When unavailability is detected, implementations SHOULD broadcast a system-level notification to all remaining participants. The recommended format is a `PROTOCOL_ERROR` with `error_code`: `PARTICIPANT_UNAVAILABLE` and the `refers_to` field set to the unavailable participant's last known `message_id`.

#### 14.7.2 Orphaned Intent Handling

When a participant is detected as unavailable, their active intents MUST be transitioned to a `SUSPENDED` state:

1. **SUSPENDED state**: A suspended intent remains visible to all participants but is not actionable — no new `OP_PROPOSE` or `OP_COMMIT` may reference a suspended intent. The scope declared by suspended intents SHOULD still be considered occupied for conflict detection purposes (to prevent silent overwrite of in-progress work).

2. **Transition trigger**: The transition to `SUSPENDED` SHOULD occur automatically upon unavailability detection. Implementations SHOULD generate a synthetic `INTENT_UPDATE` or equivalent audit record marking the state change, attributed to the system or session coordinator rather than the unavailable participant.

3. **Recovery**: If the unavailable participant reconnects (sends a new `HELLO` or resumes `HEARTBEAT`), their suspended intents SHOULD automatically transition back to `ACTIVE`. The participant SHOULD be notified of any state changes that occurred during their absence.

#### 14.7.3 Abandoned Operation Handling

In-flight `OP_PROPOSE` messages from the unavailable participant that have no corresponding `OP_COMMIT` or `OP_REJECT` MUST be marked as `ABANDONED` after the liveness timeout expires:

1. **ABANDONED state**: An abandoned proposal is no longer eligible for commit. It is retained for audit purposes but does not block other operations on the same target.

2. **Automatic marking**: Implementations SHOULD automatically transition orphaned proposals to `ABANDONED` state. This transition SHOULD generate an audit record.

3. **Governance override**: A participant with `owner` or `arbiter` role MAY explicitly reject an orphaned proposal via `OP_REJECT` (with `reason`: `participant_unavailable`) instead of waiting for automatic abandonment, if faster resolution is needed.

#### 14.7.4 `INTENT_CLAIM`

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
- `INTENT_CLAIM` is subject to governance approval: in sessions using the Governance profile, a participant with `owner` or `arbiter` role MUST approve the claim before the new intent becomes active, and the coordinator MUST record that approver in `approved_by`. In Core profile sessions, the coordinator MAY automatically approve the claim after a configurable grace period (default: 30 seconds) if no objection is raised
- a claim is not effective until the session coordinator emits `INTENT_CLAIM_STATUS` with `decision`: `approved`
- upon approval, the original suspended intent transitions to `TRANSFERRED` state and the new intent becomes `ACTIVE`
- if the original participant reconnects before the claim is approved, the coordinator MUST emit `INTENT_CLAIM_STATUS` with `decision`: `withdrawn` and the original intent MUST be restored to `ACTIVE`
- **concurrent claims**: if multiple participants submit `INTENT_CLAIM` for the same suspended intent, the session coordinator MUST accept only the first claim received (first-claim-wins) and reject subsequent claims with a `PROTOCOL_ERROR` (`error_code`: `CLAIM_CONFLICT`). The ordering is determined by the session coordinator's receipt order

##### 14.7.4.1 `INTENT_CLAIM_STATUS`

Purpose:
- communicate the authoritative disposition of an `INTENT_CLAIM`

Payload:

```json
{
  "claim_id": "claim-001",
  "original_intent_id": "intent-123",
  "new_intent_id": "intent-456",
  "decision": "approved",
  "approved_by": "human:team-lead"
}
```

Semantics:
- only the session coordinator MAY send `INTENT_CLAIM_STATUS`
- `decision`: `approved` activates the replacement intent and transitions the original intent to `TRANSFERRED`
- in Governance Profile sessions, `decision = approved` MUST include `approved_by`; in Core Profile sessions, `approved_by` MAY be omitted when the coordinator auto-approves per session policy
- `decision`: `rejected` leaves the original intent in `SUSPENDED` unless another rule changes it
- `decision`: `withdrawn` indicates that the original owner resumed before approval; the original intent returns to `ACTIVE` and the replacement intent MUST NOT become active

#### 14.7.5 Session Policy for Unavailability

Sessions MAY configure unavailability behavior through session policy:

```json
{
  "liveness": {
    "heartbeat_interval_sec": 30,
    "unavailability_timeout_sec": 90,
    "orphaned_intent_action": "suspend",
    "orphaned_proposal_action": "abandon",
    "intent_claim_approval": "governance",
    "intent_claim_grace_period_sec": 30,
    "backend_health_policy": {
      "enabled": true,
      "check_source": "https://aistatus.cc/api/check",
      "check_interval_sec": 60,
      "on_degraded": "warn",
      "on_down": "suspend_and_claim",
      "auto_switch": "allowed",
      "allowed_providers": ["anthropic", "openai", "google"]
    }
  }
}
```

`backend_health_policy` fields:
- `enabled` (boolean, default `false`): whether backend health monitoring is active for this session
- `check_source` (string, default `"https://aistatus.cc/api/check"`): URL of the status check API that agents query
- `check_interval_sec` (number, default `60`): recommended interval between backend health checks
- `on_degraded` (string, default `"warn"`): coordinator action when `provider_status` = `degraded`. One of: `ignore`, `warn`, `suspend_and_claim`
- `on_down` (string, default `"suspend_and_claim"`): coordinator action when `provider_status` = `down`. One of: `ignore`, `warn`, `suspend_and_claim`
- `auto_switch` (string, default `"allowed"`): model switching governance. One of: `allowed` (agent may switch and report after the fact), `notify_first` (agent must request approval before switching), `forbidden` (switching is not permitted)
- `allowed_providers` (string[], default: absent = no restriction): whitelist of provider slugs the agent may switch to. Configured by the session creator (principal/user), not by the protocol. When absent, any provider is accepted

See Section 14.3.1 for the full behavioral specification of backend health monitoring.

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

To enable cross-kind overlap detection, scope objects MUST include a `canonical_uris` field in sessions operating under the Authenticated or Verified security profile (Section 23.1) when the session involves participants using heterogeneous scope kinds. In sessions using the Open security profile, or sessions where all participants use the same scope kind, `canonical_uris` SHOULD be included but is not required. The field is an array of canonical resource identifiers that the scope covers, independent of representation.

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
- `ttl_sec` is measured in wall-clock seconds. TTL expiry MUST be determined by the session coordinator based on the coordinator's local wall clock. The coordinator SHOULD record a `received_at` timestamp when processing each `INTENT_ANNOUNCE` and compute expiry as `received_at + ttl_sec`. The sender's `ts` field is used for audit purposes only and MUST NOT be used for TTL computation, as clock skew between participants and the coordinator would produce inconsistent expiry judgments

#### 15.3.1 Intent Re-Announce Backoff

When a participant's intent has been rejected as the outcome of a `RESOLUTION` for a scope overlap conflict, the participant SHOULD apply an exponential backoff before re-announcing an intent with the same or overlapping scope. The recommended backoff schedule is: initial delay of 30 seconds, doubling on each subsequent rejection for the same scope, up to a maximum of 300 seconds. Implementations MAY configure different backoff parameters via session policy.

This prevents **livelock**: without backoff, two agents whose intents repeatedly overlap may enter a cycle of announce → conflict → resolution (one rejected) → re-announce → conflict → resolution, indefinitely consuming session resources without making progress.

The backoff applies specifically to re-announcement after conflict-driven rejection. It does NOT apply to:
- re-announcement after TTL expiry (the agent's intent simply timed out, not necessarily due to conflict)
- re-announcement after voluntary withdrawal (`INTENT_WITHDRAW`)
- announcement of a new intent with a different, non-overlapping scope

The session coordinator MAY enforce backoff by rejecting `INTENT_ANNOUNCE` messages that arrive before the backoff period has elapsed for a recently-rejected scope, with a `PROTOCOL_ERROR` (`error_code`: `INTENT_BACKOFF`). Alternatively, implementations MAY enforce backoff on the client side only. When the coordinator enforces backoff, the `PROTOCOL_ERROR` SHOULD include a `retry_after_sec` field in the payload's `extensions` indicating the remaining backoff duration.

```json
{
  "liveness": {
    "intent_backoff_initial_sec": 30,
    "intent_backoff_max_sec": 300,
    "intent_backoff_multiplier": 2
  }
}
```

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

Semantics:
- at least one field besides `intent_id` SHOULD be present
- when the `scope` field is updated and the new scope is **strictly larger** than the original scope (i.e., it covers resources not declared in the original `INTENT_ANNOUNCE`), the session coordinator SHOULD re-evaluate the expanded scope for overlap with other active intents. If the expansion introduces a new overlap, the coordinator SHOULD generate a `CONFLICT_REPORT` for the newly overlapping portion. This prevents participants from silently acquiring scope through incremental updates without conflict detection

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

### 15.5.1 `INTENT_DEFERRED` (v0.1.14+)

Purpose:
- record that a participant **observed** existing intent(s) on a scope and chose to **yield without announcing** one of their own.

This is a one-sided **non-claiming** signal. It is distinct from `INTENT_ANNOUNCE` (no scope claim, no participation in conflict detection) and from `CONFLICT_REPORT` (no opposing pair). Its purpose is purely UX: sibling participants render a "yielded" hint in their conflicts surface so the human owner can see *"Bob saw Alice editing X and stepped back"*.

Sender semantics:
- Senders SHOULD call `INTENT_DEFERRED` when they encountered an active intent (e.g., via a coordinator-side or client-side overlap query) and decided to back off rather than announce.
- A deferral does NOT count as an intent. It does NOT lock scope, MUST NOT trigger overlap detection, and MUST NOT block subsequent `INTENT_ANNOUNCE` calls from the same principal.

Payload (active form, sent by the deferring participant):

```json
{
  "deferral_id": "defer-bob-92a3...",
  "scope": {"kind": "file_set", "resources": ["src/db.py"]},
  "reason": "yielded_to_active_editor",
  "observed_intent_ids": ["intent-alice-7c5b..."],
  "observed_principals": ["alice"],
  "ttl_sec": 60
}
```

The coordinator stores the deferral, then emits an `INTENT_DEFERRED` envelope on the broadcast bus carrying `principal_id` (resolved from the sender) and the same fields plus an `expires_at` ISO timestamp. Coordinator-emitted variants:

```json
{
  "deferral_id": "defer-bob-92a3...",
  "principal_id": "bob",
  "scope": {"kind": "file_set", "resources": ["src/db.py"]},
  "reason": "yielded_to_active_editor",
  "observed_intent_ids": ["intent-alice-7c5b..."],
  "observed_principals": ["alice"],
  "expires_at": "2026-04-29T01:23:45Z"
}
```

Resolution / expiration follow-ups (also `INTENT_DEFERRED` envelopes) carry only the disposition:

```json
{ "deferral_id": "defer-bob-92a3...", "principal_id": "bob",
  "status": "resolved", "reason": "observed_intents_terminated" }
```

```json
{ "deferral_id": "defer-bob-92a3...", "principal_id": "bob",
  "status": "expired", "reason": "ttl" }
```

Coordinator MUST clear a deferral and emit a `status: resolved` follow-up when ANY of the following becomes true:

1. All intents listed in `observed_intent_ids` reach a terminal state.
2. The same principal subsequently announces an intent (the principal is no longer yielding).
3. The terminating intent's `principal_id` appears in `observed_principals`, OR appears in `observed_intent_ids` (defense-in-depth match for senders that conflated the two fields — common when a client built the request from a `check_overlap` response that pre-v0.2.6 did not surface `intent_id`).

Coordinator MUST clear and emit a `status: expired` follow-up when wall-clock time exceeds the deferral's `expires_at`. Default TTL when sender omits `ttl_sec`: 60 seconds.

Deferrals are NOT intents and have no formal state machine. They are ephemeral records intended for client UI hints; clients SHOULD also implement a local TTL sweep so missed broadcasts do not strand stale UI.

### 15.6 Intent Lifecycle

The intent state machine overview:

```text
DRAFT -> ANNOUNCED -> ACTIVE -> SUPERSEDED
DRAFT -> ANNOUNCED -> ACTIVE -> EXPIRED
DRAFT -> ANNOUNCED -> WITHDRAWN
ACTIVE -> SUSPENDED -> ACTIVE           (participant reconnects)
ACTIVE -> SUSPENDED -> TRANSFERRED      (intent claimed by another participant)
ACTIVE -> SUSPENDED                     (owner departs with intent_disposition: transfer)
```

MPAC does not require a `DRAFT` message on the wire. It is included here as a conceptual lifecycle state.

The `SUSPENDED` and `TRANSFERRED` states support recovery from participant unavailability (Section 14.7) and voluntary intent transfer (Section 14.4). An intent enters `SUSPENDED` when its owner becomes unavailable or when the owner departs with `intent_disposition`: `transfer`, and transitions to `TRANSFERRED` when another participant successfully claims it via `INTENT_CLAIM` and the coordinator emits `INTENT_CLAIM_STATUS` with `decision`: `approved`.

#### 15.6.1 Intent State Transition Table

The following table is normative. Implementations MUST support all transitions listed. Any transition not listed is invalid and MUST be rejected.

| Current State | Event | Guard Condition | Next State | Action | Triggered By |
|---|---|---|---|---|---|
| (none) | `INTENT_ANNOUNCE` received | sender is registered participant | ACTIVE | register intent, start TTL timer | intent owner |
| ACTIVE | `INTENT_UPDATE` received | sender is intent owner | ACTIVE | update fields, optionally reset TTL | intent owner |
| ACTIVE | `INTENT_WITHDRAW` received | sender is intent owner | WITHDRAWN | cancel TTL timer, trigger expiry cascade (Section 15.7) | intent owner |
| ACTIVE | TTL expired | coordinator wall-clock check | EXPIRED | trigger expiry cascade (Section 15.7) | coordinator |
| ACTIVE | `INTENT_ANNOUNCE` with `supersedes_intent_id` | new intent from same owner | SUPERSEDED | trigger expiry cascade (Section 15.7) | intent owner |
| ACTIVE | owner unavailability detected | Section 14.7.1 | SUSPENDED | freeze referencing ops, retain scope for conflict detection | coordinator |
| ACTIVE | owner departs with `intent_disposition`: `transfer` | `GOODBYE` received from intent owner with `intent_disposition` = `transfer` (Section 14.4) | SUSPENDED | freeze referencing ops, retain scope, intent eligible for `INTENT_CLAIM` | coordinator |
| SUSPENDED | owner reconnects (`HELLO` or `HEARTBEAT` resumes) | original owner re-authenticated | ACTIVE | unfreeze referencing ops, notify owner of changes during absence | coordinator |
| SUSPENDED | `INTENT_CLAIM_STATUS` received (`decision = approved`) | claim authorized per governance | TRANSFERRED | original intent closed, new intent created as ACTIVE | coordinator |
| SUSPENDED | TTL expired while suspended | coordinator wall-clock check | EXPIRED | trigger expiry cascade (Section 15.7) | coordinator |

Terminal states: **WITHDRAWN**, **EXPIRED**, **SUPERSEDED**, **TRANSFERRED**. No transitions out of terminal states are permitted.

### 15.7 Intent Expiry Cascade

When an intent transitions to a terminal state (`EXPIRED`, `WITHDRAWN`, `SUPERSEDED`, or `TRANSFERRED`), the session coordinator MUST evaluate all operations that reference that intent via `intent_id`:

1. **Pending proposals**: Any `OP_PROPOSE` in `PROPOSED` state that references the terminated intent — regardless of who submitted the proposal — MUST be automatically rejected. The rejection SHOULD be represented as a system-generated `OP_REJECT` with `reason`: `intent_terminated` and the `refers_to` field set to the intent's last known `message_id`.

2. **Grace period**: Sessions MAY configure an `intent_expiry_grace_sec` (recommended default: 30 seconds). When configured, the automatic rejection is deferred by the grace period to allow the proposer to re-associate the proposal with a new intent via `OP_SUPERSEDE`. If no re-association occurs within the grace period, the rejection proceeds.

3. **Already committed operations**: Operations in `COMMITTED` state are NOT affected by intent termination. An operation that was committed while its intent was active remains valid regardless of subsequent intent state changes.

4. **Suspended intent cascade**: When an intent transitions to `SUSPENDED` (Section 14.7.2), pending proposals referencing that intent MUST NOT be automatically rejected, but MUST be frozen — they cannot proceed to `COMMITTED` until the intent is restored to `ACTIVE` or claimed via `INTENT_CLAIM`. If the intent subsequently transitions from `SUSPENDED` to a terminal state (e.g., the unavailability timeout leads to intent expiry), rule 1 applies.

```json
{
  "governance": {
    "intent_expiry_grace_sec": 30
  }
}
```

## 16. Operation Layer

### 16.1 Operation Model

An operation represents a proposed or committed mutation to shared state. In pre-commit sessions, an operation MAY remain proposed after authorization and becomes committed only when the proposer declares execution completion.

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
- in pre-commit sessions, MAY also serve as the initial request-to-commit for backward compatibility; when used this way, it MUST be treated as entering `PROPOSED`, not `COMMITTED`

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
PROPOSED -> COMMITTED          (post-commit declaration, or pre-commit completion after authorization)
PROPOSED -> REJECTED
PROPOSED -> REJECTED           (referenced intent terminated, per Section 15.7)
PROPOSED -> FROZEN             (referenced intent suspended, per Section 15.7)
FROZEN   -> PROPOSED           (referenced intent restored to ACTIVE)
FROZEN   -> REJECTED           (referenced intent terminated while suspended)
PROPOSED -> ABANDONED          (sender unavailable, per Section 14.7.3)
COMMITTED -> SUPERSEDED
```

#### 16.6.1 Operation State Transition Table

The following table is normative.

| Current State | Event | Guard Condition | Next State | Action | Triggered By |
|---|---|---|---|---|---|
| (none) | `OP_PROPOSE` received | sender registered, intent valid (if referenced) | PROPOSED | register proposal | proposer |
| (none) | `OP_COMMIT` received (post-commit model) | sender registered, valid state_refs | COMMITTED | register committed op, check for conflicts | proposer |
| (none) | `OP_COMMIT` received (pre-commit model, initial request) | sender registered, valid state_refs, no existing operation with same `op_id` | PROPOSED | register as pending, await authorization | proposer |
| PROPOSED | execution authorized (pre-commit model) | validation passed, no blocking conflict | PROPOSED | record authorization, notify proposer | coordinator |
| PROPOSED | `OP_COMMIT` received (pre-commit model, completion) | proposal previously authorized, valid state_refs | COMMITTED | register committed op, check for conflicts | proposer |
| PROPOSED | `OP_REJECT` received | rejector has authority (reviewer/owner/arbiter/coordinator) | REJECTED | notify proposer | rejector or coordinator |
| PROPOSED | referenced intent terminated | intent enters EXPIRED/WITHDRAWN/SUPERSEDED/TRANSFERRED (Section 15.7) | REJECTED | system-generated OP_REJECT with reason `intent_terminated` | coordinator |
| PROPOSED | referenced intent suspended | intent enters SUSPENDED (Section 14.7.2) | FROZEN | block commit until intent restored | coordinator |
| PROPOSED | sender unavailable detected | Section 14.7.3, liveness timeout | ABANDONED | retain for audit | coordinator |
| FROZEN | referenced intent restored to ACTIVE | owner reconnects | PROPOSED | resume normal lifecycle | coordinator |
| FROZEN | referenced intent terminated while suspended | SUSPENDED → terminal | REJECTED | system-generated OP_REJECT | coordinator |
| COMMITTED | `OP_SUPERSEDE` received | superseding op valid, targets same resource | SUPERSEDED | retain for audit, chain state_refs | superseder |
| (none) | `OP_BATCH_COMMIT` received (post-commit model) | all entries valid | per entry: COMMITTED | register all entries atomically if `all_or_nothing` | proposer |
| (none) | `OP_BATCH_COMMIT` received (pre-commit model, initial request) | all entries valid, new `batch_id` | per entry: PROPOSED | register batch as pending, await authorization | proposer |
| PROPOSED | `OP_BATCH_COMMIT` received (pre-commit model, completion) | all referenced entries previously authorized | COMMITTED | register batch execution completion per entry | proposer |

Terminal states: **REJECTED**, **ABANDONED**, **SUPERSEDED**. **COMMITTED** is a stable state (it may later transition to `SUPERSEDED`). For session-lifecycle purposes, a **settled** operation is any operation in `COMMITTED`, `REJECTED`, `ABANDONED`, or `SUPERSEDED` state.

### 16.7 Operation Attribution

Every committed operation MUST be attributable to a sender principal.

### 16.8 `OP_BATCH_COMMIT`

Purpose:
- declare a set of mutations across multiple targets as a single atomic logical operation

Payload:

```json
{
  "batch_id": "batch-001",
  "intent_id": "intent-123",
  "atomicity": "all_or_nothing",
  "operations": [
    {
      "op_id": "op-501",
      "target": "auth.py",
      "op_kind": "replace",
      "state_ref_before": "sha256:auth-old",
      "state_ref_after": "sha256:auth-new",
      "change_ref": "sha256:diff-auth"
    },
    {
      "op_id": "op-502",
      "target": "routes.py",
      "op_kind": "replace",
      "state_ref_before": "sha256:routes-old",
      "state_ref_after": "sha256:routes-new",
      "change_ref": "sha256:diff-routes"
    }
  ],
  "summary": "Refactor auth module: rename validate_token and update all call sites"
}
```

Semantics:
- `OP_BATCH_COMMIT` groups multiple operations that MUST be treated as a single logical unit for conflict detection and governance purposes
- the `atomicity` field determines batch behavior:
  - `all_or_nothing`: all operations in the batch succeed or all fail. If any operation in the batch triggers a conflict or fails validation, the entire batch MUST be rejected. In pre-commit model (Section 7.8), the coordinator MUST validate and authorize the entire batch before any mutation is applied, and the proposer MUST later emit a completion `OP_BATCH_COMMIT` for the same `batch_id` after execution. In post-commit model, if a conflict is detected post-facto, the compensating operation MUST reverse all operations in the batch.
  - `best_effort`: operations are processed individually. Some may succeed while others are rejected. Each operation's lifecycle is tracked independently. This mode is provided for cases where partial progress is acceptable.
- each operation entry within the batch follows the same field requirements as `OP_COMMIT` (Section 16.3)
- all operations in the batch MUST reference the same `intent_id` (if present)
- the batch's scope for conflict detection purposes is the union of all individual operation targets. Scope overlap is checked against the union, not individual operations.
- the `batch_id` MUST be unique within practical system scope. Individual `op_id` values within the batch MUST also be unique and are tracked independently in the operation lifecycle.
- `OP_REJECT` for a batch operation SHOULD reference the `batch_id` in the `op_id` field. Implementations SHOULD include a `rejected_ops` extension field listing the specific `op_id` values that caused the rejection.
- `OP_BATCH_COMMIT` follows the same execution model (pre-commit or post-commit) as `OP_COMMIT` (Section 7.8)
- **Pre-commit disambiguation**: In pre-commit model, the coordinator MUST distinguish an initial `OP_BATCH_COMMIT` (the request-to-commit step) from a completion `OP_BATCH_COMMIT` (the post-execution declaration) by checking whether a pending batch with the same `batch_id` already exists. If no batch with that `batch_id` is registered, the message is the initial request and each entry MUST enter the `PROPOSED` lifecycle state. If a batch with that `batch_id` is already registered and authorized, the message is the completion declaration and each authorized entry transitions to `COMMITTED`. This parallels the `OP_COMMIT` disambiguation rule described in Section 16.6.1.

### 16.9 Scope Consistency

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
OPEN -> DISMISSED              (all related intents terminated, per Section 17.9)
OPEN -> ESCALATED -> RESOLVED -> CLOSED
ESCALATED -> DISMISSED         (all related intents terminated, per Section 17.9)
```

MPAC v0.1 does not require all lifecycle transitions to be explicitly represented as separate messages.
It requires that conflict state be representable and auditable.

#### 17.8.1 Conflict State Transition Table

The following table is normative.

| Current State | Event | Guard Condition | Next State | Action | Triggered By |
|---|---|---|---|---|---|
| (none) | `CONFLICT_REPORT` received | valid related intents/ops, valid watermark | OPEN | register conflict, notify related participants | any participant or coordinator |
| OPEN | `CONFLICT_ACK` received (ack_type: `seen` or `accepted`) | acknowledger is related participant | ACKED | record acknowledgment | related participant |
| OPEN | `CONFLICT_ESCALATE` received | escalation target has authority | ESCALATED | notify escalation target | any participant or coordinator |
| OPEN | `RESOLUTION` received | resolver has authority for the current authority phase (owner/arbiter/coordinator) | RESOLVED | apply outcome, release frozen scope if any | resolver |
| OPEN | all related entities terminated | Section 17.9 conditions met | DISMISSED | system-generated RESOLUTION with `decision: dismissed`, release frozen scope | coordinator |
| OPEN | frozen scope Phase 3 fallback | Section 18.6.2.1 Phase 3 timeout | CLOSED | system-generated RESOLUTION with `decision: policy_override`, first-committer-wins | coordinator |
| ACKED | `CONFLICT_ESCALATE` received | escalation target has authority | ESCALATED | notify escalation target | any participant or coordinator |
| ACKED | `RESOLUTION` received | resolver has authority for the current authority phase | RESOLVED | apply outcome, release frozen scope if any | resolver |
| ACKED | all related entities terminated | Section 17.9 conditions met | DISMISSED | system-generated RESOLUTION, release frozen scope | coordinator |
| ESCALATED | `RESOLUTION` received | resolver is the escalation target, a session-policy-authorized arbiter, or the coordinator issuing a system-generated outcome | RESOLVED | apply outcome, release frozen scope if any | resolver (typically escalation target or arbiter) |
| ESCALATED | all related entities terminated | Section 17.9 conditions met | DISMISSED | system-generated RESOLUTION, release frozen scope | coordinator |
| RESOLVED | (automatic) | resolution processed | CLOSED | archive, audit log | coordinator |

Terminal states: **CLOSED**, **DISMISSED**. No transitions out of terminal states are permitted.

### 17.9 Conflict Auto-Dismissal on Intent Termination

When all intents referenced by a conflict's `related_intents` field have transitioned to terminal states (`EXPIRED`, `WITHDRAWN`, `SUPERSEDED`, or `TRANSFERRED`), and all operations referenced by the conflict's `related_ops` field are in terminal states (`REJECTED`, `ABANDONED`, or `SUPERSEDED`), the conflict SHOULD be automatically transitioned to `DISMISSED` by the session coordinator.

The auto-dismissal MUST:
1. Generate a system-attributed `RESOLUTION` message with `decision`: `dismissed` and `rationale`: `all_related_entities_terminated`
2. Release any frozen scope (Section 18.6.2) associated with the dismissed conflict
3. Be recorded in the audit log

Auto-dismissal SHOULD take precedence over the frozen scope progressive degradation phases (Section 18.6.2.1) — if all related entities have terminated, the conflict should be dismissed immediately rather than waiting for Phase 2 or Phase 3 to trigger.

If a conflict references both intents and operations, and only the intents have terminated while some operations remain in non-terminal states (e.g., `COMMITTED`), auto-dismissal MUST NOT occur. The conflict remains active and subject to normal resolution or timeout procedures.

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

When a `RESOLUTION` rejects an operation that is already in `COMMITTED` state (i.e., the mutation has already been applied to shared state), the resolver MUST include a `rollback` field in the `outcome` object. The value MUST be either a reference to a compensating `OP_COMMIT` that reverses the effect, or the string `"not_required"` to indicate that no state reversal is needed. Resolutions that reject committed operations without a `rollback` field MUST be rejected by the session coordinator with a `PROTOCOL_ERROR` (`error_code`: `MALFORMED_MESSAGE`). MPAC does not define shared state rollback semantics — this is the responsibility of the application layer — but the protocol requires that every resolution affecting committed state makes its rollback expectation explicit for auditability.

Concurrent resolution rule: If the session coordinator receives multiple `RESOLUTION` messages for the same `conflict_id`, the coordinator MUST first evaluate whether each resolver is authorized for the conflict's **current authority phase**. Messages from resolvers that are not authorized for the current phase MUST be rejected and do not participate in ordering. Among resolvers that are authorized for the current phase, the coordinator MUST accept only the first valid `RESOLUTION` received (determined by coordinator receipt order) and reject subsequent valid `RESOLUTION` messages for the same conflict with a `PROTOCOL_ERROR` (`error_code`: `RESOLUTION_CONFLICT`). Before escalation, this first-resolution-wins rule applies among the normally authorized `owner` / `arbiter` / coordinator actors. After a conflict enters `ESCALATED`, only the `escalate_to` target, any arbiter explicitly authorized by session policy for that conflict class, or coordinator system-generated outcomes may resolve it. The ordering is determined by the coordinator's receipt order, not by message timestamps. This rule parallels the first-claim-wins semantics for `INTENT_CLAIM` (Section 14.7.4) while preserving arbiter finality after escalation.

Recommended `decision` values:
- `approved`
- `rejected`
- `dismissed`
- `human_override`
- `policy_override`
- `merged`

### 18.5 Arbiter Designation

Sessions in which multiple principals hold `owner` roles SHOULD designate at least one participant with the `arbiter` role at session creation time. The arbiter serves as the final decision authority when owners reach an impasse.

Arbiter designation requirements:

1. **Governance profile sessions**: Sessions that declare MPAC Governance Profile compliance (Section 20.2) MUST designate at least one `arbiter` at session creation. If no arbiter is designated, the session coordinator SHOULD emit a warning and MAY refuse to create the session.

2. **Arbiter qualifications**: The arbiter SHOULD be a `human` principal or a `service` principal with explicit organizational authority. Agent principals MAY serve as arbiter only if the session policy explicitly permits it.

3. **Arbiter availability**: If the designated arbiter leaves the session (via `GOODBYE` or unavailability detection per Section 14.7), participants SHOULD either designate a replacement arbiter or acknowledge that deadlock resolution may require out-of-band intervention.

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

#### 18.6.2.1 Frozen Scope Progressive Degradation

To prevent indefinite freezing while preserving as much work as possible, MPAC defines a three-phase degradation sequence for frozen scopes. Sessions SHOULD configure the phase durations in session policy; recommended defaults are provided below.

**Phase 1 — Normal resolution window** (default: 0–60 seconds after freeze)

The conflict follows the standard resolution flow. Participants and automated systems attempt resolution via `CONFLICT_ACK`, `RESOLUTION`, or `CONFLICT_ESCALATE`. No special behavior is triggered.

**Phase 2 — Automatic escalation and priority-based bypass** (default: 60–300 seconds after freeze)

If no `RESOLUTION` has been received by the end of Phase 1:

1. The session coordinator MUST automatically escalate the conflict to the designated arbiter via a system-generated `CONFLICT_ESCALATE` (if an arbiter is available). If no arbiter is designated or the arbiter is unavailable, proceed directly to step 2.
2. The coordinator SHOULD evaluate the conflicting intents' `priority` fields (Section 15.3). If one intent has strictly higher priority than all others involved in the conflict, the coordinator MAY allow operations associated with the higher-priority intent to proceed while keeping lower-priority operations frozen. This partial unfreeze MUST be logged and MUST generate a `PROTOCOL_ERROR` with `error_code`: `SCOPE_FROZEN` directed at the lower-priority participants, with a `description` explaining that the scope is partially unfrozen for a higher-priority intent.
3. If priorities are equal or unset, all operations remain frozen. The coordinator SHOULD broadcast a notification (via `PROTOCOL_ERROR` with `error_code`: `RESOLUTION_TIMEOUT`) to remind participants that the scope is blocked.

**Phase 3 — First-committer-wins fallback** (default: 300+ seconds after freeze)

If no `RESOLUTION` has been received by the end of Phase 2:

1. The coordinator MUST adopt a **first-committer-wins** policy: among the conflicting operations, the operation that was received first by the coordinator (determined by coordinator receipt order, not message timestamp) is accepted, and other conflicting operations are rejected.
2. Rejected operations MUST receive `OP_REJECT` with `reason`: `frozen_scope_fallback`. Critically, rejected operations in pre-commit model (Section 7.8) are NOT lost — the proposing agent MAY re-submit them after the scope is unfrozen (potentially with updated `state_ref_before` reflecting the accepted operation's effect). In post-commit model, the rejecting agent MUST issue a compensating operation to reverse the already-applied mutation.
3. The underlying conflict MUST be transitioned to `CLOSED` with a system-generated `RESOLUTION` (`decision`: `policy_override`, `rationale`: `frozen_scope_progressive_fallback_phase_3`). The `outcome` MUST list accepted and rejected operation IDs.
4. The frozen scope is released.

This progressive approach ensures that frozen scopes degrade gracefully: from human resolution (Phase 1), through priority-aware partial unfreeze (Phase 2), to deterministic automatic resolution (Phase 3). At no point is all work discarded.

Sessions MAY customize phase durations and MAY disable specific phases:

```json
{
  "governance": {
    "frozen_scope_phase_1_sec": 60,
    "frozen_scope_phase_2_sec": 240,
    "frozen_scope_phase_3_action": "first_committer_wins",
    "frozen_scope_disable_phase_3": false
  }
}
```

Setting `frozen_scope_disable_phase_3` to `true` disables the automatic fallback, leaving the scope frozen indefinitely until manual resolution. This is NOT RECOMMENDED for production deployments.

#### 18.6.3 Session Policy Example

```json
{
  "governance": {
    "require_arbiter": true,
    "resolution_timeout_sec": 300,
    "timeout_action": "escalate_then_freeze",
    "frozen_scope_behavior": "reject_writes_and_intents",
    "frozen_scope_phase_1_sec": 60,
    "frozen_scope_phase_2_sec": 240,
    "frozen_scope_phase_3_action": "first_committer_wins"
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
- `op.batch_commit`
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
- `SESSION_INFO` (including `execution_model` declaration, Section 7.8)
- `GOODBYE`
- `HEARTBEAT`
- `INTENT_ANNOUNCE`
- `OP_COMMIT`
- `OP_BATCH_COMMIT` (Section 16.8)
- `CONFLICT_REPORT`
- `RESOLUTION`
- `PROTOCOL_ERROR`
- Lamport clock maintenance rules (Section 12.7)
- Consistency model semantics (Section 7.7)
- `post_commit` execution model only (Section 7.8)

### 20.2 MPAC Governance Profile

Adds:
- role-aware authority
- escalation support (`CONFLICT_ESCALATE`)
- override semantics
- operation rejection support (`OP_REJECT`)
- operation supersession (`OP_SUPERSEDE`)
- arbiter designation (Section 18.5) — sessions MUST designate at least one arbiter
- resolution timeout support (Section 18.6) with progressive degradation (Section 18.6.2.1)
- intent claim support (`INTENT_CLAIM`) for unavailability recovery (Section 14.7)
- pre-commit execution model support (Section 7.8) — sessions declaring `pre_commit` MUST use Governance Profile compliance

### 20.3 MPAC Semantic Profile

Adds:
- semantic conflict reporting
- `basis.kind = model_inference`
- causal confidence handling or equivalent

Note: The Semantic Profile is a placeholder in v0.1.x. Its requirements are intentionally minimal; a detailed specification (including mandatory semantic matching output fields, confidence thresholds, and cross-implementation compatibility requirements) will be provided in a future version.

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
- `PARTICIPANT_UNAVAILABLE`: a participant has been detected as unavailable (Section 14.7.1)
- `RESOLUTION_TIMEOUT`: a conflict resolution has exceeded the configured timeout (Section 18.6.1)
- `SCOPE_FROZEN`: an operation or intent targets a scope that is frozen due to an unresolved conflict timeout (Section 18.6.2)
- `CLAIM_CONFLICT`: an `INTENT_CLAIM` targets a suspended intent that has already been claimed by another participant (Section 14.7.4)
- `COORDINATOR_CONFLICT`: a participant received `COORDINATOR_STATUS` from two different coordinators in the same session (Section 8.1.1.4)
- `STATE_DIVERGENCE`: a participant's reported state diverges from the coordinator's recovered snapshot (Section 8.1.1.3)
- `SESSION_CLOSED`: a message was received for a session that has been closed (Section 9.6)
- `CREDENTIAL_REJECTED`: the credential presented in `HELLO` failed verification (Section 23.1.4)
- `REPLAY_DETECTED`: a message with a duplicate `message_id` was rejected by replay protection (Section 23.1.2). Only emitted in Authenticated and Verified security profiles
- `RESOLUTION_CONFLICT`: a `RESOLUTION` was received for a conflict that has already been resolved by another participant (Section 18.4)
- `CAUSAL_GAP`: a participant has detected a gap in its causal state and is signaling that it may have missed intermediate messages (Section 12.8)
- `INTENT_BACKOFF`: an `INTENT_ANNOUNCE` was rejected because the participant is within the backoff period after a conflict-driven rejection for the same or overlapping scope (Section 15.3.1)
- `BACKEND_SWITCH_DENIED`: an agent attempted to switch to a backend model that is not permitted by the session's `backend_health_policy` — either `auto_switch` is `forbidden`, or the target provider is not in `allowed_providers` (Section 14.3.1)

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
- principal identity MUST be verified through the credential exchange mechanism defined in Section 23.1.4 before a participant's `HELLO` is accepted
- sessions MUST reject `HELLO` messages from principals whose identity cannot be verified, with a `PROTOCOL_ERROR` (`error_code`: `CREDENTIAL_REJECTED`)
- implementations MUST bind each `sender.principal_id` to the authenticated identity, preventing principal impersonation, and MUST treat `sender.sender_instance_id` as part of sender-incarnation tracking for replay and Lamport-monotonicity enforcement
- the `signature` envelope field (Section 11.3) SHOULD be populated with a message authentication code (MAC) or digital signature on every message
- implementations MUST implement replay protection by rejecting messages with duplicate `message_id` values or timestamps outside an acceptable window (RECOMMENDED: 5 minutes)
- replay protection continuity MUST survive coordinator recovery. Authenticated profile snapshots MUST preserve enough anti-replay checkpoint state to resume the same acceptance policy after restart
- role assertions in `HELLO` messages MUST be validated by the session coordinator against the session's role policy before the participant is admitted (Section 23.1.5). Participants MUST NOT be granted roles they are not authorized for, regardless of what they declare in `HELLO`
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
- Verified profile recovery MUST restore anti-replay checkpoint state before accepting new post-recovery messages
- implementations SHOULD support key rotation without session interruption

##### 23.1.3.1 Coordinator Accountability

In the Verified profile, the session coordinator is subject to the same cryptographic accountability requirements as any other participant. This prevents a compromised or malicious coordinator from silently manipulating session state.

Requirements:
- the coordinator MUST sign all outgoing messages (including `SESSION_INFO`, `OP_REJECT`, `PROTOCOL_ERROR`, `COORDINATOR_STATUS`, `SESSION_CLOSE`, and any system-generated messages such as synthetic `INTENT_UPDATE` for unavailability transitions or system-generated `RESOLUTION` for auto-dismissal) using its authenticated identity key
- participants MUST verify the coordinator's message signatures. Messages from the coordinator with invalid or missing signatures MUST be rejected
- the coordinator's signing public key MUST be distributed to all participants. The RECOMMENDED mechanism is to include the coordinator's public key fingerprint in `SESSION_INFO` (Section 23.1.6) and make the full public key available through the session's key registry
- the tamper-evident log (Section 23.1.3) MUST include coordinator-originated messages alongside participant messages. This ensures that an independent auditor can reconstruct and verify the coordinator's decision history
- participants MAY independently verify coordinator decisions against the tamper-evident log. If a participant detects that the coordinator issued a `RESOLUTION`, `OP_REJECT`, or state transition that is inconsistent with the protocol rules (e.g., rejecting an operation without a valid conflict, or resolving a conflict in favor of a party without sufficient authority), the participant SHOULD emit a `CONFLICT_REPORT` with category `authority_conflict` and MAY escalate to an external audit service
- for session transcript export (Section 9.6.3), the coordinator's signature chain MUST be included, enabling post-hoc verification of all coordinator actions by external parties

#### 23.1.4 Credential Exchange

In the Authenticated and Verified security profiles, participants MUST present a credential during the `HELLO` handshake to establish their identity. The credential is carried in a `credential` field in the `HELLO` payload.

Extended `HELLO` payload for Authenticated/Verified profiles:

```json
{
  "display_name": "Alice",
  "roles": ["contributor"],
  "capabilities": ["intent.broadcast", "op.commit"],
  "credential": {
    "type": "bearer_token",
    "value": "eyJhbGciOiJSUzI1NiIs..."
  }
}
```

The `credential` object MUST include:

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `type` | string | R | Credential type. One of: `bearer_token`, `mtls_fingerprint`, `api_key`, `x509_chain`, `custom` |
| `value` | string | R | The credential value (token, certificate fingerprint, key, etc.) |
| `issuer` | string | O | Identity provider or certificate authority that issued the credential |
| `expires_at` | string | O | RFC 3339 timestamp when the credential expires |

Supported credential types:

1. **`bearer_token`**: An OAuth 2.0 bearer token or JWT. The coordinator MUST validate the token signature and claims (audience, expiry, issuer) against the session's identity provider configuration. The `issuer` field SHOULD contain the token issuer URL.

2. **`mtls_fingerprint`**: The SHA-256 fingerprint of the client certificate presented during the TLS handshake. This type is used when identity verification happens at the transport layer. The coordinator MUST verify that the fingerprint matches a certificate in the session's trust store.

3. **`api_key`**: A pre-shared API key issued by the session coordinator or an administrative system. The coordinator MUST validate the key against its key registry. This type is suitable for intra-organization deployments.

4. **`x509_chain`**: A PEM-encoded X.509 certificate chain. Required in the Verified profile. The coordinator MUST validate the chain against its configured trust anchors and verify that the leaf certificate's subject matches the declared `principal_id`.

5. **`custom`**: An implementation-defined credential type. The coordinator MUST have a registered handler for the custom type. Sessions using custom credentials SHOULD document the expected format in session metadata.

The coordinator's response in `SESSION_INFO` MUST include an `identity_verified` field:

```json
{
  "granted_roles": ["contributor"],
  "identity_verified": true,
  "identity_method": "bearer_token",
  "identity_issuer": "https://auth.example.com"
}
```

If credential verification fails, the coordinator MUST reject the `HELLO` with a `PROTOCOL_ERROR` (`error_code`: `CREDENTIAL_REJECTED`) and MUST NOT admit the participant to the session.

In the Open security profile, the `credential` field is optional and MAY be omitted. If present, the coordinator MAY validate it but MUST NOT reject participants solely based on credential absence.

#### 23.1.5 Role Assignment and Verification

Roles determine a participant's governance authority (Section 18.2). In all security profiles, role assignment follows this process:

1. **Role request**: The participant declares requested roles in the `HELLO` message's `roles` field.

2. **Role policy evaluation**: The coordinator evaluates the request against the session's role policy. The role policy defines:
   - which roles each identity is authorized for (identity-to-role mapping)
   - maximum number of participants per role (e.g., at most 2 arbiters)
   - role prerequisites (e.g., `arbiter` requires `human` principal type unless overridden)

3. **Role grant**: The coordinator returns the actually granted roles in `SESSION_INFO`'s `granted_roles` field. If the granted roles differ from the requested roles, the coordinator SHOULD include a human-readable explanation in `compatibility_errors`.

4. **Role enforcement**: After admission, the coordinator MUST reject messages that require authority the sender's granted roles do not provide. For example, a `contributor` sending a `RESOLUTION` (which requires `owner` or `arbiter`) MUST be rejected with `PROTOCOL_ERROR` (`error_code`: `AUTHORIZATION_FAILED`).

Role policy configuration:

```json
{
  "role_policy": {
    "default_role": "contributor",
    "role_assignments": {
      "agent:alice": ["contributor", "reviewer"],
      "human:bob": ["owner", "arbiter"]
    },
    "role_constraints": {
      "arbiter": {
        "max_count": 2,
        "allowed_principal_types": ["human", "service"]
      }
    }
  }
}
```

In the Open profile, if no role policy is defined, participants receive the roles they request. In the Authenticated and Verified profiles, a role policy MUST be defined and the coordinator MUST enforce it.

#### 23.1.6 Key Distribution and Rotation

In the Authenticated and Verified security profiles, message signing requires that participants and the coordinator can verify each other's signatures. MPAC defines the following key distribution requirements:

1. **Coordinator public key**: The coordinator's signing public key MUST be distributed to participants through a trusted channel before or during session join. The recommended mechanism is to include the coordinator's public key fingerprint in the `SESSION_INFO` message:

```json
{
  "security_config": {
    "coordinator_key_fingerprint": "sha256:abcdef1234567890",
    "key_exchange_method": "session_info"
  }
}
```

2. **Participant public keys**: Each participant's signing public key MUST be made available to other participants for signature verification. The coordinator SHOULD maintain a key registry and distribute participant public keys through an implementation-defined mechanism (e.g., a `PARTICIPANT_KEYS` extension message, or inclusion in the session's trust store).

3. **Key rotation**: If a participant needs to rotate their signing key during a session (e.g., scheduled rotation, suspected compromise), they MUST:
   - send a `HEARTBEAT` with a new `key_rotation` extension field containing the new public key fingerprint
   - the coordinator MUST validate the rotation request against the participant's authenticated identity
   - the coordinator MUST broadcast the key change to all participants
   - messages signed with the old key MUST continue to be accepted for a grace period (recommended: `2 × heartbeat_interval_sec`)

4. **Watermark integrity in Verified profile**: In the Verified profile, watermark values MUST be included in the signed portion of each message. This prevents watermark forgery — a participant cannot claim a higher Lamport clock value than they actually observed, because the signature binds the watermark to the authenticated sender.

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
10. Implement unavailability detection and orphaned intent recovery (Section 14.7)
11. Include `canonical_uris` in scope objects when participants use heterogeneous scope kinds (Section 15.2.1)
12. Use the `semantic_match` basis kind with standardized output format for assumption contradiction detection (Section 17.7.1)
13. Support `lamport_clock` as the baseline watermark kind and include `lamport_value` in non-lamport watermarks (Section 12.3)
14. Use the mandatory scope overlap rules for `file_set`, `entity_set`, and `task_set` (Section 15.2.1.1)
15. Require `state_ref_before` and `state_ref_after` in all `OP_COMMIT` messages (Section 16.3)
16. Validate role assertions against session policy in Authenticated and Verified profiles (Section 23.1.2)
17. Declare the session's execution model (`pre_commit` or `post_commit`) in `SESSION_INFO` (Section 7.8)
18. Follow the Lamport clock maintenance rules for all message sends and receives (Section 12.7)
19. Use `OP_BATCH_COMMIT` for multi-resource atomic operations instead of multiple independent `OP_COMMIT` messages (Section 16.8)
20. In Verified profile deployments, verify coordinator message signatures and include coordinator actions in the tamper-evident log (Section 23.1.3.1)
21. Implement exponential backoff for intent re-announcement after conflict-driven rejection to prevent livelock (Section 15.3.1)
22. When a causal gap is detected via watermark analysis, refrain from issuing causally-sensitive judgments until the gap is resolved (Section 12.8)
23. Preserve `sender.sender_instance_id` across coordinator reconnection when the sender process survives, and scope Lamport monotonicity per sender incarnation (Section 12.7)
24. Include and enforce `coordinator_epoch` on coordinator-authored messages so stale coordinators can be fenced during handover and failover (Section 8.1.1.4)
25. In Authenticated and Verified profiles, persist anti-replay checkpoint state in coordinator snapshots so replay protection survives recovery (Sections 8.1.1.2, 23.1.2)

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
  "version": "0.1.14",
  "message_type": "HELLO",
  "message_id": "msg-001",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:alice-coder-1",
    "principal_type": "agent",
    "sender_instance_id": "inst-a1"
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
  "version": "0.1.14",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-010",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:alice-coder-1",
    "principal_type": "agent",
    "sender_instance_id": "inst-a1"
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
  "version": "0.1.14",
  "message_type": "OP_COMMIT",
  "message_id": "msg-020",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:alice-coder-1",
    "principal_type": "agent",
    "sender_instance_id": "inst-a1"
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
  "version": "0.1.14",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-030",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "agent:bob-review-1",
    "principal_type": "agent",
    "sender_instance_id": "inst-b1"
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
  "version": "0.1.14",
  "message_type": "RESOLUTION",
  "message_id": "msg-040",
  "session_id": "sess-001",
  "sender": {
    "principal_id": "human:alice",
    "principal_type": "human",
    "sender_instance_id": "inst-h1"
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

- standard conflict ontology extensions
- conflict confidence scoring
- operation diff payload standards
- ownership lease semantics
- protocol conformance test suite
- participant capability negotiation beyond HELLO
- session-level resource registry auto-population and discovery mechanisms
- standard assumption ontology or vocabulary for common domains (to improve `semantic_match` accuracy across implementations)
- hierarchical vector clocks or interval tree clocks for reduced causal metadata overhead in large sessions
- integration architecture guidance for deployments combining MPAC with MCP (agent-to-tool) and A2A (agent-to-agent) protocols
- end-to-end payload encryption specification for deployments with untrusted coordinators
- semantic scope and dependency declaration for detecting non-file-level conflicts (e.g., API contract changes, schema-query coupling)
- post-commit rollback semantics (OP_ROLLBACK message type or OP_SUPERSEDE rollback flag)
- cross-session coordination and scope conflict detection across independent sessions
- compact envelope / binary serialization for reduced message overhead
- scope-based subscription for O(n) message routing instead of O(n²) broadcast
- session sharding with cross-session intent references

Note: The following gaps were identified in prior reviews and have been addressed across v0.1.1–v0.1.13: security profiles and trust enforcement (Section 23), credential exchange and trust establishment (Section 23.1.4), role assignment and verification (Section 23.1.5), key distribution and rotation (Section 23.1.6), coordinator accountability in Verified profile (Section 23.1.3.1), governance deadlock prevention (Sections 18.5–18.6), frozen scope progressive degradation (Section 18.6.2.1), participant unavailability recovery (Section 14.7), semantic interoperability foundations (Sections 15.2.1–15.2.3, 17.7.1), payload schema tables (Section 13.1), scope overlap standardization (Section 15.2.1), baseline watermark interoperability (Section 12.3), Lamport clock maintenance rules (Section 12.7), session coordinator role (Section 8.1), coordinator fault recovery and handover (Section 8.1.1), session lifecycle and close (Section 9.6), formal JSON Schema definitions (ref-impl/schema/), OP_SUPERSEDE handler implementation, coordinator fault recovery with snapshot + audit log replay, execution model clarification with pre-commit/post-commit modes (Section 7.8), consistency model declaration (Section 7.7), atomic multi-target operations via OP_BATCH_COMMIT (Section 16.8), formal state transition tables for all three lifecycle state machines (Sections 15.6.1, 16.6.1, 17.8.1), concurrent resolution race handling with phase-scoped first-resolution-wins (Section 18.4), intent re-announce livelock prevention with exponential backoff (Section 15.3.1), causal gap detection behavior (Section 12.8), coordinator epoch fencing (Section 8.1.1.4), sender incarnation semantics for Lamport monotonicity (Sections 11.4, 12.7), explicit claim disposition via `INTENT_CLAIM_STATUS` (Section 14.7.4.1), operation settled-state terminology (Sections 9.6.1, 16.6.1), replay-protection continuity across recovery (Sections 8.1.1.2, 23.1.2), governance-only `pre_commit` semantics with authorization separated from commit completion (Sections 7.8, 16.6.1), `TRANSFERRED` alignment in conflict auto-dismiss (Section 17.9), mandatory claim-approval attribution in Governance Profile sessions (Section 14.7.4.1), example message alignment with normative sender requirements (Section 28), `SESSION_INFO` payload completeness for `identity_issuer` (Section 13.1), `SESSION_CLOSE` summary field alignment (Sections 9.6.2, 14.5), `COORDINATOR_STATUS` cross-reference precision (Section 14.6), `OP_BATCH_COMMIT` pre-commit disambiguation rule (Section 16.8), `INTENT_UPDATE` scope-expansion conflict re-evaluation (Section 15.4), `GOODBYE` transfer disposition via `SUSPENDED`/`INTENT_CLAIM` (Section 14.4), and Semantic Profile placeholder clarification (Section 20.3).

## 30. Summary

MPAC v0.1.14 defines a structured protocol for multi-agent collaboration centered on:
- sessions with defined lifecycle (creation, discovery, close, audit export)
- session coordination with fault tolerance (state snapshots, recovery, handover, audit log replay, coordinator epoch fencing)
- explicit consistency model (coordinator-serialized total order with degraded-mode semantics, Section 7.7)
- explicit execution model (pre-commit or post-commit, declared per session, with governance-only `pre_commit` and explicit authorization-before-commit semantics, Section 7.8)
- intents with mandatory pre-execution declaration (Governance Profile), formal state transition tables, explicit claim disposition, and livelock prevention via exponential backoff (Section 15.3.1)
- operations with required state references, atomic batch commit support (`OP_BATCH_COMMIT`), formal state transition tables, and clarified settled-state terminology for session lifecycle
- conflicts with standardized scope overlap rules, formal state transition tables, and progressive frozen scope degradation
- governance with deadlock prevention, three-phase frozen scope recovery, deterministic concurrent resolution handling, and arbiter-preserving phase-scoped authority after escalation (Section 18.4)
- causal context with baseline watermark interoperability, explicit Lamport clock maintenance rules, sender-incarnation-safe rejoin semantics, and causal gap detection behavior (Section 12.8)
- security with credential exchange, role verification, key distribution, watermark integrity, replay-protection continuity, and coordinator accountability (Verified profile)
- failure recovery with concurrent claim resolution

Its central design claim is that collaborative agent systems become more interoperable, auditable, and governable when intent, mutation, conflict, and resolution are represented as explicit protocol messages rather than hidden inside application logic. The protocol provides security profiles with concrete trust establishment mechanisms — including coordinator accountability in the Verified profile — for deployments ranging from intra-team to cross-organizational, coordinator fault tolerance with snapshot-based recovery and audit log replay for production reliability, governance mechanisms to prevent deadlock between equal-authority principals with progressive degradation rather than binary timeout-then-reject, deterministic concurrent resolution handling ensuring that multiple resolvers for the same conflict produce a single authoritative outcome while preserving arbiter finality after escalation, an explicit consistency model declaring coordinator-serialized total order under normal operation, coordinator epoch fencing to keep that ordering coherent across handover and failover, an execution model that separates authorization from commit completion in governance-heavy sessions, atomic batch commit for multi-resource operations, intent re-announce backoff to prevent livelock in repeated scope overlap scenarios, explicit claim-disposition signaling for participant recovery, mandatory approval attribution for governance-mediated claim transfer, causal gap detection behavior to guide participants toward conservative decisions when their causal context is incomplete, sender-incarnation semantics that make Lamport monotonicity compatible with coordinator reconnection, replay-protection continuity across recovery in authenticated deployments, recovery semantics to handle participant failure without orphaning in-flight work, operation supersession for safe post-commit revisions, semantic interoperability mechanisms (canonical resource URIs and standardized semantic matching output) to enable cross-kind scope overlap detection and assumption contradiction identification, session lifecycle management with transcript export for compliance, formal JSON Schema definitions for machine-enforceable wire format compatibility, normative state transition tables for all three lifecycle state machines, explicit Lamport clock maintenance rules, and payload schema definitions to ensure cross-implementation field-level compatibility.
