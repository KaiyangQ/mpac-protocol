# MPAC v0.1.3 Rigorous Audit Report

**Audit Date**: 2026-04-02
**Audit Subject**: SPEC.md (MPAC v0.1.3 — Interoperability Hardening)
**Auditor Role**: Senior Distributed Systems Architect / Multi-Agent Systems Expert
**Audit Scope**: Five dimensions — Efficiency, Robustness, Scalability, Semantic Alignment, and State Machine Cross-Safety

---

## Overall Assessment

MPAC v0.1.3 is a multi-agent coordination protocol draft with **clear design intent, well-structured layering, and a sound iterative direction**. After three rounds of iteration (v0.1 -> v0.1.1 -> v0.1.2 -> v0.1.3), the protocol has evolved from a "proof of concept" into an "implementable engineering draft." The five-layer abstraction model (Session -> Intent -> Operation -> Conflict -> Governance) offers targeted solutions to the core pain points of multi-agent coordination — intent conflict pre-detection, cross-agent governance, and causal traceability.

However, from a rigorous engineering deployment perspective, the protocol still has structural issues in four areas that must be acknowledged: **message efficiency, large-scale scalability, fault recovery completeness, and semantic negotiation**. The following sections examine each in detail.

---

## 1. Efficiency Audit

### 1.1 Excessive Message Envelope Overhead

Every MPAC message must carry a full envelope (Section 11.2): `protocol`, `version`, `message_type`, `message_id`, `session_id`, `sender` (including nested object), `ts`, `payload`, plus the recommended `watermark` object. Take a simple HEARTBEAT message as an example — its payload contains only one field, `status: "idle"`, yet the JSON serialization of the envelope itself is approximately 300-500 bytes while the payload is under 30 bytes — **the envelope overhead is 10-15 times the effective payload**.

For HEARTBEAT messages sent every 30 seconds, this ratio is unreasonable. In a session with 100 participants, the network overhead from heartbeat messages alone reaches ~50KB/30s (100 x 500B), annualizing to approximately 52GB of pure heartbeat traffic.

**Severity**: Medium
**Recommendations**:
- Define a lightweight "compact envelope" mode that allows high-frequency, low-value messages such as HEARTBEAT to omit `protocol`, `version`, and the full `sender` object (replacing it with a short `sender_id` identifier)
- Alternatively, allow session-level envelope field caching — after the initial HELLO, subsequent messages may omit unchanged fields
- Consider introducing binary serialization options (e.g., CBOR/MessagePack) rather than mandating JSON

### 1.2 Two-Phase Overhead Introduced by Intent-Before-Action

Under a Governance Profile, a complete operation flow requires: `INTENT_ANNOUNCE` -> (wait for conflict detection) -> `OP_PROPOSE` -> (wait for approval) -> `OP_COMMIT`. This is a **three-message + two-wait** flow. If a conflict is detected, it additionally requires `CONFLICT_REPORT` -> `CONFLICT_ACK` -> `RESOLUTION`, totaling six messages to complete a single operation.

Compared to direct operations, this introduces at least 2 RTTs of latency. For high-frequency collaboration scenarios (e.g., real-time document editing), this latency may be unacceptable.

**Severity**: Medium
**Recommendations**:
- Introduce an `INTENT_ANNOUNCE_AND_PROPOSE` merged message type, allowing intent declaration and operation proposal to be combined into a single message when no conflicts are expected (optimistic path optimization)
- Define a "fast-path" strategy: for scope overlaps with `low` severity level, allow operations to proceed first with post-hoc conflict detection

### 1.3 Lack of Message Batching Mechanism

When an Agent needs to perform related operations on multiple resources (e.g., a refactoring affecting 10 files), the current protocol requires a separate `OP_COMMIT` for each file. There is no standard batching envelope to atomically package multiple operations together.

**Severity**: Medium
**Recommendations**: Define an `OP_BATCH` message type that allows multiple `OP_COMMIT` messages to be packaged as an atomic operation group, sharing a single envelope and watermark

### 1.4 Redundant Handshake Assessment

The protocol itself has no strict "handshake" — `HELLO` is a unidirectional declaration rather than a request/response. This is good design. However, due to the **lack of Session Negotiation** (see v0.1.3 Re-evaluation Report Section 1), participants may discover they are incompatible with the session after sending `HELLO`, forcing them to immediately send `GOODBYE`, resulting in a wasteful "join-discover incompatibility-leave" interaction. This is not a redundant handshake, but rather **implicit waste caused by the absence of a necessary handshake**.

**Severity**: Low-Medium

**Efficiency Summary**: The protocol's design prioritizes "semantic completeness over transmission efficiency," which is reasonable for a v0.1 draft. However, if compact envelopes, fast paths, and batching mechanisms are not introduced in v0.2, the protocol's practical throughput in high-frequency collaboration scenarios will become a bottleneck.

---

## 2. Robustness Audit

### 2.1 Participant Offline Recovery: Good Foundation but Blind Spots Exist

The unavailability detection and recovery mechanisms introduced in v0.1.1 (Section 14.4) are a highlight of the protocol. The `SUSPENDED` / `ABANDONED` states, the `INTENT_CLAIM` message, and the first-claim-wins race resolution are all well-considered designs.

**However, the following blind spots remain**:

**a) Session Coordinator Single Point of Failure**
Section 8.1 defines the coordinator as the sole logical center of a session, but recovery from a coordinator crash is entirely undefined. Heartbeat detection, frozen scope enforcement, identity binding — all critical runtime functions depend on the coordinator. Once the coordinator becomes unavailable, the entire session's coordination capability drops to zero.

The spec only states that "distributed deployments MUST provide equivalent mechanisms," but for the most common single-coordinator deployment, there is no recovery guidance whatsoever. There are no state persistence requirements, no suggestions for state reconstruction after restart, and no minimal framework for coordinator failover.

**Severity**: High
**Recommendations**:
- Add a SHOULD-level requirement to Section 8.1: the coordinator SHOULD support state persistence (participant roster, intent registry, conflict state) to enable state reconstruction from the audit log
- Define participant behavior when the coordinator is unavailable: SHOULD pause all conflict-sensitive operations, MAY continue read-only activities
- Suggest (without mandating) a coordinator heartbeat mechanism — participants should also be able to detect coordinator liveness

**b) Split-Brain Risk Under Network Partition**
If a network partition causes some participants to lose contact with the coordinator while remaining reachable to each other, the current protocol has no mechanism to prevent participants on both sides of the partition from simultaneously operating on the same resource. This is not a problem MPAC must solve (Section 4 explicitly states it does not replace CRDT/OT), but the protocol should **acknowledge and declare** this boundary rather than remain silent.

**Severity**: Medium
**Recommendations**: Explicitly state in Section 8.1 or Non-Goals (Section 4): MPAC does not guarantee consistency under network partitions; conflicts in partition scenarios should be retroactively resolved through the standard conflict reporting mechanism after the partition heals

**c) Race Condition Between TTL Expiration and Operation Submission**
Intent TTL (`ttl_sec`) is measured in wall-clock seconds, but the spec never defines who is responsible for executing expiration checks, the precision requirements for those checks, or how to handle operations submitted at the moment of expiration. If the coordinator uses its local wall clock to check TTL, clock skew between participants could lead to: Agent A believes the intent is still valid and submits OP_COMMIT, but the coordinator determines the intent has expired and rejects the operation.

**Severity**: Medium
**Recommendations**: Clarify that TTL is determined by the coordinator's local wall clock, and that the `ts` in `INTENT_ANNOUNCE` is used only for auditing purposes. The coordinator records a `received_at` timestamp upon receiving `INTENT_ANNOUNCE`, and TTL is calculated based on `received_at + ttl_sec`.

### 2.2 Deadlock Risk Analysis

**a) Frozen Scope Deadlock — Essentially Resolved**
The `frozen_scope_timeout_sec` in v0.1.3 (Section 18.6.2.1) provides a timeout release mechanism, which is effective protection against deadlocks. The design allows disabling (set to 0), but the default of enabled (1800 seconds) is reasonable.

**b) Governance Arbitration Deadlock — Residual Risk**
If the session's only arbiter goes offline with no substitute, conflicts will first escalate, then freeze the scope, and finally time out and release. However, the timeout release results in **rejecting all parties** — meaning both sides' work is discarded. For long-running collaborative sessions, this is a high-cost degradation path.

**Severity**: Low-Medium
**Recommendations**: Upon timeout release, add a `deferred` decision option — suspend the conflict rather than reject all parties, allowing participants to continue with other non-conflicting work until the arbiter recovers and can process the backlogged conflicts

**c) Cyclic Conflict Risk**
The current protocol does not prevent the following cycle: A's operation triggers a conflict -> after resolution B resubmits -> triggers another conflict -> after resolution A resubmits again... There is no limit on the number of conflict rounds on a single scope.

**Severity**: Low
**Recommendations**: Add a SHOULD-level suggestion — session policy MAY define a maximum number of conflict rounds on the same scope (e.g., 3), after which human intervention is required

### 2.3 Error Handling Completeness

`PROTOCOL_ERROR` (Section 22) provides 10 error codes covering common protocol violation scenarios. This is reasonable. However, `PROTOCOL_ERROR` is defined as "informational" — it does not mandate any recovery behavior. This means an implementation that receives a `MALFORMED_MESSAGE` error can choose to completely ignore it and continue sending malformed messages.

**Severity**: Low
**Recommendations**: For security-critical errors (`AUTHORIZATION_FAILED`, `VERSION_MISMATCH`), add SHOULD-level consequences — e.g., after receiving N instances of `AUTHORIZATION_FAILED`, the coordinator SHOULD suspend that participant

**Robustness Summary**: Participant-level fault recovery design is excellent (SUSPENDED/ABANDONED/INTENT_CLAIM is a highlight), but three system-level fault scenarios — coordinator single point of failure, network partition, and TTL race conditions — lack coverage.

---

## 3. Scalability Audit

### 3.1 From 3 Agents to 100: The Message Fan-Out Problem

The current protocol's messaging model is **broadcast-based** — every message is visible to all participants in the session. In a 3-Agent session, this is entirely reasonable. But in a 100-Agent session:

- Each `INTENT_ANNOUNCE` must be processed and checked for conflicts by 99 other participants
- HEARTBEAT messages every 30 seconds produce 100 messages that all participants must receive
- Conflict detection complexity goes from O(n) to O(n^2) — each new intent must be checked for scope overlap against all existing intents

**Estimates for a 100-Agent scenario**:
- Heartbeat traffic: ~100 x 500B x 2/min = ~100KB/min = ~6MB/hour (heartbeat only)
- Intent conflict detection: if each Agent has an average of 2 active intents, each new intent requires 198 scope overlap checks
- Total message throughput: assuming each Agent produces an average of 5 messages per minute, totaling 500 msg/min, each participant must process an inbound message stream of 500 msg/min

**This will not cause the protocol to "crash," but it will lead to significant performance degradation.**

**Severity**: High
**Recommendations**:
- Introduce **scope-based subscription**: participants can declare the scope ranges they are interested in, and the coordinator only forwards relevant messages
- Introduce **intent registry digest push**: instead of broadcasting every `INTENT_ANNOUNCE` in full, the coordinator maintains a digest of the intent registry (e.g., a Bloom filter), periodically pushes it to participants, and participants perform local pre-filtering before fetching details
- Consider coordinator aggregation for heartbeat messages — participants send heartbeats to the coordinator, the coordinator maintains a liveness table, and other participants query on demand rather than passively receiving all heartbeats

### 3.2 Session Coordinator Scalability

Section 8.1 requires each session to have exactly one logical coordinator. In large-scale sessions, the coordinator must:
- Maintain liveness state for 100 participants
- Handle ordering and forwarding of all messages
- Enforce frozen scope checks
- Verify identity bindings (Authenticated Profile)
- Maintain the audit log

This is a single-point performance bottleneck. The spec allows the coordinator to be implemented via distributed consensus mechanisms, but this statement reads more like a disclaimer than actionable guidance.

**Severity**: Medium-High
**Recommendations**:
- Define minimum recommended performance requirements for the coordinator (e.g., SHOULD be able to process N messages/second, where N is determined by session scale)
- Consider introducing a **session sharding** mechanism: large-scale collaborations can be split into multiple sub-sessions, each with an independent coordinator, coordinated through cross-session intent references
- Add recommended session size limits in Section 9 (e.g., Core Profile recommended <= 20 participants, Governance Profile recommended <= 50)

### 3.3 Computational Complexity of Scope Overlap Detection

For `file_set` scope (Section 15.2.1.1), overlap determination is a set intersection with complexity O(|A| x |B|) (naive implementation) or O(|A| + |B|) (hash set). This is fine when scopes are small, but if a single intent's scope declaration includes thousands of files (e.g., a large-scale refactoring) and needs to be cross-checked against 200 active intents, the computational load grows significantly.

`resource_path` glob matching is even more expensive — determining overlap between two glob patterns is in general undecidable (requiring regex intersection). The spec only requires SHOULD support for `*` and `**`, but even for just these two operators, precise determination is non-trivial.

**Severity**: Medium
**Recommendations**:
- Recommend that implementers maintain index structures for scope overlap detection (e.g., trie or inverted index)
- Define recommended size limits for scope declarations (e.g., the `resources` array in `file_set` SHOULD not exceed 1000 entries)
- For glob overlap on `resource_path`, provide a reference algorithm or explicitly state that false positives (conservatively assuming overlap) are permissible

### 3.4 Watermark Maintenance Cost

The maintenance cost of `vector_clock` grows linearly with the number of participants — each message's watermark must include clock values for all participants. In a 100-participant session, each watermark object is approximately 2-3KB (100 key-value pairs), plus merge logic is required for every message.

The spec's choice of `lamport_clock` as the MUST-support baseline is correct — its maintenance cost is O(1) and independent of participant count. However, the spec does not recommend that large-scale sessions should prefer `lamport_clock` over `vector_clock`.

**Severity**: Low
**Recommendations**: Add implementation guidance — when a session has more than 20 participants, `lamport_clock` SHOULD be preferred; `vector_clock` is suitable for scenarios with few participants that require precise causal tracing

**Scalability Summary**: The protocol performs well in scenarios with 10 or fewer participants. When scaling to 100 participants, message fan-out, coordinator bottleneck, and scope overlap computation are three engineering problems that need to be addressed. The protocol will not "crash," but performance will degrade significantly. Scope-based subscription and session sharding mechanisms need to be introduced.

---

## 4. Semantic Alignment Audit

### 4.1 Intent Understanding Between Heterogeneous Agents

MPAC's intent model uses a mixture of natural language fields (`objective`, `assumptions`) and structured fields (`scope`). This is a pragmatic design — under current technological conditions, fully formalized intent representation is unrealistic.

**But the core question is: how can Agents of varying capabilities accurately understand each other's intents?**

A coding Agent declares `objective: "Tune training stability"` + `scope: file_set ["train.py"]`, and a DevOps Agent declares `objective: "Update infrastructure config"` + `scope: entity_set ["deployment.training"]` — these two intents may conflict semantically (modifying training code vs. modifying training deployment configuration), but at the scope level they use different `kind` values and lack `canonical_uris`.

Section 15.2.1.3 requires cross-kind overlap to be determined through canonical URIs or a resource registry; otherwise it SHOULD conservatively assume potential overlap. This conservative strategy is correct, but its cost is a **high volume of false positive conflict reports**, which reduces the system's signal-to-noise ratio and causes participants and human reviewers to be overwhelmed by spurious conflicts.

**Severity**: Medium-High
**Recommendations**:
- Elevate `canonical_uris` in Section 15.2.2 from SHOULD to MUST (at least in cross-organization sessions)
- Define a `CAPABILITY_NEGOTIATION` phase that lets participants align on scope kind usage conventions at the start of a session
- Suggest (without mandating) declaring a "preferred scope kind" in session metadata to guide all participants toward a unified scope representation

### 4.2 Reliability Boundaries of `semantic_match`

Section 17.7.1 defines the `semantic_match` base structure, including a `confidence` field and a configurable threshold (recommended 0.7). This is a forward-looking design that acknowledges the role of LLM reasoning in conflict detection.

**But the problem is**: `semantic_match` results depend entirely on the matcher's capability, and different implementations' matchers may produce vastly different results. Two MPAC implementations performing semantic match on the same pair of intents — one says `contradictory` (confidence: 0.85), the other says `uncertain` (confidence: 0.45) — and the protocol does not define how to reconcile this discrepancy.

**Severity**: Medium
**Recommendations**:
- Explicitly state that `semantic_match` determination is authoritative based on the **conflict report sender's** matcher; the receiver may mark it as `disputed` (CONFLICT_ACK) but cannot unilaterally negate it
- Define a "matcher registry": a session-level declaration of which matcher serves as authoritative, preventing both sides from insisting on their own determination
- Low-confidence semantic conflicts SHOULD automatically escalate to human review rather than being debated back and forth between Agents

### 4.3 Assumption Semantic Alignment Issues

The `assumptions` field in `INTENT_ANNOUNCE` is a string array with entirely natural language content. For example, `"hidden_dim remains 256"` and `"model architecture unchanged"` may or may not be semantically equivalent — it depends on the interpreter's understanding.

The protocol relies on `semantic_match` (Section 17.7.1) to detect assumption contradictions, but if Agents in a session come from different technology stacks or use different terminology systems, semantic alignment of natural language assumptions will be very fragile.

**Severity**: Low-Medium
**Recommendations**:
- Suggest (without mandating) using a "namespace:key=value" format in assumptions (e.g., `"model:hidden_dim=256"`), providing a foundation for structured comparison
- This can be implemented as an extension rather than a core requirement, balancing flexibility and precision

### 4.4 Missing Protocol Version Negotiation

Section 25 defines the version field but does not define version negotiation. If Agent A sends a message with version "0.1.3" and Agent B only understands "0.1.0," how should this be handled? The current behavior is that B can send a `PROTOCOL_ERROR` (VERSION_MISMATCH), but no downgrade negotiation path is defined.

**Severity**: Low (currently only v0.1.x exists)
**Recommendations**: Reserve design space for a version negotiation mechanism in Section 25 — at minimum, define that the HELLO response can carry the range of versions supported by the coordinator

**Semantic Alignment Summary**: The protocol performs reasonably well on structured semantics (scope objects, enum values) and relies on LLM reasoning and human review for unstructured semantics (objective, assumptions). `canonical_uris` and `semantic_match` are the right direction, but the former's adoption rate is hard to guarantee (SHOULD rather than MUST) and the latter's cross-implementation consistency cannot be guaranteed.

---

## 5. State Machine Cross-Safety Audit

MPAC defines three core state machines (intent lifecycle, operation lifecycle, conflict lifecycle) and three semantic ordering constraints (session-first, intent-before-operation, conflict-before-resolution). These state machines execute concurrently at runtime and reference each other. This section exhaustively examines key cross-cutting scenarios to verify whether the protocol contains unreachable states, orphaned objects, or livelock risks.

### 5.1 Intent TTL Expiration + Orphaned OP_PROPOSE (Confirmed Vulnerability)

**Scenario**: Agent A sends `INTENT_ANNOUNCE` (ttl_sec: 120) + `OP_PROPOSE`; the intent expires while OP_PROPOSE is still awaiting reviewer approval.

**Protocol coverage**: **Not covered**.

The intent lifecycle defines `ACTIVE -> EXPIRED` (Section 15.6), and the operation lifecycle defines `PROPOSED -> COMMITTED / REJECTED / ABANDONED` (Section 16.6). However, the `ABANDONED` state is defined only in Section 14.4.3 for **participant unavailability** scenarios. When an intent expires due to TTL, the protocol does not define how its associated pending proposals should be handled — the proposal references a non-existent intent, but its own state is neither COMMITTED, REJECTED, nor ABANDONED.

**Risk Level**: High — this is a state inconsistency on the most common operation path
**Recommendations**: Add a rule: when an intent's state transitions to EXPIRED, all PROPOSED-state operations referencing that intent MUST automatically transition to REJECTED (reason: `intent_expired`), or provide a grace period for the submitter to re-associate with a new intent

### 5.2 Intent SUSPENDED + Another Party's Pending Proposal

**Scenario**: Agent B submits a proposal referencing Agent A's intent (via the intent_id field in OP_PROPOSE). Subsequently, Agent A goes offline and its intent is marked SUSPENDED.

**Protocol coverage**: **Partially covered; residual vulnerability exists**.

Section 14.4.2 explicitly prohibits new OP_PROPOSE/OP_COMMIT from referencing suspended intents. Section 14.4.3 covers in-flight proposals sent by the unavailable participant themselves (marked as ABANDONED). However, if the proposal's sender (Agent B) is still online but the intent owner (Agent A) is unavailable — Agent B's proposal enters a gray area not defined by the spec: it does not meet the trigger conditions for ABANDONED (the sender is online), nor can it proceed (the referenced intent is suspended).

**Risk Level**: Medium
**Recommendations**: Extend the rule in Section 14.4.2 — when an intent enters the SUSPENDED state, all PROPOSED-state operations referencing that intent (regardless of sender) SHOULD be frozen or submitted for governance review

### 5.3 Frozen Scope While Intent TTL Expires

**Scenario**: A and B's intents have scope overlap -> CONFLICT_REPORT -> governance timeout -> scope frozen. During the freeze, A and B's intents enter the EXPIRED state due to TTL expiration.

**Protocol coverage**: **Not covered**.

At this point the system enters a semantically self-contradictory state:
- The conflict (OPEN/ESCALATED) still exists, referencing two already-expired intents
- The condition for releasing the frozen scope is "receipt of a valid RESOLUTION" (Section 18.6.2), but RESOLUTION requires ruling on the intents/operations in the conflict (accepted/rejected/merged)
- Ruling accepted/rejected on already-EXPIRED intents is semantically a no-op — regardless of the ruling outcome, those intents no longer exist

Section 18.6.2.1's `frozen_scope_timeout_sec` will ultimately serve as a backstop release (auto-reject + close conflict), but in the window between intent expiration and frozen scope timeout release, the system is in an **inconsistent state where conflicts exist but their associated entities have ceased to exist**.

**Risk Level**: Medium
**Recommendations**: Add a rule — when all `related_intents` in a conflict have expired or been withdrawn, the conflict SHOULD automatically transition to DISMISSED (reason: `all_related_intents_expired`), simultaneously releasing the associated frozen scope. No need to wait for frozen_scope_timeout

### 5.4 State Divergence When RESOLUTION Rejects an Already-COMMITTED Operation

**Scenario**: Agent A's OP_COMMIT has been applied to shared state. Subsequently, RESOLUTION marks that operation as rejected.

**Protocol coverage**: **Acknowledged the problem but did not mandate a solution**.

Section 18.4 requires the resolver "SHOULD" provide compensating operations or declare `rollback: "not_required"`. But SHOULD is not MUST, and a compliant implementation can issue a RESOLUTION rejecting an already-committed operation without rolling back or declaring that rollback is unnecessary. The result is: **the operation's protocol state is REJECTED, but its effects still persist in shared state** — signaling layer and data layer state divergence.

**Risk Level**: Medium
**Recommendations**: Elevate SHOULD to MUST — when RESOLUTION rejects an operation with COMMITTED status, it MUST include an `outcome.rollback` field (either a compensating operation reference or `"not_required"`)

### 5.5 INTENT_CLAIM Approval vs. Original Participant Reconnection Race

**Scenario**: Agent A becomes unavailable -> intent is SUSPENDED -> Agent B submits INTENT_CLAIM -> Agent A reconnects during the approval period.

**Protocol coverage**: **Resolved**.

Section 14.4.4 explicitly defines: "if the original participant reconnects before the claim is approved, the claim SHOULD be automatically withdrawn and the original intent restored to ACTIVE." The original participant's reconnection takes priority over claim approval. Concurrent claims are resolved through first-claim-wins + CLAIM_CONFLICT error code. **This path is fully closed.**

### 5.6 Timeout Cascade and Livelock Risk

**Scenario**: A and B repeatedly submit -> conflict -> freeze -> timeout release -> resubmit -> conflict again, forming a cycle.

**Protocol coverage**: **Not covered**.

The three semantic ordering constraints (session-first, intent-before-operation, conflict-before-resolution) are themselves a unidirectional dependency chain and do not form circular dependencies, so they will not produce traditional deadlocks. However, when TTL timeout (intent layer), resolution_timeout (governance layer), and frozen_scope_timeout (conflict layer) — three timers fire concurrently, the cascade effect may manifest as: scope released -> Agent immediately resubmits -> overlaps again -> freezes again -> times out and releases again... This is a **liveness violation** — the system is technically making progress (states are changing), but the effective throughput is zero.

**Risk Level**: Low-Medium — requires multiple conditions to be simultaneously met
**Recommendations**: Add a SHOULD-level rule — session policy MAY define a maximum number of conflict rounds on the same scope (recommended default: 3); once exceeded, that scope is forcibly escalated to human arbitration, preventing automated Agents from retrying indefinitely

### 5.7 State Machine Cross-Safety Summary Table

| Scenario | State Machine Crossover Involved | Resolved? | Risk Level |
|------|----------------|-----------|---------|
| Intent TTL expiration + orphaned OP_PROPOSE | intent x operation | **Unresolved** | High |
| Intent SUSPENDED + another party's pending proposal | intent x operation x session | **Partially resolved** | Medium |
| Frozen scope + intent TTL exhaustion | conflict x intent x governance | **Unresolved** | Medium |
| RESOLUTION rejects already-COMMITTED operation | governance x operation x shared state | **Partially resolved** (SHOULD) | Medium |
| INTENT_CLAIM vs. original participant reconnection | session x intent | **Resolved** | -- |
| Timeout cascade livelock | intent x conflict x governance (triple timeout) | **Unresolved** | Low-Medium |

**State Machine Cross-Safety Summary**: The protocol's three core state machines are each individually well-designed, and the ordering constraints are directionally correct. However, **cross-lifecycle linkage rules** between state machines are severely insufficient — particularly the impact of intent expiration (EXPIRED/SUSPENDED) on downstream operations and conflicts, which is almost entirely undefined. It is recommended that before v0.2, formal verification of the intent x operation x conflict triple state space be conducted using TLA+ or Alloy to systematically discover and close remaining cross-cutting vulnerabilities.

---

## 6. Comprehensive Strengths and Weaknesses Summary

### Core Strengths

1. **The five-layer separation architecture** is the protocol's greatest intellectual contribution. Treating intents as first-class citizens independent of operations, and decoupling conflicts and governance from the operation layer — this design is both correct and forward-looking in the multi-agent coordination domain.

2. **The Intent-Before-Action principle** is the core differentiator compared to MCP/A2A. Elevating it to MUST under the Governance Profile was a critical correct decision in v0.1.3.

3. **The participant unavailability recovery mechanism** (SUSPENDED -> INTENT_CLAIM -> TRANSFERRED) is elegantly designed; the first-claim-wins + grace period race resolution approach is clean and effective.

4. **Frozen scope + timeout release** for deadlock protection is a pragmatic engineering choice that prevents infinite blocking while retaining configurability.

5. **The three-tier security Profile** (Open / Authenticated / Verified) layered design is well-conceived, allowing different trust environments to select the corresponding security level.

6. **The v0.1.3 improvements — payload schema, scope overlap standardization, and lamport_clock baseline** — significantly enhance cross-implementation interoperability.

### Core Weaknesses

1. **Session Coordinator single point of failure**: all runtime guarantees of the protocol depend on the coordinator, yet no fault recovery is defined for the coordinator itself.

2. **Message efficiency not optimized**: full broadcast + heavyweight envelopes + no batching will become a performance bottleneck in large-scale sessions.

3. **Session Negotiation missing**: participants can only discover incompatibility after joining; there is no pre-join capability verification.

4. **Scalability lacks architectural support**: there are no standard approaches for scope-based subscription, session sharding, or coordinator distribution.

5. **Semantic alignment depends on natural language**: understanding of assumptions and objectives is highly dependent on matcher capability, with no guarantee of cross-implementation consistency.

6. **TTL semantics are ambiguous**: the ambiguity between wall clock and logical clock has not been fully resolved, and the coordinator's checking behavior is not standardized.

---

## 7. Specific Modification Recommendations (Ordered by Priority)

| Priority | Recommendation | Affected Dimension | Estimated Effort |
|--------|------|-----------|-----------|
| P0 | Define disposition rules for associated OP_PROPOSE when an intent expires (intent_expired -> auto reject) | State machine safety | Low |
| P0 | Define minimum coordinator fault recovery requirements (state persistence + restart reconstruction) | Robustness | Medium |
| P0 | Introduce SESSION_INFO response message to implement session negotiation | Semantic alignment / Robustness | Medium |
| P0 | Auto-DISMISS conflict and release frozen scope when all related intents have expired | State machine safety | Low |
| P1 | Define scope-based subscription mechanism | Scalability | High |
| P1 | Introduce compact envelope or binary serialization option | Efficiency | Medium |
| P1 | Elevate `canonical_uris` to MUST in cross-organization sessions | Semantic alignment | Low |
| P1 | Clarify that TTL is determined by coordinator's local wall clock + received_at semantics | Robustness | Low |
| P2 | Introduce OP_BATCH message type | Efficiency | Medium |
| P2 | Define recommended session size limits and sharding guidance | Scalability | Medium |
| P2 | Define minimum enum set for op_kind | Semantic alignment | Low |
| P2 | Declare state_ref_format in session metadata | Semantic alignment | Low |
| P1 | Elevate rollback field from SHOULD to MUST when RESOLUTION rejects a COMMITTED operation | State machine safety | Low |
| P2 | INTENT_UPDATE expanding scope SHOULD trigger conflict re-check | Robustness | Low |
| P2 | Define maximum conflict rounds on same scope to prevent timeout cascade livelock | State machine safety | Low |
| P3 | Structured format suggestion for assumptions (namespace:key=value) | Semantic alignment | Low |
| P3 | Implementation guidance for preferring lamport_clock in large-scale sessions | Scalability | Low |
| P3 | Define consequences for security-critical PROTOCOL_ERROR | Robustness | Low |

---

## 8. Scoring

| Dimension | Score (1-10) | Explanation |
|------|------------|------|
| **Efficiency** | **5.5** | Prioritizing semantic completeness over transmission efficiency is a reasonable strategy, but without compact envelopes, batching, and fast-path mechanisms, overhead in high-frequency scenarios is excessive |
| **Robustness** | **7.0** | Participant-level fault recovery is excellent and deadlock protection is pragmatic, but coordinator single point of failure, network partition, and TTL race conditions are system-level blind spots |
| **Scalability** | **5.0** | Performs well with 10 or fewer participants; lacks scope subscription, session sharding, and coordinator distribution support; performance degrades significantly at 100 participants |
| **Semantic Alignment** | **6.5** | Structured scope and canonical URIs are directionally correct; semantic_match design is forward-looking; but cross-implementation consistency of natural language assumptions is questionable |
| **State Machine Cross-Safety** | **4.5** | Individual state machines are well-designed and ordering constraints are correct, but cross-lifecycle linkage rules are severely insufficient — the impact of intent expiration on downstream operations/conflicts is almost entirely undefined, with multiple confirmed orphaned object and state inconsistency scenarios |
| **Overall Score** | **5.7** | As a v0.1 draft, MPAC proposes correct abstractions and valuable mechanisms for the multi-agent coordination domain, with a sound iterative direction. However, deficiencies in state machine cross-safety expose the protocol's systematic shortcomings in "concurrency correctness." Introducing TLA+ formal verification before v0.2 is recommended. From an "implementable protocol draft" to a "production-ready interoperability protocol," substantial work remains on state machine linkage rules, efficiency optimization, scalability architecture, and session negotiation |

---

*Audit Conclusion: MPAC v0.1.3 is a protocol draft with clear academic value and engineering potential. Its five-layer abstraction model and intent-before-action principle are original contributions to the multi-agent coordination domain. However, the state machine cross-safety audit revealed multiple cross-lifecycle linkage vulnerabilities (orphaned proposals, dead zones between frozen scope and TTL exhaustion, timeout cascade livelocks) — problems that are difficult to exhaustively identify through manual review alone. Recommendations before v0.2: (1) complete the linkage rules for intent expiration's impact on downstream objects (the two P0 items); (2) conduct formal verification of the intent x operation x conflict triple state space using TLA+ or Alloy; (3) address coordinator fault recovery and session negotiation; (4) begin development of a conformance test suite.*
