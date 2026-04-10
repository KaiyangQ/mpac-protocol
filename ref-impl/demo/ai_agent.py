"""AI Agent wrapper — connects a Claude LLM to an MPAC Participant.

NOTE: This demo calls the Anthropic API (~6 requests per run).
      You will need a valid API key in local_config.json.
"""
import sys, os, json, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

import anthropic
from mpac.models import Scope, MessageType
from mpac.participant import Participant


# Load config
_cfg_path = os.path.join(os.path.dirname(__file__), '..', '..', 'local_config.json')
with open(_cfg_path) as f:
    _cfg = json.load(f)["anthropic"]

_client = anthropic.Anthropic(api_key=_cfg["api_key"])
_model = _cfg.get("model", "claude-sonnet-4-6")


class AIAgent:
    """An AI agent that uses Claude to make MPAC protocol decisions."""

    def __init__(self, name: str, role_description: str, session_id: str):
        self.name = name
        self.role_description = role_description
        self.session_id = session_id
        self.participant = Participant(
            principal_id=f"agent:{name}",
            principal_type="agent",
            display_name=name,
            roles=["contributor"],
            capabilities=["intent.broadcast", "op.propose", "op.commit", "op.batch_commit"],
        )
        self.message_log = []  # all MPAC messages this agent has seen

    def _ask_claude(self, system_prompt: str, user_prompt: str) -> str:
        """Call Claude API and return text response."""
        resp = _client.messages.create(
            model=_model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text

    def decide_intent(self, project_context: str, existing_intents: list) -> dict:
        """Ask Claude to decide what work to announce as an intent."""
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
        # Extract JSON from response
        try:
            # Try to find JSON in the response
            start = raw.index('{')
            end = raw.rindex('}') + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            return {
                "intent_id": f"intent-{self.name.lower()}-{uuid.uuid4().hex[:6]}",
                "objective": raw.strip()[:200],
                "scope_kind": "file_set",
                "files": []
            }

    def decide_on_conflict(self, conflict_info: dict, own_intent: dict, other_intent: dict) -> dict:
        """Ask Claude how to respond to a scope overlap conflict."""
        system = f"""You are {self.name}, an AI coding agent. {self.role_description}

A scope overlap conflict has been detected between your intent and another agent's intent.
You need to decide how to respond.

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
        try:
            start = raw.index('{')
            end = raw.rindex('}') + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            return {"response": "proceed", "reasoning": raw.strip()[:200]}

    def plan_operation(self, intent: dict) -> dict:
        """Ask Claude to plan the actual code change operation."""
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
        try:
            start = raw.index('{')
            end = raw.rindex('}') + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            return {
                "op_id": f"op-{self.name.lower()}-{uuid.uuid4().hex[:6]}",
                "target": intent.get("files", ["unknown"])[0],
                "op_kind": "replace",
                "summary": "code change",
                "state_ref_before": f"sha256:{uuid.uuid4().hex[:12]}",
                "state_ref_after": f"sha256:{uuid.uuid4().hex[:12]}",
            }

    # ---- MPAC message helpers ----

    def send_hello(self):
        return self.participant.hello(self.session_id)

    def send_intent(self, intent_decision: dict):
        scope = Scope(kind="file_set", resources=intent_decision.get("files", []))
        return self.participant.announce_intent(
            self.session_id,
            intent_decision["intent_id"],
            intent_decision["objective"],
            scope,
        )

    def send_op_commit(self, intent_decision: dict, op_plan: dict):
        return self.participant.commit_op(
            self.session_id,
            op_plan["op_id"],
            intent_decision["intent_id"],
            op_plan["target"],
            op_plan["op_kind"],
            state_ref_before=op_plan.get("state_ref_before"),
            state_ref_after=op_plan.get("state_ref_after"),
        )
