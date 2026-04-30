# MPAC Protocol Version History

## Directory Structure

```
version_history/
├── CHANGELOG.md                           ← this file
├── v0.1_baseline/                         ← original specification and review materials
├── v0.1.1_trust_governance_recovery/      ← first update round
├── v0.1.2_semantic_interop/               ← second update round
├── v0.1.3_interop_hardening/              ← v0.1.3 spec, audit report, reviews, update record
├── v0.1.4_state_machine_audit/            ← v0.1.4 spec, update record, protocol gap analysis
├── v0.1.5_coordinator_lifecycle_security/ ← v0.1.5 spec, update record
├── v0.1.6_p0_completion/                  ← v0.1.6 spec, update record, deep review
├── v0.1.7_review_driven_hardening/        ← v0.1.7 spec, update record, calibrated deep review
├── v0.1.8_coordination_semantics_hardening/ ← v0.1.8 spec, update record
├── v0.1.9_core_coherence_closure/         ← v0.1.9 spec snapshot, update record, and changeset
├── v0.1.10_execution_governance_closure/  ← v0.1.10 spec snapshot, update record, and changeset
├── v0.1.11_example_and_schema_alignment/  ← v0.1.11 spec snapshot, update record, and changeset
├── v0.1.12_conformance_closure/           ← v0.1.12 spec snapshot and update record
├── v0.1.13_backend_health_monitoring/     ← v0.1.13 spec snapshot and update record
└── v0.1.14_intent_deferred/               ← v0.1.14 spec snapshot and update record
```

The current source of truth is always **SPEC.md** in the project root.

Companion documents in the project root (not versioned in this folder, always reflects the latest spec):
- **MPAC_Developer_Reference.md** — Developer-facing data dictionary: all data objects, field definitions, cross-entity references, state machines, enum registries, and implementation checklist. Updated in sync with SPEC.md.

---

## v0.1 — Baseline (2026-03-29)

The original MPAC v0.1 specification defining the core protocol: sessions, intents, operations, conflicts, governance, and causal context.

**Contents:**

| File | Description |
|------|-------------|
| `MPAC Specification v0.1.docx` | Original specification document (archived, not maintained) |
| `MPAC_Analysis_Report.docx` | Five-point comparison of MPAC vs MCP vs A2A |
| `MPAC_Critique_Response_Memo.docx` | Response to critical review identifying six gap areas |

---

## v0.1.1 — Trust, Governance, Failure Recovery (2026-03-31)

Addressed three shortcomings identified in the critique: trust enforcement, governance deadlock, and silent failure recovery.

**Key changes:**
- Section 23: Security Profiles (Open / Authenticated / Verified) with MUST-level requirements
- Sections 18.5–18.6: Arbiter designation, resolution timeout, frozen scope
- Section 14.4: Unavailability detection, SUSPENDED/ABANDONED states, INTENT_CLAIM message

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.1_2026-03-31.md` | Archived SPEC.md snapshot after this update |
| `MPAC Specification Update Record 2026-03-31.docx` | Detailed changelog for this round |
| `MPAC Critique Closure Note 2026-03-31.docx` | Closure note on critique response |

---

## v0.1.2 — Semantic Interoperability (2026-03-31)

Addressed the remaining gap: semantic interoperability across scope kinds and assumption matching.

**Key changes:**
- Sections 15.2.1–15.2.2: Canonical Resource URIs + Session Resource Registry
- Section 17.7.1: Standardized `semantic_match` basis output format
- Appendix A (Real-World Scenarios) removed from main spec (available in v0.1 baseline)

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.2_2026-04-01.md` | Archived SPEC.md snapshot of the final v0.1.2 spec |
| `MPAC Specification Update Record 2026-03-31 (Semantic Interoperability).docx` | Detailed changelog for this round |

---

## v0.1.3 — Interoperability Hardening (2026-04-01)

Comprehensive update addressing cross-implementation interoperability gaps, normative language tightening, and architectural clarifications identified through independent protocol review.

**Key changes:**
- Section 13.1: Payload schema tables for all 16 message types (required/optional fields, types, enums)
- Section 15.2.1: Mandatory scope overlap determination rules for `file_set`, `entity_set`, `task_set`
- Section 12.3: `lamport_clock` as MUST-support baseline watermark kind with comparison semantics and `lamport_value` fallback field
- Section 8.1: Session Coordinator defined as a first-class protocol entity
- Section 7.1: Intent-before-action upgraded to MUST in Governance Profile
- Section 7.3: Causal context upgraded to MUST for OP_COMMIT, CONFLICT_REPORT, RESOLUTION
- Section 16.3: `state_ref_before`/`state_ref_after` MUST in OP_COMMIT; `causally_unverifiable` handling
- Section 14.4.4: Concurrent INTENT_CLAIM resolution (first-claim-wins)
- Section 18.4: Rollback expectation requirement for rejecting committed operations; `winner`/`loser` shorthand removed
- Section 18.6.2: Frozen scope also rejects INTENT_ANNOUNCE; fallback timeout mechanism (Section 18.6.2.1)
- Section 23.1.2: Replay protection upgraded to MUST; role assertion validation added
- Section 23.4: End-to-end encryption consideration added
- Multiple SHOULD → MUST upgrades (ts format, HELLO, resolution watermark, conflict based_on_watermark)

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.3_2026-04-02.md` | Archived SPEC.md snapshot of the final v0.1.3 spec |
| `MPAC_v0.1.3_Update_Record.md` | Detailed changelog with rationale for each change |
| `MPAC_v0.1.3_Audit_Report.md` | Five-dimension audit of v0.1.3: efficiency, robustness, scalability, semantic alignment, state machine cross-safety |
| `MPAC_Independent_Review_2026-04-01.md` | Independent protocol review identifying interoperability gaps |
| `MPAC_Re-evaluation_v0.1.3_2026-04-01.md` | Re-evaluation after interoperability hardening |

---

## v0.1.4 — State Machine Cross-Safety & Session Negotiation (2026-04-02)

Spec revision driven by the v0.1.3 five-dimension audit. Resolved state machine cross-lifecycle gaps (Intent Expiry Cascade, Conflict Auto-Dismiss), added coordinator fault recovery guidance, and introduced SESSION_INFO for session negotiation.

**Key changes:**
- Section 15.7 (new): Intent Expiry Cascade — intent terminal → associated PROPOSED ops auto-reject, SUSPENDED → ops FROZEN
- Section 17.9 (new): Conflict Auto-Dismissal — all related intents and ops terminal → conflict auto-DISMISS, frozen scope released
- Section 8.1.1 (new): Coordinator Fault Recovery — state persistence SHOULD, restart state rebuild, participant behavior during coordinator unavailability
- Section 14.2 (new): SESSION_INFO message type — coordinator response to HELLO with session config and compatibility check
- Multiple normative upgrades from audit recommendations

**Protocol gap analysis (2026-04-03):** After completing ~85% reference implementation coverage (16/17 message types, full state machine lifecycle, liveness, arbiter workflow, intent claim), six protocol-level design gaps were identified for future spec revisions.

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.4_2026-04-02.md` | SPEC.md snapshot of the current v0.1.4 spec |
| `MPAC_v0.1.4_Update_Record.md` | Detailed changelog: what was resolved from audit, what was deferred, and why |
| `MPAC_v0.1.4_Gap_Analysis.md` | Protocol-level gap analysis: 6 design gaps identified after reference implementation |

---

## v0.1.5 — Coordinator Fault Tolerance, Session Lifecycle, Security Trust Establishment (2026-04-03)

Protocol-level revision driven by the v0.1.4 gap analysis. Addresses three of six identified protocol design gaps: coordinator fault tolerance (the most critical structural gap), session lifecycle (no defined end for sessions), and security trust establishment (no concrete credential exchange mechanism).

**Key changes:**
- Section 8.1.1 (rewritten): Coordinator liveness via `COORDINATOR_STATUS` heartbeat, mandatory state snapshot format (JSON), recovery procedure (snapshot + audit log replay), planned/unplanned handover protocol, split-brain prevention via Lamport clock comparison
- Section 9.6 (new): Session lifecycle — `SESSION_CLOSE` conditions (manual, auto-close on completion, session TTL, coordinator shutdown), session summary, transcript export format, lifecycle policy
- Section 23.1.4 (new): Credential exchange in HELLO handshake — five credential types (bearer_token, mtls_fingerprint, api_key, x509_chain, custom), coordinator validation, CREDENTIAL_REJECTED error
- Section 23.1.5 (new): Role assignment and verification — four-step process (request → policy evaluation → grant → enforcement), role policy configuration format
- Section 23.1.6 (new): Key distribution and rotation — coordinator key in SESSION_INFO, participant key registry, rotation via HEARTBEAT, watermark integrity binding in Verified profile
- Two new message types: `SESSION_CLOSE`, `COORDINATOR_STATUS` (total: 19)
- Four new error codes: `COORDINATOR_CONFLICT`, `STATE_DIVERGENCE`, `SESSION_CLOSED`, `CREDENTIAL_REJECTED`
- Section 14.5–14.7 renumbered (old 14.5 → 14.7) with all cross-references updated

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.5_2026-04-03.md` | SPEC.md snapshot of the current v0.1.5 spec |
| `MPAC_v0.1.5_Update_Record.md` | Detailed changelog: gap analysis → resolution map, impact on reference implementations |

---

## v0.1.6 — P0 Completion: OP_SUPERSEDE, Fault Recovery, JSON Schema (2026-04-03)

Resolves all P0 priority items from v0.1.5's coverage assessment. After this version, all 19 message types have full handler implementations, the coordinator supports snapshot-based fault recovery with audit log replay, and machine-readable JSON Schema definitions cover all 11 message payload types.

**Key changes:**
- `OP_SUPERSEDE` handler implemented: validates superseded op is COMMITTED, transitions to SUPERSEDED state, chains state references, supports supersession chains
- `SUPERSEDED` added to `OperationState` enum and state machine (`COMMITTED → SUPERSEDED` transition)
- Coordinator fault recovery: `recover_from_snapshot()` restores all internal state (participants, intents, operations, conflicts, Lamport clock, session status); `replay_audit_log()` replays messages received after snapshot
- Audit log recording: all processed messages stored for replay on recovery
- JSON Schema: added `session_close.schema.json`, `coordinator_status.schema.json`, `op_supersede.schema.json`; updated `envelope.schema.json` with new message types
- Tests: Python 55 → 70 (+15), TypeScript 44 → 56 (+12)

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.6_2026-04-03.md` | SPEC.md snapshot of the v0.1.6 spec |
| `MPAC_v0.1.6_Update_Record.md` | Detailed changelog: P0 items → resolution, coverage impact |

---

## v0.1.7 — Review-Driven Hardening: Execution Model, Consistency, Atomicity, Coordinator Trust (2026-04-03)

Independent deep technical review (simulating SOSP/OSDI-level scrutiny) identified foundational gaps. After cross-referencing with the full version history (v0.1–v0.1.6), the review was calibrated: 2 findings were genuinely new (OP_COMMIT ambiguity, consistency model), 3 were known-and-deferred items promoted to this version. All 7 findings were resolved.

**Key changes:**
- Section 7.7: Explicit consistency model (coordinator-serialized total order, degraded-mode semantics, reconciliation rules)
- Section 7.8: Execution model declaration (`pre_commit` vs `post_commit`) — resolves OP_COMMIT semantic ambiguity
- Section 12.7: Lamport clock maintenance rules (6 normative rules: init, send, receive, coordinator authority, snapshot, monotonicity)
- Section 16.8: `OP_BATCH_COMMIT` message type for atomic multi-target operations (`all_or_nothing`, `best_effort`)
- Section 23.1.3.1: Coordinator accountability in Verified profile (coordinator signs all messages, tamper-evident log, independent audit)
- Section 18.6.2.1: Frozen scope progressive degradation (3-phase: normal → escalate+priority → first-committer-wins)
- Sections 15.6.1, 16.6.1, 17.8.1: Normative state transition tables for Intent, Operation, and Conflict lifecycles
- One new message type: `OP_BATCH_COMMIT` (total: 20)
- `execution_model` field added to SESSION_INFO (required)

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.6_2026-04-03.md` | Archived SPEC.md snapshot (pre-change, v0.1.6) |
| `MPAC_v0.1.6_Deep_Review_2026-04-03.md` | Independent deep review that triggered this revision |
| `MPAC_v0.1.7_Update_Record.md` | Detailed changelog: review finding → resolution map, implementation impact |

---

## v0.1.8 — Coordination Semantics Hardening (2026-04-03)

Protocol-level revision targeting three coordination semantics gaps that fall squarely within MPAC's application-layer scope: an undefined race condition in concurrent resolution, a livelock risk in intent re-announcement, and missing guidance for causal gap detection. This revision was guided by a deliberate scope calibration: distributed systems concerns (partition handling, reconciliation, replay protection) were explicitly scoped out as belonging to the transport/infrastructure layer.

**Key changes:**
- Section 18.4: Concurrent resolution rule — first-resolution-wins. Coordinator MUST accept only the first valid `RESOLUTION` for a given `conflict_id`, reject subsequent with `RESOLUTION_CONFLICT` error. Parallels `INTENT_CLAIM` first-claim-wins pattern.
- Section 15.3.1 (new): Intent re-announce backoff — exponential backoff (30s initial, 2× multiplier, 300s max) after conflict-driven intent rejection. Prevents livelock. Coordinator MAY enforce via `INTENT_BACKOFF` error. Configurable via liveness policy.
- Section 12.8 (new): Causal gap detection and behavior — participants SHOULD NOT issue causally-sensitive judgments when causal context is incomplete, MAY signal `CAUSAL_GAP` to coordinator.
- Three new error codes: `RESOLUTION_CONFLICT`, `CAUSAL_GAP`, `INTENT_BACKOFF`

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.8_2026-04-03.md` | Archived SPEC.md snapshot (v0.1.8, current version at time of release) |
| `MPAC_v0.1.8_Update_Record.md` | Detailed changelog: finding → resolution map, scope calibration rationale, implementation impact |

---

## v0.1.9 — Core Coherence Closure (2026-04-04)

Revision boundary created after the v0.1.8 gap analysis. This round does not expand MPAC's feature scope; instead, it closes coherence gaps between coordinator failover, Lamport rejoin semantics, intent-claim lifecycle, replay-protection recovery, and the repository's conformance artifacts.

**Key changes proposed:**
- Add `coordinator_epoch` fencing semantics to prevent stale coordinators from surviving handover / failover
- Add `sender_instance_id` so Lamport monotonicity and replay tracking are defined per sender incarnation, not only per principal
- Add `INTENT_CLAIM_STATUS` to make claim approval / rejection / withdrawal explicit and align the protocol on `TRANSFERRED`
- Introduce `settled` operation terminology so session auto-close no longer conflicts with `COMMITTED -> SUPERSEDED`
- Extend snapshot semantics with `anti_replay` checkpoint state so replay protection survives recovery in Authenticated / Verified profiles
- Close schema and conformance gaps: `OP_BATCH_COMMIT`, updated `SESSION_INFO`, error-code coverage, message-type-aware envelope validation

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.9_2026-04-04.md` | Archived snapshot of the implemented v0.1.9 spec |
| `MPAC_v0.1.9_Update_Record.md` | Update record mapping each P0/P1/P2 gap to the concrete v0.1.9 fix |
| `MPAC_v0.1.9_Spec_Changeset.md` | Field- and rule-level changeset that was merged into the root spec |

---

## v0.1.10 — Execution and Governance Closure (2026-04-04)

Revision boundary created after the v0.1.9 coherence closure. This round keeps MPAC on the `v0.1.x` line rather than jumping to `v0.2.0`, because the work is still closure-oriented: it tightens residual ambiguities in execution semantics, escalation authority, conflict dismissal, and governance auditability without expanding the protocol's feature scope.

**Key changes proposed:**
- Close the profile matrix: `pre_commit` now requires Governance Profile compliance, and Core Profile sessions MUST use `post_commit`
- Clarify pre-commit semantics so coordinator authorization does not itself make an operation `COMMITTED`; commit completion still requires the proposer to declare the executed mutation
- Narrow concurrent conflict resolution to the current authority phase so arbiter finality survives escalation
- Remove `deferred` from the `RESOLUTION.decision` registry because it had no state-machine semantics
- Include `TRANSFERRED` in conflict auto-dismiss terminal-intent handling
- Require `approved_by` on Governance Profile claim approvals for audit completeness

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.10_2026-04-04.md` | Archived snapshot of the implemented v0.1.10 spec |
| `MPAC_v0.1.10_Update_Record.md` | Update record mapping residual protocol gaps to the concrete v0.1.10 fixes |
| `MPAC_v0.1.10_Spec_Changeset.md` | Rule-level changeset that was merged into the root spec for v0.1.10 |

---

## v0.1.11 — Example and Schema Alignment (2026-04-04)

Revision boundary created after a systematic review of the v0.1.10 root spec. This round addresses documentation-level inconsistencies (example messages missing normative fields, payload table gaps, cross-reference errors), adds SHOULD-level normative clarifications for edge-case behaviors, and fixes one state machine table gap and one terminology inconsistency. No new message types or wire format changes; one row added to the Intent state transition table.

**Key changes:**
- Fix all Section 28 example messages: add `sender_instance_id` to sender objects, update `version` from `"0.1.0"` to `"0.1.11"`
- Add `identity_issuer` (Optional) to `SESSION_INFO` payload table in Section 13.1 to match the credential exchange example in Section 23.1.4
- Align `SESSION_CLOSE` summary example (Section 14.5) with the detailed structure defined in Section 9.6.2
- Fix `COORDINATOR_STATUS` cross-reference: `(Section 14.3)` → `(Section 14.7.5)` for `heartbeat_interval_sec`
- Add pre-commit disambiguation rule for `OP_BATCH_COMMIT`: coordinator checks `batch_id` existence to distinguish initial request from completion declaration
- Add scope-expansion conflict re-evaluation guidance to `INTENT_UPDATE` (Section 15.4)
- Clarify `GOODBYE` transfer disposition: coordinator SHOULD transition intents to `SUSPENDED`, enabling `INTENT_CLAIM`; add corresponding `ACTIVE → SUSPENDED` row to the Intent State Transition Table (Section 15.6.1)
- Add Semantic Profile placeholder note (Section 20.3)
- Unify "current conflict phase" → "current authority phase" terminology across Conflict State Transition Table and Section 18.4

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.11_2026-04-04.md` | Archived snapshot of the implemented v0.1.11 spec |
| `MPAC_v0.1.11_Update_Record.md` | Update record mapping each documentation/normative gap to its v0.1.11 fix |
| `MPAC_v0.1.11_Spec_Changeset.md` | Field- and rule-level changeset that was merged into the root spec for v0.1.11 |

---

## v0.1.12 — Conformance Closure (2026-04-05)

Schema conformance closure driven by an independent protocol audit. All 21 message types now have dedicated JSON Schema definitions, the envelope schema dispatches payload validation by `message_type` via `if/then`, and conditional constraints (handover, claim status, rollback) are machine-enforceable. The `authorization` coordinator event — already used by both reference implementations for pre-commit approval — is formally standardized. No new message types or protocol semantics beyond these closure fixes.

**Key changes:**
- 8 new message payload schemas: `heartbeat`, `goodbye`, `intent_claim`, `intent_update`, `intent_withdraw`, `op_reject`, `conflict_ack`, `conflict_escalate`
- Envelope `payload` field dispatched to per-message-type schema via `allOf` / `if/then`; coordinator-only messages (`SESSION_INFO`, `SESSION_CLOSE`, `COORDINATOR_STATUS`, `INTENT_CLAIM_STATUS`) require `coordinator_epoch`
- `COORDINATOR_STATUS`: `event` changed to enum with 5 values (added `authorization`); `next_coordinator_epoch` added with `if/then` for handover; `authorization` fields (`authorized_op_id`, `authorized_by`, `authorized_batch_id`) added with `if/then`; `snapshot` field removed (recovery is handled separately); both ref-impl `authorizeOperation` updated to include required `coordinator_id` and `session_health`
- `OP_BATCH_COMMIT`: entry `required` tightened to include `state_ref_before` and `state_ref_after`, matching spec and `OP_COMMIT`
- `INTENT_CLAIM_STATUS`: `if/then` constraints for `approved` → `new_intent_id`, `rejected`/`withdrawn` → `reason`
- `outcome.schema.json`: rollback requirement documented in description (runtime-state-dependent; cannot be fully expressed in JSON Schema)
- Demo transcript version fixed from `0.1.10` to `0.1.12`
- SPEC.md Section 13.1 payload table and Section 14.6 semantic enumeration both updated with `authorization` event
- `MPAC_Developer_Reference.md` synced to v0.1.12: COORDINATOR_STATUS fields, authorization event, cross-references
- **Runtime enforcement hardening** (both Python and TypeScript reference implementations):
  - HELLO-first gate: unregistered senders rejected with `AUTHORIZATION_FAILED`
  - Credential validation: non-open profiles reject HELLO without valid credential (`CREDENTIAL_REJECTED`)
  - Resolution authority: only owner/arbiter pre-escalation; only escalate_to target or arbiter post-escalation
  - Frozen-scope enforcement: scopes freeze only after `resolution_timeout_sec` expires with no arbiter (per Section 18.6.2); `INTENT_ANNOUNCE`, `OP_PROPOSE`, `OP_COMMIT`, `OP_BATCH_COMMIT` blocked when scope overlaps frozen conflict (`SCOPE_FROZEN`)
  - Batch atomicity rollback: `all_or_nothing` batches clean up registered operations on validation failure
  - Error codes: `CAUSAL_GAP` and `INTENT_BACKOFF` added to ErrorCode enum; `authorization` added to CoordinatorEvent enum
- **P1 enforcement corrections** (second audit pass):
  - GOODBYE removed from HELLO-first gate exemption — unregistered senders cannot force-withdraw other principals' intents via `active_intents` payload
  - GOODBYE ownership guard added: sender can only withdraw/transfer their own intents
  - Frozen-scope timing corrected: `scope_frozen` flag on Conflict, set only by `checkResolutionTimeouts` when no arbiter available (not on conflict creation)
  - `OP_BATCH_COMMIT` frozen-scope check added (was missing from initial enforcement pass)
- **P1+P2 enforcement corrections** (third audit pass):
  - `scope_frozen` persisted in snapshot: both serialization and recovery now include the flag
  - `INTENT_ANNOUNCE` partial overlap: fully contained in frozen scope → reject; partially overlapping → accept with warning (Section 18.6.2)
  - HELLO-first gate error code corrected from `AUTHORIZATION_FAILED` to `INVALID_REFERENCE` per Section 14.1
- **P1 frozen-scope target-based correction** (fourth audit pass):
  - All frozen-scope checks changed from intent-based to **target-based**: `OP_PROPOSE`, `OP_COMMIT`, `OP_BATCH_COMMIT` now check each operation's `target` field directly against frozen scopes, not the parent intent's scope. This closes the bypass where `intent_id` (optional per schema) could be omitted to skip the check.
  - Python `_handle_op_propose` and `_handle_op_commit` aligned with TypeScript (which already used target-based checks for single ops)
- 66 new adversarial tests (Python 34, TypeScript 32) covering all 6 enforcement rules + target-based frozen-scope
- **P1 security/consistency closure** (fifth audit pass):
  - Role policy evaluation enforced: coordinator evaluates HELLO `requested_roles` against `role_policy` per Section 23.1.5; Authenticated/Verified profiles no longer accept self-asserted roles. `SESSION_INFO.granted_roles` reflects actually granted roles.
  - Replay protection enforced: duplicate `message_id` rejected with `REPLAY_DETECTED` in Authenticated/Verified profiles; protection state restored from snapshot on recovery (Section 23.1.2). `REPLAY_DETECTED` added to SPEC.md error code registry and both ErrorCode enums.
  - SESSION_CLOSE schema aligned with spec: `reason` enum corrected to 5 values (removed `error`/`admin_close`/`transfer`); `final_lamport_clock` made required; `active_intents_disposition` corrected to 2 values (removed `transfer`). Implementation summary expanded to include per-state breakdowns per Section 9.6.2.
- **P1+P2 enforcement corrections** (sixth audit pass):
  - Replay timestamp window check: both Python and TypeScript `processMessage` now verify message timestamp drift against `replay_window_sec` (default 300s / RECOMMENDED: 5 minutes); excessive drift rejected with `REPLAY_DETECTED`
  - `REPLAY_DETECTED` added to `protocol_error.schema.json` error code enum (was missing despite being in SPEC.md and both ErrorCode enums)
  - No-policy rejection: Authenticated/Verified profiles without a `role_policy` now return `AUTHORIZATION_FAILED` instead of silently granting `["participant"]`; `handleHello` checks for empty granted roles and rejects
  - `max_count` self-exclusion: `evaluateRolePolicy` excludes the joining principal from the role count, preventing rejoin from being blocked by the principal's own prior registration
- **P2 invalid timestamp bypass** (seventh audit pass):
  - Unparseable `ts` (e.g. `"not-a-timestamp"`) in Authenticated/Verified profiles no longer silently bypasses the replay-window check; rejected with `REPLAY_DETECTED` requiring RFC 3339 date-time format
- **P2 RFC 3339 format strictness** (eighth audit pass):
  - Timestamps that are runtime-parseable but not valid RFC 3339 (e.g. space instead of `T` separator) are now rejected by an explicit regex check before parsing, matching the `format: "date-time"` requirement in `envelope.schema.json`

- **Distributed validation** (real-world deployment testing):
  - WebSocket transport binding: coordinator server + agent clients, message routing by type (unicast/multicast/broadcast)
  - Concurrent Claude agent decision-making: parallel LLM calls for intent decisions, conflict positions, and code generation
  - Real code modification: agents read, fix (via Claude), and commit actual Python source files with SHA-256 state_ref tracking
  - Optimistic concurrency control: `state_ref_before` validation in `_handle_op_commit` and `_handle_op_batch_commit`; stale commits rejected with `STALE_STATE_REF`; agents rebase on latest committed version and retry
  - Coordinator auto-resolve: `resolve_as_coordinator()` method for pure-agent scenarios where no human arbiter is available
  - HELLO-first gate coordinator exemption: coordinator's self-sent messages bypass the registration check
  - All 109 unit tests pass with zero regressions after changes

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.12_2026-04-05.md` | Archived SPEC.md snapshot of the v0.1.12 spec |
| `MPAC_v0.1.12_Update_Record.md` | Detailed update record: audit findings → resolution map |
| `MPAC_v0.1.12_Distributed_Validation.md` | Distributed validation report: WebSocket transport, concurrent Claude agents, real code modification, optimistic concurrency control |

---

## v0.1.13 — Backend Health Monitoring (2026-04-07)

New feature: backend AI model health monitoring integrated with [aistatus.cc](https://aistatus.cc). Agents can declare their AI model dependency at session join, report backend provider health in heartbeats, and trigger coordinator-mediated alerts and model switching governance. All changes are additive and backward-compatible — agents that don't declare a `backend` are unaffected.

**Key changes:**
- `HELLO` payload: new optional `backend` field (`model_id`, `provider`) for declaring AI model dependency
- `HEARTBEAT` payload: new optional `backend_health` field (`model_id`, `provider_status`, `status_detail`, `checked_at`, `alternatives`, `switched_from`, `switch_reason`) for reporting backend health
- `COORDINATOR_STATUS`: new `backend_alert` event with conditional fields `affected_principal` and `backend_detail`
- `SESSION_INFO` liveness_policy: new optional `backend_health_policy` object (`enabled`, `check_source`, `check_interval_sec`, `on_degraded`, `on_down`, `auto_switch`, `allowed_providers`)
- New error code: `BACKEND_SWITCH_DENIED` for rejected model switches (auto_switch=forbidden or provider not in allowed_providers)
- New SPEC Section 14.3.1: full behavioral specification of backend health monitoring, including coordinator actions (ignore/warn/suspend_and_claim) and model switching governance (allowed/notify_first/forbidden)
- Protocol vs. implementation boundary: protocol manages signaling and governance rules; model selection, switch timing, and fallback strategy are implementation decisions
- `provider_status` enum and `alternatives` structure directly mirror the aistatus.cc `/api/check` response format
- Both reference implementations (Python + TypeScript) updated: `ParticipantInfo` tracks backend state, `handleHeartbeat` processes backend_health, coordinator emits `backend_alert` events and enforces switch policy
- Participant helper classes extended: `hello()` accepts `backend` param, `heartbeat()` accepts `backend_health` param (Python + TypeScript)
- Demo transcript enhanced: 18-step backend health scenario covering degraded → down → switch → INTENT_CLAIM transfer → BACKEND_SWITCH_DENIED → provider recovery
- Specialized backend health tests: 13 test cases in each language covering all monitoring scenarios
- Fixed Python `_process_backend_health` naming bug (`stateMachine` → `state_machine`) and transition event (`"unavailable"` → `"SUSPENDED"`)
- All 122 Python tests + 101 TypeScript tests pass with zero regressions
- **Coordination overhead demo** (`run_overhead_comparison.py`): same 3-agent PR review scenario run in Traditional (serial) vs MPAC (parallel) mode, with precise decision_time / coordination_overhead breakdown. Representative results: decision time -9% (API noise), coordination overhead **-95%**, wall clock -79%.
- **Pre-commit + INTENT_CLAIM demo** (`run_precommit_claim.py`): 3 agents in `pre_commit` + `governance` mode exercise 6 previously uncovered message types (INTENT_UPDATE, INTENT_WITHDRAW, INTENT_CLAIM, INTENT_CLAIM_STATUS, OP_PROPOSE, OP_REJECT). Demonstrates pre-commit authorization flow, agent crash simulation with liveness detection, and governance-mediated claim approval.
- **Conflict escalation demo** (`run_escalation.py`): 2 owner agents + 1 arbiter exercise CONFLICT_ESCALATE with Claude-powered arbiter resolution. Demonstrates multi-level governance (owner → arbiter) and binding arbitration.
- **Full message type demo coverage**: all 21 MPAC message types now have live Claude API demo coverage across 7 distributed demos.
- `ws_coordinator.py` constructor now accepts `**kwargs` for `execution_model`, `compliance_profile`, etc. (backward-compatible)
- `ws_agent.py` Python 3.9 compatibility fix (`from __future__ import annotations`)
- Apache License 2.0 added (`LICENSE`)
- **Demo hardening for open-source release:** removed `httpx.Client(verify=False)` from all demo agents (Anthropic SDK handles HTTPS natively); updated default model from dated snapshot `claude-sonnet-4-20250514` to stable family ID `claude-sonnet-4-6`; added API cost disclaimer notes to all demo docstrings; fixed `pyproject.toml` license from MIT to Apache-2.0

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.13_2026-04-07.md` | Archived SPEC.md snapshot of the v0.1.13 spec |
| `MPAC_v0.1.13_Update_Record.md` | Detailed update record: feature design, API alignment, and implementation notes |

---

## Pip Package and Remote Collaboration (2026-04-08)

Engineering-only release: the MPAC protocol core is now available as a pip-installable Python package (`mpac-protocol`) with a built-in WebSocket coordinator, shared file workspace, and interactive agent CLI. Two people on different computers can collaboratively operate AI agents on shared code files through the MPAC protocol. No protocol changes — SPEC.md is unchanged.

**Key changes:**
- `mpac-package/`: pip-installable package wrapping protocol core (7 modules), WebSocket transport (MPACServer + MPACAgent), in-memory FileStore with SHA-256 optimistic concurrency, and interactive CLI (view files, give tasks, see color-coded diffs)
- Sideband file operations: `FILE_LIST`, `FILE_READ`, `FILE_UPDATED` messages over WebSocket alongside MPAC protocol messages; `OP_COMMIT` payload carries `file_changes` for coordinator-side storage
- `test_site_A/` and `test_site_B/`: two-site simulation with separate venvs, each `pip install`-ing the package independently
- `mpac-starter-kit.zip`: self-contained distribution (`.whl` + `run.py` + `README.txt`) for collaborators
- ngrok compatibility: agent auto-detects ngrok URLs and adds `ngrok-skip-browser-warning` header
- End-to-end validated: both agents connect, read workspace, announce intents, detect conflicts, generate fixes via Claude, commit with state_ref tracking, see each other's changes in real-time

---

## v0.1.14 — INTENT_DEFERRED (2026-04-28)

New optional message type — `INTENT_DEFERRED` — a non-claiming "yield" signal that lets a participant record *"I saw an active intent on this scope and chose to step back"* without announcing a competing intent. Pure UX affordance: lets the human owner see cooperative deference (e.g. *"Bob saw Alice editing X and stepped back"*) instead of either polluting the conflict surface with non-conflicts or hiding the social fact entirely. Strictly additive — no existing message type, field, or state transition is changed.

**Key changes:**
- New SPEC §15.5.1 + §13.1 payload table: `INTENT_DEFERRED` with two payload shapes sharing one `message_type` — an **active form** sent by the deferring participant (carries `deferral_id`, `scope`, optional `observed_intent_ids` / `observed_principals` / `reason` / `ttl_sec`) and a **resolution form** emitted only by the coordinator (carries `deferral_id`, `principal_id`, `status: resolved | expired`, optional `reason`).
- Coordinator MUST fill `principal_id` and `expires_at` (= `received_at + ttl_sec`, default 60s) when re-broadcasting the active form.
- **Three-axis cleanup rule** — coordinator MUST emit a `status: resolved` follow-up when ANY of: (1) all intents in `observed_intent_ids` reach a terminal state; (2) the same `principal_id` subsequently sends `INTENT_ANNOUNCE`; (3) the terminating intent's `principal_id` appears in `observed_principals` OR `observed_intent_ids` (defense-in-depth match for clients that conflated the two fields). When wall-clock exceeds `expires_at`, emit `status: expired`.
- **Non-properties (explicitly defined):** `INTENT_DEFERRED` is NOT an intent — no state machine entry, does not lock scope, MUST NOT trigger overlap detection or `CONFLICT_REPORT`, MUST NOT block the same principal's subsequent `INTENT_ANNOUNCE`. Distinct from both `INTENT_ANNOUNCE` (no scope claim) and `CONFLICT_REPORT` (no opposing pair).
- **Compliance profile:** `INTENT_DEFERRED` is **not** in any profile's MUST set (Core / Governance / Semantic). It is an optional UX-affordance message — implementations that surface a "yielded" hint in their UI SHOULD support it.
- Protocol version bump 0.1.13 → 0.1.14 across SPEC.md (header, body, all example envelopes) and `MPAC_Developer_Reference.md` (title). The historical retrospective in SPEC §28 (`"addressed across v0.1.1–v0.1.13"`) is intentionally **not** extended, because v0.1.14 adds a new feature rather than closing a previously identified gap.
- **Spec/package version decoupling:** prior drafts of this feature carried a `(v0.2.5+)` tag in SPEC body, mixing protocol version and Python package (`mpac` PyPI) version. SPEC.md now refers only to protocol versions (e.g. `(v0.1.14+)`); reference-implementation availability (`mpac` ≥ 0.2.5, `mpac-mcp` ≥ 0.2.9) is recorded in the Update Record only.
- `MPAC_Developer_Reference.md` updated in 11 locations: §2 message roster (added row + ⚪ optional marker + footnote), new §3.7.1 payload section, §4 entity diagram, §4.1 cross-reference table (3 new rows), §5.1 / §5.4 cascade notes, §6.4 compliance footnote, new §6.9 Deferral Status enum registry, new §8.15 protocol semantics summary, §9 implementation checklist (new "v0.1.14 INTENT_DEFERRED" group).

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.14_2026-04-28.md` | Archived SPEC.md snapshot of the v0.1.14 spec |
| `MPAC_v0.1.14_Update_Record.md` | Detailed update record: motivation, payload schemas, three-axis cleanup rule, non-properties, compatibility, and the spec-vs-package version decoupling rationale |

---

## v0.1.15 — Cross-Principal Scope Race Lock (2026-04-29)

Tightens `INTENT_ANNOUNCE` arrival semantics: cross-principal same-resource collisions are now hard-rejected with a new `STALE_INTENT` error code instead of producing an advisory `CONFLICT_REPORT(category="scope_overlap")`. Mirrors source-control's split between **merge conflicts** (must resolve before push) and **semantic conflicts** (warn, defer to CI). Cross-file `dependency_breakage` candidates remain advisory — auto-rejecting every dependent whenever a hub file is touched would block legitimate parallel work.

Motivated by 2026-04-29 field testing with two LLM-driven Claude relays: the prior advisory model assumed agents would re-evaluate after seeing a `CONFLICT_REPORT`, but synchronous-blocking LLMs are already mid-write by the time the report arrives. The hard-reject path forces the loser into a structured "yield" flow before any write happens.

**Key changes:**
- New SPEC §15.3.2 (Cross-Principal Scope Race Lock): coordinator MUST reject `INTENT_ANNOUNCE` with `PROTOCOL_ERROR(STALE_INTENT)` when the proposed scope's resources overlap an active intent owned by a **different** principal. Rejected intent MUST NOT be registered; no `CONFLICT_REPORT` MUST fire (race lock pre-empts the advisory path). Rejection's `description` SHOULD identify the colliding `intent_id` and `principal_id` so the client can construct an `INTENT_DEFERRED` correctly.
- **Same-vs-cross-file scope:** rule applies ONLY to direct resource overlap (would-be `scope_overlap`). `dependency_breakage` cross-file candidates remain advisory — keeps collaboration alive on hub modules where dependent edits are often backward-compatible.
- **Same-principal exemption:** re-announcement by the same principal on the same scope is NOT race-locked; it goes through the auto-supersede path (treats prior intent as orphan from a crashed retry).
- **Lock release:** bound to the holding intent's lifecycle. Withdraw / TTL / supersede / transfer all release the lock. Coordinator MUST NOT retain race-lock state beyond the holding intent's lifetime.
- **Disambiguation from existing rejection codes:** `SCOPE_FROZEN` (Section 18.6.2, conflict-resolution timeout) and `INTENT_BACKOFF` (Section 15.3.1, post-RESOLUTION livelock prevention) are independent mechanisms with different recovery semantics. `STALE_INTENT` (Section 15.3.2) is none of those — it's bound to a peer's active intent lifecycle.
- New `PROTOCOL_ERROR` code added to Section 22.1's recommended values list.
- Section 15.5.1 (`INTENT_DEFERRED`) clarification: coordinator MUST evaluate the three-axis cleanup conditions both at **arrival time** (if any condition is already true, emit `status: resolved` in the same response that delivers the active broadcast) AND on subsequent intent-state transitions. Without arrival-time evaluation, a slow-yielding agent whose deferral arrives after the observed peer terminated would leave a stranded entry until TTL expiry. The original three-axis rules are unchanged.
- **Intentionally out of scope (deferred to v0.2.x or later):** the deeper architectural limitation that LLM relay subprocesses do not subscribe to coordinator broadcasts (so the "first to announce" participant in a same-tick collision never learns it collided, and reply text can use stale `check_overlap` snapshots). Recorded in the Update Record as a known limitation.
- Protocol version bump 0.1.14 → 0.1.15 (header + Status section). The historical retrospective in §28 is intentionally not extended (v0.1.15 tightens an existing message's arrival semantics rather than closing a previously identified gap).
- `MPAC_Developer_Reference.md`: needs `STALE_INTENT` row in error code registry, plus a brief note on §15.3.2's race-lock semantics and same-principal exemption. (Update may lag; SPEC.md is source of truth.)

**Contents:**

| File | Description |
|------|-------------|
| `SPEC_v0.1.15_2026-04-29.md` | Archived SPEC.md snapshot of the v0.1.15 spec |
| `MPAC_v0.1.15_Update_Record.md` | Detailed update record: motivation, the new `STALE_INTENT` code's distinction from `SCOPE_FROZEN` / `INTENT_BACKOFF`, the §15.3.2 normative rule, the §15.5.1 fast-resolve clarification, the explicitly-out-of-scope reactive event subscription limitation, and reference-implementation status (`mpac` 0.2.8, `mpac-mcp` 0.2.12; TypeScript still TODO) |

---

## Archival Convention and Procedure

When the user says "归档" or "archive the spec" or "参考 version history 里的 readme 把现有 spec 归档", follow this procedure exactly:

### Step 1: Determine the new version number

- Read this CHANGELOG to find the latest version entry (e.g., `v0.1.4_state_machine_audit`)
- The new version number increments the patch version (e.g., `v0.1.4` → `v0.1.5`)
- If the user specifies a version number, use that instead

### Step 2: Determine the folder name suffix

- Ask the user for a short descriptive suffix, or infer from context (e.g., `interop_hardening`, `state_machine_audit`)
- Folder name format: `v{version}_{suffix}`

### Step 3: Create the archive folder

```
mkdir version_history/v{version}_{suffix}/
```

### Step 4: Archive the versioned SPEC.md

- After the revision is applied, copy the resulting `SPEC.md` from the project root into the new folder
- Name it `SPEC_v{new_version}_{today's date YYYY-MM-DD}.md`
- Example: if the new spec version is v0.1.4 and today is 2026-04-02, the file is `SPEC_v0.1.4_2026-04-02.md`
- This snapshot captures the version represented by that archive folder

### Step 5: Add supporting documents

- If there is an audit report, changelog, or update record, copy or create it in the same folder
- Common file types:
  - `MPAC_v{version}_Audit_Report.md` — external review or audit
  - `MPAC_v{version}_Update_Record.md` — detailed changelog with rationale
  - Other analysis documents as needed

### Step 6: Update this CHANGELOG

1. **Directory structure**: add the new folder to the tree at the top of this file
2. **Version entry**: add a new `## v{version} — {Title} ({date})` section before the "Convention" section, containing:
   - One-paragraph summary of what this version represents
   - `**Key changes:**` or `**Key findings:**` bullet list
   - `**Contents:**` table listing every file in the folder with a description
3. Keep entries in chronological order (newest last, just before this Convention section)

### Step 7: Apply changes to SPEC.md and save the final snapshot (if applicable)

- If the archive is in preparation for a spec revision, the user will instruct what changes to make to `SPEC.md` in the project root separately
- After changes are applied, the root `SPEC.md` should be updated to reflect the new version number in its Section 1
- Then copy the updated root `SPEC.md` into the archive folder using the `SPEC_v{new_version}_{date}.md` naming rule above

### Quick reference

| What | Where | Naming |
|------|-------|--------|
| Current source of truth | `SPEC.md` (project root) | Always `SPEC.md` |
| Version snapshot | `version_history/v{new}/SPEC_v{new}_{date}.md` | Version = the spec version represented by that folder |
| Audit / review report | `version_history/v{new}/MPAC_v{old}_Audit_Report.md` | Version = spec being reviewed |
| Update record | `version_history/v{new}/MPAC_v{new}_Update_Record.md` | Version = new spec version |
| This index | `version_history/CHANGELOG.md` | Always `CHANGELOG.md` |
