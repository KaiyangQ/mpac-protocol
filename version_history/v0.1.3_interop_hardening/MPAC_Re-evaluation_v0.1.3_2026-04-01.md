# MPAC v0.1.3 Re-evaluation Report

**Review Date**: 2026-04-01
**Review Subject**: SPEC.md (MPAC v0.1.3 — Interoperability Hardening)
**Background**: A full review of v0.1.2 was previously conducted with improvement recommendations. The protocol author revised accordingly to produce v0.1.3. This report re-evaluates the revised spec from the standpoint of an independent reviewer, without presupposing prior conclusions.

---

## 1. Protocol Design: Core Abstraction Assessment

### Verdict: Significant improvement; inter-layer relationships are much clearer than before

The five-layer model (Session → Intent → Operation → Conflict → Governance) remains unchanged, which is the right call — the core architecture did not need changing. The key advancement in v0.1.3 is:

**Session Coordinator (Section 8.1)** resolves the largest architectural gap from before. Previously, the spec implied a centralized component without acknowledging it; now it explicitly defines the coordinator's responsibility boundaries (state maintenance, ordering enforcement, liveness detection, identity binding, audit logging) while maintaining the transport independence stance. The constraint "each session MUST have exactly one logical coordinator" anchors the executor for many downstream behaviors.

**Remaining issues:**

- **Session negotiation is still missing.** Section 9.2 defines three creation methods, but there is still no standard way for two implementations joining the same session to verify capability compatibility. HELLO carries a capabilities list (Section 14.1), but the behavior upon receiving incompatible capabilities remains undefined. For example: A only supports lamport_clock, B only supports vector_clock — although 12.3 defines lamport_value fallback, there is no negotiation failure path at the session level. **Recommendation**: Add a coordinator compatibility check responsibility to the HELLO semantics in Section 14.1 — the coordinator SHOULD at minimum verify compatibility of critical capabilities (such as causality kind) and return PROTOCOL_ERROR when incompatible.

- **The interaction contracts between the five layers are still implicit.** Section 6 says "externally visible semantics SHOULD remain distinct," but "externally visible" is still not defined. In practice, in v0.1.3 the layers are indirectly linked through the ordering constraints in Section 8.2 and the shared principles in Sections 7.1–7.3, but this has not been unified into an "inter-layer interface" description. This is not a blocking issue, but for teams that want to implement strict layering, the spec should provide clearer guidance.

- **Removing the winner/loser shorthand was the correct decision.** A protocol spec should not provide syntactic sugar.

---

## 2. Implementability

### Verdict: Elevated from "not interoperable" to "conditionally interoperable"

The three major interoperability obstacles in v0.1.2 have all been addressed in v0.1.3:

**Payload Schema (Section 13.1)**: This is the single most impactful change. All 16 message types now have field-level schema tables, including required/optional annotations, types, enum values, and conditional dependencies (the C annotation on Scope objects). Two independent teams can now write field-level compatible parsers/validators based on these tables.

**Scope Overlap Standardization (Section 15.2.1)**: file_set, entity_set, and task_set now have MUST-level determination rules (canonicalized paths + set intersection). resource_path has SHOULD-level minimal glob support. Cross-kind overlap has a clear determination chain (canonical_uris → resource registry → conservative default). This means that for the most common scope kinds, two compliant implementations will produce consistent overlap determinations.

**Watermark Baseline (Section 12.3)**: lamport_clock as a MUST-supported baseline, with defined comparison semantics and an added lamport_value fallback field. Cross-implementation causal comparison has gone from "impossible" to "at least one operable fallback path."

**Areas that may still produce incompatibilities:**

- **state_ref format is still implementation-defined.** Section 16.3 says state_ref_before/after MUST exist and "format is implementation-defined but MUST be consistent within a session." This means Team A uses SHA-256, Team B uses git commit hash, and if they want to join the same session, they need to negotiate the state_ref format in advance. But the spec does not define this negotiation mechanism. **Recommendation**: Add a `state_ref_format` declaration field to session metadata (e.g., `"sha256"`, `"git_hash"`, `"monotonic_version"`), and have the coordinator verify during HELLO that each participant's state_ref format matches the session declaration.

- **The value space of `op_kind` is unconstrained.** The OP_COMMIT schema in Section 13.1 says op_kind is a string and gives examples (replace, insert, delete, patch), but there is no MUST-level enumeration. If Team A uses `"replace"` and Team B uses `"overwrite"` for the same semantics, the conflict detector cannot determine whether they are equivalent. **Recommendation**: Define a minimal MUST-supported op_kind enumeration (`replace`, `insert`, `delete`), allowing extensions.

- **The file_set path canonicalization rules in Scope objects (Section 15.2.1.1) have an omission.** They define removal of `./`, collapsing of `//`, and stripping of trailing `/`, but do not mention handling of `..`. If A uses `src/../config.yaml` and B uses `config.yaml`, under the current rules they do not match. **Recommendation**: Add canonicalization of `..` segments (resolving parent directory references), or explicitly state that paths containing `..` MUST be fully resolved by the sender before transmission.

---

## 3. Edge Cases

### Verdict: Major deadlock and race condition paths have been closed, but residual issues remain

**Resolved edge cases:**

- Concurrent INTENT_CLAIM race (Section 14.4.4) — first-claim-wins + CLAIM_CONFLICT error
- Frozen scope deadlock (Section 18.6.2.1) — frozen_scope_timeout_sec fallback
- Intent accumulation under frozen scope (Section 18.6.2) — fully contained intents are rejected
- Resolution rollback ambiguity (Section 18.4) — rollback field clarifies expectations
- Signaling-state discontinuity (Section 16.3) — causally_unverifiable fallback

**Remaining edge cases:**

- **The ambiguity between TTL and wall clock vs. logical clock remains unresolved.** The INTENT_ANNOUNCE schema in Section 13.1 explicitly states that `ttl_sec` is "Time-to-live in wall-clock seconds," which is good. However, the spec never defines how the coordinator checks for TTL expiration. If the coordinator checks `ts + ttl_sec < now()` when processing each message, clock skew will cause inconsistencies. If lamport clock is used, it conflicts with the "wall-clock seconds" semantics. **Recommendation**: Explicitly state that TTL checks are performed by the session coordinator based on the coordinator's local wall clock, and that the participant's `ts` field is used only for auditing, not for TTL calculations.

- **Conflict re-detection after INTENT_UPDATE expands scope is undefined.** If A's intent originally scoped to `["train.py"]` is updated to `["train.py", "config.yaml"]`, and B's intent covers `["config.yaml"]` — the spec does not say whether INTENT_UPDATE SHOULD trigger conflict re-detection. The reference implementation does re-check (engine.py line 228-229), but the spec only implies conflict detection in the INTENT_ANNOUNCE semantics. **Recommendation**: Explicitly state that INTENT_UPDATE expanding scope SHOULD trigger conflict detection equivalent to INTENT_ANNOUNCE.

- **Failure recovery for the session coordinator itself.** Section 8.1 states the coordinator is a single point, but what happens when the coordinator crashes? All heartbeat detection, frozen scope enforcement, and identity binding depend on it. The spec only says "distributed deployments MUST provide equivalent mechanisms," but offers no recommendations for failure recovery in single-coordinator deployments. **Recommendation**: Add a SHOULD-level recommendation in Section 8.1 — the coordinator should support state persistence so that session state can be reconstructed from the audit log after a restart.

---

## 4. Normative Language

### Verdict: MUST/SHOULD usage in v0.1.3 is much more precise than in v0.1.2

Key improvements:
- Section 7.1 intent-before-action: MUST under Governance Profile, SHOULD under Core Profile — reasonable layering
- Section 7.3 causal context: MUST for three critical message types, SHOULD for others — precise
- Section 12.3 lamport_clock MUST support — resolves the interoperability baseline
- Section 14.1 HELLO MUST — now consistent with Section 8.2 ordering constraints
- Section 16.3 state_ref MUST — closes the largest payload ambiguity
- Section 23.1.2 replay protection MUST — a security-critical path cannot be SHOULD

**Items still worth adjusting:**

| Section | Current | Recommendation | Rationale |
|---------|---------|----------------|-----------|
| 11.4 | `watermark` SHOULD describe causal state | Should cross-reference Section 7.3's MUST for OP_COMMIT/CONFLICT_REPORT/RESOLUTION | A subtle contradiction exists between 11.4 and 7.3: 11.4 says watermark is overall optional (Section 11.3), but 7.3 says three message types MUST include watermark. A clarifying note should be added to 11.4 to resolve the ambiguity |
| 15.3 | "participants SHOULD announce intent before non-trivial work" | Remove or replace with a cross-reference to 7.1 | This sentence is a legacy from v0.1, duplicates the new wording in 7.1 but is weaker, and may confuse readers |
| 23.3.3 | governance authority verification uses SHOULD | MUST under Authenticated Profile | Without mandatory role permission checks, the value of role assertion validation (23.1.2) is halved |

---

## 5. Positioning Relative to MCP/A2A

### Verdict: Differentiated positioning is clearly established; integration challenges remain the biggest adoption barrier

Section 2.1's three-protocol positioning (MCP = agent-to-tool, A2A = single-principal agent-to-agent, MPAC = multi-principal coordination) is clear and accurate. v0.1.3 does not overstep by defining things outside its scope (Non-Goals Section 4 is well maintained), nor does it miss core semantics it should cover.

**However, integration guidance with MCP/A2A is still lacking.** Section 29's future work mentions "integration architecture guidance," but for a team looking to adopt MPAC, this is the very first question they will ask:

- My agent called a tool via MCP that modified a file — how does this tool call become an MPAC OP_COMMIT? What do I use for state_ref_before? MCP does not provide a state hash.
- My A2A orchestrator delegated a subtask to a sub-agent — how does the sub-agent's result map back to MPAC's intent/operation?

These do not require normative definitions, but an informative appendix or integration pattern document would significantly lower the adoption barrier. **Recommendation**: Mark this item as high priority in Section 29's future work, or provide a non-normative integration guide outside the spec.

**Semantic Profile (Section 20.3) is still premature.** Its existence as an optional profile does no harm, but its definition is too thin — only three lines with no MUST-level requirements. This contrasts sharply with the thorough definitions of Core Profile and Governance Profile. **Recommendation**: Either flesh out the Semantic Profile requirements (e.g., MUST support parsing of `basis.kind = semantic_match`, MUST escalate when confidence is below threshold), or candidly label it as "placeholder for future definition."

---

## 6. Security Model

### Verdict: Elevated from "self-consistent on paper" to "implementable"

Key improvements:
- Replay protection upgraded from SHOULD to MUST (Section 23.1.2) — critical security fix
- Role assertion validation (Section 23.1.2) — closes the role injection vulnerability during Open → Authenticated upgrade
- Sender identity binding executor explicitly assigned to the session coordinator (Section 8.1 + 23.1)
- End-to-end encryption included as a consideration (Section 23.4)

**Remaining security concerns:**

- **Role abuse under Open Profile still has no protection.** This is by design (Open Profile is intended for trusted environments), but the spec says "If no security profile is declared, implementations SHOULD default to the Open profile" (Section 23.2). This means a deployment that forgets to declare a profile automatically falls into a state with no role validation. **Recommendation**: Add a MUST-level warning in Section 23.2 — if a session includes principals from different organizational domains (inferred via principal_id prefix or authentication token issuer), the coordinator MUST refuse to use the Open Profile.

- **Authentication of the session coordinator itself is undefined.** The Authenticated Profile requires participant identity verification, but who verifies the coordinator's identity? If the coordinator is replaced by a man-in-the-middle, all identity binding and audit logging become ineffective. **Recommendation**: Add a SHOULD under the Authenticated Profile — participants SHOULD verify the coordinator's identity via the same authentication mechanism (e.g., mTLS is mutual, OAuth token issuer is verified).

- **Watermark forgery is still possible under the Authenticated Profile.** Section 23.3.4 says watermark integrity checks are only under the Verified Profile. But under the Authenticated Profile, an authenticated-but-malicious participant can forge watermark values (claiming to have seen more messages), thereby influencing conflict determination. **Recommendation**: Add a SHOULD under the Authenticated Profile — the coordinator SHOULD cross-check participant watermark claims against its own message delivery records.

---

## 7. Three Issues Most Impacting Production Readiness

v0.1.3 resolved the three blocking issues from v0.1.2 (payload schema, scope overlap, watermark baseline); these are no longer blockers. For the current version, the three issues most impacting production readiness are:

### #1: Lack of MCP/A2A Integration Guidance (Adoption Barrier)

This is not a technical deficiency in the spec but an ecosystem positioning issue. MPAC's target users are inevitably already using MCP and/or A2A. If they do not know how to map MCP tool calls to MPAC operations, or how to embed MPAC intents within A2A task delegation, they will not adopt MPAC — not because MPAC is inadequate, but because the integration cost is unpredictable. A non-normative integration pattern appendix can address this issue.

### #2: Missing Session Negotiation (Interoperability Risk)

The current spec assumes all participants know the session's policy, security profile, watermark strategy, and state_ref format in advance. This may hold for out-of-band provisioned sessions (Section 9.2.3), but for implicit creation (Section 9.2.2) — where the first HELLO creates the session — subsequent participants have no opportunity to check whether the session configuration is compatible with their own. This will produce "joined and then discovered incompatibility" problems in real deployments.

**Recommendation**: Define a `SESSION_INFO` response message (returned by the coordinator upon receiving HELLO), containing key session configurations such as security profile, governance policy, watermark kind, and state_ref format. Participants SHOULD verify compatibility after receiving SESSION_INFO, and SHOULD send GOODBYE to exit when incompatible.

### #3: Missing Conformance Test Suite (Trust Issue)

The spec is now sufficiently precise — payload schema, scope overlap rules, and watermark comparison semantics all have MUST-level definitions. But "a precise spec" does not equal "verifiable compliance." Without a conformance test suite, there is no objective way to verify a claim of "MPAC v0.1.3 compliant." For a multi-party protocol, this is more critical than for a single-party protocol — because you need to trust that the other party's implementation is also compliant.

**Recommendation**: Elevate the conformance test suite from future work to a P0 goal for v0.2. At minimum, cover: message parsing (required field validation for all 16 types), scope overlap determination (file_set path normalization + set intersection), and watermark comparison (lamport_clock baseline + lamport_value fallback).

---

## Overall Assessment

MPAC v0.1.3 represents a substantive improvement over v0.1.2. All three previously blocking issues (payload schema, scope overlap, watermark baseline) have been resolved. The introduction of the Session Coordinator eliminates the largest architectural ambiguity. The precision of normative language has improved significantly.

The current version has reached the level of "one engineering team can begin implementation, and two teams can most likely achieve basic flow interoperability." The remaining issues (session negotiation, MCP/A2A integration, conformance test) fall into the category of "should be resolved in v0.2" rather than "v0.1 cannot be published."

**Maturity Rating**: Elevated from v0.1.2's "design philosophy document" to **"implementable protocol draft."** Production-interoperable protocol status requires session negotiation and a conformance test suite.

---

## Appendix: v0.1.2 → v0.1.3 Change Effectiveness Scores

| Change | Effectiveness | Notes |
|--------|---------------|-------|
| Payload schema tables (Section 13.1) | ★★★★★ | Foundation for interoperability; highest priority change |
| Scope overlap rules (Section 15.2.1) | ★★★★★ | Core semantics standardization |
| Watermark baseline (Section 12.3) | ★★★★☆ | Resolves cross-implementation causal comparison, but lamport_value being an optional field means it may still be absent |
| Session coordinator (Section 8.1) | ★★★★☆ | Architectural clarification, but coordinator's own failure recovery is not covered |
| Intent-before-action MUST (Section 7.1) | ★★★★☆ | Reasonable layering; MUST under Governance Profile |
| state_ref MUST (Section 16.3) | ★★★★☆ | Critical fix, but format negotiation is missing |
| Concurrent INTENT_CLAIM (Section 14.4.4) | ★★★★☆ | Clean and decisive race condition resolution |
| Frozen scope fallback (Section 18.6.2.1) | ★★★★☆ | Resolves deadlock, with option to disable |
| Frozen scope rejects INTENT_ANNOUNCE (Section 18.6.2) | ★★★☆☆ | Correct direction, but handling of partially overlapping scopes is somewhat complex |
| Resolution rollback semantics (Section 18.4) | ★★★☆☆ | Clarifies expectations, but SHOULD rather than MUST leaves actual enforcement rate questionable |
| Role assertion validation (Section 23.1.2) | ★★★★☆ | Critical security fix |
| Replay protection MUST (Section 23.1.2) | ★★★★★ | Hard security requirement; no exceptions should apply |
