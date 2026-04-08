# MPAC v0.1.4 Update Record

**Date**: 2026-04-02
**Update Name**: State Machine Cross-Safety & Session Negotiation
**Previous Version**: v0.1.3 (Interoperability Hardening)
**Trigger**: Five-dimension audit (MPAC_v0.1.3_Audit_Report.md) identifying state machine cross-lifecycle gaps, coordinator single-point-of-failure, and session negotiation absence

---

## Overview

This update addresses the findings from the v0.1.3 audit, with priority on **state machine cross-safety** (the newly added fifth audit dimension) and **session negotiation**. The core protocol model (Session → Intent → Operation → Conflict → Governance) is unchanged. All changes are additive rules, new message types, or normative language upgrades on the existing architecture.

---

## Audit Findings → Resolution Map

### Resolved (P0)

| Audit Finding | Severity | Resolution | Spec Location |
|---------------|----------|------------|---------------|
| When intent TTL expires, associated pending OP_PROPOSE becomes orphaned — state is neither COMMITTED nor REJECTED | High | Added Intent Expiry Cascade rule: when intent enters terminal state, associated PROPOSED operations MUST be automatically rejected; when SUSPENDED, operations enter FROZEN state | Section 15.7 (new) |
| During frozen scope, all associated intents expire; conflict references defunct entities but cannot be naturally resolved | Medium | Added Conflict Auto-Dismissal: when all associated intents and operations have terminated, conflict automatically DISMISSes and immediately releases frozen scope | Section 17.9 (new) |
| Session Coordinator single point of failure with no recovery definition | High | Added Coordinator Fault Recovery: state persistence SHOULD, restart state reconstruction, behavioral specification for participants when coordinator is unavailable | Section 8.1.1 (new) |
| Session Negotiation missing — participants discover incompatibility only after joining | Medium | Added SESSION_INFO message type: coordinator's response to HELLO, carrying session configuration and compatibility check results | Section 14.2 (new), Section 13.1 payload schema |

### Resolved (P1)

| Audit Finding | Severity | Resolution | Spec Location |
|---------------|----------|------------|---------------|
| Ambiguity on whether TTL is based on wall clock or logical clock | Medium | Clarified that TTL MUST be determined by coordinator's local wall clock, calculated based on received_at + ttl_sec; sender's ts is used for auditing only | Section 15.3 semantics |
| When RESOLUTION rejects an already COMMITTED operation, the rollback field is SHOULD, which can cause state divergence between signaling layer and data layer | Medium | SHOULD → MUST; resolution missing the rollback field is rejected by coordinator | Section 18.4 |
| canonical_uris is SHOULD; in cross-organization sessions, cross-scope-kind conflict detection produces numerous false positives | Medium-High | Elevated to MUST for cross-scope-kind sessions under Authenticated/Verified profile | Section 15.2.2 |

### Not Yet Resolved (Deferred to v0.2)

| Audit Finding | Severity | Reason for Deferral |
|---------------|----------|-------------------|
| Message envelope overhead is heavy (compact envelope / binary serialization) | Medium | Need to evaluate compatibility impact on existing implementations; suitable as a transport optimization track for v0.2 |
| Missing OP_BATCH message batching mechanism | Medium | Need to define atomicity semantics (all succeed or all fail or partial success); large design space |
| Large-scale session message fan-out (scope-based subscription) | High | Architectural change; requires redesigning the coordinator's message routing model |
| Session sharding mechanism | Medium-High | Need to define cross-session intent references and cross-coordinator coordination semantics |
| op_kind minimum enumeration set | Medium | Need to collect more real-world usage scenarios before determining enumeration range |
| state_ref_format declared in session metadata | Medium | SESSION_INFO already includes state_ref_format field, but the coordinator's format validation logic during HELLO has not been standardized |
| Maximum conflict rounds per scope (preventing timeout cascade livelock) | Medium-Low | Need more real-world scenario data to determine reasonable default values |
| Conformance test suite | — | Belongs to toolchain rather than spec content; recommended to launch as a separate project |

---

## Change Log

### 1. Intent Expiry Cascade [NEW Section 15.7]

**Problem**: When an intent enters a terminal state (EXPIRED/WITHDRAWN/SUPERSEDED), pending OP_PROPOSE referencing that intent has no defined ownership — the protocol does not define disposition rules, producing orphaned proposals.

**Change**:
- Intent terminal state → associated PROPOSED operations MUST be automatically rejected (reason: `intent_terminated`)
- Intent SUSPENDED → associated PROPOSED operations enter FROZEN state (cannot proceed but not rejected)
- FROZEN operations automatically unfreeze back to PROPOSED after intent resumes ACTIVE
- Configurable `intent_expiry_grace_sec` (default 30 seconds), allowing submitters to re-associate with a new intent during the grace period
- Already COMMITTED operations are not affected by intent terminal state

**Impact**: Closes the highest-risk state machine cross-lifecycle gap identified in the audit report. Operation lifecycle gains a new FROZEN state and its transition paths.

---

### 2. Conflict Auto-Dismissal [NEW Section 17.9]

**Problem**: During a frozen scope, if all associated intents expire, the conflict has semantically lost its meaning, but the protocol has no automatic resolution mechanism — it can only wait for frozen_scope_timeout (default 30 minutes).

**Change**:
- When all of a conflict's `related_intents` have terminated, and all `related_ops` are in terminal state, the conflict SHOULD automatically DISMISS
- Auto-dismiss MUST generate a system-attributed RESOLUTION (decision: dismissed, rationale: all_related_entities_terminated)
- Auto-dismiss immediately releases the associated frozen scope, taking priority over frozen_scope_timeout
- Auto-dismiss is not triggered when only intents have terminated but operations are still in non-terminal state

**Impact**: Eliminates the inconsistency window where "conflict exists but associated entities have ceased to exist." Conflict lifecycle gains new intent-termination-triggered paths from OPEN/ESCALATED to DISMISSED.

---

### 3. Coordinator Fault Recovery [NEW Section 8.1.1]

**Problem**: All protocol runtime guarantees depend on the coordinator, but recovery when the coordinator itself crashes is completely undefined.

**Change**:
- State persistence SHOULD (participant roster, intent registry, operation states, conflict states)
- After restart, rebuild state through persisted snapshot + audit log
- Participants detect coordinator unavailability (no coordinator messages for 2x unavailability_timeout_sec) and then pause conflict-sensitive operations
- Coordinator broadcasts notification upon recovery; participants resend HELLO

**Impact**: Elevated from "completely undefined" to "clearly defined SHOULD-level recovery path."

---

### 4. SESSION_INFO Message [NEW Section 14.2, NEW payload schema]

**Problem**: After HELLO, participants have no way to know whether the session configuration is compatible with their own capabilities — they can only discover incompatibilities incrementally during subsequent interactions (e.g., watermark kind mismatch, security profile not supported).

**Change**:
- Added SESSION_INFO message type; coordinator MUST respond after receiving HELLO
- Carries: protocol_version, security_profile, compliance_profile, watermark_kind, state_ref_format, governance_policy, liveness_policy, granted_roles, compatibility_errors
- `granted_roles` may differ from the roles requested in HELLO (permission check result)
- `compatibility_errors` lists detected incompatibilities; participants can decide whether to exit based on this
- Added to the list of messages that Core Profile must support

**Impact**: Implements session negotiation, resolving the problem of "discovering incompatibility only after joining."

---

### 5. TTL Wall-Clock Semantics [REVISED Section 15.3]

**Problem**: ttl_sec is nominally wall-clock seconds, but the coordinator's checking method and clock skew handling are undefined.

**Change**: TTL MUST be determined by the coordinator's local wall clock, calculated based on the coordinator's received_at + ttl_sec; the sender's ts is used for auditing only.

---

### 6. Resolution Rollback: SHOULD → MUST [REVISED Section 18.4]

**Problem**: When RESOLUTION rejects an already COMMITTED operation, the rollback field is SHOULD, which can cause state divergence between the signaling layer (REJECTED) and the data layer (effects still persist).

**Change**: MUST include the rollback field. When missing, the coordinator MUST reject the resolution with PROTOCOL_ERROR (MALFORMED_MESSAGE).

---

### 7. Canonical URIs: SHOULD → MUST (Cross-Org) [REVISED Section 15.2.2]

**Problem**: canonical_uris is SHOULD; in cross-organization sessions, conflict detection between participants using different scope kinds produces numerous false positives.

**Change**: Cross-scope-kind sessions under Authenticated/Verified security profile MUST include canonical_uris. Open profile or homogeneous scope kind sessions remain SHOULD.

---

## Structural Changes

- Section 14.x numbering shifted: original 14.2 HEARTBEAT → 14.3, original 14.3 GOODBYE → 14.4, original 14.4 Unavailability → 14.5 (including all subsections 14.5.1–14.5.5)
- Operation lifecycle (Section 16.6) gains new FROZEN state and 4 transition paths
- Conflict lifecycle (Section 17.8) gains 2 new intent-termination-triggered DISMISSED paths
- Full-text cross-reference updates (Section 14.4.x → 14.5.x, 12 occurrences total)
- Version number updated to v0.1.4 (Section 1, Section 30)

---

## Cross-References

- Audit report: `version_history/v0.1.4_state_machine_audit/MPAC_v0.1.3_Audit_Report.md`
- Archived pre-update spec: `version_history/v0.1.4_state_machine_audit/SPEC_v0.1.3_2026-04-02.md`
