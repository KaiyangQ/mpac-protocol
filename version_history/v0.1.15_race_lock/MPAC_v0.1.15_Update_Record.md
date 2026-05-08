# MPAC v0.1.15 Update Record — Cross-Principal Scope Race Lock

**Date:** 2026-04-29
**Previous version:** v0.1.14
**Scope:** New normative rule for `INTENT_ANNOUNCE` arrival semantics — a
cross-principal same-resource race-lock that hard-rejects late
announcements with a new `STALE_INTENT` error code, plus a clarification
that `INTENT_DEFERRED` fast-resolution must fire at deferral arrival
time when the observed targets are already terminal.

---

## Motivation

Through v0.1.14 the protocol treated `INTENT_ANNOUNCE` as **always
accepted** (subject only to `SCOPE_FROZEN` rejections from active conflict
freezes and `INTENT_BACKOFF` rejections after a prior conflict-driven
`RESOLUTION`). When two participants raced to claim the same resource
"at the same time," both `INTENT_ANNOUNCE` succeeded; the coordinator
then fired an advisory `CONFLICT_REPORT(category="scope_overlap")` after
the fact.

Field testing on 2026-04-29 (case 5 + race scenarios — see
`daily_reports/2026-04-29.md`) showed this advisory model breaks down
when the agents are LLM-driven and synchronous-blocking: by the time
`CONFLICT_REPORT` is broadcast, both agents are already executing their
write step, with no flow to reconsider. Both writes land on the same
file; the second overwrites the first. The user's mental model — "if
you saw a conflict, why did you both proceed?" — is violated.

The fix mirrors `git`'s split between **merge conflicts** (must resolve
before `push`) and **semantic conflicts** (warn, defer to type checker /
CI / reviewer):

- `scope_overlap` (same resource) → **hard reject** at announce time.
  Almost always a real conflict.
- `dependency_breakage` (cross-file dependency) → **remain advisory**.
  Often backward-compatible; auto-rejecting every dependent whenever
  a hub file is touched would block legitimate parallel work.

The hard-reject path needs a new error code with semantics distinct
from the two existing `INTENT_ANNOUNCE` rejection codes:

- `SCOPE_FROZEN` (Section 18.6.2): scope is frozen due to **conflict
  resolution timeout**. Indefinite until the conflict resolves.
- `INTENT_BACKOFF` (Section 15.3.1): participant is in **livelock
  prevention backoff** after their own intent was just rejected by a
  RESOLUTION. Time-bounded; specific to the rejected participant.
- `STALE_INTENT` (NEW, Section 15.3.2): scope is held by an active
  intent owned by **another principal**. Bound to the holding intent's
  lifecycle.

Conflating any two of these would lose normative meaning — the client's
recovery action differs (wait-for-unfreeze vs. exponential-retry vs.
yield-and-watch).

---

## Changes

### 1. New `PROTOCOL_ERROR` code: `STALE_INTENT`

Added to the recommended `error_code` list in Section 22.1 (`PROTOCOL_ERROR`).

> `STALE_INTENT`: an `INTENT_ANNOUNCE` was rejected because at least one
> resource in its scope already overlaps the resources of an active intent
> owned by a **different** principal (Section 15.3.2). The lock pre-empts
> the advisory `CONFLICT_REPORT` path for would-be `scope_overlap`
> collisions; cross-file `dependency_breakage` candidates remain advisory.

### 2. New normative section: §15.3.2 Cross-Principal Scope Race Lock

A complete normative section was added after §15.3.1 (Intent Re-Announce
Backoff) and before §15.4 (`INTENT_UPDATE`). Key normative bullets:

- **Coordinator MUST reject** with `STALE_INTENT` when an `INTENT_ANNOUNCE`'s
  `scope.resources` directly overlaps an active intent owned by a
  different principal.
- **Coordinator MUST NOT register** the rejected intent in the intent table.
- **Coordinator MUST NOT generate** a `CONFLICT_REPORT` for this collision
  (the race lock pre-empts the advisory path).
- **Rejection's `description` SHOULD identify** both the colliding
  `intent_id` and the holding `principal_id`.

The section also defines:

- **Same-vs-cross-file scope** of the rule (only same-resource overlap;
  cross-file `dependency_breakage` remains advisory) and the rationale
  (backward-compat dependency edits are common; killing collaboration
  on hub modules is unacceptable).
- **Race lock vs. intent backoff** disambiguation (independent
  mechanisms).
- **Same-principal exemption** — re-announcement by the same principal
  on the same scope is NOT race-locked; it goes through the auto-supersede
  path (treats prior intent as orphan from a crashed retry).
- **Lock release** — bound to the holding intent's lifecycle. On terminal
  transition (withdraw / TTL expiry / supersede / transfer), the lock
  releases. Coordinator MUST NOT retain race-lock state beyond the
  holding intent's lifetime.
- **Informative client recovery flow** — extract colliding intent_id from
  rejection description, send `INTENT_DEFERRED` with that id in
  `observed_intent_ids`, surface to principal, optionally retry on
  observed-intent termination.

### 3. §15.5.1 (`INTENT_DEFERRED`) clarification: fast-resolve at arrival

The cleanup-rule list was supplemented with an explicit "evaluate-at-arrival"
requirement, paired with the existing "evaluate-on-transition" semantics
that were already implicit in v0.1.14.

The new normative paragraph:

> The coordinator MUST evaluate these conditions both:
> (a) on every relevant intent-state transition that could change the
>     truth value (the standard reactive cleanup path); AND
> (b) at the moment the deferral is first registered — if any condition
>     is already true at arrival time (for example, the observed intent
>     withdrew before the deferral arrived), the coordinator MUST emit
>     `status: resolved` in the same response that delivers the active
>     broadcast, rather than wait for a future state transition that
>     will never come.
>
> Without (b), a slow-yielding agent whose deferral arrives after its
> observed peer has already terminated would leave a stranded entry in
> the deferral table, and the corresponding UX hint would persist on
> sibling clients for the full TTL window despite the underlying
> coordination already being moot.

This clarification was prompted by the same 2026-04-29 testing: a
deferring Claude with ~14s call latency yielded after the observed
peer had already withdrawn (~12s task), leaving the yield-chip
hanging on sibling browsers for the full 60-second TTL.

The original three-axis cleanup rules (1) all observed intents terminal,
(2) same principal later announces, (3) defense-in-depth principal-in-
intent-ids match — are unchanged. The clarification only adds *when*
those conditions must be evaluated.

---

## Out of Scope (Intentionally NOT in v0.1.15)

The 2026-04-29 testing surfaced a deeper architectural limitation: the
relay subprocess hosting `claude -p` does not subscribe to coordinator
broadcasts. The Claude process only sees the result of MCP tool calls
it explicitly invokes within a turn — it cannot react to inbound
`CONFLICT_REPORT` / `INTENT_WITHDRAW` envelopes that arrive after its
last tool call but before its reply.

Consequences:

- The "first to announce" participant in a same-tick collision never
  learns it collided — its own `announce_intent` response was empty
  (the colliding peer hadn't announced yet); the subsequent
  `CONFLICT_REPORT` broadcast reaches the relay process but is not
  forwarded into the running `claude -p` subprocess.
- Reply text uses stale `check_overlap` snapshots ("Alice is editing X")
  even if Alice has finished by reply time.

A reactive-event-subscription mechanism would close this gap (the
client tells the coordinator "push these envelope types into my
subprocess as new tool-call observations"). It is a substantial
architectural addition — relay daemon design, subprocess IPC, MCP
extension semantics — and is deferred to v0.2.x or later. v0.1.15
records the limitation in scope language; future versions will
address it normatively.

---

## Compatibility

- **Backward-compatible for clients that always succeeded under v0.1.14**:
  if an old client never raced into a same-resource collision, no
  observable change.
- **Behavior change for clients that previously relied on advisory
  `scope_overlap`**: those clients now see a `PROTOCOL_ERROR(STALE_INTENT)`
  on the loser's `INTENT_ANNOUNCE` instead of a fired `CONFLICT_REPORT`
  for both sides. Recommended client adaptation: handle `STALE_INTENT`
  as a structured signal, send `INTENT_DEFERRED`, and surface the
  situation to the principal.
- **No change** to error codes, message types, payload schemas, or
  state-machine transitions for intents/operations/conflicts beyond
  the `STALE_INTENT` error code addition and the §15.3.2 rule.

A v0.1.14 coordinator paired with a v0.1.15 client: client may issue
`INTENT_ANNOUNCE` that v0.1.14 coordinator accepts where v0.1.15 would
reject. No protocol error; the client just doesn't get the new safety
guarantee.

A v0.1.15 coordinator paired with a v0.1.14 client: client may receive
`PROTOCOL_ERROR(STALE_INTENT)` where it doesn't recognize the error
code. Per §22.1's general error semantics, unknown error codes are
informational; the client SHOULD treat them as "intent rejected" and
back off accordingly. v0.1.14 clients that hardcode the old error code
list will simply log "unknown error code STALE_INTENT" but not crash.

---

## Reference Implementation Status

- **`mpac` Python package** v0.2.8 ships the race-lock rule
  (`coordinator._handle_intent_announce` cross-principal check) and
  `ErrorCode.STALE_INTENT`. v0.2.7 ships the deferral fast-resolve at
  arrival.
- **`mpac-mcp` Python package** v0.2.12 ships the client-side recovery:
  `relay_tools.announce_intent` translates the server's HTTP 409
  (`STALE_INTENT`) into a structured `{"rejected": true, ...}` dict
  rather than raising, and the relay system prompt has a normative
  branch instructing Claude to call `defer_intent` and surface the
  situation to the user when the announce is rejected.
- **TypeScript reference implementation** has not been updated for
  v0.1.15 yet; the `STALE_INTENT` rule and §15.3.2 race-lock semantics
  are still TODO there.

Test coverage in `mpac-package/tests/`:

- `test_self_conflict_supersede.py::test_cross_principal_same_file_announce_rejected_with_stale_intent`
- `test_self_conflict_supersede.py::test_orphan_after_retry_does_not_block_fresh_announce_with_third_party`
- `test_self_conflict_supersede.py::test_race_lock_does_not_block_dependency_breakage_announce`
- `test_self_conflict_supersede.py::test_race_lock_does_not_block_disjoint_files`
- `test_self_conflict_supersede.py::test_race_lock_allows_same_principal_retry`
- `test_self_conflict_supersede.py::test_race_lock_releases_on_first_intent_withdraw`
- `test_intent_deferred.py::test_deferral_resolves_immediately_when_observed_intent_already_terminal`
- `test_intent_deferred.py::test_deferral_with_some_observed_terminated_does_not_immediately_resolve`
- `test_intent_deferred.py::test_deferral_with_no_observed_targets_does_not_auto_resolve`

97/97 mpac suite pass on the v0.1.15 implementation.

---

## Document Trail

- Spec snapshot: `version_history/v0.1.15_race_lock/SPEC_v0.1.15_2026-04-29.md`
- Daily report: `daily_reports/2026-04-29.md` (events 6–10 cover the
  motivation, design discussion with the project owner, implementation,
  and the field-testing that exposed the limitation now recorded as
  out-of-scope)
- Test scenarios: `docs/testing/conflict/CONFLICT_TEST_SCENARIOS.md` 场景 7–9 (race
  detection scenarios validating the new behavior end-to-end)
