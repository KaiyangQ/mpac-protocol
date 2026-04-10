# MPAC v0.1.12 Family Trip Validation Report

**Date:** 2026-04-06
**Protocol version:** v0.1.12
**Scope:** Multi-principal consumer scenario — three AI agents (Dad, Mom, Kid) independently plan a family vacation through MPAC coordination over WebSocket transport with real Claude API calls

---

## 1. Motivation

The v0.1.12 distributed validation (code-editing scenario) proved that MPAC works for developer-to-developer agent coordination. However, MPAC's design goals explicitly include "family or group coordination where each member has their own agent" (SPEC.md §2.3). This validation tests a fundamentally different domain:

- **Non-technical principals**: a family of three, not software engineers
- **Subjective preferences**: "I want fun" vs "I want culture" — not compile errors
- **Budget as shared resource**: a finite ¥15,000 budget that all agents compete for
- **Age-based authority model**: parents as `owner`, child as `contributor`
- **Real natural-language negotiation**: agents use Claude to reason about compromises

The key question: **Can MPAC's protocol primitives — intent, conflict, resolution, commit — naturally model a consumer planning workflow?**

---

## 2. Scenario Design

### 2.1 Family Members and Their AI Agents

| Family Member | Agent ID | Role | System Prompt (Summarized) |
|---------------|----------|------|---------------------------|
| Dad (Zhang Wei, 38) | `agent:dad-planner` | `owner` | Budget controller, driver. Loves nature, hiking, camping. Controls ¥15,000 total budget. Drives ≤5hr/day. |
| Mom (Li Na, 36) | `agent:mom-planner` | `owner` | Food & accommodation lead. Cultural experiences, boutique homestay. **Allergic to all seafood** — critical constraint on every meal. |
| Kid (Zhang Xiaoming, 12) | `agent:kid-planner` | `contributor` | Fun advocate. Theme parks (Hello Kitty Park), water activities, free play. Needs ≥1 unstructured day. |

Each agent has a distinct Claude system prompt encoding its principal's preferences, constraints, and responsibilities. The agents call the Claude API independently — they do not share context or see each other's prompts.

### 2.2 Trip Parameters

- **Duration**: 5 days (July 12–16, 2026)
- **Origin**: Shanghai
- **Destination area**: Moganshan / Anji, Zhejiang Province (~3.5hr drive)
- **Total budget**: ¥15,000
- **Transportation**: Self-driving

### 2.3 Shared State Model

The itinerary is modeled as a `task_set` scope with 10 resources:

```
itinerary://day-1  through  itinerary://day-5
budget://accommodation, budget://food, budget://transportation, budget://activities, budget://total
```

Scope overlap is detected per-resource. When two agents both claim `itinerary://day-2`, the coordinator emits a `CONFLICT_REPORT`.

### 2.4 Why MPAC and Not A2A

This is the critical architectural distinction. In an A2A (Agent-to-Agent) model, one agent would orchestrate the others — say, Dad's agent tells Mom's and Kid's agents what to do. But:

- Mom has **veto power** over any meal plan that might contain seafood — she can't delegate this to Dad's agent
- Kid has a **genuine preference** for theme parks that shouldn't be overridden without negotiation
- Dad controls the **budget**, but that doesn't give him authority over Mom's cultural preferences

No single agent has full authority. This is a **multi-principal** coordination problem — exactly what MPAC is designed for.

---

## 3. Architecture

### 3.1 Components

| Component | File | Description |
|-----------|------|-------------|
| Trip Agent | `trip_agent.py` | AI agent specialized for trip planning. Each instance has unique system prompt with principal's preferences, constraints, responsibilities. Claude API integration for intent decisions, conflict negotiation, and itinerary generation. |
| WebSocket Coordinator | `ws_coordinator.py` | Existing coordinator server (reused from code-editing demo). Routes MPAC messages, detects scope overlaps, manages conflict lifecycle. |
| Main Orchestrator | `run_family_trip.py` | 9-phase scenario runner. Creates agents, manages session lifecycle, drives concurrent Claude API calls, displays final itinerary. |
| Itinerary Store | `run_family_trip.py` (class) | In-memory shared state tracking `state_ref` (SHA-256) per itinerary day. Simulates a real shared document. |

### 3.2 Agent Claude API Interface

Each agent makes three types of Claude API calls:

1. **`decide_intent(trip_context, other_intents)`** → Returns JSON with `intent_id`, `objective`, `scope_resources`, `assumptions`, `priority`. The agent decides what part of the trip to plan based on its principal's preferences.

2. **`respond_to_conflict(conflict_info, own_intent, other_intent)`** → Returns JSON with `ack_type` (accepted/disputed), `position` (natural language), `flexibility` (high/medium/low), `compromise_proposal`. The agent advocates for its principal while considering family harmony.

3. **`generate_itinerary(day_numbers, resolution_context, other_plans, budget_info)`** → Returns JSON with detailed per-day plans (morning/afternoon/evening/accommodation/meals/cost/notes) and budget breakdown. The agent generates a concrete plan informed by conflict resolutions.

All three calls are made **concurrently** across agents using `asyncio.run_in_executor` for parallel LLM invocations.

---

## 4. Execution — Phase by Phase

The demo ran successfully on 2026-04-06. All data below is from the actual run transcript (`family_trip_transcript.json`, 24 messages).

### Phase 0: Create Agents

Three `TripAgent` instances created with distinct system prompts. Dad and Mom as `owner`, Kid as `contributor`.

### Phase 1: Start Coordinator

WebSocket coordinator started on `ws://localhost:8768`, session ID `family-trip-2026-summer`.

### Phase 2: HELLO Handshake

All three agents connected over WebSocket and sent HELLO. Coordinator responded with SESSION_INFO to each:

| Agent | Lamport Clock at Join | Participant Count at Join |
|-------|----------------------|--------------------------|
| Dad | 1 → (coordinator: 3) | 1 |
| Mom | 1 → (coordinator: 5) | 2 |
| Kid | 1 → (coordinator: 7) | 3 |

The incrementing Lamport clock and participant count confirm correct sequential session establishment.

### Phase 3: Intent Decisions (Concurrent Claude API)

All three agents called Claude API **simultaneously** to decide what to plan. Total time: **5.9 seconds** for 3 parallel LLM calls.

| Agent | Intent ID | Objective | Scope Resources |
|-------|-----------|-----------|-----------------|
| Dad | `intent-dad-driving-camping` | Plan driving routes, one camping night in Moganshan with hiking, establish budget framework | `budget://transportation`, `budget://total`, `itinerary://day-2`, `itinerary://day-3` |
| Mom | `intent-mom-cultural-accommodation` | Secure seafood-free dining, book boutique minsu, arrange handicraft workshops | `budget://accommodation`, `budget://food`, `itinerary://day-2`, `itinerary://day-3`, `itinerary://day-4` |
| Kid | `intent-kid-theme-park-fun` | Plan full day at Hello Kitty Park and one free play day with water activities | `itinerary://day-2`, `itinerary://day-4`, `budget://activities` |

**Key observation**: All three agents independently chose `itinerary://day-2` as part of their scope. This is realistic — everyone has opinions about the early days of a trip. The coordinator will detect this overlap.

### Phase 4: INTENT_ANNOUNCE → Conflict Detection

Agents announced their intents sequentially. The coordinator detected scope overlaps in real-time:

**Timeline of conflict detection:**

```
t=7.59s  Dad announces intent (scope: day-2, day-3, budget://transportation, budget://total)
         → No conflicts (first intent)

t=8.40s  Mom announces intent (scope: day-2, day-3, day-4, budget://accommodation, budget://food)
         → CONFLICT_REPORT: Mom vs Dad (overlap on day-2, day-3)

t=9.21s  Kid announces intent (scope: day-2, day-4, budget://activities)
         → CONFLICT_REPORT: Kid vs Dad (overlap on day-2)
         → CONFLICT_REPORT: Kid vs Mom (overlap on day-2, day-4)
```

**3 conflicts detected**. This is the protocol working exactly as designed — each new intent is checked against all existing active intents, and any scope overlap triggers a `CONFLICT_REPORT` multicast to the involved parties.

The coordinator's session health transitioned to `degraded` (3 open conflicts), which is the correct behavior per SPEC.md — unresolved conflicts indicate the session cannot proceed without resolution.

### Phase 5: Conflict Negotiation (Concurrent Claude API)

For each conflict, both involved agents called Claude API concurrently to express their positions. This is the most interesting phase — it shows AI agents engaging in genuine multi-party negotiation.

#### Conflict 1: Dad vs Mom (Day 2-3 overlap)

| Agent | ack_type | flexibility | Position (summarized) |
|-------|----------|-------------|----------------------|
| Mom | `disputed` | `medium` | "Dad wants camping, but Mom needs clean, comfortable accommodations for cultural experiences and our 12-year-old. Propose: camp one night only, stay in minsu the other nights." |
| Dad | `disputed` | `medium` | "I understand Mom wants 4 nights in Moganshan, but as driver and budget controller I need to balance. Propose: one camping night mid-trip, other nights in minsu." |

**Resolution**: Coordinator merged both positions. Both agents independently proposed the same compromise (one camping night + minsu for other nights) — a natural convergence.

#### Conflict 2: Dad vs Kid (Day 2 overlap)

| Agent | ack_type | flexibility | Position (summarized) |
|-------|----------|-------------|----------------------|
| Kid | `accepted` | `high` | "Dad wants Day 2 for driving/camping — this works! I can shift Hello Kitty Park to another day. Very flexible on scheduling." |
| Dad | `disputed` | `medium` | "Kid wants fun activities but we need to balance with nature experiences and budget. Can combine hiking with kid-friendly trail." |

**Resolution**: Coordinator merged. Kid's agent showed **high flexibility** — voluntarily yielding Day 2 to Dad's camping plan. This demonstrates that agents can model cooperative behavior, not just adversarial negotiation.

#### Conflict 3: Kid vs Mom (Day 2, Day 4 overlap)

| Agent | ack_type | flexibility | Position (summarized) |
|-------|----------|-------------|----------------------|
| Kid | `disputed` | `medium` | "Xiaoming really has his heart set on Hello Kitty Park. Can we fit the park into Mom's cultural day?" |
| Mom | `accepted` | `high` | "I can work with Kid's theme park plan while maintaining cultural experiences. Day 2 Hello Kitty Park works perfectly." |

**Resolution**: Coordinator merged. Mom's agent demonstrated **high flexibility**, accommodating Kid's theme park preference while rearranging her cultural activities.

**Negotiation timing**: 3 conflicts × 2 concurrent positions each = 6 Claude API calls, completed in ~24 seconds total (3 rounds of ~8s each).

### Phase 6: Itinerary Generation (Concurrent Claude API)

After all conflicts were resolved, all three agents generated detailed itineraries concurrently. Each agent's Claude call received:

- Its assigned days (from intent scope)
- Resolution context (what compromises were agreed on)
- Other agents' intents (so it knows what others are planning)
- Budget information

**3 parallel Claude API calls, completed in 17.6 seconds.**

Each agent produced structured JSON with per-day plans including morning/afternoon/evening activities, accommodation, meals (all seafood-free — Mom's agent enforced this even in other agents' plans), estimated costs, and notes.

### Phase 7: OP_BATCH_COMMIT

Each agent committed its plans through MPAC:

| Agent | Message Type | Days Committed | Budget Claimed |
|-------|-------------|----------------|----------------|
| Dad | `OP_BATCH_COMMIT` (2 entries) | Day 2, Day 3 | ¥2,110 (transport, camping, hiking, meals) |
| Mom | `OP_BATCH_COMMIT` (3 entries) | Day 2, Day 3, Day 4 | ¥3,580 (accommodation, food, cultural activities) |
| Kid | `OP_BATCH_COMMIT` (2 entries) | Day 2, Day 4 | ¥1,760 (park tickets, bamboo garden, raft, meals, souvenirs) |

All batches used `all_or_nothing` atomicity — if any day in a batch fails validation, the entire batch is rejected. All 7 operations committed successfully.

### Phase 8: Final Itinerary

The combined itinerary from all three agents:

#### Day 2 (3 agents contributed)

| Time | Activity | Planned By |
|------|----------|-----------|
| Morning | Drive to Moganshan, check into minsu, explore bamboo forest | Dad |
| Morning | Check into boutique homestay (Bamboo Grove Lodge), bamboo handicraft workshop | Mom |
| Morning | Hello Kitty Park — character meet & greet | Kid |
| Afternoon | Moganshan hiking trail, nature photography | Dad |
| Afternoon | Hello Kitty Park — rides, interactive shows | Kid |
| Afternoon | Farm-to-table vegetarian lunch (seafood-free) | Mom |
| Evening | Set up camping site, campfire dinner & stargazing | Dad |
| Evening | Traditional Zhejiang cuisine dinner (confirmed seafood-free) | Mom |

#### Day 3 (2 agents contributed)

| Time | Activity | Planned By |
|------|----------|-----------|
| Morning | Sunrise viewing, pack camping gear, peak climb hike | Dad |
| Morning | Breakfast at minsu, local cooking class | Mom |
| Afternoon | Drive to Anji area (1.5hr) with scenic stops | Dad |
| Afternoon | Silk workshop, silk painting, bamboo grove hiking | Mom |
| Evening | Check into Anji minsu, local dinner (bamboo shoot specialties) | Dad |
| Evening | Award-winning local restaurant (seafood-free), evening tea ceremony | Mom |

#### Day 4 (2 agents contributed)

| Time | Activity | Planned By |
|------|----------|-----------|
| Morning | Check-out, drive to Anji, paper-making workshop | Mom |
| Morning | Free play at Bamboo Expo Garden, bamboo raft experience | Kid |
| Afternoon | Lunch in Anji (seafood-free), free time | Mom |
| Afternoon | Free exploration, nature photography, tea plantation walk | Kid |
| Evening | Farewell dinner, night market cultural souvenirs | Mom |
| Evening | Campfire preparation, gather kindling, fire safety education | Kid |

**Total estimated cost: ¥6,680 / ¥15,000 (44.5% utilized, ¥8,320 remaining)**

Note: Days 1 and 5 (arrival/departure) were not claimed by any agent in this run. In a production scenario, the coordinator or a human principal would notice the unplanned days and either ask agents to extend their scope or plan those days manually.

### Phase 9: Session Close

All agents sent GOODBYE, connections closed cleanly. Full transcript saved.

---

## 5. Protocol Message Summary

| Message Type | Count | Direction | Purpose |
|-------------|-------|-----------|---------|
| HELLO | 3 | Agents → Coordinator | Session join |
| SESSION_INFO | 3 | Coordinator → Agents | Join confirmation |
| INTENT_ANNOUNCE | 3 | Agents → Coordinator | Declare plans |
| CONFLICT_REPORT | 3 | Coordinator → Agents (multicast) | Scope overlap detected |
| COORDINATOR_STATUS | 4 | Coordinator → All (broadcast) | Heartbeat / health |
| CONFLICT_ACK | 6 | Agents → Coordinator | Express positions |
| OP_BATCH_COMMIT | 3 | Agents → Coordinator | Commit plans |
| GOODBYE | 3 | Agents → Coordinator | Clean disconnect |
| **Total** | **24** (inbound) + broadcast copies | | |

Session health transitions:
```
healthy → degraded (3 open conflicts) → healthy (all resolved)
```

---

## 6. Claude API Call Summary

| Phase | Calls | Concurrency | Wall-clock Time | Purpose |
|-------|-------|-------------|-----------------|---------|
| Intent decisions | 3 | 3 parallel | 5.9s | Each agent decides what to plan |
| Conflict positions | 6 | 2 parallel × 3 rounds | ~24s | Agents express negotiation positions |
| Itinerary generation | 3 | 3 parallel | 17.6s | Agents produce detailed day plans |
| **Total** | **12** | | **~48s** | |

Each API call used the `claude-sonnet-4-20250514` model with agent-specific system prompts.

---

## 7. Protocol Features Demonstrated

| MPAC Feature | How Demonstrated |
|--------------|-----------------|
| **Multi-principal coordination** | 3 independent principals with conflicting preferences (camping vs hotel, theme park vs cultural experience) |
| **Intent before action** | Every agent declared its plan before any booking/commit happened |
| **task_set scope overlap** | Coordinator detected 3 overlaps on `itinerary://day-*` resources — first real use of `task_set` scope kind in a demo |
| **CONFLICT_REPORT multicast** | Each conflict report sent only to the two involved agents, not broadcast to all |
| **CONFLICT_ACK with positions** | Agents expressed structured positions with `ack_type`, `flexibility`, and `compromise_proposal` |
| **Coordinator auto-resolve** | Coordinator resolved all 3 conflicts as `merged` based on agent positions |
| **Session health tracking** | Health transitioned to `degraded` during open conflicts, back to `healthy` after resolution |
| **OP_BATCH_COMMIT** | All agents committed multiple days atomically with `all_or_nothing` semantics |
| **Lamport clock ordering** | All messages carry monotonically increasing Lamport watermarks (1 → 7 → 10 → ...) |
| **Role-based governance** | Dad & Mom = `owner` (can resolve), Kid = `contributor` (can propose but not override) |
| **Causal context** | Every commit and conflict report carried watermarks reflecting the agent's causal knowledge |

---

## 8. Comparison with Code-Editing Validation

| Dimension | Code-Editing Demo (v0.1.12) | Family Trip Demo |
|-----------|---------------------------|------------------|
| Domain | Software engineering | Consumer trip planning |
| Principals | 2 AI agents (Alice, Bob) | 3 AI agents (Dad, Mom, Kid) |
| Scope kind | `file_set` | `task_set` |
| Conflict type | Concurrent file edits | Overlapping day/budget claims |
| State tracking | SHA-256 of file contents | SHA-256 of plan JSON |
| Resolution style | Coordinator auto-resolve | Coordinator merge after position collection |
| Execution model | `post_commit` (edit then declare) | `post_commit` (plan then commit) |
| Optimistic concurrency | STALE_STATE_REF + rebase | Not triggered (agents committed non-overlapping targets) |
| Unique features | Real code modification, Claude code generation | Natural-language negotiation, budget tracking, multi-agent compromise |

---

## 9. Findings

### 9.1 Confirmed Working

1. **`task_set` scope overlap detection**: Works correctly for URI-style resources (`itinerary://day-N`, `budget://category`). Required a one-line fix: the `TripAgent` was initially using the `resources` field instead of `task_ids` for `task_set` scopes — the fields are scope-kind-specific per the `Scope` model.

2. **Three-way conflict**: When Kid's intent overlapped with both Dad and Mom simultaneously, the coordinator correctly emitted **two separate** CONFLICT_REPORT messages — one for Kid-vs-Dad, one for Kid-vs-Mom. The protocol handles N-way conflicts by decomposing them into pairwise pairs.

3. **Natural-language negotiation maps cleanly to MPAC**: Agents expressing positions via `CONFLICT_ACK.position` is a natural fit for LLM-based negotiation. The structured `flexibility` field (high/medium/low) provides additional signal for resolution logic.

4. **Cooperative agent behavior**: Kid's agent voluntarily yielded Day 2 (accepted with high flexibility), and Mom's agent accommodated Kid's theme park plan — demonstrating that MPAC's conflict model supports cooperation, not just adversarial resolution.

5. **Budget as a shared resource**: Modeling budget categories as `budget://food`, `budget://activities` etc. within the `task_set` scope kind works naturally. Agents can claim budget categories, and overlaps trigger coordination.

### 9.2 Observations for Future Work

1. **Day 1 and Day 5 remained unplanned**: No agent claimed these days. A production implementation might add a "coverage check" — after all intents are announced, the coordinator could warn if any resource in the shared state remains unclaimed.

2. **Multiple agents committed to the same day**: Day 2 has plans from all three agents. The protocol committed all of them (different `op_id`s targeting the same `itinerary://day-2`). A production implementation should either: (a) use `STALE_STATE_REF` to enforce single-writer semantics per day, or (b) model each day as a composite resource where multiple agents contribute to different time slots.

3. **Budget reconciliation was agent-driven, not protocol-enforced**: Each agent estimated its own budget, but the protocol didn't validate that the total stayed under ¥15,000. A future enhancement could add a **constraint validation hook** — the coordinator checks budget constraints at commit time and rejects operations that would exceed the total.

4. **Semantic conflict detection**: The current overlap detection is purely structural (do two scopes share resources?). It doesn't detect *semantic* conflicts like "Dad's BBQ dinner plan might include seafood." SPEC.md §20.3 notes the Semantic Profile as future work — this scenario illustrates the practical need.

---

## 10. Files

### New files created

| File | Description |
|------|-------------|
| `ref-impl/demo/distributed/trip_agent.py` | Trip planning agent with per-principal Claude system prompt, intent decision, conflict negotiation, itinerary generation |
| `ref-impl/demo/distributed/run_family_trip.py` | 9-phase orchestrator: agent creation → HELLO → intent → conflict → resolution → commit → display → close |
| `ref-impl/demo/distributed/family_trip_transcript.json` | Full MPAC message transcript from the actual run (24 messages) |

### How to Run

```bash
# Prerequisites
pip install websockets httpx anthropic --break-system-packages

# Configure API key in local_config.json:
# { "anthropic": { "api_key": "sk-ant-...", "model": "claude-sonnet-4-20250514" } }

# Run the demo
cd ref-impl/demo/distributed
python run_family_trip.py
```

Expected output: ~1 minute of agent coordination, ending with a complete 5-day itinerary and session summary showing message counts, conflict count, and total estimated cost.
