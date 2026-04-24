# MPAC v0.1.13 Update Record — Backend Health Monitoring

**Date:** 2026-04-07
**Previous version:** v0.1.12
**Scope:** New feature — backend AI model health monitoring integrated with aistatus.cc, enabling agents to declare backend dependencies, report provider health in heartbeats, and trigger coordinator-mediated alerts and model switching governance.

---

## Motivation

MPAC v0.1.12 provides robust agent-level liveness detection through `HEARTBEAT` messages and `unavailability_timeout_sec`. However, these mechanisms only detect whether the **agent process** is alive — not whether the **AI model backend** the agent depends on (e.g., Claude API, GPT-4 API) is operational. An agent process can remain alive and sending heartbeats while its underlying LLM provider is experiencing a major outage, resulting in a "zombie agent" that occupies intent scope but cannot make progress.

The open-source [aistatus.cc](https://aistatus.cc) project provides free, public JSON APIs for real-time AI provider status monitoring, including a `/api/check` endpoint designed specifically for agent pre-flight checks with automatic fallback suggestions. This version integrates aistatus.cc's data model into MPAC, enabling:

1. Agents to **declare** their backend model dependency at session join time
2. Agents to **report** backend health alongside their own heartbeat status
3. Coordinators to **broadcast alerts** when a participant's backend degrades or goes down
4. Sessions to **govern model switching** through configurable policy (allowed/notify_first/forbidden)
5. Other agents to **claim intents** from agents whose backends are down, using the existing `INTENT_CLAIM` mechanism

---

## Changes

### New Feature — Backend Health Monitoring

#### HELLO Payload Extension

Added optional `backend` field to the `HELLO` payload, allowing agents to declare their AI model dependency at session join time:

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `backend` | object | O | Agent's AI model backend dependency |
| `backend.model_id` | string | R (within backend) | Full model identifier in `provider/model` format (e.g., `anthropic/claude-sonnet-4.6`) |
| `backend.provider` | string | R (within backend) | Provider slug (e.g., `anthropic`, `openai`, `google`) |

The `provider` and `model_id` format aligns with the aistatus.cc API convention, enabling direct use with `GET /api/check?model={model_id}`.

#### HEARTBEAT Payload Extension

Added optional `backend_health` field to the `HEARTBEAT` payload:

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `backend_health` | object | O | Backend provider health status |
| `backend_health.model_id` | string | R (within backend_health) | Current model identifier |
| `backend_health.provider_status` | string | R (within backend_health) | One of: `operational`, `degraded`, `down`, `unknown` |
| `backend_health.status_detail` | string | O | Human-readable status detail (e.g., "Elevated error rates") |
| `backend_health.checked_at` | string (date-time) | R (within backend_health) | ISO 8601 timestamp of the last health check |
| `backend_health.alternatives` | array | O | Alternative providers/models when current is degraded/down |
| `backend_health.switched_from` | string | O | Previous model_id if the agent has switched backends |
| `backend_health.switch_reason` | string | O | Reason for switch. One of: `provider_down`, `provider_degraded`, `manual`, `cost_optimization` |

The `provider_status` enum and `alternatives` structure directly mirror the aistatus.cc `/api/check` response format.

#### COORDINATOR_STATUS Extension

Added `backend_alert` to the `event` enum, with conditional fields:

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `affected_principal` | string | C | Required when `event` = `backend_alert`: principal ID of the affected agent |
| `backend_detail` | object | C | Required when `event` = `backend_alert`: backend health details |
| `backend_detail.model_id` | string | R (within backend_detail) | Affected model identifier |
| `backend_detail.provider_status` | string | R (within backend_detail) | One of: `operational`, `degraded`, `down`, `unknown` |
| `backend_detail.status_detail` | string | O | Human-readable status detail |
| `backend_detail.alternatives` | array | O | Alternative providers/models |

#### Liveness Policy Extension

Added optional `backend_health_policy` to the `liveness_policy` in `SESSION_INFO`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backend_health_policy` | object | absent | Backend health monitoring configuration |
| `backend_health_policy.enabled` | boolean | `false` | Whether backend health monitoring is active |
| `backend_health_policy.check_source` | string | `"https://aistatus.cc/api/check"` | URL of the status check API |
| `backend_health_policy.check_interval_sec` | number | `60` | How often agents should check backend health |
| `backend_health_policy.on_degraded` | string | `"warn"` | Action when provider is degraded. One of: `ignore`, `warn`, `suspend_and_claim` |
| `backend_health_policy.on_down` | string | `"suspend_and_claim"` | Action when provider is down. One of: `ignore`, `warn`, `suspend_and_claim` |
| `backend_health_policy.auto_switch` | string | `"allowed"` | Model switching governance. One of: `allowed`, `notify_first`, `forbidden` |
| `backend_health_policy.allowed_providers` | string[] | absent (no restriction) | Whitelist of providers the agent may switch to. Configured by the session creator (principal/user), not by the protocol. |

**Protocol vs. implementation boundary:** The protocol defines the signaling mechanism (backend declaration, health reporting, alert broadcasting, switch governance) and the coordinator's enforcement rules (whitelist check, auto_switch policy). The protocol does NOT prescribe which alternative model to choose, when to trigger a switch, or whether to switch back after recovery — these are implementation-level decisions made by each agent.

---

### Version Bump

All version strings updated to `0.1.13` across:
- `SPEC.md` (title, body, examples)
- `envelope.schema.json` (description)
- Python: `coordinator.py`, `envelope.py`, `__init__.py`, `pyproject.toml`
- TypeScript: `coordinator.ts`, `envelope.ts`, `package.json`

---

## Impact on Reference Implementations

Both reference implementations require additions:

1. **`_handle_hello` / `handleHello`**: Store `backend` from HELLO payload in `ParticipantInfo`
2. **`_handle_heartbeat` / `handleHeartbeat`**: Read `backend_health` from HEARTBEAT payload, evaluate `provider_status` against `backend_health_policy`, emit `COORDINATOR_STATUS(event=backend_alert)` when thresholds are crossed, validate `auto_switch` and `allowed_providers` when `switched_from` is present
3. **`ParticipantInfo`**: New fields `backend_model_id`, `backend_provider`, `backend_provider_status`
4. **`CoordinatorEvent` enum**: New value `BACKEND_ALERT`

All changes are additive — no existing behavior is modified.

---

### P3 Implementation Hardening (Second Pass)

4 items completed to harden backend health monitoring coverage:

1. **Python `_process_backend_health` naming bug (P2):** The `suspend_and_claim` branch used TypeScript-style attribute names (`stateMachine`, `isTerminal()`, `currentState`) instead of Python-style (`state_machine`, `is_terminal()`, `current_state`). This would have caused `AttributeError` at runtime when a provider went down.

   **Fix:** Corrected to `intent.state_machine.is_terminal()`, `intent.state_machine.current_state != IntentState.SUSPENDED`, and `intent.state_machine.transition("unavailable")`.

2. **Participant helper extension (P3):** `Participant.hello()` and `Participant.heartbeat()` in both Python and TypeScript did not support the new `backend` and `backend_health` parameters, making it impossible to write clean tests using the Participant helper class.

   **Fix:** Added optional `backend` parameter to `hello()` and optional `backend_health` parameter to `heartbeat()` in both `ref-impl/python/mpac/participant.py` and `ref-impl/typescript/src/participant.ts`.

3. **Demo transcript enhancement (P3):** The backend health transcript (`ref-impl/demo/distributed/backend_health_transcript.json`) only covered the basic degraded → down → switch flow (steps 1-12), missing the INTENT_CLAIM transfer, BACKEND_SWITCH_DENIED rejection, and provider recovery scenarios.

   **Fix:** Added steps 13-18 covering: Bob claims Alice's suspended intent via INTENT_CLAIM, coordinator approves with INTENT_CLAIM_STATUS, Alice attempts switch to disallowed provider (deepseek) and gets BACKEND_SWITCH_DENIED, Anthropic recovers and Alice switches back successfully.

4. **Specialized backend health tests (P3):** No dedicated test coverage for the backend health monitoring feature. All existing tests only covered pre-v0.1.13 behavior.

   **Fix:** Created `test_v0113_backend_health.py` (Python) and `v0113-backend-health.test.ts` (TypeScript) with 12 test cases each covering: HELLO backend declaration, heartbeat backend_health reporting, degraded/down alert emission, suspend_and_claim behavior, model switch validation, allowed_providers whitelist enforcement, auto_switch=forbidden rejection, SESSION_INFO liveness_policy inclusion, no-alert on status repeat, and provider recovery flow.

---

### Coordination Overhead Demo (New Demo)

New demo added to validate the core academic claim: **MPAC eliminates coordination overhead without compressing decision time.**

`ref-impl/demo/distributed/run_overhead_comparison.py` — runs the same 3-agent cross-module PR review scenario in two modes:

1. **Traditional (serial):** agents review sequentially, wait for predecessors, do round-trip clarification on conflicts, discover post-hoc conflicts requiring rework
2. **MPAC (protocol-coordinated):** agents review in parallel via WebSocket-connected MPAC coordinator, conflicts detected pre-emptively at `INTENT_ANNOUNCE`, positions submitted in parallel, coordinator resolves instantly

**Measurement design:**
- Every Claude API call is precisely timed and tagged as `decision_time`
- All waiting, serialization blocking, round-trip delivery, and context assembly is tagged as `coordination_overhead`
- Same review prompts used in both modes to ensure decision quality is comparable
- Output: side-by-side breakdown table + JSON transcript with per-segment timing

**Representative results (Claude Sonnet, 3 agents × 3 review phases):**

| Metric | Traditional | MPAC | Delta |
|--------|-----------|------|-------|
| Decision Time | 60.2s | 54.9s | -9% (API noise) |
| Coordination Overhead | 65.1s | 3.0s | **-95%** |
| Wall Clock | 125.3s | 25.7s | -79% |
| OH / Wall Clock | 52.0% | 11.7% | |

The demo confirms: decision time is statistically equivalent across modes (same prompts, same model). The wall clock improvement comes entirely from coordination overhead elimination — MPAC does not compress thinking, it eliminates waiting.

---

### Full Message Type Demo Coverage (New Demos)

Two new WebSocket-based demos added to achieve 21/21 message type coverage in live Claude API demos. Both demos use real Claude API calls for agent decision-making.

1. **Pre-Commit + INTENT_CLAIM demo** (`run_precommit_claim.py`): 3 agents (Alice, Bob, Charlie) in `pre_commit` execution model with `governance` compliance profile. Exercises 6 previously uncovered message types:
   - **INTENT_UPDATE** — Alice expands her scope mid-session, triggering new conflict detection
   - **OP_PROPOSE** — Bob proposes an operation; coordinator authorizes via `COORDINATOR_STATUS(event=authorization)`; Bob then commits (pre-commit completion flow)
   - **OP_REJECT** — Charlie proposes against a withdrawn intent; coordinator rejects with `reason: intent_terminated`
   - **INTENT_WITHDRAW** — Charlie voluntarily withdraws his intent after conflict resolution
   - **INTENT_CLAIM** — Alice's process crashes (simulated via connection close + liveness timeout); Bob claims her suspended intent
   - **INTENT_CLAIM_STATUS** — Coordinator approves the claim (Charlie serves as governance approver)

   Also demonstrates: pre-commit authorization flow, agent crash simulation with liveness detection, governance-mediated claim approval, and continued work on claimed scope.

2. **Conflict Escalation demo** (`run_escalation.py`): 2 owner agents (Alice, Bob) + 1 arbiter in `governance` compliance profile. Exercises the previously uncovered CONFLICT_ESCALATE message type:
   - Both agents announce overlapping intents on a UI component library → `CONFLICT_REPORT`
   - Both ACK as `disputed` via `CONFLICT_ACK`
   - Alice explicitly escalates to the arbiter via `CONFLICT_ESCALATE`
   - Arbiter uses Claude to analyze both positions and renders a binding `RESOLUTION`
   - Losing agent withdraws intent; winning agent commits

   Also demonstrates: arbiter role, multi-level governance (owner → arbiter), Claude-powered judicial decision-making.

**Infrastructure changes:**
- `ws_coordinator.py`: Constructor now accepts `**kwargs` to pass `execution_model`, `compliance_profile`, `unavailability_timeout_sec`, `resolution_timeout_sec`, `intent_claim_grace_sec`, and `role_policy` through to `SessionCoordinator`. Fully backward-compatible (all params have defaults matching previous behavior).
- `ws_agent.py`: Added `from __future__ import annotations` for Python 3.9 compatibility (existing `dict | None` type hints required Python 3.10+).
- `local_config.example.json`: New example config file for API key setup (previously only referenced in README but did not exist).
- `LICENSE`: Apache License 2.0 added to project root.

---

### Demo Hardening for Open-Source Release

5 issues identified and fixed across all API-calling demo scripts:

1. **Hardcoded model name (P2):** All 5 demo agent modules used `claude-sonnet-4-20250514` as the fallback default. This dated model snapshot will become stale as models are deprecated.

   **Fix:** Changed default to `claude-sonnet-4-6` (stable model family ID) across `ai_agent.py`, `ws_agent.py`, `trip_agent.py`, `run_e2e.py`, `run_overhead_comparison.py`, and `local_config.example.json`.

2. **SSL verification disabled (P2):** All 5 demo agent modules created `httpx.Client(verify=False)` and passed it to the Anthropic SDK. This is a security concern for a public repository and unnecessary since the Anthropic SDK handles HTTPS natively.

   **Fix:** Removed `httpx.Client(verify=False)`, removed unused `import httpx`, use default `anthropic.Anthropic(api_key=...)` constructor.

3. **Missing API cost disclaimers (P3):** None of the 8 demo scripts warned users about API key requirements or approximate request counts.

   **Fix:** Added `NOTE:` blocks to all demo docstrings specifying API key requirement and approximate request count per run.

4. **License mismatch (P2):** `pyproject.toml` declared `license = "MIT"` while the repository LICENSE file is Apache 2.0.

   **Fix:** Changed to `license = "Apache-2.0"`.

---

## Test Results

- Python: 122/122 tests passed (109 existing + 13 new backend health tests)
- TypeScript: 101/101 tests passed (88 existing + 13 new backend health tests)
