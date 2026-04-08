#!/usr/bin/env python3
"""
MPAC Demo: Conflict Escalation to Arbiter

Exercises the previously uncovered message type: CONFLICT_ESCALATE
Also demonstrates: multi-level governance (owner → arbiter), arbiter
resolution via Claude, and the full disputed conflict workflow.

Scenario: 2 owner agents (Alice, Bob) hit a scope overlap on a UI
component library. Both dispute the conflict. Alice escalates to a
designated arbiter, who analyzes both positions via Claude and renders
a binding resolution.

Requires: pip install websockets httpx anthropic
           local_config.json with Anthropic API key
"""
import sys, os, json, asyncio, uuid, logging, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))

from ws_coordinator import WSCoordinator
from ws_agent import WSAgent, _client, _model, _cfg

from mpac.models import Scope, MessageType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("escalation")

HOST, PORT = "localhost", 8771
SESSION_ID = f"sess-escalation-{uuid.uuid4().hex[:6]}"
EXECUTOR = ThreadPoolExecutor(max_workers=4)

PROJECT_CONTEXT = """
A shared UI component library with these files:
- components/nav.tsx        — main navigation component
- components/sidebar.tsx    — sidebar navigation panel
- styles/layout.css         — layout styles shared across nav and sidebar
- styles/theme.css          — color/font theme variables
- hooks/useNavigation.ts    — navigation state hook

Current situation: The nav component needs a major redesign. Alice wants to
restructure it as a responsive mega-menu. Bob wants to refactor it into a
minimal hamburger menu for mobile-first design. Both approaches require
changes to nav.tsx, layout.css, and the navigation hook.
"""


class ExtendedWSAgent(WSAgent):
    """WSAgent extended with escalation and conflict workflow support."""

    def __init__(self, name, role_description, roles=None, **kwargs):
        super().__init__(name, role_description, **kwargs)
        if roles:
            self.participant.roles = roles
            self.participant.capabilities.extend([
                "intent.withdraw", "conflict.ack", "governance.override",
            ])

    async def do_conflict_ack(self, conflict_id, ack_type="seen"):
        """Send CONFLICT_ACK."""
        msg = self.participant.ack_conflict(self.session_id, conflict_id, ack_type)
        await self.send(msg)
        await asyncio.sleep(0.3)

    async def do_escalate_conflict(self, conflict_id, escalate_to, reason, context=None):
        """Send CONFLICT_ESCALATE."""
        msg = self.participant.escalate_conflict(
            self.session_id, conflict_id, escalate_to, reason, context=context,
        )
        await self.send(msg)
        await asyncio.sleep(0.5)

    async def do_resolve_conflict(self, conflict_id, decision, rationale, outcome=None):
        """Send RESOLUTION."""
        msg = self.participant.resolve_conflict(
            self.session_id, conflict_id, decision, rationale=rationale, outcome=outcome,
        )
        await self.send(msg)
        await asyncio.sleep(0.5)

    async def do_intent_withdraw(self, intent_id, reason=None):
        """Send INTENT_WITHDRAW."""
        msg = self.participant.withdraw_intent(self.session_id, intent_id, reason=reason)
        await self.send(msg)
        await asyncio.sleep(0.3)

    def decide_as_arbiter(self, conflict_info, alice_position, bob_position):
        """Arbiter uses Claude to analyze both positions and render a decision."""
        system = f"""You are {self.name}, a designated arbiter in a multi-agent coordination session.

Two engineers have a scope overlap conflict on a UI component library. Both have
valid engineering perspectives but their approaches are incompatible — they cannot
both proceed on the same files.

Your job is to render a BINDING decision: which approach should proceed, and which
must yield. Consider technical merit, user impact, and feasibility.

Reply with ONLY a JSON object (no markdown, no explanation):
{{
  "decision": "approved",
  "rationale": "<clear explanation of why one approach wins>",
  "winner_principal": "<principal_id of the winning agent>",
  "loser_principal": "<principal_id of the losing agent>",
  "accepted_intents": ["<intent_id that survives>"],
  "rejected_intents": ["<intent_id that must withdraw>"]
}}"""

        user = f"""CONFLICT DETAILS:
{json.dumps(conflict_info, indent=2)}

ALICE'S POSITION:
{json.dumps(alice_position, indent=2)}

BOB'S POSITION:
{json.dumps(bob_position, indent=2)}

Render your decision."""

        raw = self._ask_claude(system, user)
        try:
            start = raw.index('{')
            end = raw.rindex('}') + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            # Fallback: pick Alice as winner
            return {
                "decision": "approved",
                "rationale": raw.strip()[:200],
                "winner_principal": "agent:Alice",
                "loser_principal": "agent:Bob",
                "accepted_intents": [],
                "rejected_intents": [],
            }


def phase(n, title):
    log.info(f"\n{'='*60}")
    log.info(f"  PHASE {n}: {title}")
    log.info(f"{'='*60}\n")


async def run_escalation():
    # ── Phase 0: Start coordinator ──────────────────────────────
    phase(0, "Start coordinator (governance profile)")

    coordinator = WSCoordinator(
        SESSION_ID, HOST, PORT,
        compliance_profile="governance",
        execution_model="post_commit",
        resolution_timeout_sec=300.0,
    )
    server_task = asyncio.create_task(coordinator.run())
    await asyncio.sleep(1.0)
    log.info(f"Coordinator running on ws://{HOST}:{PORT}")

    # ── Phase 1: Agents + Arbiter connect ────────────────────────
    phase(1, "Agents + Arbiter connect (HELLO)")

    alice = ExtendedWSAgent("Alice", "Frontend architect — owns UI component structure",
                            roles=["owner"])
    bob = ExtendedWSAgent("Bob", "UX engineer — owns user interaction patterns",
                          roles=["owner"])
    arbiter = ExtendedWSAgent("Arbiter", "Senior tech lead — final authority on design disputes",
                              roles=["arbiter"],
                              principal_id="human:arbiter")

    uri = f"ws://{HOST}:{PORT}"
    await asyncio.gather(
        alice.connect(uri, SESSION_ID),
        bob.connect(uri, SESSION_ID),
        arbiter.connect(uri, SESSION_ID),
    )

    for agent in [alice, bob, arbiter]:
        resp = await agent.do_hello()
        if resp:
            roles = resp["payload"].get("granted_roles", [])
            log.info(f"  {agent.name} joined — roles={roles}")

    # ── Phase 2: Intent decisions via Claude ─────────────────────
    phase(2, "Intent decisions via Claude (parallel)")

    loop = asyncio.get_event_loop()

    alice_intent, bob_intent = await asyncio.gather(
        loop.run_in_executor(EXECUTOR, alice.decide_intent, PROJECT_CONTEXT, []),
        loop.run_in_executor(EXECUTOR, bob.decide_intent, PROJECT_CONTEXT, []),
    )

    # Ensure both target overlapping files (nav.tsx, layout.css)
    alice_intent["files"] = ["components/nav.tsx", "styles/layout.css", "hooks/useNavigation.ts"]
    alice_intent["intent_id"] = f"intent-alice-{uuid.uuid4().hex[:6]}"
    alice_intent["objective"] = alice_intent.get("objective",
        "Redesign nav as responsive mega-menu with dropdown panels")

    bob_intent["files"] = ["components/nav.tsx", "styles/layout.css", "components/sidebar.tsx"]
    bob_intent["intent_id"] = f"intent-bob-{uuid.uuid4().hex[:6]}"
    bob_intent["objective"] = bob_intent.get("objective",
        "Refactor nav into mobile-first hamburger menu")

    log.info(f"  Alice: {alice_intent['objective'][:60]}...")
    log.info(f"         files: {alice_intent['files']}")
    log.info(f"  Bob:   {bob_intent['objective'][:60]}...")
    log.info(f"         files: {bob_intent['files']}")

    # ── Phase 3: INTENT_ANNOUNCE → CONFLICT_REPORT ───────────────
    phase(3, "INTENT_ANNOUNCE → CONFLICT_REPORT")

    await alice.do_announce_intent(alice_intent)
    log.info(f"  Alice announced: {alice_intent['intent_id']}")
    await bob.do_announce_intent(bob_intent)
    log.info(f"  Bob announced: {bob_intent['intent_id']}")

    # Collect conflict reports
    for agent in [alice, bob, arbiter]:
        await agent.drain_inbox(duration=2.0)

    conflict = None
    for agent in [alice, bob]:
        if agent.conflicts_received:
            conflict = agent.conflicts_received[0]
            break

    if not conflict:
        log.warning("  No conflict detected — agents chose non-overlapping files")
        # Force a conflict by having coordinator detect it
        for agent in [alice, bob, arbiter]:
            await agent.drain_inbox(duration=2.0)
        if alice.conflicts_received:
            conflict = alice.conflicts_received[0]

    if conflict:
        conflict_id = conflict["payload"]["conflict_id"]
        log.info(f"  CONFLICT detected: {conflict_id}")
        log.info(f"  Related intents: {conflict['payload'].get('related_intents', [])}")
    else:
        log.error("  No conflict — cannot proceed with escalation demo")
        server_task.cancel()
        return

    # ── Phase 4: Both agents ACK as "disputed" ───────────────────
    phase(4, "CONFLICT_ACK — both agents dispute")

    # Get positions from Claude
    alice_position = await loop.run_in_executor(
        EXECUTOR, alice.decide_on_conflict,
        conflict["payload"], alice_intent, bob_intent,
    )
    bob_position = await loop.run_in_executor(
        EXECUTOR, bob.decide_on_conflict,
        conflict["payload"], bob_intent, alice_intent,
    )

    log.info(f"  Alice's position: {alice_position.get('response', '?')} — {alice_position.get('reasoning', '')[:80]}")
    log.info(f"  Bob's position:   {bob_position.get('response', '?')} — {bob_position.get('reasoning', '')[:80]}")

    await alice.do_conflict_ack(conflict_id, "disputed")
    log.info(f"  Alice ACKed as 'disputed'")
    await bob.do_conflict_ack(conflict_id, "disputed")
    log.info(f"  Bob ACKed as 'disputed'")

    # ── Phase 5: CONFLICT_ESCALATE to arbiter ────────────────────
    phase(5, "CONFLICT_ESCALATE — Alice escalates to arbiter")

    await alice.do_escalate_conflict(
        conflict_id,
        escalate_to=arbiter.principal_id,
        reason="Both owners dispute the conflict; arbiter decision needed",
        context=f"Alice wants mega-menu; Bob wants hamburger menu. "
                f"Both approaches require changes to the same core files.",
    )
    log.info(f"  Conflict escalated to {arbiter.principal_id}")

    # Arbiter receives the escalation
    await arbiter.drain_inbox(duration=2.0)

    # Verify conflict state
    coord_conflict = coordinator.coordinator.conflicts.get(conflict_id)
    if coord_conflict:
        log.info(f"  Conflict state: {coord_conflict.state_machine.current_state}")
        log.info(f"  Escalated to: {getattr(coord_conflict, 'escalated_to', '?')}")

    # ── Phase 6: Arbiter resolves via Claude ─────────────────────
    phase(6, "Arbiter resolves — Claude analyzes both positions")

    arbiter_decision = await loop.run_in_executor(
        EXECUTOR, arbiter.decide_as_arbiter,
        conflict["payload"], alice_position, bob_position,
    )

    winner = arbiter_decision.get("winner_principal", "agent:Alice")
    loser = arbiter_decision.get("loser_principal", "agent:Bob")
    rationale = arbiter_decision.get("rationale", "Arbiter decision")

    log.info(f"  Arbiter decision: {arbiter_decision.get('decision', '?')}")
    log.info(f"  Winner: {winner}")
    log.info(f"  Rationale: {rationale[:100]}...")

    # Build outcome
    accepted = arbiter_decision.get("accepted_intents", [])
    rejected = arbiter_decision.get("rejected_intents", [])
    # Ensure we have valid intent IDs
    if not accepted or not rejected:
        if winner == alice.principal_id:
            accepted = [alice_intent["intent_id"]]
            rejected = [bob_intent["intent_id"]]
        else:
            accepted = [bob_intent["intent_id"]]
            rejected = [alice_intent["intent_id"]]

    await arbiter.do_resolve_conflict(
        conflict_id,
        decision="human_override",
        rationale=rationale,
        outcome={"accepted": accepted, "rejected": rejected, "merged": []},
    )
    log.info(f"  Resolution sent: accepted={accepted}, rejected={rejected}")

    # Drain all inboxes
    for agent in [alice, bob, arbiter]:
        await agent.drain_inbox(duration=1.5)

    # ── Phase 7: Losing agent withdraws, winner commits ──────────
    phase(7, "Loser withdraws intent, winner commits")

    # Determine winner/loser agents
    if winner == alice.principal_id:
        winner_agent, winner_intent = alice, alice_intent
        loser_agent, loser_intent = bob, bob_intent
    else:
        winner_agent, winner_intent = bob, bob_intent
        loser_agent, loser_intent = alice, alice_intent

    log.info(f"  {loser_agent.name} withdrawing intent: {loser_intent['intent_id']}")
    await loser_agent.do_intent_withdraw(
        loser_intent["intent_id"],
        reason=f"Arbiter ruled in favor of {winner_agent.name}'s approach",
    )

    # Winner commits their operation
    winner_op = await loop.run_in_executor(
        EXECUTOR, winner_agent.plan_operation, winner_intent)
    winner_op["op_id"] = f"op-{winner_agent.name.lower()}-{uuid.uuid4().hex[:6]}"
    winner_op["target"] = winner_intent["files"][0]

    log.info(f"  {winner_agent.name} committing: {winner_op['op_id']} on {winner_op['target']}")
    await winner_agent.do_commit(winner_intent, winner_op)
    log.info(f"  {winner_agent.name} committed successfully")

    # ── Phase 8: Verification + cleanup ──────────────────────────
    phase(8, "Verification + cleanup")

    # State snapshot
    snapshot = coordinator.coordinator.snapshot()
    log.info(f"  Lamport clock: {snapshot['lamport_clock']}")
    log.info(f"  Intents:")
    for intent in snapshot.get("intents", []):
        log.info(f"    {intent['intent_id']}: state={intent['state']}, owner={intent['principal_id']}")
    log.info(f"  Conflicts:")
    for cid, conf in coordinator.coordinator.conflicts.items():
        state = conf.state_machine.current_state
        esc = getattr(conf, 'escalated_to', None)
        log.info(f"    {cid}: state={state}, escalated_to={esc}")

    # Message type coverage check
    transcript = coordinator.transcript
    msg_types = set(t.get("message_type") for t in transcript if "message_type" in t)
    target_types = {"CONFLICT_ACK", "CONFLICT_ESCALATE", "RESOLUTION"}
    covered = target_types & msg_types
    missing = target_types - msg_types
    log.info(f"\n  Target message types covered: {sorted(covered)}")
    if missing:
        log.warning(f"  Missing: {sorted(missing)}")
    else:
        log.info(f"  ALL target message types exercised!")

    # All message types in transcript
    log.info(f"  All message types in transcript: {sorted(msg_types)}")

    # Goodbye
    for agent in [alice, bob, arbiter]:
        await agent.do_goodbye("session_complete")
    log.info(f"  All agents disconnected")

    # Save transcript
    transcript_path = os.path.join(os.path.dirname(__file__), "escalation_transcript.json")
    coordinator.save_transcript(transcript_path)
    log.info(f"  Transcript saved to {transcript_path}")

    # Cleanup
    server_task.cancel()
    log.info(f"\n{'='*60}")
    log.info(f"  DEMO COMPLETE")
    log.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(run_escalation())
