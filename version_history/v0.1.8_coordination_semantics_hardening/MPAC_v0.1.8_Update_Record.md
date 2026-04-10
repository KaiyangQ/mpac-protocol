# MPAC v0.1.8 Update Record

**Date**: 2026-04-03
**Trigger**: Protocol review focused on coordination semantics — specifically, behaviors that fall squarely within MPAC's application-layer coordination scope (as opposed to distributed systems concerns that belong at the transport or infrastructure layer). Three gaps were identified: an undefined race condition in concurrent resolution, a livelock risk in intent re-announcement, and missing guidance for causal gap detection. All three are resolved in this version.

---

## Design Philosophy Note

This revision was guided by a deliberate scope calibration: MPAC is a coordination semantics protocol, not a distributed systems protocol. Issues like network partition handling, state reconciliation after coordinator failure, and replay protection across recovery boundaries are real concerns, but they belong to the transport layer, infrastructure layer, or deployment architecture — not to MPAC's specification. This version addresses only issues that are within MPAC's own responsibility: governance race conditions, coordination livelock, and causal context guidance.

---

## Changes Summary

### New Sections

| Section | Title | What it adds |
|---------|-------|-------------|
| 15.3.1 | Intent Re-Announce Backoff | Exponential backoff (default: 30s initial, 2× multiplier, 300s max) after conflict-driven intent rejection. Prevents livelock from repeated overlapping intent cycles. Coordinator MAY enforce via `INTENT_BACKOFF` error. Configurable via liveness policy. |
| 12.8 | Causal Gap Detection and Behavior | Defines participant behavior when watermark analysis reveals missed messages: SHOULD NOT issue causally-sensitive judgments, MAY signal `CAUSAL_GAP` to coordinator, MAY continue non-causally-sensitive activities. Best-effort detection, conservative behavior. |

### Modified Sections

| Section | Change |
|---------|--------|
| 1 | Version bumped to 0.1.8 |
| 18.4 | Added concurrent resolution rule: first-resolution-wins. Coordinator MUST accept only the first valid `RESOLUTION` for a given `conflict_id`, reject subsequent with `RESOLUTION_CONFLICT` error. Parallels `INTENT_CLAIM` first-claim-wins pattern (Section 14.7.4). |
| 22.1 | Three new error codes: `RESOLUTION_CONFLICT` (Section 18.4), `CAUSAL_GAP` (Section 12.8), `INTENT_BACKOFF` (Section 15.3.1) |
| 26 | Interoperability guidance items 21–22 added (intent backoff, causal gap behavior) |
| 29 | Updated addressed-gaps note to include v0.1.8 additions |
| 30 | Summary rewritten for v0.1.8: added livelock prevention, concurrent resolution handling, causal gap detection |

---

## Mapping from Review Findings to Changes

| Finding | Severity | Disposition | Resolution |
|---|---|---|---|
| Dual RESOLUTION race: two resolvers send RESOLUTION for same conflict, behavior undefined | Medium (coordination semantics gap) | **Fixed in v0.1.8** | Section 18.4: first-resolution-wins rule, `RESOLUTION_CONFLICT` error code |
| Intent re-announce livelock: agents cycle announce→conflict→reject→re-announce indefinitely | Medium (coordination semantics gap) | **Fixed in v0.1.8** | Section 15.3.1: exponential backoff, `INTENT_BACKOFF` error code, liveness policy config |
| Causal gap detection: watermark reveals missed messages but no guidance on what to do | Medium (causal context gap) | **Fixed in v0.1.8** | Section 12.8: conservative behavior rules, `CAUSAL_GAP` error code |

### Findings explicitly scoped out (not MPAC's responsibility)

| Finding | Reason for scoping out |
|---|---|
| Network partition vs coordinator crash indistinguishable | Transport/infrastructure layer concern. MPAC defines coordinator liveness detection (Section 8.1.1.1) but partition diagnosis is outside protocol scope. |
| Reconciliation protocol after STATE_DIVERGENCE | Governance-level decision by design. In multi-principal systems, automatic state merge may be more dangerous than surfacing divergence for human resolution. |
| Replay protection gap after coordinator recovery | Infrastructure layer concern. Snapshot contents and audit log durability are deployment decisions, not protocol semantics. |
| Scalability (O(n²) broadcast, scope overlap computation) | Optimization concern for future versions. Current spec targets 2–10 agent sessions. |
| Resource as first-class entity | Deferred to v0.2. Current string-level resource identification is sufficient for v0.1 use cases. |
| Cross-session coordination | Already in Section 29 future work. |

---

## Impact on Reference Implementations

### Python (ref-impl/python/)
- Coordinator must implement first-resolution-wins: track resolved conflict IDs, reject duplicate `RESOLUTION` with `RESOLUTION_CONFLICT`
- Optional: coordinator-side intent backoff enforcement (track rejected scopes per participant, enforce cooldown)
- Optional: causal gap detection in message processing (compare incoming Lamport values against expected sequence)

### TypeScript (ref-impl/typescript/)
- Same changes as Python implementation

### JSON Schema (ref-impl/schema/)
- No new message schemas needed (changes are behavioral, not structural)
- Updated: `envelope.schema.json` error code enum (add `RESOLUTION_CONFLICT`, `CAUSAL_GAP`, `INTENT_BACKOFF`)
