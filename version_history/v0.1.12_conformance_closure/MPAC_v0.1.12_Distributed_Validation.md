# MPAC v0.1.12 Distributed Validation Report

**Date:** 2026-04-05
**Protocol version:** v0.1.12
**Scope:** Real-world multi-agent deployment validation — WebSocket transport, concurrent Claude agents, live code modification, optimistic concurrency control

---

## Motivation

MPAC v0.1.12 had 109 Python tests and 88 TypeScript tests passing, covering all 21 message types, 3 state machines, 6 runtime enforcement rules, and adversarial edge cases. However, all tests were in-process unit tests using direct function calls. Three critical questions remained unanswered:

1. **Transport:** Can MPAC messages survive serialization, network transmission, and deserialization over a real transport layer?
2. **Concurrency:** Do multiple agents making concurrent decisions via real LLM APIs produce protocol-conformant behavior?
3. **Real work:** Can the protocol coordinate agents that actually read, modify, and commit real files — not just exchange mock messages?

This document records the validation of all three properties through a series of progressively more realistic integration tests, culminating in a full end-to-end demonstration with optimistic concurrency control.

---

## Validation Architecture

### Components Built

| Component | File | Purpose |
|-----------|------|---------|
| WebSocket Coordinator | `ref-impl/demo/distributed/ws_coordinator.py` | WebSocket server wrapping `SessionCoordinator`. Routes responses by message type: `SESSION_INFO` to sender, `CONFLICT_REPORT` to involved parties, `SESSION_CLOSE` broadcast. Runs heartbeat loop every 10s. |
| WebSocket Agent | `ref-impl/demo/distributed/ws_agent.py` | WebSocket client wrapping an AI agent. Claude API integration for `decide_intent`, `decide_on_conflict`, `plan_operation`. Async inbox queue with `drain_inbox`. Background listener task. |
| Distributed Demo | `ref-impl/demo/distributed/run_distributed.py` | Orchestrator for network-based multi-agent coordination. Phases 0–9 covering full session lifecycle with concurrent agent decision-making. |
| End-to-End Test | `ref-impl/demo/distributed/run_e2e.py` | Full validation: agents read real source files, generate fixes via Claude, write changes to disk, commit through MPAC with SHA-256 state_ref tracking and rebase on rejection. |
| Test Project | `ref-impl/demo/distributed/test_project/src/` | 5 Python source files with intentional security bugs (token expiry, timing side-channel, code duplication, weak hashing, N+1 queries). |

### Transport Design

The WebSocket transport binding maps MPAC envelopes 1:1 to JSON-over-WebSocket frames. The coordinator server routes responses based on message type:

- `SESSION_INFO` → unicast to sender (session join confirmation)
- `PROTOCOL_ERROR` → unicast to sender (error feedback)
- `CONFLICT_REPORT` → multicast to involved parties (`principal_a`, `principal_b`)
- `OP_REJECT`, `INTENT_CLAIM_STATUS` → unicast to sender
- `SESSION_CLOSE` → broadcast to all connected agents
- All other types → broadcast

Connection tracking uses a `principal_id → WebSocket` mapping established on HELLO.

---

## Phase 1: Network Transport Validation

**Goal:** Verify MPAC messages work over WebSocket transport.

**Setup:** Two AI agents (Alice: security engineer, Bob: code quality engineer) connect to a WebSocket coordinator. Each agent uses the Claude API to make independent decisions.

**Protocol flow validated:**

1. **HELLO handshake over WebSocket** — Both agents send HELLO concurrently; coordinator responds with SESSION_INFO containing participant count, execution model, and session config
2. **Concurrent INTENT_ANNOUNCE** — Both agents independently decide what to work on via Claude API (parallel LLM calls), then announce through the protocol
3. **CONFLICT_REPORT routing** — When scope overlap is detected (both agents target `auth.py`), coordinator multicasts the conflict report to exactly the two involved agents
4. **Conflict resolution with coordinator auto-resolve** — Agents express positions concurrently via Claude, coordinator resolves as authoritative party
5. **OP_COMMIT over WebSocket** — Agents commit operations with state references
6. **HEARTBEAT liveness** — Coordinator broadcasts status every 10 seconds; agents receive and handle heartbeats without disruption
7. **GOODBYE and session teardown** — Clean disconnect sequence

**Result:** All 9 phases completed successfully. Messages serialized, transmitted, deserialized, and processed correctly over WebSocket. No wire format issues.

### Discovery: Governance Authority Gap

During initial testing, a governance gap was discovered and fixed:

**Problem:** When Alice (role: `contributor`) tried to send a RESOLUTION message, the coordinator rejected it with `AUTHORIZATION_FAILED`. Per Section 18.4, only `owner`, `arbiter`, or the `escalate_to` target can resolve pre-escalation conflicts. In a pure agent-to-agent scenario with no human arbiter, no agent has the authority to resolve conflicts.

**Fix:** Added `resolve_as_coordinator()` method to `SessionCoordinator`. The coordinator itself always has resolution authority (confirmed by `_is_authorized_resolver` returning `True` for `coordinator_id`). After collecting both agents' positions, the coordinator auto-resolves with a rationale summarizing both perspectives. This required a secondary fix: the coordinator's self-sent messages were being blocked by the HELLO-first gate (the coordinator never sends itself a HELLO). Added `pid != self.coordinator_id` exemption to the gate condition.

**Impact:** This pattern — coordinator auto-resolve after collecting agent positions — is the recommended approach for pure-agent scenarios. It preserves the governance model (only authorized parties resolve conflicts) while enabling autonomous operation.

---

## Phase 2: Real Code Modification

**Goal:** Verify agents can coordinate actual file changes, not just exchange abstract messages.

**Test project:** 5 Python files with intentional security bugs:

| File | Bugs |
|------|------|
| `auth.py` | Token expiry not checked; timing side-channel in `authenticate()`; non-constant-time string comparison |
| `auth_middleware.py` | Duplicates all `auth.py` logic (dangerous); no expiry check; `require_role` always returns `True` |
| `models.py` | Incomplete User model; missing email uniqueness, timestamps, `is_active` |
| `utils/crypto.py` | Plain SHA-256 for passwords; `constant_time_compare()` exists but unused; `verify_password()` not constant-time |
| `api/users.py` | N+1 query pattern; no email uniqueness check in `create_user` |

**Protocol flow:**

1. Agents read all source files and decide intents via Claude
2. Both agents target `auth.py` → coordinator detects scope overlap → conflict resolved
3. Each agent asks Claude to generate real code fixes based on actual file content
4. Agents write fixed code to disk and commit through MPAC with real SHA-256 file hashes as `state_ref_before` / `state_ref_after`

**Result:** Agents successfully coordinated real code changes. However, this phase revealed a critical concurrency problem (see Phase 3).

### Discovery: Lost Write Problem

Both agents read `auth.py` at the same time (hash `d9d9f1ed...`), independently generated fixes, and both committed successfully. The second writer's changes silently overwrote the first writer's changes — a classic lost write.

**Root cause:** The coordinator stored `state_ref_before` and `state_ref_after` from OP_COMMIT but never validated them. The spec defines these fields (Section 16.3) but enforcement was left to the implementation. The coordinator's `_commit_operation_entry` persisted the refs without checking consistency.

---

## Phase 3: Optimistic Concurrency Control

**Goal:** Enforce `state_ref` consistency so stale commits are rejected and agents must rebase.

### Coordinator Changes

Three modifications to `SessionCoordinator`:

**1. State tracking (in `__init__`):**
```python
# Maps target (e.g. file path) -> latest known state_ref_after
self.target_state_refs: Dict[str, str] = {}
```

**2. Validation (in `_handle_op_commit`, post-commit path):**
```python
# After frozen-scope check, before committing:
if commit_target:
    state_ref_before = payload.get("state_ref_before")
    known_ref = self.target_state_refs.get(commit_target)
    if known_ref is not None and state_ref_before is not None:
        if state_ref_before != known_ref:
            return [self._make_protocol_error(
                "STALE_STATE_REF",
                envelope.message_id,
                f"Target '{commit_target}' state_ref_before does not match "
                f"latest known state; another agent has committed a newer "
                f"version — rebase required",
            )]
```

**3. Tracking update (in `_commit_operation_entry`):**
```python
# After successful commit:
if target and state_ref_after:
    self.target_state_refs[target] = state_ref_after
```

The same validation was added to `_handle_op_batch_commit` for each entry in the batch.

### Agent Rebase Logic

The E2E test script was updated with a commit-then-write model:

1. Agent reads file, computes `state_ref_before` hash
2. Agent asks Claude to generate fix
3. Agent computes `state_ref_after` hash from generated content (but does NOT write to disk yet)
4. Agent sends OP_COMMIT over WebSocket
5. **If accepted:** write to disk — commit is the source of truth
6. **If rejected (STALE_STATE_REF):** re-read the file (now containing the other agent's committed changes), ask Claude to regenerate the fix on top of those changes, retry up to 2 times

The key insight: **disk writes happen only after the coordinator accepts the commit.** This ensures the file on disk always reflects the last accepted commit, so rebase reads the correct base state.

### Validation Results

**Successful E2E run with optimistic concurrency control:**

```
Phase 6: Agents Execute REAL Code Changes

  Bob: Reading auth.py (d9d9f1ed5da96c8c)...
  Bob: Asking Claude to fix auth.py...
  Bob: Generated fix for auth.py (d9d9f1ed → c3af27d9)
  Bob: Wrote auth.py to disk (commit accepted)          ← First commit wins

  Alice: Generated fix for auth.py (d9d9f1ed → fb431567)
  Alice: ⚠ STALE_STATE_REF on auth.py!                  ← Second commit rejected
         Rebasing (attempt 1/2)...
  Alice: Reading auth.py (c3af27d9) (rebase attempt 1)  ← Re-reads Bob's version
  Alice: Asking Claude to fix auth.py...
  Alice: Generated fix for auth.py (c3af27d9 → 173aa17b)
  Alice: Wrote auth.py to disk (commit accepted)         ← Rebase succeeds
  Alice: ✓ Rebase successful for auth.py on attempt 1
```

**Summary metrics:**

| Metric | Value |
|--------|-------|
| Total messages exchanged | 17 |
| Conflicts detected & resolved | 1 |
| Stale commits rejected | 1 |
| Successful rebases | 1 |
| Files modified | 3 (auth.py, auth_middleware.py, utils/crypto.py) |
| Operations committed | 6 (3 per agent) |
| All operations have real SHA-256 refs | Yes (6/6) |

**Causal chain preserved:**

```
auth.py: original (d9d9f1ed)
    → Bob's fix (c3af27d9)     [commit accepted, first writer]
    → Alice's rebase (173aa17b) [commit accepted, builds on Bob's version]
```

No lost writes. Alice's final version contains both Bob's refactoring changes and her own security fixes layered on top.

---

## Regression

After all changes, the full unit test suite was run:

```
Python: 109/109 passed (0.07s)
```

Zero regressions. The `STALE_STATE_REF` error code and `target_state_refs` tracking are implementation-level additions that don't affect any existing protocol behavior — they only reject commits that would previously have been silently accepted with stale state.

---

## Findings Summary

### Confirmed Working

1. **WebSocket transport binding:** MPAC messages serialize, transmit, and deserialize correctly over JSON-over-WebSocket. Routing by message type works as designed.
2. **Concurrent LLM decision-making:** Two Claude agents making independent decisions via parallel API calls produce valid, protocol-conformant MPAC messages.
3. **Conflict detection on concurrent intents:** When agents independently choose overlapping files, the coordinator correctly detects scope overlap and emits CONFLICT_REPORT to both parties.
4. **Real file coordination:** Agents successfully read, modify, and commit real source files with SHA-256 state tracking through the full MPAC lifecycle.
5. **Optimistic concurrency control:** `state_ref_before` validation prevents lost writes; rejected agents rebase on the latest committed version and retry successfully.

### Gaps Discovered and Fixed

| Gap | Severity | Fix |
|-----|----------|-----|
| No governance authority path for pure-agent scenarios | P1 | Added `resolve_as_coordinator()` method |
| HELLO-first gate blocks coordinator self-messages | P1 | Added coordinator exemption to gate |
| `state_ref_before` not validated — lost writes possible | P1 | Added optimistic concurrency check in `_handle_op_commit` and `_handle_op_batch_commit` |
| Agents write to disk before commit acceptance | P2 | Changed to commit-then-write model |

### Protocol Observations

1. **Post-commit execution model works well for file-based coordination.** Agents apply changes and declare them via OP_COMMIT with real state refs. The coordinator validates causal consistency without needing to understand the changes themselves.

2. **The conflict resolution flow (detect → positions → resolve) maps naturally to LLM agents.** Each agent can explain its reasoning in natural language, and the coordinator (or a human arbiter) can make an informed decision.

3. **Rebase-on-rejection is a clean pattern.** When an agent's commit is rejected for stale state, it re-reads the current version (which now includes the other agent's changes), asks the LLM to regenerate its fix on the new base, and retries. This is analogous to `git rebase` in distributed version control.

4. **The `STALE_STATE_REF` error code should be formally added to the SPEC.md error code registry** in a future version. Currently it is implementation-level.

---

## Files Modified

### New files created:

| File | Description |
|------|-------------|
| `ref-impl/demo/distributed/ws_coordinator.py` | WebSocket coordinator server |
| `ref-impl/demo/distributed/ws_agent.py` | WebSocket AI agent client |
| `ref-impl/demo/distributed/run_distributed.py` | Network-based distributed demo |
| `ref-impl/demo/distributed/run_e2e.py` | End-to-end validation with real code modification |
| `ref-impl/demo/distributed/test_project/src/auth.py` | Test file: authentication with intentional bugs |
| `ref-impl/demo/distributed/test_project/src/auth_middleware.py` | Test file: middleware duplicating auth logic |
| `ref-impl/demo/distributed/test_project/src/models.py` | Test file: incomplete data model |
| `ref-impl/demo/distributed/test_project/src/utils/crypto.py` | Test file: weak crypto utilities |
| `ref-impl/demo/distributed/test_project/src/api/users.py` | Test file: API with query issues |

### Existing files modified:

| File | Change |
|------|--------|
| `ref-impl/python/mpac/coordinator.py` | Added `target_state_refs` tracking, `STALE_STATE_REF` validation in `_handle_op_commit` and `_handle_op_batch_commit`, state tracking update in `_commit_operation_entry`, `resolve_as_coordinator()` method, HELLO-first gate coordinator exemption |

---

## How to Run

### Prerequisites

```bash
pip install websockets httpx anthropic --break-system-packages
```

An Anthropic API key must be configured in `local_config.json` at the repository root.

### Run the end-to-end validation

```bash
cd ref-impl/demo/distributed
python run_e2e.py
```

This will:
1. Copy test project files to a working directory
2. Start a WebSocket coordinator on `localhost:8767`
3. Connect two AI agents (Alice and Bob) over WebSocket
4. Have them independently decide intents via Claude API
5. Detect and resolve scope conflicts
6. Generate and apply real code fixes with SHA-256 state tracking
7. Validate optimistic concurrency control (stale commits rejected, rebase succeeds)
8. Print a full summary with diffs, coordinator state, and concurrency metrics

Expected output includes `STALE_STATE_REF` rejections whenever both agents target the same file, followed by successful rebase.

### Run the distributed demo (without code modification)

```bash
cd ref-impl/demo/distributed
python run_distributed.py
```

This runs the same protocol flow but with mock operations (no real file I/O), useful for validating transport and conflict resolution without LLM code generation.
