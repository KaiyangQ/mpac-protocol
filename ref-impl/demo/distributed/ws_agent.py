#!/usr/bin/env python3
from __future__ import annotations
"""
MPAC WebSocket Agent Client.

An AI agent that connects to the coordinator over WebSocket,
makes decisions via Claude API, and communicates through MPAC messages.

Runs as a standalone process — multiple agents can connect concurrently.

NOTE: This module calls the Anthropic API. You will need a valid API key
      in local_config.json.
"""
import sys, os, json, asyncio, uuid, logging, time

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


class WSAgent:
    """An AI agent that communicates with the coordinator over WebSocket."""

    def __init__(self, name: str, role_description: str, principal_id: str = None):
        self.name = name
        self.role_description = role_description
        self.principal_id = principal_id or f"agent:{name}"
        self.participant = Participant(
            principal_id=self.principal_id,
            principal_type="agent",
            display_name=name,
            roles=["contributor"],
            capabilities=["intent.broadcast", "op.propose", "op.commit", "op.batch_commit"],
        )
        self.ws = None
        self.session_id = None
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.my_intent: dict | None = None
        self.my_ops: list[dict] = []
        self.conflicts_received: list[dict] = []
        self.session_info: dict | None = None
        self.log = logging.getLogger(f"agent.{name}")

    # ── Claude API ──────────────────────────────────────────────

    def _ask_claude(self, system_prompt: str, user_prompt: str) -> str:
        resp = _client.messages.create(
            model=_model,
            max_tokens=1024,
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

    def decide_intent(self, project_context: str, existing_intents: list) -> dict:
        system = f"""You are {self.name}, an AI coding agent. {self.role_description}

You participate in a multi-agent coordination protocol (MPAC). You must decide what coding task to work on and express it as an intent.

Reply with ONLY a JSON object (no markdown, no explanation):
{{
  "intent_id": "intent-{self.name.lower()}-<short-slug>",
  "objective": "<one sentence describing what you plan to do>",
  "scope_kind": "file_set",
  "files": ["<file1>", "<file2>", ...]
}}"""

        existing_str = json.dumps(existing_intents, indent=2) if existing_intents else "None yet."
        user = f"""Project context:
{project_context}

Intents already announced by other agents:
{existing_str}

What do you want to work on? Pick specific files. You CAN overlap with others if you genuinely need those files — the protocol will handle conflicts."""

        raw = self._ask_claude(system, user)
        return self._parse_json(raw, {
            "intent_id": f"intent-{self.name.lower()}-{uuid.uuid4().hex[:6]}",
            "objective": raw.strip()[:200],
            "scope_kind": "file_set",
            "files": [],
        })

    def decide_on_conflict(self, conflict_info: dict, own_intent: dict, other_intent: dict) -> dict:
        system = f"""You are {self.name}, an AI coding agent. {self.role_description}

A scope overlap conflict has been detected. You need to decide how to respond.

Reply with ONLY a JSON object:
{{
  "response": "proceed" | "yield" | "negotiate",
  "reasoning": "<brief explanation>",
  "proposed_resolution": "<if negotiate, what do you suggest?>"
}}"""

        user = f"""CONFLICT DETECTED:
{json.dumps(conflict_info, indent=2)}

YOUR intent:
{json.dumps(own_intent, indent=2)}

OTHER agent's intent:
{json.dumps(other_intent, indent=2)}

How do you want to handle this?"""

        raw = self._ask_claude(system, user)
        return self._parse_json(raw, {"response": "proceed", "reasoning": raw.strip()[:200]})

    def plan_operation(self, intent: dict) -> dict:
        system = f"""You are {self.name}, an AI coding agent. {self.role_description}

You've announced an intent and now need to plan the specific code operation.

Reply with ONLY a JSON object:
{{
  "op_id": "op-{self.name.lower()}-<short-slug>",
  "target": "<primary file being changed>",
  "op_kind": "replace" | "insert" | "delete" | "patch",
  "summary": "<brief description of the change>",
  "state_ref_before": "<mock hash representing current state>",
  "state_ref_after": "<mock hash representing state after change>"
}}"""

        user = f"""Your intent:
{json.dumps(intent, indent=2)}

Plan the specific code operation."""

        raw = self._ask_claude(system, user)
        return self._parse_json(raw, {
            "op_id": f"op-{self.name.lower()}-{uuid.uuid4().hex[:6]}",
            "target": intent.get("files", ["unknown"])[0],
            "op_kind": "patch",
            "summary": "code change",
            "state_ref_before": f"sha256:{uuid.uuid4().hex[:12]}",
            "state_ref_after": f"sha256:{uuid.uuid4().hex[:12]}",
        })

    # ── WebSocket communication ─────────────────────────────────

    async def connect(self, uri: str, session_id: str):
        """Connect to coordinator and start listening."""
        self.session_id = session_id
        self.ws = await websockets.connect(uri)
        self.log.info(f"Connected to {uri}")

        # Start listener task
        self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self):
        """Background task: read messages from WebSocket into inbox."""
        try:
            async for raw in self.ws:
                envelope = json.loads(raw)
                msg_type = envelope.get("message_type", "?")
                self.log.info(f"← Received: {msg_type}")
                await self.inbox.put(envelope)
        except websockets.exceptions.ConnectionClosed:
            self.log.info("Connection closed by server")

    async def send(self, envelope: dict):
        """Send an MPAC envelope over WebSocket."""
        msg_type = envelope.get("message_type", "?")
        self.log.info(f"→ Sending: {msg_type}")
        await self.ws.send(json.dumps(envelope, ensure_ascii=False))

    async def recv(self, timeout: float = 30.0, filter_type: str = None) -> dict | None:
        """Receive next message from inbox, optionally filtering by type."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                remaining = deadline - time.time()
                msg = await asyncio.wait_for(self.inbox.get(), timeout=max(0.1, remaining))
                if filter_type is None or msg.get("message_type") == filter_type:
                    return msg
                # Not the type we want, but save it for later (e.g. conflict reports)
                if msg.get("message_type") == "CONFLICT_REPORT":
                    self.conflicts_received.append(msg)
                elif msg.get("message_type") == "COORDINATOR_STATUS":
                    pass  # ignore heartbeats while waiting
                else:
                    await self.inbox.put(msg)  # put back
            except asyncio.TimeoutError:
                continue
        return None

    async def drain_inbox(self, duration: float = 2.0):
        """Drain inbox for a short time, collecting any conflict reports."""
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
        """Send HELLO and wait for SESSION_INFO."""
        hello = self.participant.hello(self.session_id)
        await self.send(hello)
        resp = await self.recv(filter_type="SESSION_INFO")
        if resp:
            self.session_info = resp
            self.log.info(f"  Joined session. Participants: {resp['payload'].get('participant_count', '?')}")
        return resp

    async def do_announce_intent(self, intent_decision: dict):
        """Send INTENT_ANNOUNCE."""
        scope = Scope(kind="file_set", resources=intent_decision.get("files", []))
        msg = self.participant.announce_intent(
            self.session_id,
            intent_decision["intent_id"],
            intent_decision["objective"],
            scope,
        )
        self.my_intent = intent_decision
        await self.send(msg)
        # Give coordinator time to process and potentially send conflict reports
        await asyncio.sleep(0.5)

    async def do_commit(self, intent_decision: dict, op_plan: dict):
        """Send OP_COMMIT."""
        msg = self.participant.commit_op(
            self.session_id,
            op_plan["op_id"],
            intent_decision["intent_id"],
            op_plan["target"],
            op_plan["op_kind"],
            state_ref_before=op_plan.get("state_ref_before"),
            state_ref_after=op_plan.get("state_ref_after"),
        )
        self.my_ops.append(op_plan)
        await self.send(msg)
        await asyncio.sleep(0.3)

    async def do_heartbeat(self, status: str = "working"):
        """Send HEARTBEAT."""
        msg = self.participant.heartbeat(self.session_id, status=status)
        await self.send(msg)

    async def do_goodbye(self, reason: str = "completed"):
        """Send GOODBYE."""
        msg = self.participant.goodbye(self.session_id, reason=reason)
        await self.send(msg)

    async def close(self):
        """Close WebSocket connection."""
        if self._listener_task:
            self._listener_task.cancel()
        if self.ws:
            await self.ws.close()
            self.log.info("Disconnected")
