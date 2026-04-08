# MPAC Demo Scripts

This directory contains demonstrations of the MPAC protocol in action. The demos are divided into two categories: **local interop tests** (no API key needed) and **live AI agent demos** (require an Anthropic API key).

---

## Prerequisites

```bash
pip install anthropic websockets   # for live demos
```

Copy the API key config:

```bash
cp local_config.example.json local_config.json
# Edit local_config.json and set your Anthropic API key
```

> **Do not commit `local_config.json`** — it is gitignored.

---

## Demo Overview

### Local Tests (No API Key)

| Script | What It Does |
|--------|-------------|
| `generate_messages_py.py` | Generates 7 MPAC messages from Python and processes them through the Python coordinator |
| `process_messages_ts.mjs` | TypeScript counterpart — processes Python messages through the TypeScript coordinator |
| `consume_ts_messages.py` | Validates TypeScript-generated messages against the Python coordinator |
| `run_interop.sh` | Orchestrates the full cross-language round-trip: Python generates → TS processes → TS generates → Python consumes |

These tests verify that the Python and TypeScript reference implementations produce identical wire formats with zero deviation.

---

### Live AI Agent Demos (Require API Key)

All demos below use the Claude API for agent decision-making. Each agent calls Claude independently — the agents do not share context or see each other's prompts. The MPAC coordinator mediates all coordination through protocol messages.

#### 1. Two-Agent Code Coordination (`run_ai_agents.py`)

```bash
cd ref-impl/demo
python run_ai_agents.py          # ~6 API calls
```

**Purpose:** Baseline demonstration of the core MPAC lifecycle.

**Scenario:** Two AI agents (Alice: security engineer, Bob: code quality engineer) independently decide what to work on in a shared Python web project. The coordinator detects when their scopes overlap and mediates the conflict.

**Protocol coverage:**
- `HELLO` / `SESSION_INFO` — session establishment
- `INTENT_ANNOUNCE` — each agent declares planned work
- `CONFLICT_REPORT` — coordinator detects scope overlap on `auth.py`
- `OP_COMMIT` / `OP_SUPERSEDE` — agents commit changes, one supersedes the other
- `COORDINATOR_STATUS` — coordinator heartbeat, state snapshot, fault recovery simulation
- `SESSION_CLOSE` — orderly shutdown with final Lamport clock

**What this proves:** Agents with independent LLM contexts can coordinate through structured protocol messages without sharing prompts or internal state.

---

#### 2. WebSocket Distributed Demo (`distributed/run_distributed.py`)

```bash
cd ref-impl/demo/distributed
python run_distributed.py        # ~6 API calls
```

**Purpose:** Validate that MPAC works over a real network transport, not just in-process.

**Scenario:** Same two-agent code coordination as above, but the coordinator runs as a WebSocket server and agents connect as separate async clients. Agents make Claude API calls concurrently.

**Protocol coverage:** Same as demo #1, but messages travel over WebSocket instead of in-memory function calls.

**What this proves:** MPAC is transport-independent — the same protocol semantics work identically over the network with concurrent agent decision-making.

---

#### 3. End-to-End Real File Coordination (`distributed/run_e2e.py`)

```bash
cd ref-impl/demo/distributed
python run_e2e.py                # ~6-10 API calls
```

**Purpose:** Prove that MPAC can coordinate actual file mutations with optimistic concurrency control.

**Scenario:** Two agents read real source files from `test_project/src/` (which contain intentional bugs), generate real code fixes via Claude, and commit changes via `OP_COMMIT` with SHA-256 state references. When a second agent's commit is based on a stale file version, the coordinator rejects it with `STALE_STATE_REF` and the agent rebases (re-reads the updated file, regenerates its fix, and retries).

**Protocol coverage:**
- `OP_COMMIT` with real `state_ref_before` / `state_ref_after` (SHA-256 hashes of actual file content)
- `PROTOCOL_ERROR: STALE_STATE_REF` — coordinator rejects commits based on outdated state
- Rebase-and-retry loop — agent updates its local state and retries

**What this proves:** MPAC's `state_ref` mechanism provides real optimistic concurrency control over shared files — not just message passing, but actual coordinated mutation with conflict detection at the data level.

---

#### 4. Family Trip Planning — 3 Agents (`distributed/run_family_trip.py`)

```bash
cd ref-impl/demo/distributed
python run_family_trip.py        # ~9-15 API calls
```

**Purpose:** Demonstrate MPAC in a non-engineering domain with 3 independent principals who have genuinely conflicting goals.

**Scenario:** A family of three plans a 5-day vacation. Dad's agent controls the budget and driving; Mom's agent handles accommodation and cultural experiences; Kid's agent advocates for theme parks. Each agent has different preferences and constraints (e.g., Mom is allergic to seafood — every meal must be verified). The agents negotiate through MPAC when their plans conflict (e.g., budget overruns, schedule overlaps).

**Protocol coverage:**
- `task_set` scope kind (non-file resources: `itinerary://day-1`, `budget://food`)
- `OP_BATCH_COMMIT` — multi-day itinerary committed as atomic batch
- `CONFLICT_ACK` with detailed negotiation positions
- Role-based authority — Dad is `owner` (can override), Kid is `contributor` (can propose but not override)

**What this proves:** MPAC is not limited to software engineering. The protocol's intent/scope/conflict model works for any domain where multiple independent principals need to coordinate over shared resources.

---

#### 5. Pre-Commit + Fault Recovery (`distributed/run_precommit_claim.py`)

```bash
cd ref-impl/demo/distributed
python run_precommit_claim.py    # ~6-10 API calls
```

**Purpose:** Exercise the Governance Profile's pre-commit execution model and the fault recovery mechanism (INTENT_CLAIM).

**Scenario:** Three agents (Alice, Bob, Charlie) refactor an API gateway in `pre_commit` mode. Operations must be proposed and explicitly authorized by the coordinator before execution. Mid-session, Alice's process crashes (simulated). The coordinator detects her unavailability via heartbeat timeout, suspends her intent, and Bob claims her abandoned work via `INTENT_CLAIM`.

**Protocol coverage (6 message types not covered by other demos):**
- `OP_PROPOSE` → `COORDINATOR_STATUS(event=authorization)` → `OP_COMMIT` — the full pre-commit flow
- `OP_REJECT` — Charlie's proposal rejected because his intent was withdrawn
- `INTENT_UPDATE` — Alice expands her scope mid-session, triggering re-check
- `INTENT_WITHDRAW` — Charlie voluntarily withdraws after conflict resolution
- `INTENT_CLAIM` / `INTENT_CLAIM_STATUS` — Bob claims Alice's suspended intent; coordinator approves with governance sign-off

**What this proves:** MPAC's governance layer (pre-commit authorization, intent claiming) provides a safe recovery path when agents fail mid-task — work is not lost, it can be transferred to another agent through a structured protocol mechanism.

---

#### 6. Conflict Escalation to Arbiter (`distributed/run_escalation.py`)

```bash
cd ref-impl/demo/distributed
python run_escalation.py         # ~6-8 API calls
```

**Purpose:** Exercise the multi-level governance model — when owners cannot resolve a conflict, it escalates to a designated arbiter.

**Scenario:** Two owner agents (Alice, Bob) both want to redesign a UI navigation component but with incompatible approaches (mega-menu vs. hamburger menu). Both dispute the conflict. Alice escalates to a designated arbiter, who uses Claude to analyze both positions and renders a binding resolution.

**Protocol coverage:**
- `CONFLICT_ACK(ack_type=disputed)` — both parties dispute the conflict
- `CONFLICT_ESCALATE` — explicit escalation to arbiter
- `RESOLUTION` — arbiter's binding decision with structured outcome
- `INTENT_WITHDRAW` — losing agent withdraws after arbitration

**What this proves:** MPAC supports multi-level governance (owner → arbiter). When peer negotiation fails, conflicts can be escalated to a higher authority who renders a binding decision — similar to how real organizations handle disputes.

---

#### 7. Coordination Overhead Comparison (`distributed/run_overhead_comparison.py`)

```bash
cd ref-impl/demo/distributed
python run_overhead_comparison.py    # ~12 API calls (both modes)
python run_overhead_comparison.py --mode traditional
python run_overhead_comparison.py --mode mpac
```

**Purpose:** Empirically measure MPAC's coordination overhead versus traditional sequential workflows.

**Scenario:** The same 3-agent PR review task is run in two modes:
- **Traditional (serial):** agents review sequentially, wait for predecessors, discover conflicts post-hoc, require rework
- **MPAC (parallel):** agents review concurrently via WebSocket, conflicts detected pre-emptively at `INTENT_ANNOUNCE`, resolved instantly by coordinator

**Measurement:** Every Claude API call is precisely timed as `decision_time`; everything else (waiting, serialization, round-trips) is tagged as `coordination_overhead`. Same prompts in both modes ensure decision quality is comparable.

**What this proves:** MPAC does not compress thinking time — it eliminates the waiting time around it. Representative results show decision time is roughly equal (~9% variance from API noise), while coordination overhead drops by ~95%.

---

## Architecture

All live demos follow the same architecture:

```
┌─────────────┐     WebSocket      ┌──────────────┐
│  Agent (AI)  │ ◄──────────────► │  Coordinator  │
│  Claude API  │                   │  (MPAC core)  │
└─────────────┘                   └──────────────┘
       ×N agents                    single server

Each agent:
1. Connects to coordinator via WebSocket (or in-process for demo #1)
2. Sends HELLO → receives SESSION_INFO
3. Calls Claude API to decide what to work on
4. Sends INTENT_ANNOUNCE with its planned scope
5. Receives CONFLICT_REPORT if scopes overlap
6. Calls Claude API to negotiate / generate work product
7. Sends OP_COMMIT (or OP_PROPOSE in pre-commit mode)
8. Coordinator enforces ordering, conflict detection, and governance rules
```

The Claude API is used **only for agent decision-making** (what to work on, how to resolve conflicts, what code to generate). All coordination logic is handled by the MPAC protocol — the LLM never sees protocol messages directly.

---

## Transcripts

Each demo saves a full JSON transcript of all protocol messages exchanged. These transcripts are committed to the repository so you can inspect the protocol flow without running the demos:

| Transcript | Demo | Size |
|-----------|------|------|
| `ai_demo_transcript.json` | #1 Two-agent code coordination | 11 KB |
| `family_trip_transcript.json` | #4 Family trip planning | 30 KB |
| `backend_health_transcript.json` | Backend health monitoring scenario | 22 KB |
| `overhead_comparison_results.json` | #7 Overhead comparison metrics | 6 KB |
| `precommit_claim_transcript.json` | #5 Pre-commit + fault recovery | 25 KB |
| `escalation_transcript.json` | #6 Conflict escalation | 16 KB |

---

## Message Type Coverage

Across all 7 live demos, every one of MPAC's 21 message types is exercised at least once:

| Message Type | Demos |
|-------------|-------|
| `HELLO` | All |
| `SESSION_INFO` | All |
| `HEARTBEAT` | All |
| `GOODBYE` | All |
| `SESSION_CLOSE` | #1, #5 |
| `COORDINATOR_STATUS` | All |
| `INTENT_ANNOUNCE` | All |
| `INTENT_UPDATE` | #5 |
| `INTENT_WITHDRAW` | #5, #6 |
| `INTENT_CLAIM` | #5 |
| `INTENT_CLAIM_STATUS` | #5 |
| `OP_PROPOSE` | #5 |
| `OP_COMMIT` | All |
| `OP_REJECT` | #5 |
| `OP_SUPERSEDE` | #1 |
| `OP_BATCH_COMMIT` | #4 |
| `CONFLICT_REPORT` | #1, #2, #3, #4, #5, #6 |
| `CONFLICT_ACK` | #4, #6 |
| `CONFLICT_ESCALATE` | #6 |
| `RESOLUTION` | #1, #4, #5, #6 |
| `PROTOCOL_ERROR` | #3 (STALE_STATE_REF), #5 (various) |
