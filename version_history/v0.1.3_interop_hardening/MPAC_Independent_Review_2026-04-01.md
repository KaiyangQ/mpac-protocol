# MPAC v0.1 Independent Review Report

**Review Date**: 2026-04-01
**Review Subject**: SPEC.md (MPAC v0.1, including addenda from v0.1.1 and v0.1.2)
**Reviewer Stance**: Independent review from the protocol design domain, assuming I need to guide an engineering team to implement an interoperable runtime based on this spec

---

## 1. Protocol Design: Core Abstraction Assessment

### 1.1 The Five-Layer Abstraction Is Fundamentally Sound, but Inter-Layer Coupling Is Insufficiently Defined

The five-layer division of Session → Intent → Operation → Conflict → Governance (Section 6) is directionally correct. In multi-principal coordination scenarios, intent as a pre-execution declaration is a core differentiating design, and separating conflict and governance into their own layers is also the right choice.

**However, the problem is that the inter-layer interaction contracts are essentially empty.** Section 6 states "Implementations MAY merge these layers internally, but their externally visible semantics SHOULD remain distinct" — this statement is inherently contradictory. If you allow internal merging but require externally distinct semantics, you must define what constitutes "externally visible semantics." Currently, no such definition exists.

### 1.2 Intent Is the Most Valuable yet Most Fragile Abstraction

Intent-before-action (Section 7.1) is MPAC's strongest design differentiator compared to MCP/A2A. However, the spec defines it as SHOULD rather than MUST ("Participants SHOULD announce intent before committing non-trivial operations"), which means a fully compliant implementation could never send an intent and jump straight to OP_COMMIT. At that point, MPAC degrades into an operation log protocol without conflict pre-checking, and its core value drops to zero.

**Recommendation**: Section 7.1 should elevate intent-before-action to MUST (at least under the Governance Profile), or the Core Profile should explicitly state the consequences of skipping intent (e.g., the operation is automatically marked as uncoordinated with reduced priority).

### 1.3 Missing Abstraction: Session Negotiation

Currently, Session creation (Section 9.2) supports three modes (explicit, implicit, out-of-band), but there is no capability negotiation phase. When two implementations join the same session, there is no standard method to confirm: Are the watermark kinds supported by both sides compatible? Are the conflict detection strategies aligned? Do the security profiles match?

The HELLO message (Section 14.1) carries a capabilities list, but the spec does not define what to do when incompatible capabilities are received. There is no failure path for negotiation.

### 1.4 Redundant Concept: winner/loser Shorthand

Section 18.4 introduces `winner`/`loser` as shorthands for `outcome`. This introduces two non-equivalent ways of expressing the same semantics at the spec level, directly increasing the interoperability burden. A protocol spec should not provide syntactic sugar. **Recommend removal.**

---

## 2. Implementability: Can Two Teams Write Compatible Implementations?

### 2.1 The Biggest Interoperability Risk: No Standard Algorithm for Scope Overlap Determination

Section 15.2 defines 6 scope kinds (file_set, resource_path, task_set, query, entity_set, custom), but overlap determination is entirely left to implementations. The canonical_uris in Section 15.2.1 is MAY, and the resource registry in Section 15.2.2 is also MAY.

**This means**: Team A uses file_set exact matching and determines no conflict; Team B uses resource_path glob expansion and determines a conflict exists. Two fully compliant implementations produce contradictory conflict reports for the same scenario. This is not an edge case — this is a divergence on the most common operation path.

Referring to the actual code (`conflict_detector.py`), the reference implementation uses pure string set intersection (`targets & existing.scope.targets()`), and resource_path globs are never expanded — this is already a spec-vs-implementation divergence.

**Recommendation**: At minimum, for file_set — the most common scope kind — define MUST-level overlap determination rules (exact string matching after path normalization). For resource_path, define a minimum glob subset that MUST be supported.

### 2.2 Watermark Interoperability Is Illusory

Section 12.2 lists four watermark kinds (vector_clock, lamport_clock, causal_frontier, opaque), and Section 12.3 states "if an unrecognized kind is received, MAY continue processing but SHOULD treat causality judgments as partial."

**Problem**: If two implementations use vector_clock and lamport_clock respectively, they have absolutely no way to compare causal relationships. The spec does not define comparison semantics for watermarks, nor does it define how one implementation can verify the causal completeness claimed by another implementation's watermark. This means watermarks in cross-implementation scenarios are merely an opaque audit field, not an actionable causal mechanism.

**Recommendation**: Either MUST specify comparison semantics for at least one watermark kind (lamport_clock recommended, as it is the simplest), or honestly acknowledge that cross-implementation causal comparison is not feasible in v0.1 and downgrade watermarks to a purely audit-oriented purpose.

### 2.3 No JSON Schema — Payload Structure Is Entirely Inferred from Examples

Section 29 lists JSON Schema definitions as future work, but this means all payload structures can only be reverse-engineered from the examples in Section 28. For instance:

- Is the `assumptions` field of `INTENT_ANNOUNCE` MUST or MAY? (The spec says SHOULD include, but what if it is omitted?)
- Can `state_ref_before` of `OP_COMMIT` be null? (The reference implementation allows None.)
- Can `related_intents` and `related_ops` of `CONFLICT_REPORT` both be empty?

Without a schema, the required/optional status and type constraints of every field are purely guesswork. **This is the most fundamental obstacle to interoperability.**

**Recommendation**: v0.1 must include a payload schema for each message type, at minimum defining required fields, field types, and enum value sets. A full JSON Schema file is not necessary — table format embedded in the spec is sufficient.

---

## 3. Edge Cases

### 3.1 Concurrent INTENT_CLAIM Race Condition

Section 14.4.4 defines INTENT_CLAIM but does not address the situation where two participants simultaneously claim the same suspended intent. Who wins? First-come-first-served? Does it require governance approval? If two claims arrive at the session coordinator simultaneously, the coordinator's behavior is undefined.

**Recommendation**: MUST define arbitration rules for competing claims. The simplest approach is first-claim-wins, with subsequent claims receiving a PROTOCOL_ERROR.

### 3.2 TTL Expiration vs. OP_COMMIT Race Condition

Intents have TTL (Section 15.3), but if an agent submits an OP_COMMIT referencing that intent at the exact moment the TTL expires, is the operation valid? The reference implementation (`engine.py` lines 453-459) checks TTL on every `_process` call using the lamport clock rather than wall-clock time — meaning the TTL semantics are completely inconsistent with the `ttl_sec` (seconds) described in the spec.

**This is not an implementation bug — it is a spec ambiguity**: Is TTL based on wall-clock time or logical time? In distributed environments, these two differ enormously.

**Recommendation**: Clarify that TTL is wall-clock based (UTC timestamp), since the `ttl_sec` naming already implies this. Mark the logical clock usage as a simplification in the reference implementation.

### 3.3 Livelock Risk with Frozen Scope

Section 18.6.2 states that OP_PROPOSE and OP_COMMIT are rejected under frozen scope, but INTENT_ANNOUNCE is still accepted. This means during a scope freeze, new intents can continuously declare plans covering the frozen area, but no operations can make progress, and each new intent may trigger a new CONFLICT_REPORT, further complicating governance decisions.

**Recommendation**: Frozen scope should also reject or defer new INTENT_ANNOUNCE (not merely warn), or at least SHOULD NOT allow new intents whose scope is entirely contained within the frozen scope.

### 3.4 Post-Resolution State Recovery Is Undefined

Section 18.4 defines that RESOLUTION can accept/reject intents and operations, but does not define: what happens if a rejected operation has already been COMMITTED (i.e., has already modified shared state)? The spec only defines lifecycle state transitions for operations, but does not define rollback semantics for shared state.

The reference implementation (`governor.py` lines 88-104) directly modifies intent/operation states upon resolution but never rolls back values already written to the `shared_state` dict. This means rejecting an already-committed operation is a state contradiction.

**Recommendation**: Explicitly state that MPAC is not responsible for shared state rollback (this is delegated to the application layer), but MUST require that if an operation in the RESOLUTION's `rejected` list has COMMITTED status, the resolver must simultaneously provide a compensating operation (compensating OP_COMMIT) or declare no-rollback-needed.

---

## 4. Normative Language

### 4.1 The Following SHOULDs Should Be Elevated to MUST

| Section | Current Wording | Recommendation | Rationale |
|---------|----------------|----------------|-----------|
| 7.1 | "Participants SHOULD announce intent" | MUST (under Governance Profile) | Otherwise the core value is nullified |
| 7.3 | "Committed operations and conflict reports SHOULD include causal context" | MUST | Causal traceability is a core design goal; SHOULD will lead to a large volume of messages without causal context |
| 11.4 | "`ts` SHOULD use RFC 3339" | MUST | Inconsistent timestamp formats will cause sorting and audit failures |
| 14.1 | "a participant SHOULD send HELLO when entering" | MUST | Section 8.1 already requires session-first; HELLO is semantically already a MUST |
| 18.7 | "RESOLUTION SHOULD include watermark" | MUST (already MUST under Verified Profile, but should also be MUST under Authenticated Profile) | A resolution without causal context cannot be audited |

### 4.2 The Following MUSTs May Be Overly Strict

| Section | Current Wording | Recommendation | Rationale |
|---------|----------------|----------------|-----------|
| 14.4.2 | "active intents MUST be transitioned to SUSPENDED" | SHOULD | Implementations may choose to directly WITHDRAW rather than SUSPEND, depending on business scenarios |
| 23.1 | "Sessions MUST declare which security profile they operate under" | SHOULD, defaulting to Open when undeclared | Overly strict for simple development environments |

---

## 5. Positioning Relative to MCP and A2A

### 5.1 The Differentiated Positioning Is Fundamentally Sound

The positioning analysis of MCP (agent-to-tool) and A2A (single-principal agent-to-agent) in Section 2.1 is accurate. MPAC anchors itself in the multi-principal coordination layer, which is indeed an uncovered space.

### 5.2 But the Spec Does Not Define Integration Points with MCP/A2A

If MPAC is to be deployed in real systems, agents will almost inevitably use MCP (tool invocation), A2A (subtask delegation), and MPAC (cross-principal coordination) simultaneously. The spec does not define:

- How does an MPAC operation wrap a tool call executed via MCP?
- How does an A2A task delegation map to an MPAC intent?
- How are sessions/contexts across the three protocols correlated?

**This is not a scope creep issue — this is the first question adopters will ask.** Recommend at minimum providing a sketch of the integration architecture in Section 29's future work, or explicitly stating in Non-Goals (Section 4) that MPAC is not responsible for defining these integration points.

### 5.3 Over-Engineered Parts

The Semantic Profile (Section 20.3) and semantic_match basis (Section 17.7.1) may be premature for v0.1. Standardizing the output format of LLM reasoning results has limited value without an interop test suite — each implementation's LLM will produce entirely different confidence scores and explanations, and "format uniformity" does not deliver "semantic interoperability."

### 5.4 Under-Specified Parts

There is no consideration for **batch operations**. In real-world scenarios, agents frequently modify multiple files at once (a single git commit may change 20 files), but OP_COMMIT's `target` is singular. The spec does not define atomic multi-target operations, nor does it explain how to express atomicity using multiple OP_COMMITs.

---

## 6. Security Model

### 6.1 The Three-Tier Security Profile Design Approach Is Sound

The progressive security model of Open → Authenticated → Verified (Section 23.1) is pragmatic and avoids the "one-size-fits-all" trap.

### 6.2 The Authenticated Profile Lacks an Enforcement Mechanism for Sender Binding

Section 23.1.2 states "implementations MUST bind each sender field to the authenticated identity," but does not define where this binding is enforced. If enforced by the session coordinator, the centralized coordinator becomes a security bottleneck. If enforced peer-to-peer, every peer needs to hold credentials for all participants.

**Recommendation**: Explicitly state that sender binding is enforced by the session coordinator (or equivalent gateway layer) at the message ingress point, or define a token-binding mechanism that allows any participant to verify.

### 6.3 No Mechanism to Prevent Governance Privilege Escalation

The spec defines roles (Section 10.3) and permission mappings (Section 18.2), but does not define the role change process. How can a contributor be promoted to owner within a session, if at all? If possible, who authorizes it? If not, the spec should state this.

Under the current spec, if the session coordinator is compromised, an attacker can declare any role (including arbiter) in the HELLO message. Under the Open Profile, there is no prevention mechanism whatsoever; under the Authenticated Profile, only identity is verified, not the legitimacy of role claims.

**Recommendation**: Section 23 should add role assertion verification requirements — at minimum under the Authenticated Profile, role declarations MUST be validated by the session policy or coordinator before taking effect.

### 6.4 Missing: Message Confidentiality

None of the three security profiles mention encryption of message contents. In cross-organizational scenarios (the target scenario for the Verified Profile), transport-level TLS may be insufficient — an intermediary session coordinator can see all message plaintext. If the coordinator is operated by a third party, this is a real privacy risk.

**Recommendation**: At minimum, mention the need for end-to-end encryption in Section 23.4's general considerations.

---

## 7. Three Issues with the Greatest Impact on Adoption

If I could only point out three issues, I would choose these three:

### #1: No Payload Schema (The Largest Debt in Section 29)

No schema means no interoperability. Every implementation is guessing at field required/optional status, types, and default values. Two teams working from the same spec will inevitably produce implementations that are incompatible at the field level. This is not future work — this is a prerequisite for v0.1.

**Action Item**: Before releasing v0.1 stable, add payload schema tables for all 16 message types listed in Section 13. Each field should be annotated with required/optional, type, default, and enum values. This is much faster than writing JSON Schema files, yet sufficient for two independent teams to produce compatible implementations.

### #2: No Standardization for Scope Overlap Determination (Section 15.2)

Conflict detection is MPAC's core value proposition, and the first step in conflict detection is scope overlap determination. The current spec leaves this entirely to implementations, effectively outsourcing the protocol's most critical semantic decision. The result is that two compliant implementations produce different conflict judgments for the same scenario, and users cannot trust the consistency of conflict reports.

**Action Item**: Define MUST-level overlap determination rules for file_set and entity_set (exact string matching after normalization + set intersection). Elevate canonical_uris (Section 15.2.1) from MAY to SHOULD (in multi-scope-kind environments). Acknowledge that overlap for query and custom kinds cannot be standardized in v0.1.

### #3: Illusory Watermark Interoperability (Section 12)

The spec provides four watermark kinds but no comparison semantics, causing watermarks to be effectively inoperable in cross-implementation scenarios. This renders causal traceability — one of the spec's six core design goals — unachievable in heterogeneous deployments.

**Action Item**: Designate lamport_clock as the MUST-support baseline watermark kind. Define its comparison rules (monotonically increasing integer; greater-than implies happens-after). Allow other kinds as optional extensions, but they MUST be able to fall back to lamport_clock comparison.

---

## Appendix: Deviations Between the Reference Implementation and the Spec

The following spec-vs-code inconsistencies were found during review of the reference implementation code:

1. **IntentState Missing SUSPENDED and TRANSFERRED**: The `IntentState` enum in `models/intent.py` does not include these two states, yet Section 14.4 and 15.6 define them. The reference implementation cannot execute the unavailability recovery flow.

2. **TTL Uses Lamport Clock Instead of Wall Clock**: `engine.py` line 458 uses `lamport_clock - created_at_tick >= ttl_sec` for TTL checking, but the `ttl_sec` naming and the semantics of Section 15.3 imply wall-clock seconds.

3. **Inverted Empty Set Logic in Scope.contains**: `intent.py` line 54 returns True from `contains()` when `targets()` returns an empty set (i.e., an empty scope contains everything), which has no explicit correspondence in the spec.

4. **canonical_uris Completely Unimplemented**: `conflict_detector.py` performs overlap detection using only `targets()` set intersection, with no canonical_uris processing logic whatsoever.

5. **INTENT_CLAIM Not Implemented**: The handler map in `engine.py` does not include a handler for INTENT_CLAIM.

These deviations are understandable in themselves (the reference implementation was written during the v0.1 baseline period, and subsequent spec addenda were not synchronized back to the code), but they precisely corroborate the earlier conclusion: too many critical semantics in the spec remain at the SHOULD/MAY level, allowing the reference implementation to "compliantly" not implement them.

---

## Overall Assessment

MPAC targets a real and uncovered protocol space (multi-principal agent coordination), and the direction of the core abstractions (intent → operation → conflict → governance) is correct. The differentiated positioning relative to MCP/A2A is convincing.

However, the current version is still some distance from being an "interoperable protocol specification" on three levels: **imprecise data formats** (no schema), **overly flexible core semantics** (scope overlap, watermarks all MAY), and **security model lacking enforcement details**. Until these three issues are resolved, MPAC is closer to a "design philosophy document" than a "protocol specification."

The good news is that all these issues are fixable and do not require changes to the protocol's core architecture. It is recommended that v0.2 prioritize resolving payload schema and scope overlap standardization — these two changes can significantly improve interoperability without altering the protocol model.
