"""
MPAC Agent — autonomous AI agent that coordinates via MPAC protocol.

Connects to an MPACServer, reads shared workspace files, uses Claude to
decide what to work on, and commits changes through the protocol.
"""
from __future__ import annotations

import json
import asyncio
import uuid
import hashlib
import logging
import difflib
import time

import anthropic
import websockets

from .core.models import Scope, MessageType
from .core.participant import Participant

log = logging.getLogger("mpac.agent")


# ── Pretty terminal output helpers ─────────────────────────────

def _box(title: str, lines: list[str], width: int = 64):
    """Print a bordered box."""
    print()
    print(f"  +{'-' * (width - 2)}+")
    print(f"  | {title:<{width - 4}} |")
    print(f"  +{'-' * (width - 2)}+")
    for line in lines:
        # Truncate long lines
        display = line[:width - 4]
        print(f"  | {display:<{width - 4}} |")
    print(f"  +{'-' * (width - 2)}+")
    print()


def _header(text: str):
    print()
    print(f"  {'=' * 60}")
    print(f"    {text}")
    print(f"  {'=' * 60}")


def _show_file(path: str, content: str, max_lines: int = 40):
    """Display file content with line numbers."""
    lines = content.split("\n")
    print(f"\n  --- {path} ({len(lines)} lines) ---")
    for i, line in enumerate(lines[:max_lines], 1):
        print(f"  {i:4d} | {line}")
    if len(lines) > max_lines:
        print(f"  ... ({len(lines) - max_lines} more lines)")
    print(f"  --- end {path} ---\n")


def _show_diff(path: str, before: str, after: str):
    """Show unified diff between before and after."""
    diff = list(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"before/{path}",
        tofile=f"after/{path}",
    ))
    if not diff:
        print(f"  (no changes to {path})")
        return

    print(f"\n  --- Changes to {path} ---")
    for line in diff:
        line = line.rstrip("\n")
        if line.startswith("+") and not line.startswith("+++"):
            print(f"  \033[32m{line}\033[0m")  # green
        elif line.startswith("-") and not line.startswith("---"):
            print(f"  \033[31m{line}\033[0m")  # red
        elif line.startswith("@@"):
            print(f"  \033[36m{line}\033[0m")  # cyan
        else:
            print(f"  {line}")
    print()


# ── MPACAgent ──────────────────────────────────────────────────

class MPACAgent:
    """Self-contained MPAC agent that connects to a server and runs tasks autonomously."""

    def __init__(
        self,
        name: str,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        role_description: str = "A collaborative AI coding agent",
    ):
        self.name = name
        self.principal_id = f"agent:{name}"
        self.role_description = role_description
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.participant = Participant(
            principal_id=self.principal_id,
            principal_type="agent",
            display_name=name,
            roles=["contributor"],
            capabilities=["intent.broadcast", "op.propose", "op.commit"],
        )
        self.ws = None
        self.session_id = None
        self.protocol_inbox: asyncio.Queue = asyncio.Queue()
        self.sideband_inbox: asyncio.Queue = asyncio.Queue()
        self._listener_task = None
        self._event_printer_task = None
        self.conflicts_received: list[dict] = []
        self.log = logging.getLogger(f"mpac.agent.{name}")

    # ── WebSocket communication ────────────────────────────────

    async def connect(self, uri: str, session_id: str):
        """Connect to MPAC server."""
        self.session_id = session_id
        # Add ngrok header for free-tier compatibility
        headers = {}
        if "ngrok" in uri:
            headers["ngrok-skip-browser-warning"] = "true"
        self.ws = await websockets.connect(uri, additional_headers=headers)
        self._listener_task = asyncio.create_task(self._listen())
        self.log.info(f"Connected to {uri}")

    async def _listen(self):
        """Background: route incoming messages to correct queue."""
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                if "message_type" in data:
                    # Print real-time events for the user to see
                    self._print_event(data)
                    await self.protocol_inbox.put(data)
                else:
                    await self.sideband_inbox.put(data)
        except websockets.exceptions.ConnectionClosed:
            self.log.info("Connection closed")
        except Exception as e:
            self.log.error(f"Listener error: {e}")

    def _print_event(self, msg: dict):
        """Print important protocol events in real-time so user sees activity."""
        mt = msg.get("message_type", "")
        payload = msg.get("payload", {})
        sender = msg.get("sender", {}).get("principal_id", "?")

        # Only print events from OTHER agents (not self)
        if sender == self.principal_id:
            return

        if mt == "INTENT_ANNOUNCE":
            obj = payload.get("objective", "?")
            scope = payload.get("scope", {})
            files = scope.get("resources", [])
            print(f"\n  >> {sender} announced intent: {obj}")
            print(f"     Files: {files}")
        elif mt == "OP_COMMIT":
            target = payload.get("target", "?")
            ref = payload.get("state_ref_after", "?")
            print(f"\n  >> {sender} committed changes to: {target} ({ref})")
        elif mt == "CONFLICT_REPORT":
            cat = payload.get("category", "?")
            print(f"\n  >> CONFLICT detected! Category: {cat}")
        elif mt == "HELLO":
            principal = payload.get("principal", {})
            name = principal.get("display_name", sender)
            print(f"\n  >> {name} joined the session")
        elif mt == "GOODBYE":
            print(f"\n  >> {sender} left the session")

    async def _send(self, data: dict):
        """Send JSON over WebSocket."""
        await self.ws.send(json.dumps(data, ensure_ascii=False))

    async def _recv_protocol(self, timeout: float = 30.0,
                             filter_type: str = None) -> dict | None:
        """Receive next MPAC protocol message."""
        deadline = time.time() + timeout
        stash = []
        while time.time() < deadline:
            try:
                remaining = max(0.1, deadline - time.time())
                msg = await asyncio.wait_for(self.protocol_inbox.get(), timeout=remaining)
                msg_type = msg.get("message_type", "")
                if filter_type is None or msg_type == filter_type:
                    for s in stash:
                        await self.protocol_inbox.put(s)
                    return msg
                if msg_type == "CONFLICT_REPORT":
                    self.conflicts_received.append(msg)
                elif msg_type == "COORDINATOR_STATUS":
                    pass
                else:
                    stash.append(msg)
            except asyncio.TimeoutError:
                continue
        for s in stash:
            await self.protocol_inbox.put(s)
        return None

    async def _recv_sideband(self, timeout: float = 10.0,
                             filter_type: str = None) -> dict | None:
        """Receive next sideband message."""
        deadline = time.time() + timeout
        stash = []
        while time.time() < deadline:
            try:
                remaining = max(0.1, deadline - time.time())
                msg = await asyncio.wait_for(self.sideband_inbox.get(), timeout=remaining)
                msg_type = msg.get("type", "")
                if filter_type is None or msg_type == filter_type:
                    for s in stash:
                        await self.sideband_inbox.put(s)
                    return msg
                stash.append(msg)
            except asyncio.TimeoutError:
                continue
        for s in stash:
            await self.sideband_inbox.put(s)
        return None

    async def _drain_conflicts(self, duration: float = 5.0):
        """Collect conflict reports for a while."""
        deadline = time.time() + duration
        while time.time() < deadline:
            try:
                remaining = max(0.1, deadline - time.time())
                msg = await asyncio.wait_for(self.protocol_inbox.get(), timeout=remaining)
                msg_type = msg.get("message_type", "")
                if msg_type == "CONFLICT_REPORT":
                    self.conflicts_received.append(msg)
            except asyncio.TimeoutError:
                continue

    # ── File operations (sideband) ─────────────────────────────

    async def list_files(self) -> list[dict]:
        """Get workspace file list from server."""
        await self._send({"type": "FILE_LIST"})
        resp = await self._recv_sideband(timeout=10.0, filter_type="FILE_LIST_RESPONSE")
        if resp:
            return resp.get("files", [])
        return []

    async def read_file(self, path: str) -> tuple[str, str] | None:
        """Read a file from server workspace. Returns (content, state_ref) or None."""
        await self._send({"type": "FILE_READ", "path": path})
        resp = await self._recv_sideband(timeout=10.0, filter_type="FILE_CONTENT")
        if resp and resp.get("type") == "FILE_CONTENT":
            return resp["content"], resp["state_ref"]
        return None

    # ── Claude API ─────────────────────────────────────────────

    def _ask_claude(self, system: str, user: str, max_tokens: int = 2048) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    def _parse_json(self, raw: str, fallback: dict) -> dict:
        try:
            start = raw.index('{')
            end = raw.rindex('}') + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            return fallback

    def _decide_intent(self, task: str, files_info: list[dict]) -> dict:
        file_summary = "\n".join(
            f"  - {f['path']} ({f['size']} bytes, ref: {f['state_ref']})"
            for f in files_info
        )
        system = f"""You are {self.name}, an AI coding agent. {self.role_description}

You participate in MPAC (Multi-Principal Agent Coordination Protocol).
Decide which files you need to modify for the given task.

Reply with ONLY a JSON object:
{{
  "intent_id": "intent-{self.name.lower()}-<short-slug>",
  "objective": "<one sentence: what you plan to do>",
  "files": ["<file1>", "<file2>"]
}}"""

        user = f"""YOUR TASK: {task}

Available workspace files:
{file_summary}

Pick the files you need to modify. Be specific."""

        raw = self._ask_claude(system, user)
        return self._parse_json(raw, {
            "intent_id": f"intent-{self.name.lower()}-{uuid.uuid4().hex[:6]}",
            "objective": task[:200],
            "files": [f["path"] for f in files_info[:1]],
        })

    def _decide_conflict(self, conflict: dict, own_intent: dict) -> str:
        system = f"""You are {self.name}. A scope conflict was detected with another agent.
Decide: 'proceed' (keep working, protocol will resolve) or 'yield' (withdraw your intent).
Reply with ONLY a JSON: {{"decision": "proceed"|"yield", "reason": "..."}}"""

        user = f"""CONFLICT:
{json.dumps(conflict, indent=2)}

YOUR INTENT:
{json.dumps(own_intent, indent=2)}"""

        raw = self._ask_claude(system, user, max_tokens=512)
        result = self._parse_json(raw, {"decision": "proceed", "reason": "defaulting to proceed"})
        return result.get("decision", "proceed")

    def _generate_fix(self, task: str, path: str, content: str,
                      other_agent_info: str = "") -> str:
        system = f"""You are {self.name}, an AI coding agent. {self.role_description}

You are given a Python source file. Fix it according to the objective.
Return ONLY the complete fixed file — no markdown fences, no explanations."""

        coordination = ""
        if other_agent_info:
            coordination = f"""
COORDINATION NOTE: Another agent is also working. Their work:
{other_agent_info}
Do NOT conflict with their changes. Focus only on your objective."""

        user = f"""OBJECTIVE: {task}
{coordination}
FILE: {path}

CURRENT CONTENT:
{content}

Return the complete fixed Python file."""

        result = self._ask_claude(system, user, max_tokens=4096)
        result = self._extract_code(result)
        return result

    @staticmethod
    def _extract_code(text: str) -> str:
        """Extract code from Claude response, stripping markdown fences and explanations."""
        # Find the last ```-fenced code block (most likely the complete file)
        import re
        blocks = list(re.finditer(
            r"```(?:python|py)?\s*\n(.*?)```",
            text, re.DOTALL,
        ))
        if blocks:
            # Use the last (or longest) fenced block — that's the full file
            best = max(blocks, key=lambda m: len(m.group(1)))
            return best.group(1).rstrip("\n")

        # No fenced block — strip a leading ``` line and trailing ``` if present
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)

    # ── MPAC message helpers ───────────────────────────────────

    async def _do_hello(self):
        msg = self.participant.hello(self.session_id)
        await self._send(msg)
        resp = await self._recv_protocol(filter_type="SESSION_INFO")
        if resp:
            count = resp.get("payload", {}).get("participant_count", "?")
            self.log.info(f"Joined session (participants: {count})")
        return resp

    async def _do_announce_intent(self, intent: dict):
        scope = Scope(kind="file_set", resources=intent.get("files", []))
        msg = self.participant.announce_intent(
            self.session_id,
            intent["intent_id"],
            intent["objective"],
            scope,
        )
        await self._send(msg)
        await asyncio.sleep(0.5)

    async def _do_commit(self, intent_id: str, op_id: str, target: str,
                         content: str, state_ref_before: str) -> bool:
        new_ref = "sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16]
        msg = self.participant.commit_op(
            self.session_id, op_id, intent_id, target, "replace",
            state_ref_before=state_ref_before,
            state_ref_after=new_ref,
        )
        msg["payload"]["file_changes"] = {
            target: {
                "content": content,
                "state_ref_before": state_ref_before,
            }
        }
        await self._send(msg)
        await asyncio.sleep(1.0)

        rejected = False
        try:
            while not self.protocol_inbox.empty():
                check = self.protocol_inbox.get_nowait()
                msg_type = check.get("message_type", "")
                if (msg_type == "PROTOCOL_ERROR" and
                        check.get("payload", {}).get("error_code") == "STALE_STATE_REF"):
                    rejected = True
                elif msg_type == "CONFLICT_REPORT":
                    self.conflicts_received.append(check)
        except asyncio.QueueEmpty:
            pass

        if rejected:
            return False
        return True

    async def _do_goodbye(self):
        msg = self.participant.goodbye(self.session_id, reason="completed")
        await self._send(msg)

    # ── Interactive workflow ───────────────────────────────────

    async def run_interactive(self):
        """Interactive mode: show files, ask user what to do, show diff."""

        _header(f"{self.name} - MPAC Collaborative Agent")

        # 1. Join
        print("  Connecting to session...")
        await self._do_hello()

        # 2. Show workspace files
        files = await self.list_files()
        file_lines = []
        for f in files:
            file_lines.append(f"{f['path']:20s}  {f['size']:>6d} bytes  {f['state_ref']}")
        _box(f"Workspace ({len(files)} files)", file_lines)

        # 3. Ask user which files to view
        while True:
            print("  Commands:")
            print("    view <filename>    - View file content")
            print("    task <description> - Start working on a task")
            print("    quit               - Leave session")
            print()
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input(f"  [{self.name}] > ")
                )
            except (EOFError, KeyboardInterrupt):
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.lower() == "quit":
                break

            if user_input.lower().startswith("view "):
                fname = user_input[5:].strip()
                result = await self.read_file(fname)
                if result:
                    content, ref = result
                    _show_file(fname, content)
                else:
                    print(f"  File not found: {fname}")
                continue

            if user_input.lower().startswith("task "):
                task = user_input[5:].strip()
                if task:
                    await self._run_task_interactive(task, files)
                    # Refresh file list after task
                    files = await self.list_files()
                    file_lines = []
                    for f in files:
                        file_lines.append(f"{f['path']:20s}  {f['size']:>6d} bytes  {f['state_ref']}")
                    _box(f"Updated Workspace ({len(files)} files)", file_lines)
                continue

            print(f"  Unknown command. Try: view <file>, task <description>, quit")

        # Goodbye
        print(f"\n  {self.name} leaving session...")
        await self._do_goodbye()

    async def _run_task_interactive(self, task: str, files: list[dict]):
        """Run a task with full visual feedback."""

        _header(f"Task: {task}")

        # Clear any stale conflicts from previous tasks
        self.conflicts_received = []

        # 1. Decide intent
        print("  [1/4] Analyzing workspace and planning... (calling Claude)")
        intent = await asyncio.get_event_loop().run_in_executor(
            None, self._decide_intent, task, files
        )

        target_files = intent.get("files", [])
        _box("Plan", [
            f"Objective: {intent.get('objective', '?')}",
            f"Files to modify: {', '.join(target_files)}",
        ])

        # 2. Show the files that will be modified
        print("  [2/4] Reading target files...")
        originals = {}  # path -> (content, state_ref)
        for fname in target_files:
            result = await self.read_file(fname)
            if result:
                content, ref = result
                originals[fname] = (content, ref)
                _show_file(fname, content)
            else:
                print(f"  WARNING: {fname} not found in workspace")

        # 3. Announce intent and check for conflicts
        print("  [3/4] Announcing intent to coordinator...")
        await self._do_announce_intent(intent)
        print("         Waiting for other agents (5 seconds)...")
        await self._drain_conflicts(5.0)

        if self.conflicts_received:
            print(f"\n  CONFLICT with another agent!")
            for c in self.conflicts_received:
                cp = c.get("payload", {})
                print(f"    Category: {cp.get('category', '?')}")
                print(f"    Between: {cp.get('intent_a', '?')} vs {cp.get('intent_b', '?')}")

                decision = await asyncio.get_event_loop().run_in_executor(
                    None, self._decide_conflict, cp, intent
                )
                print(f"    Decision: {decision}")
                if decision == "yield":
                    print("  Yielding to other agent. Task cancelled.")
                    msg = self.participant.withdraw_intent(
                        self.session_id, intent["intent_id"], "yielded"
                    )
                    await self._send(msg)
                    return
            print("  Proceeding — coordinator will resolve.")
        else:
            print("         No conflicts detected.")

        # 4. Generate fixes and commit
        print("  [4/4] Generating fixes...")
        max_rebase = 2

        for fname in target_files:
            if fname not in originals:
                continue

            for attempt in range(max_rebase + 1):
                # Read latest version (might have been updated by another agent)
                result = await self.read_file(fname)
                if result is None:
                    print(f"  ERROR: Cannot read {fname}")
                    break
                content, state_ref = result
                original_content = originals[fname][0]

                if attempt > 0:
                    print(f"\n  Rebasing {fname} (attempt {attempt + 1})...")
                    print(f"  File was modified by another agent. Reading updated version...")
                    _show_file(fname, content)
                    original_content = content  # diff against rebased version

                print(f"\n  Asking Claude to fix {fname}...")
                rebase_note = ""
                if attempt > 0:
                    rebase_note = ("\nIMPORTANT: Another agent already modified this file. "
                                   "Build on top of their changes.")
                fixed = await asyncio.get_event_loop().run_in_executor(
                    None, self._generate_fix, task + rebase_note, fname, content
                )

                # Show diff
                _show_diff(fname, original_content, fixed)

                # Commit
                op_id = f"op-{self.name.lower()}-{fname.replace('/', '-').replace('.', '-')}"
                if attempt > 0:
                    op_id += f"-r{attempt}"

                print(f"  Committing {fname}...")
                ok = await self._do_commit(intent["intent_id"], op_id, fname, fixed, state_ref)
                if ok:
                    new_ref = "sha256:" + hashlib.sha256(fixed.encode()).hexdigest()[:16]
                    print(f"  Committed! {fname} -> {new_ref}")
                    break
                elif attempt < max_rebase:
                    print(f"  STALE! Another agent changed {fname}. Rebasing...")
                else:
                    print(f"  ERROR: Failed to commit {fname} after {max_rebase} rebases")

        # Withdraw the intent — task is done, scope should no longer be "claimed".
        # This aligns intent lifecycle with task lifecycle for the interactive CLI.
        try:
            msg = self.participant.withdraw_intent(
                self.session_id, intent["intent_id"], "task_completed"
            )
            await self._send(msg)
        except Exception as e:
            self.log.debug(f"withdraw_intent failed: {e}")

        # Clear stale conflict reports from this task so the next task starts clean
        self.conflicts_received = []

        _header("Task Complete!")

    # ── Original autonomous workflow (still available) ─────────

    async def run_task(self, task: str):
        """Run a complete autonomous task (non-interactive)."""
        self.log.info(f"=== {self.name} starting task: {task} ===")

        self.log.info("Phase 1: Joining session...")
        await self._do_hello()

        self.log.info("Phase 2: Reading workspace...")
        files = await self.list_files()
        for f in files:
            self.log.info(f"  {f['path']} ({f['size']} bytes)")

        self.log.info("Phase 3: Deciding intent (calling Claude)...")
        intent = await asyncio.get_event_loop().run_in_executor(
            None, self._decide_intent, task, files
        )
        self.log.info(f"  Intent: {intent.get('objective', '?')}")

        self.log.info("Phase 4: Announcing intent...")
        await self._do_announce_intent(intent)

        self.log.info("Phase 5: Waiting for conflicts (5s)...")
        await self._drain_conflicts(5.0)

        if self.conflicts_received:
            self.log.info(f"  {len(self.conflicts_received)} conflict(s) detected!")
            for c in self.conflicts_received:
                decision = await asyncio.get_event_loop().run_in_executor(
                    None, self._decide_conflict, c.get("payload", {}), intent
                )
                self.log.info(f"  Decision: {decision}")
                if decision == "yield":
                    msg = self.participant.withdraw_intent(
                        self.session_id, intent["intent_id"], "yielded"
                    )
                    await self._send(msg)
                    await self._do_goodbye()
                    return
            self.log.info("  Proceeding — coordinator will auto-resolve.")
        else:
            self.log.info("  No conflicts.")

        self.log.info("Phase 6: Generating fixes and committing...")
        target_files = intent.get("files", [])
        max_rebase = 2

        for target in target_files:
            for attempt in range(max_rebase + 1):
                result = await self.read_file(target)
                if result is None:
                    self.log.warning(f"  File not found: {target}")
                    break
                content, state_ref = result
                label = f" (rebase #{attempt})" if attempt > 0 else ""
                self.log.info(f"  Reading {target}{label} ref={state_ref}")

                rebase_note = ""
                if attempt > 0:
                    rebase_note = ("\nIMPORTANT: Another agent already modified this file. "
                                   "Build on top of their changes.")

                self.log.info(f"  Calling Claude to fix {target}...")
                fixed = await asyncio.get_event_loop().run_in_executor(
                    None, self._generate_fix, task + rebase_note, target, content
                )

                op_id = f"op-{self.name.lower()}-{target.replace('/', '-').replace('.', '-')}"
                if attempt > 0:
                    op_id += f"-r{attempt}"

                ok = await self._do_commit(intent["intent_id"], op_id, target, fixed, state_ref)
                if ok:
                    self.log.info(f"  COMMITTED: {target}")
                    break
                elif attempt < max_rebase:
                    self.log.info(f"  Rebasing {target}...")
                else:
                    self.log.error(f"  Failed to commit {target} after {max_rebase} rebases")

        self.log.info("Phase 7: Done!")
        await self._do_goodbye()
        self.log.info(f"=== {self.name} completed ===")

    async def close(self):
        """Clean up connection."""
        if self._listener_task:
            self._listener_task.cancel()
        if self.ws:
            await self.ws.close()
