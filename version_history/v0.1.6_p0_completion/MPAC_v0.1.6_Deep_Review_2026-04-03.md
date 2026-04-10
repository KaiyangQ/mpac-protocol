# MPAC v0.1.6 Independent Technical Review

**Reviewer Role**: Simulated SOSP/OSDI/NSDI-level reviewer
**Review Date**: 2026-04-03
**Document Version**: MPAC Specification v0.1.6 (Draft / Experimental)

---

## Overall Assessment

MPAC attempts to address a real and important problem: how to coordinate when multiple independent principals (each with their own agent) need to collaborate on shared state. This problem indeed falls in a gap between existing MCP (agent-to-tool) and A2A (agent-to-agent, single principal) protocols.

However, as a protocol specification, MPAC v0.1.6 suffers from serious design ambiguities and engineering feasibility issues across multiple critical dimensions. The following is a dimension-by-dimension in-depth analysis.

---

## 1. Core Design and Abstractions

### 1.1 Conceptual Definitions

MPAC's core conceptual hierarchy is Session -> Participant -> Intent -> Operation -> Conflict -> Resolution, which is a reasonable layering. Each concept has a clear Section definition, and the glossary (Section 5) is reasonably clear.

**Positive assessment**: Elevating conflict and resolution to first-class protocol objects (rather than hiding them in application logic) is a good design decision. The intent-before-action philosophy is also commendable -- it is conceptually similar to the "declaration phase" in two-phase locking.

### 1.2 Issues

**Confused abstraction levels**: The protocol simultaneously tries to do two things -- define message semantics (protocol layer) and define entity lifecycle state machines (runtime layer). For example, Intent has a state machine (DRAFT->ANNOUNCED->ACTIVE->...), but the DRAFT state "does not require on-the-wire manifestation" (Section 15.6), which significantly undermines the normative force of the state machine. A protocol specification should either fully define on-the-wire observable state transitions or explicitly exclude internal states from the protocol scope.

**Session definition is too loose**: The Session's shared state can be "file set, document graph, task graph, database snapshot, tool state machine, simulation state" (Section 9.5). This over-generalization means the protocol cannot make any meaningful guarantees about state. For comparison: Raft explicitly defines a replicated log, Paxos explicitly defines a consensus value. MPAC's shared state is a completely opaque external concept, rendering the semantics of `state_ref_before` / `state_ref_after` entirely implementation-dependent.

**Scope abstraction overload**: Scope supports 6 kinds (file_set, resource_path, task_set, query, entity_set, custom), where the overlap determination for `query` and `custom` is entirely left to the implementation (Section 15.2.1.2). This means two MPAC-conformant implementations could reach opposite overlap conclusions for the same pair of scopes -- directly breaking conflict detection interoperability.

### 1.3 Missing Abstractions

**Missing "Resource" as a first-class entity**: The protocol extensively discusses resource overlap, lock, and freeze, but resource itself has no independent data model. Scope references resource, Operation targets resource, Frozen scope locks resource -- yet "resource" remains a string-level identifier with no type, version, ownership, or other attributes. This will lead to numerous edge cases in real systems.

**Missing transaction semantics**: The protocol defines OP_PROPOSE and OP_COMMIT, but has no concept of atomic batch commit. If an intent involves modifying 3 files, the agent must send 3 independent OP_COMMITs. Between the 2nd and 3rd commit, the system is in a partially committed state -- the protocol provides no guarantees or handling mechanisms for this.

---

## 2. Consistency and Unambiguity

### 2.1 Key Ambiguity Points

**Semantic ambiguity of `OP_COMMIT`**: Does `OP_COMMIT` mean "request to commit" (requiring coordinator confirmation) or "declare already committed" (agent has already modified the shared state)? Section 16.3 says "declare that a mutation has been committed into shared state," implying the agent has already directly modified the state. But Section 16.6's state machine shows PROPOSED->COMMITTED, implying this is an approval workflow. If the agent has already modified the underlying state when sending OP_COMMIT, what is the semantics of OP_REJECT? The data has already been changed. If it hasn't been modified, the word "committed" is misleading.

This is a fatal ambiguity. Different implementation teams will make completely different choices, making interoperability impossible.

**Unclear responsibility for conflict detection**: Who is responsible for detecting conflicts? Section 17 says any participant can send `CONFLICT_REPORT`, and so can the coordinator. But if the coordinator performs conflict detection while a certain agent does not (or reaches a different conclusion), what is the system behavior? Undefined. Compare Perforce's approach: the server is the sole authority for conflict detection.

**Overuse of "SHOULD" vs "MUST"**: The protocol extensively uses SHOULD, making almost all key behaviors optional. For example:
- "participants SHOULD announce intent before non-trivial work" (Section 15.3) -- what if they don't announce?
- "implementations SHOULD detect and flag operations that fall outside the scope" (Section 23.3) -- what if they don't detect?
- Watermark in non-OP_COMMIT/CONFLICT_REPORT/RESOLUTION messages is "SHOULD include" (Section 7.3)

When the protocol's core mechanisms (intent announcement, scope violation detection) are at the SHOULD level, a MUST-only implementation and a full-SHOULD implementation can barely interoperate.

### 2.2 Terminology Issues

**`principal` vs `participant` vs `sender`**: The three concepts overlap. Principal is an "accountable actor," Participant is a "principal currently joined to a session," and Sender is a message-level identifier. But can a principal have multiple agents? Can a human principal send messages through different devices? These edge cases are undefined.

**Ambiguous authority boundaries for the `arbiter` role**: An arbiter "may resolve any conflict and override any participant" (Section 18.2), but Section 18.5 says disagreements among arbiters require "session policy SHOULD define a precedence rule." What if the policy doesn't define one? The system behavior when two arbiters issue contradictory RESOLUTIONs is completely undefined.

---

## 3. Concurrency and Conflict Handling

### 3.1 Race Condition Analysis

**Intent-Operation timing window race**: Consider the following scenario:
1. Agent A sends INTENT_ANNOUNCE (scope: auth.py)
2. Agent B sends INTENT_ANNOUNCE (scope: auth.py)
3. Agent A sends OP_COMMIT (target: auth.py) before seeing B's intent
4. Agent B sends OP_COMMIT (target: auth.py) before seeing A's commit

At this point both commits are legitimate (each agent's watermark may not include the other's messages). The protocol does not define who wins. `state_ref_before` could serve as the basis for optimistic concurrency control, but only if the coordinator serializes commit processing -- and whether the coordinator must do this is not explicitly specified by the protocol.

**RESOLUTION race**: If two authorized participants (e.g., two owners) simultaneously send RESOLUTIONs for the same conflict, what is the result? Section 18.5 mentions that for multiple arbiters "SHOULD define precedence rule," but the case of multiple owners resolving simultaneously is completely unaddressed.

**Frozen scope boundary race**: When a scope is frozen (Section 18.6.2), OP_COMMIT will be rejected. But what if an OP_COMMIT message was sent before the scope freeze and arrives at the coordinator after it? This depends on whether the coordinator uses its own reception time or the message's watermark for judgment. Undefined.

### 3.2 Deadlock Risk

**Circular scope dependency deadlock**:
1. Agent A declares intent, scope = {file1.py, file2.py}
2. Agent B declares intent, scope = {file2.py, file3.py}
3. Agent C declares intent, scope = {file3.py, file1.py}

If conflicts trigger frozen scopes (Section 18.6.2), the three scopes could mutually lock each other. While frozen_scope_timeout_sec (Section 18.6.2.1) provides a timeout fallback, the default timeout of 30 minutes is too long for real-time collaboration. More importantly, after timeout all conflicting operations are rejected -- there is no heuristic to determine whose work should be preserved.

### 3.3 Livelock Risk

**Intent TTL retry livelock**: If two agents' intents repeatedly overlap, expire, and re-announce, the system may enter a livelock. The protocol has no backoff mechanism, priority arbitration, or lease-based exclusive locks to break the symmetry.

---

## 4. Fault Handling and Recovery Mechanisms

### 4.1 Positive Assessment

Section 8.1.1 (Coordinator Fault Recovery) and Section 14.7 (Participant Unavailability) are the most substantive parts of this specification. The recovery strategy of state snapshot + audit log replay is sound. The INTENT_CLAIM mechanism (Section 14.7.4) provides an ownership transfer path for orphaned intents.

### 4.2 Key Issues

**No snapshot consistency guarantee**: Section 8.1.1.2 requires the coordinator to "persist a state snapshot at least once per heartbeat interval," but there may be a gap between the snapshot and the audit log. If the coordinator crashes after a snapshot but before the next one, and the audit log is also lost (e.g., audit log writes are asynchronous), the recovered state will be stale. The protocol says "SHOULD use a write-ahead or atomic write mechanism," but this is SHOULD, not MUST. In SOSP/OSDI-level systems, this kind of SHOULD-level durability guarantee is unacceptable.

**STATE_DIVERGENCE handling is too vague**: Section 8.1.1.3 says that if a participant's local state and the coordinator's snapshot are inconsistent, the coordinator "SHOULD emit a PROTOCOL_ERROR with error_code: STATE_DIVERGENCE." And then what? "include the divergent message IDs for manual or governance-level resolution" -- kicking the hardest problem to humans. In a multi-agent system, if after coordinator crash recovery 3 agents have each committed different modifications during the coordinator's downtime, merely reporting divergence is insufficient. A reconciliation protocol needs to be defined.

**Consistency model is unstated**: The protocol never explicitly states whether it provides strong consistency or eventual consistency. From the design (coordinator is single point of authority, but agents can continue "read-only or non-conflicting activities" when the coordinator is down), this looks like a hybrid model -- strong consistency when the coordinator is available, degrading to eventual consistency when it is down. But this has never been formalized. Readers do not know what guarantees the protocol provides.

**Network partition handling**: Section 8.1.1.1 says participants "suspend all conflict-sensitive operations" when they detect coordinator unavailability. But if the partition is a network issue between the participant and coordinator (rather than a coordinator crash), the coordinator is still running normally, other participants are still working normally, and the partitioned participant has suspended all its operations -- this is an unnecessary availability loss. Worse, the coordinator will also mark that participant as unavailable, potentially triggering SUSPENDED transitions for its intents. When the network recovers, the reconciliation complexity far exceeds the protocol's current handling capability.

---

## 5. Security and Trust Model

### 5.1 Positive Assessment

The three-tier security configuration (Open / Authenticated / Verified) is a pragmatic design. Credential exchange (Section 23.1.4) supports multiple authentication methods. Requiring message signing + tamper-evident log in the Verified profile is the right direction.

### 5.2 Key Issues

**Coordinator is a single point of trust**: Under all security configurations, the coordinator holds full power -- verifying identity, assigning roles, enforcing scope freezes, deciding conflict resolution order. If the coordinator is compromised, an attacker can impersonate any principal, modify role assignments, and manipulate conflict resolution. The Verified profile requires message signing, but the coordinator's own behavior is not constrained by any mechanism. In a truly adversarial multi-party scenario, this is unacceptable. Some form of coordinator accountability is needed -- for example, all coordinator decisions must also be signed and independently auditable.

**Replay protection is not strict enough**: The Authenticated profile requires "rejecting messages with duplicate message_id values or timestamps outside an acceptable window (RECOMMENDED: 5 minutes)" (Section 23.1.2). A 5-minute replay window is too large. Moreover, the message_id uniqueness check requires the coordinator to maintain a "seen message_id set" -- what if this set is lost after coordinator crash recovery? The snapshot does not include this set.

**Credential transmission security in HELLO messages**: In the Authenticated profile, the bearer token is placed directly in a plaintext field of the HELLO payload (Section 23.1.4 example). If the transport layer is not TLS (the protocol claims to be transport-independent), the token is transmitted in plaintext. Although Section 23.4 says "SHOULD use TLS 1.3," this is a SHOULD. A security protocol should not transmit credentials over SHOULD-level transport security.

**Malicious Agent scope spoofing**: An agent can declare a very narrow intent scope, then commit an operation that exceeds the scope. Section 23.3 says this "SHOULD be logged and MAY trigger a CONFLICT_REPORT" -- this is entirely insufficient. In cross-organization scenarios, this should be MUST reject.

---

## 6. Implementability

### 6.1 Directly Implementable Parts

The message format (JSON envelope + payload) is clearly defined, with complete payload schemas (Section 13.1). The basic message flow (HELLO -> SESSION_INFO -> INTENT_ANNOUNCE -> OP_COMMIT -> CONFLICT_REPORT -> RESOLUTION) is implementable.

### 6.2 Implementation Barriers

**Cross-kind scope overlap determination**: Section 15.2.1.3 says cross-kind overlap "MUST be determined via canonical URIs or session resource registry"; if neither is available, "SHOULD treat cross-kind scopes as potentially overlapping." But what does "potentially overlapping" mean? Does it immediately trigger a CONFLICT_REPORT? Does it block OP_COMMIT? Implementers face a specification with undetermined behavior.

**Implementation burden of semantic match**: Section 17.7.1 defines the semantic_match basis kind, containing fields like confidence, matched_pair, and explanation. But the protocol says "The semantic matching algorithm itself is explicitly outside the scope of MPAC." This means implementing the Semantic Profile requires integrating an NLP/LLM system, yet the protocol provides no guidance on threshold calibration, false positive handling, or consistency between different matchers.

**Missing formal state machine definitions**: The state machines for Intent and Operation are represented as ASCII art (Section 15.6, 16.6), but there is no formalized transition table (from_state, event, guard_condition -> to_state, action). For example, who can trigger the ACTIVE->SUSPENDED transition? Only the coordinator? Any governance authority? Under what conditions?

**Missing sequence diagrams or interaction sequences**: Section 27 provides an 8-step "minimal flow," but for complex scenarios (e.g., intent claim during coordinator failover, frozen scope escalation + timeout sequences), there are no sequence diagrams. Engineering teams must derive all edge cases on their own.

### 6.3 Missing Key Details

- **Message size limits**: Not defined. What if a CONFLICT_REPORT's description field contains 10MB of text?
- **Concurrent session limits**: How many sessions can a single agent participate in simultaneously?
- **Message delivery guarantees**: The protocol says transport is responsible for delivery, but does not define what the protocol should do if messages are lost (aside from watermark being able to detect gaps).
- **Lamport clock maintenance rules**: Who increments the Lamport clock? Is it incremented for every message? Only by the coordinator? How is it updated upon message reception? These are fundamental rules for implementing a Lamport clock, but the protocol does not define them.

---

## 7. Comparison with Existing Systems

### 7.1 Similar Paradigms

**Optimistic Concurrency Control (OCC)**: MPAC's intent-announce + OP_COMMIT + state_ref_before is essentially an OCC variant. But standard OCC (such as MVCC in databases) has well-defined abort-and-retry semantics; MPAC does not.

**Two-Phase Commit (2PC)**: OP_PROPOSE -> OP_COMMIT resembles 2PC's prepare -> commit, but lacks an abort protocol and coordinator-driven commit decisions.

**Google Docs-style OT/CRDT**: MPAC explicitly states it is not a replacement for CRDT/OT (Section 4), but it also does not define how to coexist with CRDT/OT. If shared state is managed with CRDT, what is the relationship between MPAC's state_ref_before/after and CRDT's causal consistency?

**Paxos/Raft**: The coordinator's single-leader design is similar to a Raft leader, but there is no election protocol, no log replication, and no concept of committed index. Section 8.1.1.4 mentions failover, but in practice it is "somebody else takes over and loads a snapshot" -- far less rigorous than Raft's guarantees.

### 7.2 Innovation Assessment

MPAC's core innovation lies in introducing **intent** as a first-class protocol object in multi-agent coordination. This differs from traditional database transactions (which do not declare intent) and also from traditional locks (intent is not exclusive; overlapping intents can be resolved through governance). The "soft lock + structured conflict resolution" design point is valuable.

However, this innovation is more at the **conceptual level** than the **mechanism level**. The protocol does not provide any new distributed algorithms -- it uses Lamport clocks, state snapshots, and timeout-based failure detection, all of which are classic techniques. The innovation lies in combining these techniques for the agent coordination problem domain and adding a governance layer.

---

## 8. Key Deficiencies (Top 5)

### Deficiency #1: Semantic ambiguity of OP_COMMIT (Severity: Fatal)

**Problem**: Does OP_COMMIT mean "declare already modified" or "request to commit"? If the former, then OP_REJECT and conflict resolution both require rollback, but the protocol has no rollback mechanism. If the latter, the name "commit" is misleading.

**Why this is dangerous**: This is the semantic foundation of the entire operation layer. If Implementation A interprets OP_COMMIT as "already modified shared state" while Implementation B interprets it as "request coordinator approval before modifying," the two will produce catastrophic inconsistency in the same session -- A's state has already changed, B is still waiting for approval.

### Deficiency #2: Lack of atomicity guarantees (Severity: High)

**Problem**: An intent involving multiple resources requires multiple independent OP_COMMITs. In the intermediate state of partial commits, other agents may see inconsistent shared state and may make erroneous conflict judgments or new commits based on it.

**Why this is dangerous**: In real collaborative programming scenarios, refactoring often involves atomic cross-file modifications (e.g., renaming a function referenced in multiple places). Without atomic batch commit, MPAC cannot safely support such operations. Section 29 (Future Work) acknowledges this issue ("atomic multi-target operations"), but in the current version this is a known safety gap.

### Deficiency #3: Undefined consistency model (Severity: High)

**Problem**: The protocol does not state what consistency guarantees it provides. When the coordinator is running normally, does it guarantee linearizability? When the coordinator is down, what are the semantics of participants continuing "non-conflicting activities" -- eventual consistency?

**Why this is dangerous**: Users of distributed systems need to know the system's consistency guarantees to correctly build higher-level applications. If MPAC does not declare a consistency level, implementers will make different choices (some choosing to block and wait for the coordinator, others choosing to continue execution), resulting in different implementations exhibiting different behaviors under the same scenarios -- directly violating the interoperability goal.

### Deficiency #4: Over-centralized coordinator trust (Severity: Medium-High)

**Problem**: The coordinator serves as identity verifier, role assigner, conflict resolution enforcer, scope freeze executor, and snapshot maintainer -- all trust is concentrated in this single component. Yet the coordinator's own behavior is not constrained or audited by any mechanism (in the Verified profile, are the coordinator's messages also required to be signed?).

**Why this is dangerous**: In cross-organization scenarios (MPAC's core use case), the coordinator is typically operated by one party. If the operating party has a conflict of interest, they can manipulate conflict resolution through the coordinator, delay competitors' intents, or selectively enforce scope freezes. Without a coordinator accountability mechanism, the Verified profile's security guarantees are significantly diminished.

### Deficiency #5: Availability impact of Frozen Scope (Severity: Medium)

**Problem**: When a conflict triggers a frozen scope (Section 18.6.2), all write operations on the related resources are blocked until the conflict is resolved. The default frozen scope timeout is 30 minutes. If the arbiter is offline, 30 minutes of blocking is unacceptable for a real-time collaboration system.

**Why this is dangerous**: In practical use, a frozen scope on a frequently modified core file (such as main.py, index.ts) will stall all agents. The fallback after 30 minutes is "reject all conflicting operations" -- meaning after 30 minutes of waiting, everyone's work is discarded. This is not a graceful degradation design; it is a "wait 30 minutes then fail entirely" design.

---

## 9. Recommendations

### Recommendation 1: Clarify the OP_COMMIT execution model

Define two explicit modes:
- **Pre-commit mode**: OP_PROPOSE is an intent declaration; OP_COMMIT requires coordinator confirmation before modifying shared state. Suitable for Governance Profile.
- **Post-commit mode**: OP_COMMIT is a declaration that modification has been completed; the coordinator is responsible for detecting conflicts and triggering compensating actions when needed. Suitable for Core Profile.

Both modes must be declared in SESSION_INFO and cannot be mixed.

### Recommendation 2: Introduce an OP_BATCH message type

Define an OP_BATCH message containing atomic operations across multiple targets:

```json
{
  "message_type": "OP_BATCH",
  "payload": {
    "batch_id": "batch-001",
    "intent_id": "intent-123",
    "operations": [
      { "op_id": "op-1", "target": "auth.py", "op_kind": "replace", ... },
      { "op_id": "op-2", "target": "routes.py", "op_kind": "replace", ... }
    ],
    "atomicity": "all_or_nothing"
  }
}
```

This solves the multi-file atomic modification problem and also provides the coordinator with clear batch conflict detection boundaries.

### Recommendation 3: Declare the consistency model

Add to Section 7 (Shared Principles):
- **Coordinator-available**: All state transitions are serialized through the coordinator, providing total order.
- **Coordinator-unavailable**: Participants can only perform read-only operations and local cache writes. After coordinator recovery, a reconciliation protocol must be run.
- Explicitly state that MPAC does not provide linearizability (because agents can perform local operations between declaring intent and committing).

### Recommendation 4: Introduce Coordinator Accountability

Add to the Verified profile:
- All coordinator decision messages (SESSION_INFO, OP_REJECT, SCOPE_FROZEN notifications, etc.) must also be signed.
- Any participant can submit the coordinator's signed decision chain to an external audit service to verify whether the coordinator has faithfully executed the protocol.
- Declare the coordinator's public key in session metadata so all participants can independently verify the coordinator's messages.

### Recommendation 5: Improve the Frozen Scope degradation strategy

Replace the current "wait 30 minutes then reject all" strategy with a progressive degradation approach:
1. **Phase 1 (0-60s)**: Wait normally for resolution.
2. **Phase 2 (60-300s)**: Automatically escalate to the arbiter; if no arbiter is available, allow the agent with higher intent priority to proceed.
3. **Phase 3 (300s+)**: Adopt a first-committer-wins strategy; later commits are rejected but not discarded (converted to PROPOSED status for resubmission).

This avoids prolonged blocking and the extreme case of "total failure."

### Recommendation 6: Formalize the state machines

Define a complete state transition table for each of Intent, Operation, and Conflict:

| Current State | Event | Guard | Next State | Action |
|---|---|---|---|---|
| ACTIVE | HEARTBEAT_TIMEOUT | owner unavailable | SUSPENDED | notify all, freeze ops |
| SUSPENDED | HELLO received | original owner | ACTIVE | unfreeze ops |
| SUSPENDED | INTENT_CLAIM approved | claim authorized | TRANSFERRED | transfer scope |

This eliminates the ambiguities in the current ASCII state diagrams and provides implementers with a directly codable specification.

### Recommendation 7: Define Lamport Clock maintenance rules

Add a dedicated subsection:
- Each participant maintains a local Lamport counter.
- When sending a message: counter++, use the counter value as watermark.value.
- When receiving a message: counter = max(local_counter, received_counter) + 1.
- The coordinator maintains a session-global Lamport counter for snapshots and session close.

These are the standard semantics of a Lamport clock, but the protocol must state them explicitly; otherwise implementers may make different choices.

---

## Summary Scores

| Dimension | Score (1-5) | Notes |
|---|---|---|
| Problem Importance | 4.5 | Multi-principal agent coordination is a real and important problem |
| Core Design | 3.0 | Intent-first philosophy is good, but abstraction levels are confused |
| Consistency/Unambiguity | 2.0 | Multiple fatal ambiguities, overuse of SHOULD |
| Concurrency Handling | 2.0 | Lacks systematic analysis of race conditions |
| Fault Handling | 3.0 | Reasonable framework, but insufficient detail |
| Security Model | 3.5 | Three-tier profile design is good, but coordinator trust is a major issue |
| Implementability | 2.5 | Missing formal state machines, sequence diagrams, key details |
| Innovation | 3.0 | Conceptual innovation is valuable, no new contributions at the mechanism level |

**Overall Judgment**: This is a promising protocol design that addresses a genuine gap. However, as a specification intended for cross-implementation interoperability, the current version has fatal ambiguities in fundamental issues such as OP_COMMIT semantics, consistency model, and atomicity guarantees. A major revision is recommended, focusing on resolving the above Top 5 deficiencies before entering a stable state.

---

*This review is based on the MPAC Specification v0.1.6 document, conducting an independent technical assessment simulating SOSP/OSDI/NSDI-level review standards.*
