#!/usr/bin/env python3
"""
MPAC Family Trip Agent — an AI agent specialized for trip planning.

Each agent represents one family member's preferences and constraints.
Uses Claude API for decision-making: intent planning, conflict negotiation,
and itinerary generation.

NOTE: This module calls the Anthropic API. You will need a valid API key
      in local_config.json.
"""
import sys, os, json, asyncio, uuid, logging, time, hashlib
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))

import anthropic
import websockets
from mpac.models import Scope, MessageType
from mpac.participant import Participant

# Load config
_cfg_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'local_config.json')
with open(_cfg_path) as f:
    _cfg = json.load(f)["anthropic"]

_client = anthropic.Anthropic(api_key=_cfg["api_key"])
_model = _cfg.get("model", "claude-sonnet-4-6")


class TripAgent:
    """An AI agent that plans trips on behalf of a family member."""

    def __init__(
        self,
        name: str,
        principal_id: str,
        role_description: str,
        preferences: str,
        constraints: str,
        responsibilities: List[str],
        roles: List[str] = None,
    ):
        self.name = name
        self.principal_id = principal_id
        self.role_description = role_description
        self.preferences = preferences
        self.constraints = constraints
        self.responsibilities = responsibilities

        self.participant = Participant(
            principal_id=principal_id,
            principal_type="agent",
            display_name=name,
            roles=roles or ["contributor"],
            capabilities=[
                "intent.broadcast", "op.propose", "op.commit",
                "op.batch_commit", "conflict.report",
            ],
        )
        self.ws = None
        self.session_id = None
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.my_intents: List[dict] = []
        self.my_ops: List[dict] = []
        self.conflicts_received: List[dict] = []
        self.session_info: dict | None = None
        self._listener_task = None
        self.log = logging.getLogger(f"agent.{name}")

    # ── Claude API ──────────────────────────────────────────────

    def _ask_claude(self, system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> str:
        resp = _client.messages.create(
            model=_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text

    def _parse_json(self, raw: str, fallback: dict) -> dict:
        try:
            start = raw.index('{')
            end = raw.rindex('}') + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            return fallback

    def _system_prompt(self) -> str:
        return f"""You are {self.name}'s AI travel planning agent.

ROLE: {self.role_description}

PRINCIPAL'S PREFERENCES:
{self.preferences}

CONSTRAINTS:
{self.constraints}

RESPONSIBILITIES: {', '.join(self.responsibilities)}

You participate in the MPAC (Multi-Principal Agent Coordination) protocol to coordinate with other family members' agents. You advocate for your principal's preferences while being willing to compromise for family harmony.

IMPORTANT: Always respond with ONLY a JSON object. No markdown fences, no explanations outside the JSON."""

    def decide_intent(self, trip_context: str, other_intents: List[dict]) -> dict:
        """Decide what to plan, returning an intent declaration."""
        user = f"""TRIP CONTEXT:
{trip_context}

OTHER AGENTS' INTENTS (already announced):
{json.dumps(other_intents, indent=2, ensure_ascii=False) if other_intents else "None yet — you're first."}

Based on your principal's preferences and your responsibilities, decide what part of the trip to plan.
Reply with ONLY a JSON object:
{{
  "intent_id": "intent-{self.name.lower().replace(' ', '-')}-<short-slug>",
  "objective": "<1-2 sentences: what you plan to arrange>",
  "scope_resources": ["itinerary://day-1", "budget://transportation", ...],
  "assumptions": ["<key assumption 1>", "<key assumption 2>", ...],
  "priority": "high" or "normal"
}}

AVAILABLE RESOURCES:
- itinerary://day-1 through itinerary://day-5
- budget://total, budget://accommodation, budget://food, budget://transportation, budget://activities"""

        raw = self._ask_claude(self._system_prompt(), user)
        result = self._parse_json(raw, {
            "intent_id": f"intent-{self.name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
            "objective": "Plan trip activities",
            "scope_resources": [],
            "assumptions": [],
            "priority": "normal",
        })
        return result

    def respond_to_conflict(
        self, conflict_info: dict, own_intent: dict, other_intent: dict, other_agent_name: str
    ) -> dict:
        """Express position on a conflict."""
        user = f"""A CONFLICT has been detected between your plan and {other_agent_name}'s plan.

CONFLICT DETAILS:
{json.dumps(conflict_info, indent=2, ensure_ascii=False)}

YOUR INTENT:
{json.dumps(own_intent, indent=2, ensure_ascii=False)}

{other_agent_name.upper()}'S INTENT:
{json.dumps(other_intent, indent=2, ensure_ascii=False)}

Consider your principal's priorities but also family harmony. Propose a creative compromise if possible.

Reply with ONLY a JSON object:
{{
  "ack_type": "disputed" or "accepted",
  "position": "<your detailed position, including any compromise proposal>",
  "flexibility": "high" or "medium" or "low",
  "compromise_proposal": "<specific compromise suggestion, if any>"
}}"""

        raw = self._ask_claude(self._system_prompt(), user)
        return self._parse_json(raw, {
            "ack_type": "disputed",
            "position": raw.strip()[:300],
            "flexibility": "medium",
        })

    def generate_itinerary(
        self,
        day_numbers: List[int],
        resolution_context: str,
        other_committed_plans: str,
        budget_info: str,
    ) -> dict:
        """Generate detailed itinerary for assigned days."""
        user = f"""Generate a detailed itinerary for the day(s) you're responsible for.

DAYS TO PLAN: {', '.join(f'Day {d}' for d in day_numbers)}

RESOLUTION CONTEXT (agreements from conflict resolution):
{resolution_context}

OTHER AGENTS' COMMITTED PLANS:
{other_committed_plans}

BUDGET INFORMATION:
{budget_info}

Reply with ONLY a JSON object:
{{
  "plans": [
    {{
      "day": <day_number>,
      "target": "itinerary://day-<N>",
      "morning": "<morning activities with times>",
      "afternoon": "<afternoon activities with times>",
      "evening": "<evening activities with times>",
      "accommodation": "<where to stay, or null if last day>",
      "meals": "<meal plan, noting any dietary restrictions>",
      "estimated_cost": <cost in RMB>,
      "notes": "<any important notes>"
    }}
  ],
  "budget_breakdown": {{
    "<category>": <amount>,
    ...
  }}
}}"""

        raw = self._ask_claude(self._system_prompt(), user, max_tokens=4096)
        return self._parse_json(raw, {
            "plans": [{"day": d, "target": f"itinerary://day-{d}",
                        "morning": "TBD", "afternoon": "TBD", "evening": "TBD",
                        "accommodation": "TBD", "meals": "TBD",
                        "estimated_cost": 0, "notes": ""} for d in day_numbers],
            "budget_breakdown": {},
        })

    # ── WebSocket communication ─────────────────────────────────

    async def connect(self, uri: str, session_id: str):
        self.session_id = session_id
        self.ws = await websockets.connect(uri)
        self._listener_task = asyncio.create_task(self._listen())
        self.log.info(f"Connected to {uri}")

    async def _listen(self):
        try:
            async for raw in self.ws:
                envelope = json.loads(raw)
                msg_type = envelope.get("message_type", "?")
                self.log.info(f"  <- {msg_type}")
                await self.inbox.put(envelope)
        except websockets.exceptions.ConnectionClosed:
            self.log.info("Connection closed")

    async def send(self, envelope: dict):
        msg_type = envelope.get("message_type", "?")
        self.log.info(f"  -> {msg_type}")
        await self.ws.send(json.dumps(envelope, ensure_ascii=False))

    async def recv(self, timeout: float = 30.0, filter_type: str = None) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                remaining = deadline - time.time()
                msg = await asyncio.wait_for(self.inbox.get(), timeout=max(0.1, remaining))
                if filter_type is None or msg.get("message_type") == filter_type:
                    return msg
                if msg.get("message_type") == "CONFLICT_REPORT":
                    self.conflicts_received.append(msg)
                elif msg.get("message_type") == "COORDINATOR_STATUS":
                    pass  # skip heartbeats
                else:
                    await self.inbox.put(msg)
            except asyncio.TimeoutError:
                continue
        return None

    async def drain_inbox(self, duration: float = 2.0):
        deadline = time.time() + duration
        while time.time() < deadline:
            try:
                remaining = deadline - time.time()
                msg = await asyncio.wait_for(self.inbox.get(), timeout=max(0.1, remaining))
                if msg.get("message_type") == "CONFLICT_REPORT":
                    self.conflicts_received.append(msg)
                    self.log.info(f"  Collected CONFLICT_REPORT: {msg['payload'].get('conflict_id', '?')}")
            except asyncio.TimeoutError:
                continue

    # ── MPAC message helpers ────────────────────────────────────

    async def do_hello(self):
        hello = self.participant.hello(self.session_id)
        await self.send(hello)
        resp = await self.recv(filter_type="SESSION_INFO")
        if resp:
            self.session_info = resp
            count = resp['payload'].get('participant_count', '?')
            self.log.info(f"  Joined session (participants: {count})")
        return resp

    async def do_announce_intent(self, intent_decision: dict):
        resources = intent_decision.get("scope_resources", [])
        # task_set scopes use task_ids field for overlap detection
        scope = Scope(kind="task_set", task_ids=resources)
        msg = self.participant.announce_intent(
            self.session_id,
            intent_decision["intent_id"],
            intent_decision["objective"],
            scope,
            ttl_sec=3600,
        )
        # Inject assumptions into payload
        msg["payload"]["assumptions"] = intent_decision.get("assumptions", [])
        msg["payload"]["priority"] = intent_decision.get("priority", "normal")
        self.my_intents.append(intent_decision)
        await self.send(msg)
        await asyncio.sleep(0.5)

    async def do_conflict_ack(self, conflict_id: str, ack_type: str, position: str):
        """Send CONFLICT_ACK with position."""
        msg = self.participant.ack_conflict(self.session_id, conflict_id, ack_type)
        msg["payload"]["position"] = position
        await self.send(msg)

    async def do_commit(self, intent_id: str, op_id: str, target: str,
                        summary: str, state_ref_before: str, state_ref_after: str):
        msg = self.participant.commit_op(
            self.session_id, op_id, intent_id, target, "create",
            state_ref_before=state_ref_before,
            state_ref_after=state_ref_after,
        )
        msg["payload"]["summary"] = summary
        await self.send(msg)
        await asyncio.sleep(0.3)
        # Check for rejection
        rejected = False
        try:
            while not self.inbox.empty():
                m = self.inbox.get_nowait()
                mt = m.get("message_type", "")
                if mt == "PROTOCOL_ERROR":
                    ec = m.get("payload", {}).get("error_code", "")
                    if ec == "STALE_STATE_REF":
                        self.log.warning(f"  STALE_STATE_REF on {target}!")
                        rejected = True
                    else:
                        self.log.error(f"  PROTOCOL_ERROR: {ec}")
                elif mt == "CONFLICT_REPORT":
                    self.conflicts_received.append(m)
                elif mt == "COORDINATOR_STATUS":
                    pass
                else:
                    await self.inbox.put(m)
        except asyncio.QueueEmpty:
            pass
        return not rejected

    async def do_batch_commit(self, intent_id: str, batch_id: str,
                              entries: List[dict], atomicity: str = "all_or_nothing"):
        msg = self.participant.batch_commit_op(
            self.session_id, batch_id, entries,
            atomicity=atomicity, intent_id=intent_id,
        )
        await self.send(msg)
        await asyncio.sleep(0.5)

    async def do_goodbye(self, reason: str = "session_complete"):
        msg = self.participant.goodbye(self.session_id, reason=reason)
        await self.send(msg)

    async def close(self):
        if self._listener_task:
            self._listener_task.cancel()
        if self.ws:
            await self.ws.close()
            self.log.info("Disconnected")


def content_hash(text: str) -> str:
    """SHA-256 hash (first 16 hex chars) of text content."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]
