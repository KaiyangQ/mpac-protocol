# Introducing MPAC: A Coordination Protocol for Multi-Agent Collaboration

*When multiple AI agents — serving different people — need to work together, who coordinates them?*

## The Problem

The AI agent ecosystem is growing fast. MCP lets agents discover and use tools. A2A lets one orchestrator delegate tasks to other agents. But both assume a **single controlling principal** — one person or organization that owns and trusts all the agents involved.

What happens when that assumption breaks?

Consider a software team where Alice's coding agent and Bob's coding agent are both working on the same codebase. Alice's agent wants to refactor the authentication module. Bob's agent wants to fix a performance bug in the same files. Neither agent reports to the other. Neither principal (Alice or Bob) has authority over the other's agent. Yet their agents are about to create a merge conflict — or worse, silently overwrite each other's work.

This isn't a hypothetical. As AI agents become more autonomous, multi-principal coordination is becoming a real, unsolved infrastructure problem. It shows up whenever:

- Two people's agents touch the same shared resources
- Agents from different teams or organizations need to collaborate
- Family members' agents negotiate a shared trip, budget, or schedule without a single controller
- Multiple stakeholders have competing priorities over shared state
- Someone needs to audit *who decided what and why* across organizational boundaries

MCP doesn't address this — it's about tool invocation, not inter-principal coordination. A2A doesn't either — it explicitly assumes a single orchestrator with full authority. The coordination layer between independent principals and their agents is simply missing.

## What MPAC Does

MPAC (Multi-Principal Agent Coordination Protocol) fills this gap. It's an application-layer protocol that provides coordination semantics for agents serving **multiple independent principals**.

The core idea is simple: important actions should be declared before executed, conflicts should be made explicit rather than hidden, and decisions should carry enough context to be auditable.

MPAC organizes this into five layers:

| Layer | What it does |
|-------|-------------|
| **Session** | Agents join, discover each other, negotiate capabilities |
| **Intent** | Agents announce what they *plan* to do before doing it |
| **Operation** | Agents propose and commit actual changes to shared state |
| **Conflict** | Overlapping scopes or contradictory goals are detected and reported as structured objects |
| **Governance** | Conflicts are resolved through arbitration, escalation, or policy — with human override always available |

This layering is what makes MPAC different from "just use a message queue" or "just add locking." It separates *planning* from *execution* from *dispute* from *governance*, so each concern can be handled independently without tangling them into application logic.

## How It Works in Practice

Here's what a real MPAC session looks like, using two AI agents (Claude) that independently decide what to work on.

**Setup:** A Flask web application has several known issues — a token expiry bug, N+1 queries, code duplication. Two AI agents join a session: Alice (security engineer) and Bob (code quality engineer).

**Phase 1 — Session Join & Capability Negotiation:**

```
Alice  → Coordinator:  HELLO  (roles: owner, capabilities: intent.broadcast, op.commit)
Coordinator → Alice:   SESSION_INFO  (profile: open, compliance: core, execution_model: post_commit)
Bob    → Coordinator:  HELLO  (roles: contributor)
Coordinator → Bob:     SESSION_INFO
```

The coordinator validates credentials (required for non-open security profiles), assigns roles, and returns the session configuration. Unregistered senders cannot participate — any message other than HELLO from an unknown principal is rejected immediately.

**Phase 2 — Intent Declaration:**

Each agent independently calls Claude to decide what to work on. Alice decides to fix token expiry validation in `auth.py` and `auth_middleware.py`. Bob decides to refactor auth logic to eliminate duplication — in `auth.py`, `auth_middleware.py`, and `models.py`.

```
Alice → Coordinator:  INTENT_ANNOUNCE
  intent_id: "intent-alice-token-expiry-fix"
  scope: { kind: "file_set", resources: ["src/auth.py", "src/auth_middleware.py"] }

Bob   → Coordinator:  INTENT_ANNOUNCE
  intent_id: "intent-bob-refactor-auth-models"
  scope: { kind: "file_set", resources: ["src/auth.py", "src/auth_middleware.py", "src/models.py"] }
```

**Phase 3 — Automatic Conflict Detection:**

The coordinator detects that both intents touch `src/auth.py` and `src/auth_middleware.py`. It automatically generates a structured conflict report:

```
Coordinator → All:  CONFLICT_REPORT
  conflict_id: "de63124c-..."
  category: "scope_overlap"
  severity: "medium"
```

If the conflict remains unresolved past `resolution_timeout_sec` and no arbiter is available, the overlapping scope enters a **frozen state**. While frozen, new operations targeting those files are blocked with `SCOPE_FROZEN`, and new intents fully contained within the frozen scope are rejected — though intents that only partially overlap are accepted with a warning.

**Phase 4 — AI-Driven Negotiation:**

Both agents are asked how to handle the conflict. Each independently calls Claude:

- **Alice:** "This is a critical security vulnerability. I should proceed first, then Bob can incorporate my changes into his refactoring."
- **Bob:** "Alice's security fix is urgent. My refactoring can wait. Let her go first, and I'll build on her changes."

Two independent AI agents, with no shared prompt and no hardcoded coordination logic, reached the same conclusion through the protocol's structured conflict channel. Only the owner or a designated arbiter can submit the resolution — the protocol enforces this based on participant roles.

**Phase 5 — Execution:**

Both agents plan and commit their operations through `OP_COMMIT`, carrying state references (`state_ref_before`, `state_ref_after`) and causal watermarks for auditability. For multi-file changes, `OP_BATCH_COMMIT` provides atomic batches with `all_or_nothing` or `best_effort` semantics — including rollback of partially-created operations on validation failure.

Total protocol messages: **10.** The entire coordination — from joining to conflict resolution to commit — happened through structured MPAC messages, not ad-hoc chat or manual human intervention.

The same pattern also shows up well outside software. In a second validation scenario, three agents serving Dad, Mom, and Kid plan a 5-day family trip. They claim itinerary days and budget categories as `task_set` resources, negotiate overlaps like "camping night vs boutique minsu" and "theme park vs cultural workshop," and commit the resulting plan through `OP_BATCH_COMMIT`. The protocol primitives are the same; only the domain changes.

## What Makes v0.1.13 Different

MPAC has evolved through thirteen revision rounds, each driven by independent audit. The current version represents a step-change in maturity: the protocol is no longer just a specification — it has machine-enforceable constraints, adversarial-tested reference implementations, and backend health monitoring for production resilience.

**Schema conformance closure.** All 21 message types have dedicated JSON Schema definitions (Draft 2020-12). The envelope schema dispatches payload validation to the correct message-specific schema via `if/then` conditional constraints. A third-party implementation can now get wire compatibility by passing schema validation alone.

**Runtime enforcement.** Both reference implementations enforce normative spec requirements that were previously only in prose:

- **HELLO-first gate** — unregistered senders are rejected immediately; only HELLO is exempt.
- **Credential validation** — non-open security profiles reject HELLO without valid credentials.
- **Role policy evaluation** — the coordinator evaluates requested roles against the session's role policy (Section 23.1.5) and only grants authorized roles. Self-asserted `arbiter` in Authenticated/Verified profiles is no longer silently accepted.
- **Replay protection** — duplicate `message_id` values are rejected with `REPLAY_DETECTED` in Authenticated/Verified profiles. Timestamp drift beyond the replay window (RECOMMENDED: 5 minutes) is also rejected. Protection state survives coordinator recovery via snapshot checkpointing.
- **Resolution authority** — only owners/arbiters can resolve conflicts pre-escalation; only the escalation target or arbiter can resolve post-escalation.
- **Frozen-scope enforcement** — operations targeting resources within a frozen conflict scope are blocked. The check is target-based, not intent-based, so it cannot be bypassed by omitting optional fields.
- **Batch atomicity** — `all_or_nothing` batches that fail validation clean up all already-registered operations before returning the rejection.
- **Snapshot persistence** — frozen state survives coordinator recovery. A coordinator restart doesn't silently unfreeze contested scopes.
- **Backend health monitoring** — coordinators expose health metrics and readiness state for production deployments; participants can query endpoint availability and recovery status.

**Adversarial testing.** 66 new tests (34 Python + 32 TypeScript) specifically target enforcement bypass attempts: unregistered senders, missing credentials, unauthorized resolvers, frozen-scope evasion via omitted `intent_id`, snapshot recovery state loss, and partial-overlap edge cases. These tests were written in response to real findings from five rounds of independent audit.

## What MPAC Does *Not* Do

Being clear about boundaries is as important as explaining capabilities:

- **Not a transport protocol.** MPAC defines coordination semantics, not how messages are delivered. Use it over WebSocket, HTTP, message queues — whatever fits your infrastructure.
- **Not a state sync engine.** It doesn't replace CRDTs, OT, or version control. It coordinates *around* shared state, not the state itself.
- **Not a conflict resolution algorithm.** It provides the structured pipe — detection, reporting, escalation, resolution — but the actual decision logic is left to agents, arbiters, or policies.
- **Not a replacement for MCP or A2A.** It complements them. MCP handles tool invocation, A2A handles single-principal delegation, MPAC handles multi-principal coordination. They work at different layers.

## Current Status

MPAC is at **v0.1.13** — a draft protocol with conformance-tested reference implementations and production readiness features.

What exists today:

- **Full protocol specification** ([SPEC.md](../SPEC.md)) — 30 sections covering all five layers, three security profiles, three compliance profiles, explicit consistency and execution models, normative state transition tables, and cross-lifecycle state machine rules.
- **Developer reference** ([MPAC_Developer_Reference.md](../MPAC_Developer_Reference.md)) — complete data dictionary with 10 core objects, 21 message types, 3 state machines with normative transition tables, and an implementation checklist.
- **JSON Schema** ([ref-impl/schema/](../ref-impl/schema/)) — machine-readable wire format definitions for envelope and all 21 message payload schemas, with `if/then` conditional constraints for coordinator-only messages, handover fields, claim status decisions, and authorization events.
- **Reference implementations** in [Python](../ref-impl/python/) (109 tests) and [TypeScript](../ref-impl/typescript/) (88 tests) — full protocol coverage including session lifecycle, intent management, operation execution (pre-commit and post-commit models), conflict detection and resolution, coordinator fault recovery with snapshot persistence, atomic batch operations, frozen-scope enforcement, credential validation, and backend health monitoring.
- **AI agent demo** ([ref-impl/demo/](../ref-impl/demo/)) — two Claude agents coordinating through the full protocol lifecycle, exercising session join, intent declaration, conflict detection, negotiation, commit, coordinator status, state snapshot, and session close.
- **Distributed validation demos** ([ref-impl/demo/distributed/](../ref-impl/demo/distributed/)) — WebSocket-based live runs in three domains: code-editing with optimistic concurrency control, family-trip planning with `task_set` scope overlap, and a **coordination overhead benchmark** that runs the same 3-agent PR review in Traditional (serial) vs MPAC (parallel) mode, demonstrating that MPAC eliminates coordination overhead (-95%) while preserving decision time.
- **Audit-driven evolution** — every version change is archived with rationale. The protocol has been through thirteen revision rounds including a five-dimension audit (v0.1.3), a gap analysis (v0.1.4→v0.1.5), a SOSP/OSDI-level deep review (v0.1.6→v0.1.7), schema conformance closure (v0.1.12), four rounds of adversarial runtime enforcement audit, a security/consistency closure pass, a conformance hardening pass (timestamp window, schema enum alignment, max_count self-exclusion, no-policy rejection), and backend health monitoring integration (v0.1.13).

What's still ahead:

- **Lamport monotonicity enforcement** — sender-frontier data is tracked and persisted in snapshots, but incoming messages are not yet rejected for Lamport regression within the same sender incarnation.
- **Frozen scope progressive degradation** — the three-phase degradation sequence (normal → escalate+priority bypass → first-committer-wins) is specified in Section 18.6.2.1 but not yet implemented.
- **Multi-coordinator fencing** — split-brain prevention via epoch comparison is specified but not yet exercised under concurrent coordinator scenarios.
- **Formal verification** — the state machine interactions have normative transition tables but haven't been formally verified (e.g., TLA+).
- **Production deployment** — no known production system runs MPAC yet.

## Why Now

Three trends are converging that make multi-principal coordination increasingly urgent:

**Agents are gaining autonomy.** As AI agents move from "tool that answers questions" to "system that takes actions," the cost of uncoordinated concurrent action rises dramatically. Two chatbots giving conflicting advice is annoying; two autonomous agents overwriting each other's code changes is a real production incident.

**Multi-agent architectures are proliferating.** MCP and A2A have established that agents won't operate in isolation. But the more agents interact, the more likely they'll serve different principals with different goals — and the more urgent the need for coordination semantics that don't assume a single authority.

**Accountability requirements are tightening.** As agents make consequential decisions on behalf of people, the ability to trace *who instructed what, based on which information, and why* becomes a governance requirement, not a nice-to-have. MPAC's causal watermarking, structured conflict objects, and role-enforced resolution authority are designed to make this traceability a first-class protocol feature.

## Get Involved

MPAC is an open protocol in active development. If you're working on multi-agent systems, agent coordination frameworks, or collaborative AI applications, we'd welcome your perspective.

- **Read the spec:** [SPEC.md](../SPEC.md)
- **Try the reference implementations:** [Python](../ref-impl/python/) | [TypeScript](../ref-impl/typescript/)
- **Run the AI agent demo:** [ref-impl/demo/run_ai_agents.py](../ref-impl/demo/run_ai_agents.py)
- **Review the protocol evolution:** [version_history/CHANGELOG.md](../version_history/CHANGELOG.md)

The hardest problems in multi-agent coordination aren't about message formats — they're about deciding what coordination semantics are worth standardizing. That's a conversation that benefits from diverse perspectives. We're looking forward to yours.
