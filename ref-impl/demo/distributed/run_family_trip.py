#!/usr/bin/env python3
"""
MPAC Family Trip Planning Demo — Three AI Agents Coordinate a Family Vacation.

This is a real multi-principal coordination scenario:
  - Dad's agent (Zhang Wei): Budget controller, driver, outdoor enthusiast
  - Mom's agent (Li Na): Food & accommodation, cultural experiences
  - Kid's agent (Zhang Xiaoming, 12yo): Theme parks, water activities, fun

Each agent calls the Claude API independently to make decisions.
The coordinator detects scope overlaps and mediates conflicts.
A human arbiter (Dad) resolves disputed conflicts.

NOTE: This demo calls the Anthropic API (~9-15 requests per run).
      You will need a valid API key in local_config.json.

Usage:
    python run_family_trip.py
"""
import sys, os, json, asyncio, logging, time, hashlib, uuid
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))

import websockets
from ws_coordinator import WSCoordinator
from trip_agent import TripAgent, content_hash

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-20s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("family-trip")

HOST = "localhost"
PORT = 8768
SESSION_ID = "family-trip-2026-summer"
COORDINATOR_URI = f"ws://{HOST}:{PORT}"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════════════════════════════════
#  Itinerary state store — simulates shared state (like a shared doc)
# ═══════════════════════════════════════════════════════════════════

class ItineraryStore:
    """In-memory store for the shared itinerary. Tracks state_ref per day."""

    def __init__(self):
        self.days: dict[str, dict] = {}       # "itinerary://day-1" -> plan dict
        self.state_refs: dict[str, str] = {}   # "itinerary://day-1" -> sha256 hash
        self.budget: dict[str, float] = {
            "accommodation": 0, "food": 0, "transportation": 0,
            "activities": 0, "misc": 0,
        }
        # Initialize empty state for all 5 days
        for i in range(1, 6):
            key = f"itinerary://day-{i}"
            self.days[key] = {"day": i, "status": "unplanned"}
            self.state_refs[key] = content_hash(json.dumps(self.days[key], sort_keys=True))

    def get_ref(self, target: str) -> str:
        return self.state_refs.get(target, "sha256:0000000000000000")

    def commit_day(self, target: str, plan: dict) -> str:
        """Commit a plan for a day, returning the new state_ref."""
        self.days[target] = plan
        new_ref = content_hash(json.dumps(plan, sort_keys=True, ensure_ascii=False))
        self.state_refs[target] = new_ref
        return new_ref

    def summary(self) -> str:
        lines = []
        for i in range(1, 6):
            key = f"itinerary://day-{i}"
            plan = self.days.get(key, {})
            if plan.get("status") == "unplanned":
                lines.append(f"  Day {i}: [unplanned]")
            else:
                lines.append(f"  Day {i}: {plan.get('morning', '?')} | {plan.get('afternoon', '?')} | {plan.get('evening', '?')}")
                if plan.get("accommodation"):
                    lines.append(f"         Accommodation: {plan['accommodation']}")
                if plan.get("meals"):
                    lines.append(f"         Meals: {plan['meals']}")
        return "\n".join(lines)


def phase(title: str):
    log.info("")
    log.info("=" * 72)
    log.info(f"  {title}")
    log.info("=" * 72)
    log.info("")


# ═══════════════════════════════════════════════════════════════════
#  Trip context — shared knowledge all agents receive
# ═══════════════════════════════════════════════════════════════════

TRIP_CONTEXT = """
FAMILY TRIP PLANNING — Summer 2026

FAMILY:
  - Dad (Zhang Wei): 38, drives, budget controller, loves hiking and camping
  - Mom (Li Na): 36, food enthusiast, cultural experiences, allergic to seafood
  - Kid (Zhang Xiaoming): 12 years old, wants theme parks and water activities

TRIP PARAMETERS:
  - Duration: 5 days (July 12-16, 2026)
  - Starting point: Shanghai
  - Total budget: ¥15,000
  - Transportation: Self-driving (own car)
  - Destination area: Moganshan / Anji, Zhejiang Province
    (about 3-3.5 hours drive from Shanghai)

KNOWN OPTIONS IN THE AREA:
  - Moganshan: Bamboo forests, hiking trails, boutique homestay, campsite
  - Anji: Hello Kitty Park (theme park), water parks, bamboo museum, tea plantations
  - Local food: Bamboo shoots, smoked tofu, local mountain vegetables (NO seafood)

CONSTRAINTS:
  - Dad drives ≤ 5 hours per day
  - Kid needs at least 1 day of "free play" (unstructured)
  - All meals must be seafood-free (Mom's allergy)
  - Kid's school break: July 10-25
  - Budget: accommodation ~¥4,000-6,000, food ~¥3,000, activities ~¥3,000, transport ~¥1,500

SHARED STATE RESOURCES:
  - itinerary://day-1 through itinerary://day-5
  - budget://accommodation, budget://food, budget://transportation, budget://activities
"""


# ═══════════════════════════════════════════════════════════════════
#  Main scenario
# ═══════════════════════════════════════════════════════════════════

async def run_family_trip():
    store = ItineraryStore()

    # ──── Phase 0: Create agents ────
    phase("Phase 0: Create Family Agents")

    dad_agent = TripAgent(
        name="Dad",
        principal_id="agent:dad-planner",
        role_description="Dad's (Zhang Wei) travel planner — handles transportation, driving routes, outdoor activities, and overall budget control",
        preferences="Loves nature, hiking, camping under the stars. Prefers budget-efficient options. Enjoys teaching his kid about nature. Wants at least one night camping.",
        constraints="Must drive ≤ 5 hours/day. Controls total budget of ¥15,000. Already owns camping gear. Responsible for all driving logistics.",
        responsibilities=["driving routes", "outdoor activities", "budget oversight", "transportation"],
        roles=["owner"],
    )

    mom_agent = TripAgent(
        name="Mom",
        principal_id="agent:mom-planner",
        role_description="Mom's (Li Na) travel planner — handles accommodation booking, restaurant selection, and cultural experiences",
        preferences="Loves cultural experiences: local cooking classes, handicraft workshops, boutique homestay. Foodie but allergic to all seafood. Wants the family to experience local culture together.",
        constraints="CRITICAL: Allergic to seafood — ALL meals must be seafood-free, verify with every restaurant. Accommodation must be clean and kid-friendly (child is 12). Budget for accommodation: ¥4,000-6,000 for 4 nights.",
        responsibilities=["accommodation", "restaurants", "cultural experiences", "meal planning"],
        roles=["owner"],
    )

    kid_agent = TripAgent(
        name="Kid",
        principal_id="agent:kid-planner",
        role_description="Xiaoming's (Zhang Xiaoming, 12yo) fun planner — advocates for theme parks, water activities, and free play time",
        preferences="LOVES theme parks (especially Hello Kitty Park in Anji), water parks, swimming. Wants at least one full day at a theme park and one day of free/unstructured play. Likes campfires and stargazing too!",
        constraints="Must be age-appropriate activities (12 years old). Needs at least 1 day of free play. Activity budget should stay under ¥3,000. School break July 10-25.",
        responsibilities=["theme parks", "water activities", "fun activities", "free play day"],
        roles=["contributor"],  # Kid can propose but not override
    )

    agents = [dad_agent, mom_agent, kid_agent]
    log.info(f"Created 3 agents: {', '.join(a.name for a in agents)}")

    # ──── Phase 1: Start coordinator ────
    phase("Phase 1: Start WebSocket Coordinator")

    coordinator = WSCoordinator(SESSION_ID, HOST, PORT)
    ws_server = await websockets.serve(coordinator.handler, HOST, PORT)
    heartbeat_task = asyncio.create_task(coordinator.heartbeat_loop())
    log.info(f"Coordinator running on ws://{HOST}:{PORT}")
    await asyncio.sleep(0.5)

    # ──── Phase 2: All agents join ────
    phase("Phase 2: Agents Join Session (HELLO)")

    for agent in agents:
        await agent.connect(COORDINATOR_URI, SESSION_ID)
    await asyncio.sleep(0.3)

    # Sequential HELLO so coordinator can track each
    for agent in agents:
        await agent.do_hello()
        await asyncio.sleep(0.3)

    log.info("All 3 family agents joined the session")

    # ──── Phase 3: Agents decide intents (concurrent Claude calls) ────
    phase("Phase 3: Agents Decide Intents (Concurrent Claude API)")

    log.info("All 3 agents asking Claude what to plan CONCURRENTLY...")
    t0 = time.time()

    # All three decide in parallel
    loop = asyncio.get_event_loop()
    dad_intent_future = loop.run_in_executor(
        None, dad_agent.decide_intent, TRIP_CONTEXT, []
    )
    mom_intent_future = loop.run_in_executor(
        None, mom_agent.decide_intent, TRIP_CONTEXT, []
    )
    kid_intent_future = loop.run_in_executor(
        None, kid_agent.decide_intent, TRIP_CONTEXT, []
    )

    dad_intent, mom_intent, kid_intent = await asyncio.gather(
        dad_intent_future, mom_intent_future, kid_intent_future
    )
    elapsed = time.time() - t0

    log.info(f"All 3 intent decisions in {elapsed:.1f}s")
    log.info("")
    for name, intent in [("Dad", dad_intent), ("Mom", mom_intent), ("Kid", kid_intent)]:
        log.info(f"  {name}: {intent.get('objective', '?')}")
        log.info(f"    scope: {intent.get('scope_resources', [])}")
        log.info(f"    assumptions: {intent.get('assumptions', [])[:3]}")
        log.info("")

    intent_map = {
        dad_agent.principal_id: dad_intent,
        mom_agent.principal_id: mom_intent,
        kid_agent.principal_id: kid_intent,
    }
    agent_map = {
        dad_agent.principal_id: dad_agent,
        mom_agent.principal_id: mom_agent,
        kid_agent.principal_id: kid_agent,
    }

    # ──── Phase 4: Announce intents → conflict detection ────
    phase("Phase 4: INTENT_ANNOUNCE → Conflict Detection")

    for agent, intent in [(dad_agent, dad_intent), (mom_agent, mom_intent), (kid_agent, kid_intent)]:
        await agent.do_announce_intent(intent)
        await asyncio.sleep(0.3)

    # Give coordinator time to detect conflicts, then drain inboxes
    await asyncio.sleep(1.0)
    await asyncio.gather(
        dad_agent.drain_inbox(2.0),
        mom_agent.drain_inbox(2.0),
        kid_agent.drain_inbox(2.0),
    )

    # Collect unique conflicts
    all_conflicts = []
    seen_cids = set()
    for agent in agents:
        for c in agent.conflicts_received:
            cid = c.get("payload", {}).get("conflict_id", "")
            if cid and cid not in seen_cids:
                seen_cids.add(cid)
                all_conflicts.append(c)

    log.info(f"Conflicts detected: {len(all_conflicts)}")
    for c in all_conflicts:
        cp = c["payload"]
        pa = cp.get("principal_a", cp.get("intent_a", "?"))
        pb = cp.get("principal_b", cp.get("intent_b", "?"))
        log.info(f"  {cp['conflict_id'][:30]}: {pa} vs {pb}")
        log.info(f"    Category: {cp.get('category', '?')}")
        log.info(f"    Description: {cp.get('description', '?')[:80]}")

    # ──── Phase 5: Conflict negotiation ────
    if all_conflicts:
        phase("Phase 5: Conflict Negotiation (Concurrent Claude API)")

        for conflict_envelope in all_conflicts:
            cp = conflict_envelope["payload"]
            cid = cp["conflict_id"]

            # Identify involved agents
            intent_a = cp.get("intent_a", "")
            intent_b = cp.get("intent_b", "")
            principal_a = cp.get("principal_a", "")
            principal_b = cp.get("principal_b", "")

            agent_a = agent_map.get(principal_a)
            agent_b = agent_map.get(principal_b)
            intent_a_data = intent_map.get(principal_a, {})
            intent_b_data = intent_map.get(principal_b, {})

            if not agent_a or not agent_b:
                log.warning(f"  Could not identify agents for conflict {cid}")
                continue

            log.info(f"  Conflict: {agent_a.name} vs {agent_b.name}")
            log.info(f"  Both agents expressing positions via Claude...")

            t0 = time.time()
            pos_a_future = loop.run_in_executor(
                None, agent_a.respond_to_conflict, cp, intent_a_data, intent_b_data, agent_b.name
            )
            pos_b_future = loop.run_in_executor(
                None, agent_b.respond_to_conflict, cp, intent_b_data, intent_a_data, agent_a.name
            )
            pos_a, pos_b = await asyncio.gather(pos_a_future, pos_b_future)
            elapsed = time.time() - t0

            log.info(f"  Positions received in {elapsed:.1f}s:")
            log.info(f"    {agent_a.name} ({pos_a.get('ack_type', '?')}, flexibility={pos_a.get('flexibility', '?')}):")
            log.info(f"      {pos_a.get('position', '?')[:120]}")
            log.info(f"    {agent_b.name} ({pos_b.get('ack_type', '?')}, flexibility={pos_b.get('flexibility', '?')}):")
            log.info(f"      {pos_b.get('position', '?')[:120]}")

            # Send CONFLICT_ACK over WebSocket
            await agent_a.do_conflict_ack(cid, pos_a.get("ack_type", "disputed"),
                                          pos_a.get("position", ""))
            await agent_b.do_conflict_ack(cid, pos_b.get("ack_type", "disputed"),
                                          pos_b.get("position", ""))

            # ── Arbiter resolution (Dad as human arbiter, mediated by coordinator) ──
            rationale = (
                f"{agent_a.name}'s position: {pos_a.get('position', '')[:100]}. "
                f"{agent_b.name}'s position: {pos_b.get('position', '')[:100]}. "
                f"Compromise: {pos_a.get('compromise_proposal', pos_b.get('compromise_proposal', 'merge both plans where possible'))}."
            )
            coordinator.coordinator.resolve_as_coordinator(cid, "merged", rationale)
            log.info(f"  Coordinator resolved conflict {cid[:20]}... as MERGED")
            log.info(f"    Rationale: {rationale[:120]}...")
            log.info("")

        await asyncio.sleep(1.0)
    else:
        log.info("No conflicts — agents chose completely non-overlapping resources!")

    # ──── Phase 6: Generate detailed itineraries (concurrent Claude calls) ────
    phase("Phase 6: Agents Generate Itineraries (Concurrent Claude API)")

    # Build resolution context from all conflict resolutions
    resolution_context = ""
    for c in all_conflicts:
        cp = c["payload"]
        resolution_context += f"- Conflict between agents resolved as MERGED: {cp.get('description', '')[:100]}\n"
    if not resolution_context:
        resolution_context = "No conflicts occurred — agents have free rein over their assigned resources."

    budget_info = f"""Total budget: ¥15,000
Accommodation: ¥4,000-6,000 for 4 nights
Food: ~¥3,000 for 5 days
Activities: ~¥3,000
Transportation: ~¥1,500 (gas + tolls)"""

    # Assign days to agents based on their intent scope
    def days_from_intent(intent: dict) -> list[int]:
        days = []
        for r in intent.get("scope_resources", []):
            if r.startswith("itinerary://day-"):
                try:
                    days.append(int(r.split("-")[-1]))
                except ValueError:
                    pass
        return sorted(days) if days else []

    dad_days = days_from_intent(dad_intent)
    mom_days = days_from_intent(mom_intent)
    kid_days = days_from_intent(kid_intent)

    # If no days claimed, assign defaults
    if not dad_days and not mom_days and not kid_days:
        dad_days = [1, 5]
        mom_days = [2, 3]
        kid_days = [3, 4, 5]

    log.info(f"Day assignments: Dad={dad_days}, Mom={mom_days}, Kid={kid_days}")
    log.info("All 3 agents generating itineraries via Claude CONCURRENTLY...")

    t0 = time.time()
    all_other_intents = json.dumps([dad_intent, mom_intent, kid_intent], indent=2, ensure_ascii=False)

    dad_plan_future = loop.run_in_executor(
        None, dad_agent.generate_itinerary,
        dad_days if dad_days else [1, 5], resolution_context, all_other_intents, budget_info,
    )
    mom_plan_future = loop.run_in_executor(
        None, mom_agent.generate_itinerary,
        mom_days if mom_days else [2, 3], resolution_context, all_other_intents, budget_info,
    )
    kid_plan_future = loop.run_in_executor(
        None, kid_agent.generate_itinerary,
        kid_days if kid_days else [4], resolution_context, all_other_intents, budget_info,
    )

    dad_plan, mom_plan, kid_plan = await asyncio.gather(
        dad_plan_future, mom_plan_future, kid_plan_future,
    )
    elapsed = time.time() - t0
    log.info(f"All 3 itineraries generated in {elapsed:.1f}s")

    # ──── Phase 7: Commit plans through MPAC ────
    phase("Phase 7: Commit Itineraries (OP_COMMIT / OP_BATCH_COMMIT)")

    committed_plans = []  # (agent_name, day, plan_dict)

    for agent, intent, plan_result in [
        (dad_agent, dad_intent, dad_plan),
        (mom_agent, mom_intent, mom_plan),
        (kid_agent, kid_intent, kid_plan),
    ]:
        plans = plan_result.get("plans", [])
        if not plans:
            log.warning(f"  {agent.name}: No plans generated!")
            continue

        intent_id = intent["intent_id"]

        if len(plans) == 1:
            # Single day — use OP_COMMIT
            p = plans[0]
            day_num = p.get("day", 0)
            target = p.get("target", f"itinerary://day-{day_num}")
            state_ref_before = store.get_ref(target)
            new_ref = store.commit_day(target, p)
            summary_text = f"Day {day_num}: {p.get('morning', '?')[:40]} | {p.get('afternoon', '?')[:40]} | {p.get('evening', '?')[:40]}"

            op_id = f"op-{agent.name.lower()}-day{day_num}"
            accepted = await agent.do_commit(
                intent_id, op_id, target, summary_text,
                f"sha256:{state_ref_before}", f"sha256:{new_ref}",
            )
            status = "COMMITTED" if accepted else "REJECTED"
            log.info(f"  {agent.name}: Day {day_num} → {status}")
            committed_plans.append((agent.name, day_num, p))

        else:
            # Multiple days — use OP_BATCH_COMMIT
            entries = []
            for p in plans:
                day_num = p.get("day", 0)
                target = p.get("target", f"itinerary://day-{day_num}")
                state_ref_before = store.get_ref(target)
                new_ref = store.commit_day(target, p)
                entries.append({
                    "op_id": f"op-{agent.name.lower()}-day{day_num}",
                    "target": target,
                    "op_kind": "create",
                    "state_ref_before": f"sha256:{state_ref_before}",
                    "state_ref_after": f"sha256:{new_ref}",
                    "summary": f"Day {day_num} plan",
                })
                committed_plans.append((agent.name, day_num, p))

            batch_id = f"batch-{agent.name.lower()}-days{''.join(str(p['day']) for p in plans)}"
            await agent.do_batch_commit(intent_id, batch_id, entries)
            log.info(f"  {agent.name}: Batch committed {len(entries)} days → COMMITTED")

        # Log budget
        budget = plan_result.get("budget_breakdown", {})
        if budget:
            log.info(f"  {agent.name}'s budget: {json.dumps(budget, ensure_ascii=False)}")

    # ──── Phase 8: Final itinerary display ────
    phase("Phase 8: FINAL ITINERARY")

    # Organize by day
    day_plans: dict[int, list] = {}
    for agent_name, day_num, plan in committed_plans:
        day_plans.setdefault(day_num, []).append((agent_name, plan))

    total_cost = 0
    for day_num in sorted(day_plans.keys()):
        entries = day_plans[day_num]
        log.info(f"━━━ Day {day_num} ━━━")
        for agent_name, plan in entries:
            log.info(f"  [Planned by {agent_name}'s Agent]")
            log.info(f"  Morning:       {plan.get('morning', 'N/A')}")
            log.info(f"  Afternoon:     {plan.get('afternoon', 'N/A')}")
            log.info(f"  Evening:       {plan.get('evening', 'N/A')}")
            if plan.get('accommodation'):
                log.info(f"  Accommodation: {plan['accommodation']}")
            if plan.get('meals'):
                log.info(f"  Meals:         {plan['meals']}")
            cost = plan.get('estimated_cost', 0)
            if cost:
                log.info(f"  Est. Cost:     ¥{cost}")
                total_cost += cost
            if plan.get('notes'):
                log.info(f"  Notes:         {plan['notes']}")
        log.info("")

    log.info(f"TOTAL ESTIMATED COST: ¥{total_cost:,.0f} / ¥15,000")
    remaining = 15000 - total_cost
    log.info(f"REMAINING BUDGET: ¥{remaining:,.0f}")

    # ──── Phase 9: Session close ────
    phase("Phase 9: Session Close")

    for agent in agents:
        await agent.do_goodbye("session_complete")
    await asyncio.sleep(1.0)

    for agent in agents:
        await agent.close()

    heartbeat_task.cancel()
    ws_server.close()
    await ws_server.wait_closed()

    # Save transcript
    transcript_path = os.path.join(SCRIPT_DIR, "family_trip_transcript.json")
    coordinator.save_transcript(transcript_path)

    # ──── Final summary ────
    phase("SESSION SUMMARY")

    snap = coordinator.coordinator.snapshot()
    log.info(f"Messages exchanged:    {len(coordinator.transcript)}")
    log.info(f"Participants:          {len(snap['participants'])}")
    log.info(f"Intents announced:     {len(snap['intents'])}")
    log.info(f"Operations committed:  {len(snap['operations'])}")
    log.info(f"Conflicts detected:    {len(snap['conflicts'])}")
    log.info(f"Conflicts resolved:    {sum(1 for c in snap['conflicts'] if c['state'] in ('RESOLVED', 'CLOSED'))}")
    log.info(f"Total estimated cost:  ¥{total_cost:,.0f}")
    log.info(f"Transcript saved:      {transcript_path}")

    log.info("")
    log.info("Coordinator state:")
    for i in snap["intents"]:
        log.info(f"  Intent: {i['intent_id'][:40]} → {i['state']}")
    for o in snap["operations"]:
        log.info(f"  Op: {o['op_id'][:40]} → {o['state']} (target={o.get('target', '?')})")
    for c in snap["conflicts"]:
        log.info(f"  Conflict: {c['conflict_id'][:30]}... → {c['state']}")

    return {
        "messages": len(coordinator.transcript),
        "conflicts": len(all_conflicts),
        "days_planned": len(committed_plans),
        "total_cost": total_cost,
        "agents": 3,
    }


if __name__ == "__main__":
    result = asyncio.run(run_family_trip())
    print(f"\n{'=' * 72}")
    print(f"  FAMILY TRIP DEMO COMPLETE")
    print(f"  Messages: {result['messages']}, Conflicts: {result['conflicts']}, "
          f"Days planned: {result['days_planned']}, Est. cost: ¥{result['total_cost']:,.0f}")
    print(f"{'=' * 72}")
