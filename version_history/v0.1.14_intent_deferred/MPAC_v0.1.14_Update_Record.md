# MPAC v0.1.14 Update Record — INTENT_DEFERRED

**Date:** 2026-04-28
**Previous version:** v0.1.13
**Scope:** New optional message type — `INTENT_DEFERRED` — a non-claiming "yield" signal that lets a participant record *"I saw an active intent on this scope and chose to step back"* without announcing a competing intent of its own.

---

## Motivation

Through v0.1.13, a participant who detected (via overlap query or visual inspection) that another participant was already working on a scope had two options:

1. **Announce anyway** — creates a `CONFLICT_REPORT`, escalates to governance, generates churn for what is fundamentally a polite deference, not a real disagreement.
2. **Stay silent** — no record exists. The human owner cannot see *"Bob noticed Alice editing X and stepped back."* From the dashboard, Bob looks idle and uncoordinated.

The protocol provided no first-class way to express *"I am yielding to you"*. Implementations were forced to either pollute the conflict surface with non-conflicts or hide cooperative behavior entirely.

`INTENT_DEFERRED` fills that gap: a one-sided, non-claiming UX signal. It is **distinct from** `INTENT_ANNOUNCE` (no scope claim, no overlap detection) and **distinct from** `CONFLICT_REPORT` (no opposing pair). Sibling participants render a "yielded" chip in their conflict surface so the human owner sees the social fact: *"Bob saw Alice editing X and stepped back."*

---

## Changes

### New Message Type — `INTENT_DEFERRED`

A single `message_type` carries two payload shapes: an **active form** (sent by the deferring participant; coordinator re-broadcasts with `principal_id` and `expires_at` filled in) and a **resolution form** (emitted only by the coordinator when the deferral is cleared).

#### Active Form

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `deferral_id` | string | R | Sender-chosen unique id |
| `principal_id` | string | C | Filled by coordinator on re-broadcast; clients SHOULD omit |
| `scope` | Scope | R | Scope the sender was about to claim before yielding |
| `reason` | string | O | Free-form rationale (e.g. `"yielded_to_active_editor"`) |
| `observed_intent_ids` | string[] | O | Intent ids the sender saw on the scope |
| `observed_principals` | string[] | O | Principal ids the sender saw working on the scope |
| `ttl_sec` | number | O | TTL in seconds; default `60` |
| `expires_at` | string | C | ISO timestamp; coordinator MUST fill on re-broadcast based on `received_at + ttl_sec` |

#### Resolution Form

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `deferral_id` | string | R | Deferral being resolved |
| `principal_id` | string | R | Original deferring principal |
| `status` | string | R | `"resolved"` or `"expired"` |
| `reason` | string | O | Free-form, e.g. `"observed_intents_terminated"` / `"principal_announced"` / `"ttl"` |

#### Coordinator Three-Axis Cleanup Rule

The coordinator MUST clear a deferral and emit a `status: resolved` follow-up when ANY of the following becomes true:

1. All intents listed in `observed_intent_ids` reach a terminal state.
2. The same `principal_id` subsequently sends an `INTENT_ANNOUNCE` (the principal is no longer yielding).
3. The terminating intent's `principal_id` appears in `observed_principals`, **OR** appears in `observed_intent_ids` (defense-in-depth match for clients that conflated the two fields — common when the request was built from a `check_overlap` response that did not surface `intent_id`).

When wall-clock time exceeds `expires_at`, the coordinator MUST emit a `status: expired` follow-up. Default TTL when sender omits `ttl_sec`: 60 seconds.

#### Non-Properties (What `INTENT_DEFERRED` Is NOT)

- **Not an intent.** No state machine entry. Does not appear in `granted_roles`/intent registries.
- **Does not lock scope.** MUST NOT trigger `CONFLICT_REPORT`. MUST NOT participate in overlap detection.
- **Does not block the same principal's subsequent `INTENT_ANNOUNCE`.** Once the principal announces, their active deferrals are cleared (rule 2 above).

#### Compliance Profile

`INTENT_DEFERRED` is **not** in the MUST set of any compliance profile (Core / Governance / Semantic). It is an optional UX-affordance message. Implementations that surface a "yielded" hint in their UI SHOULD support it.

---

### Version Bump

All `0.1.13` version strings updated to `0.1.14`:

- `SPEC.md` (title, body, all example envelopes and `protocol_version` fields)
- `MPAC_Developer_Reference.md` (title)

The historical retrospective sentence in SPEC.md §28 (`"addressed across v0.1.1–v0.1.13"`) is intentionally **not** extended to v0.1.14, because v0.1.14 adds a new feature rather than closing a previously identified gap.

---

## Reference Implementation

The Python reference package `mpac` shipped INTENT_DEFERRED support in PyPI version **0.2.5** (with a follow-up cleanup-correctness fix in **0.2.6**). The package version is decoupled from the protocol version — these are separate identifiers maintained in their respective version registries.

| Identifier | Version | Notes |
|---|---|---|
| MPAC protocol | `0.1.14` | Authoritative — declared in `SPEC.md` §1 and in `SESSION_INFO.protocol_version` |
| `mpac` PyPI package | `≥ 0.2.5` | First version implementing INTENT_DEFERRED. `0.2.6` added defense-in-depth match (rule 3 above) for clients that conflated `observed_principals` and `observed_intent_ids` |
| `mpac-mcp` PyPI package | `≥ 0.2.9` | Exposes `defer_intent` tool for MCP clients |

Going forward, SPEC.md will refer only to protocol versions (e.g. `(v0.1.14+)`). Implementation availability is recorded here in the Update Record, not in the spec body.

---

## Compatibility

This change is **strictly additive**:

- No existing message type is modified.
- No existing field is changed or removed.
- No existing state machine transition is altered.
- Implementations that do not support `INTENT_DEFERRED` MAY safely ignore it (it is not in any compliance MUST set).
- A v0.1.13 participant joining a v0.1.14 session will continue to function — it simply will not emit or react to deferrals.

A v0.1.14 participant joining a v0.1.13 session SHOULD expect that the coordinator will not understand `INTENT_DEFERRED` and SHOULD either fall back to silent yielding or detect the protocol version mismatch via `SESSION_INFO.protocol_version`.

---

## Sections Affected

**SPEC.md:**
- §1 (version declaration)
- §13 (core message type list)
- §13.1 (`INTENT_DEFERRED` payload schema — both forms)
- §15.5.1 (new section — full semantics)
- §28 (closing summary)

**MPAC_Developer_Reference.md:**
- Title (version bump)
- §2 (message type roster — added row, footnote on optional ⚪ marker)
- §3.7.1 (new payload section)
- §4 (entity diagram — INTENT layer extended)
- §4.1 (cross-reference table — 3 new rows)
- §5.1 (intent state machine — clarifying note that deferrals do not enter it)
- §5.4 (cross-state-machine cascade — deferral cleanup arrows added)
- §6.4 (compliance profile — footnote)
- §6.9 (new — Deferral Status enum registry)
- §8.15 (new — v0.1.14 protocol semantics summary)
- §9 (implementation checklist — new "v0.1.14 INTENT_DEFERRED" group)
