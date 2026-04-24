# MPAC v0.1.5 Update Record

**Date**: 2026-04-03
**Update Name**: Coordinator Fault Tolerance, Session Lifecycle, Security Trust Establishment
**Previous Version**: v0.1.4 (State Machine Cross-Safety & Session Negotiation)
**Trigger**: Protocol-level gap analysis (MPAC_v0.1.4_Gap_Analysis.md) identifying six design gaps after completing ~85% reference implementation coverage

---

## Overview

This update addresses the three highest-priority protocol-level gaps identified in the v0.1.4 gap analysis. The core protocol model (Session → Intent → Operation → Conflict → Governance) is unchanged. All changes are new sections, new message types, or normative language upgrades on the existing architecture.

Two new message types are introduced: `SESSION_CLOSE` and `COORDINATOR_STATUS`, bringing the total from 17 to 19.

---

## Gap Analysis → Resolution Map

### Resolved (P0)

| Gap Analysis Finding | Severity | Resolution | Spec Location |
|---------------------|----------|------------|---------------|
| Gap 1: Single Coordinator with no fault tolerance or handover mechanism | High | Defined coordinator liveness (COORDINATOR_STATUS heartbeat), state snapshot format (JSON schema), recovery procedure, planned/unplanned handover protocol, and split-brain prevention | Section 8.1.1.1–8.1.1.4 |
| Gap 2: Security model lacks operational trust establishment | High | Defined credential exchange mechanism in HELLO handshake (5 credential types), role assignment/verification process, key distribution and rotation, watermark integrity binding | Sections 23.1.4–23.1.6 |
| Gap 5: Session lifecycle has no close, no archival | Medium | Defined SESSION_CLOSE message, auto-close conditions, session summary, transcript export format, session TTL, lifecycle policy | Sections 9.6, 14.5 |

### Deferred to v0.2.0

| Gap Analysis Finding | Severity | Status | Rationale |
|---------------------|----------|--------|-----------|
| Gap 3: Scope expressiveness — semantic conflicts invisible | Medium | Deferred | Requires deeper research into dependency graph representation; listed in Recommended Future Work |
| Gap 4: No post-commit rollback or undo semantics | Medium | Deferred | Requires OP_ROLLBACK message type design; listed in Recommended Future Work |
| Gap 6: No cross-session coordination | Low | Deferred | Requires Session Registry service design; listed in Recommended Future Work |

---

## Detailed Changes

### 1. Coordinator Fault Tolerance [Section 8.1.1, rewritten]

**Section 8.1.1.1 — Coordinator Liveness**: The coordinator MUST broadcast `COORDINATOR_STATUS` at the heartbeat interval. Participants detect coordinator unavailability after `2 × heartbeat_interval_sec` without a `COORDINATOR_STATUS`.

**Section 8.1.1.2 — State Snapshot**: Defined a mandatory JSON snapshot format containing: snapshot_version, session_id, protocol_version, captured_at, lamport_clock, participants (with status/availability), intents (with state/scope/expiry), operations (with state), conflicts (with state/relations), and policies. Coordinator MUST persist at least once per heartbeat interval.

**Section 8.1.1.3 — Coordinator Recovery**: Upon restart, coordinator MUST load snapshot → replay audit log → broadcast `COORDINATOR_STATUS` with `event: recovered` → accept `HELLO` from reconnecting participants → detect state divergence and emit `STATE_DIVERGENCE` errors if needed.

**Section 8.1.1.4 — Coordinator Handover**: Defined planned handover (`handover` → state transfer → `assumed`) and unplanned failover (standby detects absence → loads shared snapshot → `recovered`). Split-brain prevention: participants reject messages from the coordinator with the lower Lamport clock. Single-coordinator invariant MUST be maintained.

**Previous text**: Section 8.1.1 was a single paragraph with SHOULD-level persistence guidance and no defined snapshot format, no handover protocol, and no coordinator liveness mechanism.

### 2. Session Lifecycle [Section 9.6, new; Section 14.5, new]

**Section 9.6.1 — Session Close Conditions**: Five conditions: manual close (owner/arbiter), auto-close on completion (all entities terminal, configurable), session TTL, coordinator shutdown. Auto-close has a 60-second grace period.

**Section 9.6.2 — Session Summary**: Structured summary object in SESSION_CLOSE with aggregate statistics (total/completed/expired intents, operations, conflicts, participants, duration).

**Section 9.6.3 — Transcript Export**: Defined transcript format: ordered array of MessageEnvelopes sorted by Lamport clock, plus final state snapshot. Authenticated/Verified profiles MUST retain for configured audit_retention_days.

**Section 9.6.4 — Lifecycle Policy**: New session policy block: auto_close, auto_close_grace_sec, session_ttl_sec, transcript_export, audit_retention_days.

**Section 14.5 — SESSION_CLOSE message**: New message type. Coordinator-only. Carries reason, final_lamport_clock, summary, active_intents_disposition (withdraw_all/expire_all), transcript_ref.

### 3. Security Trust Establishment [Sections 23.1.4–23.1.6, new]

**Section 23.1.4 — Credential Exchange**: New `credential` field in HELLO payload for Authenticated/Verified profiles. Five credential types: bearer_token (OAuth/JWT), mtls_fingerprint (TLS layer), api_key (pre-shared), x509_chain (certificate chain for Verified), custom (implementation-defined). Coordinator MUST validate and respond with identity_verified/identity_method in SESSION_INFO. Failure → PROTOCOL_ERROR with CREDENTIAL_REJECTED.

**Section 23.1.5 — Role Assignment and Verification**: Formalized the four-step role process: request → policy evaluation → grant → enforcement. Defined role policy configuration format (default_role, role_assignments, role_constraints). Open profile allows self-declared roles; Authenticated/Verified profiles require a defined role policy.

**Section 23.1.6 — Key Distribution and Rotation**: Coordinator public key fingerprint in SESSION_INFO. Participant key registry maintained by coordinator. Key rotation via HEARTBEAT extension field with grace period. Verified profile requires watermark values included in signed message portion (prevents Lamport clock forgery).

### 4. New Message Types

| Message Type | Direction | Purpose |
|-------------|-----------|---------|
| `SESSION_CLOSE` | Coordinator → All | Formally end a session |
| `COORDINATOR_STATUS` | Coordinator → All | Coordinator liveness and lifecycle events |

### 5. New Error Codes

| Error Code | Description |
|-----------|-------------|
| `COORDINATOR_CONFLICT` | Two coordinators detected in same session |
| `STATE_DIVERGENCE` | Participant state diverges from recovered snapshot |
| `SESSION_CLOSED` | Message received for a closed session |
| `CREDENTIAL_REJECTED` | Credential verification failed |

### 6. Payload Schema Updates

- `HELLO`: added optional `credential` field (conditionally required in Authenticated/Verified)
- `SESSION_INFO`: added `identity_verified` (boolean) and `identity_method` (string) fields

### 7. Section Renumbering

- Section 14.5 is now `SESSION_CLOSE` (new)
- Section 14.6 is now `COORDINATOR_STATUS` (new)
- Section 14.7 is now Participant Unavailability and Recovery (was 14.5)
- All cross-references updated: 14.5.x → 14.7.x throughout the document

### 8. Recommended Future Work Updates

Removed from future work (now addressed):
- "richer session negotiation and discovery protocols" → addressed by SESSION_INFO (v0.1.4) and credential exchange (v0.1.5)
- "session transfer and migration" → addressed by coordinator handover (v0.1.5)

Added to future work:
- semantic scope and dependency declaration
- post-commit rollback semantics (OP_ROLLBACK)
- cross-session coordination

---

## Impact on Reference Implementations

The following changes are needed in the Python and TypeScript reference implementations:

1. **New message types**: Register `SESSION_CLOSE` and `COORDINATOR_STATUS` in MessageType enums
2. **New handlers**: Implement coordinator status broadcasting, session close logic
3. **State snapshot**: Implement snapshot serialization/deserialization per Section 8.1.1.2
4. **Credential exchange**: Add credential field to HELLO, validation in coordinator
5. **Session lifecycle**: Implement auto-close detection, transcript export
6. **Error codes**: Register new error codes (COORDINATOR_CONFLICT, STATE_DIVERGENCE, SESSION_CLOSED, CREDENTIAL_REJECTED)

These changes are additive and do not break existing message flows.
