# MPAC v0.1.3 Update Record

**Date**: 2026-04-01
**Update Name**: Interoperability Hardening
**Previous Version**: v0.1.2 (Semantic Interoperability)
**Trigger**: Independent protocol review identifying cross-implementation interoperability gaps

---

## Overview

This update addresses the three most critical barriers to MPAC interoperability identified in the independent review (MPAC_Independent_Review_2026-04-01.md), plus additional improvements from cross-review analysis. The changes fall into three categories: **data format precision** (payload schemas), **core semantic standardization** (scope overlap, watermark baseline), and **architectural clarification** (session coordinator, normative language tightening).

No changes were made to the core protocol model (session → intent → operation → conflict → governance). All changes are additive constraints or clarifications on the existing architecture.

---

## Change Log

### 1. Payload Schema Tables [NEW Section 13.1]

**Problem**: All 16 message types had no formal field definitions. Required/optional status, types, and enum values could only be inferred from examples in Section 28. Two independent implementations would inevitably disagree on field-level requirements.

**Change**: Added comprehensive payload schema tables for every message type, the Scope object, and the Watermark object. Each field specifies type, requirement level (R/O/C), and description. Enum values are listed inline.

**Impact**: This is the single highest-impact change for interoperability. Implementors can now build parsers and validators directly from the spec.

---

### 2. Scope Overlap Standardization [NEW Section 15.2.1]

**Problem**: Conflict detection — MPAC's core value proposition — depends on scope overlap judgment, but the spec provided no standard algorithm. Two compliant implementations could produce contradictory conflict reports for identical scenarios.

**Change**:
- Section 15.2.1.1: MUST-level overlap rules for `file_set` (normalized path string matching + set intersection), `entity_set` (exact string matching + set intersection), and `task_set` (exact string matching + set intersection)
- Section 15.2.1.2: SHOULD-level guidance for `resource_path` (minimum glob support) and conservative defaults for `query`/`custom`
- Section 15.2.1.3: Cross-kind overlap MUST use canonical URIs or resource registry; MUST NOT assume non-overlap from kind mismatch alone

**Impact**: The most common scope kinds now have deterministic, interoperable overlap judgment.

---

### 3. Watermark Baseline Kind [REVISED Section 12.2–12.4]

**Problem**: Four watermark kinds with no comparison semantics meant cross-implementation causal tracing was impossible. Watermarks were effectively opaque audit fields.

**Change**:
- `lamport_clock` designated as MUST-support baseline
- Comparison semantics defined (monotonic integer, greater-than = happens-after)
- New `lamport_value` field for non-lamport watermarks to enable fallback comparison
- Interoperability rule: uninterpretable watermark kind → MUST fall back to `lamport_value`

**Why lamport_clock over vector_clock**: Lamport clocks are simpler to implement, have no participant-set maintenance overhead, and are sufficient for the ordering guarantees MPAC actually needs. Vector clocks remain available as an optional enhancement.

---

### 4. Session Coordinator [NEW Section 8.1]

**Problem**: Multiple MPAC features (heartbeat-based liveness, sender identity binding, frozen scope enforcement, tamper-evident logging) implicitly require a centralized component, but the spec claimed transport independence and P2P compatibility without acknowledging this dependency.

**Change**: Defined "session coordinator" as a first-class logical role with explicit responsibilities. Every session MUST have exactly one logical coordinator. Acknowledged that P2P deployments need an equivalent distributed consensus mechanism.

**Impact**: Eliminates the disconnect between the spec's decentralized rhetoric and its centralized mechanisms. Implementors now know what component they must build.

---

### 5. Intent-Before-Action: SHOULD → MUST (Governance Profile) [REVISED Section 7.1]

**Problem**: The core differentiating feature of MPAC (intent declaration before execution) was a SHOULD, meaning compliant implementations could skip it entirely, reducing MPAC to an uncoordinated operation log.

**Change**: MUST in Governance Profile sessions. SHOULD in Core Profile. Operations without active intent flagged as `uncoordinated`.

---

### 6. Causal Context: SHOULD → MUST [REVISED Section 7.3]

**Problem**: Causal traceability is a stated design goal, but causal context on the three most important message types was only SHOULD.

**Change**: OP_COMMIT, CONFLICT_REPORT, and RESOLUTION MUST include watermark. Other types SHOULD.

---

### 7. OP_COMMIT State References: MUST [REVISED Section 16.3]

**Problem**: `state_ref_before` and `state_ref_after` were implicitly optional (reference implementation allowed None). Without these, receivers cannot verify causal consistency of committed operations.

**Change**: Both fields MUST be present in OP_COMMIT. Defined `causally_unverifiable` local processing hint for receivers who cannot match `state_ref_before` against their local state.

**Design note**: This also addresses the "signaling-state gap" identified in cross-review analysis — the spec now explicitly handles the case where signaling (OP_COMMIT) arrives before data synchronization.

---

### 8. Concurrent INTENT_CLAIM Resolution [REVISED Section 14.4.4]

**Problem**: Two participants simultaneously claiming the same suspended intent had no defined resolution.

**Change**: First-claim-wins, determined by session coordinator receipt order. Subsequent claims rejected with PROTOCOL_ERROR (CLAIM_CONFLICT).

---

### 9. Resolution Rollback Semantics [REVISED Section 18.4]

**Problem**: Rejecting an already-committed operation via RESOLUTION left shared state in a contradictory condition — the operation's state transitions to REJECTED but its effects remain in shared state.

**Change**: Resolver SHOULD provide compensating OP_COMMIT or explicit `"rollback": "not_required"`. MPAC does not own rollback (application layer responsibility) but requires the resolution to make its rollback expectation explicit.

**Also**: Removed `winner`/`loser` shorthand fields. Protocol specs should not provide syntactic sugar that creates two non-equivalent representations of the same semantic.

---

### 10. Frozen Scope Hardening [REVISED Section 18.6.2, NEW Section 18.6.2.1]

**Problem**: (a) Frozen scope accepted new INTENT_ANNOUNCE, which could trigger cascading conflicts without any ability to act on them. (b) No fallback if arbiter is permanently unavailable — scope frozen indefinitely.

**Change**:
- INTENT_ANNOUNCE fully contained in frozen scope now MUST be rejected
- New `frozen_scope_timeout_sec` (default 1800s): auto-reject conflicting operations and release scope after timeout
- Disableable via `frozen_scope_timeout_sec: 0`

---

### 11. Security Hardening [REVISED Section 23.1.2, 23.4]

**Problem**: (a) Replay protection was SHOULD in Authenticated Profile — dangerous for cross-trust-domain coordination. (b) Role assertions in HELLO were not validated — any participant could claim `arbiter` role. (c) No mention of end-to-end encryption for untrusted coordinator deployments.

**Change**:
- Replay protection → MUST
- Role assertion validation by session coordinator → MUST
- End-to-end encryption noted in Section 23.4 general considerations

---

### 12. Normative Language Tightening (Various Sections)

| Section | Change | Rationale |
|---------|--------|-----------|
| 11.4 | `ts` SHOULD → MUST RFC 3339 | Timestamp format inconsistency breaks sorting and audit |
| 12.5 (old 12.4) | `based_on_watermark` SHOULD → MUST in CONFLICT_REPORT | Core auditability requirement |
| 14.1 | HELLO SHOULD → MUST as first message | Already implied by Section 8.2 ordering constraints |
| 18.7 | RESOLUTION watermark SHOULD → MUST | Cannot audit resolution without causal context |

---

## Items Not Changed (With Rationale)

| Suggestion | Decision | Rationale |
|------------|----------|-----------|
| INTENT_CLAIM is unnecessary (replace with new INTENT_ANNOUNCE) | Kept | INTENT_CLAIM preserves causal chain for audit (which intent was taken over from whom and why) |
| Section 23.1 security profile declaration MUST → SHOULD | Kept as MUST | Explicit security posture is a baseline interoperability requirement |
| Section 14.4.2 SUSPENDED MUST → SHOULD | Kept as MUST | SUSPENDED state is needed for INTENT_CLAIM to work; relaxing it would break the recovery flow |
| Semantic Profile (Section 20.3) should be removed as premature | Kept | Low implementation burden as an optional profile; provides forward-compatible extension point |

---

## Cross-References

- Independent review: `version_history/v0.1.3_interop_hardening/MPAC_Independent_Review_2026-04-01.md`
- Archived pre-update spec: `version_history/v0.1.3_interop_hardening/SPEC_v0.1.2_2026-04-01.md`
