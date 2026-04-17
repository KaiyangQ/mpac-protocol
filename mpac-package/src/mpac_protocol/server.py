from __future__ import annotations
"""
MPAC Server — Coordinator + shared file workspace.

Runs a WebSocket server that:
1. Routes MPAC protocol messages (HELLO, INTENT, OP_COMMIT, etc.)
2. Hosts a shared file workspace that agents read/write through sideband messages
3. Optionally serves multiple sessions from a single port (multi_session mode),
   with URL paths of the form ``/session/<session_id>`` selecting the target.
"""
import json
import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import websockets

from .core.coordinator import CredentialVerifier, SessionCoordinator

log = logging.getLogger("mpac.server")


# Directories and files skipped by FileStore.load_directory by default.
# These are the usual suspects that almost nobody wants shared in a
# collaborative workspace (VCS metadata, build caches, virtualenvs, OS cruft).
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".venv", "venv", "env",
    ".idea", ".vscode",
    "dist", "build", ".next", ".turbo",
})
DEFAULT_IGNORE_FILES: frozenset[str] = frozenset({
    ".DS_Store", "Thumbs.db", ".gitignore",
})


# ── FileStore ──────────────────────────────────────────────────

class FileStore:
    """In-memory file store with SHA-256 state tracking."""

    def __init__(self):
        self.files: dict[str, dict] = {}  # path -> {content, state_ref}

    def load_directory(
        self,
        dir_path: str,
        ignore_dirs: frozenset[str] | set[str] | None = None,
        ignore_files: frozenset[str] | set[str] | None = None,
    ):
        """Load all text files from a directory into the store.

        Walks ``dir_path`` recursively and registers every text file it finds
        as a shared resource. Binary files (anything that cannot be decoded as
        UTF-8) are skipped with a warning — the MPAC protocol represents file
        content as text, so binaries cannot participate in optimistic
        concurrency control.

        Parameters
        ----------
        dir_path:
            Root directory to share. The caller can point this at any path;
            nothing about the workspace is bundled with the MPAC package.
        ignore_dirs / ignore_files:
            Names to skip during the walk. Defaults to ``DEFAULT_IGNORE_DIRS``
            and ``DEFAULT_IGNORE_FILES`` — VCS metadata, build caches,
            virtualenvs, IDE configs, and OS cruft. Pass an empty set to load
            literally everything.
        """
        ignore_dirs = DEFAULT_IGNORE_DIRS if ignore_dirs is None else ignore_dirs
        ignore_files = DEFAULT_IGNORE_FILES if ignore_files is None else ignore_files

        for root, dirs, files in os.walk(dir_path):
            # Prune ignored subdirectories in-place so os.walk doesn't descend.
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for fname in files:
                if fname in ignore_files:
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, dir_path)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                except UnicodeDecodeError:
                    log.warning(f"  Skipped (binary): {rel}")
                    continue
                except OSError as e:
                    log.warning(f"  Skipped (read error): {rel}: {e}")
                    continue
                ref = "sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16]
                self.files[rel] = {"content": content, "state_ref": ref}
                log.info(f"  Loaded: {rel} ({ref})")

    def list_files(self) -> list[dict]:
        """List all files with metadata."""
        return [
            {"path": path, "state_ref": info["state_ref"], "size": len(info["content"])}
            for path, info in sorted(self.files.items())
        ]

    def read(self, path: str) -> tuple[str, str] | None:
        """Read file content and state_ref. Returns None if not found."""
        info = self.files.get(path)
        if info is None:
            return None
        return info["content"], info["state_ref"]

    def write(self, path: str, content: str, expected_ref: str) -> tuple[bool, str]:
        """Write file with optimistic concurrency.
        Returns (success, new_state_ref_or_current_ref).
        """
        info = self.files.get(path)
        if info is not None and info["state_ref"] != expected_ref:
            return False, info["state_ref"]
        new_ref = "sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16]
        self.files[path] = {"content": content, "state_ref": new_ref}
        return True, new_ref

    def save_to_directory(self, dir_path: str):
        """Save current state to disk."""
        os.makedirs(dir_path, exist_ok=True)
        for path, info in self.files.items():
            fpath = os.path.join(dir_path, path)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, "w") as f:
                f.write(info["content"])


# ── Per-session state (shared by single- and multi-session modes) ──

@dataclass
class _SessionState:
    """All coordinator / file / connection state scoped to one MPAC session.

    An MPACServer holds exactly one of these in single-session mode, or a
    dict of them keyed by session_id in multi_session mode. Keeping every
    session-scoped piece of state on this object makes the handler body
    session-agnostic — it just receives the right ``_SessionState`` and
    references ``state.coordinator`` / ``state.file_store`` / etc.
    """

    session_id: str
    coordinator: SessionCoordinator
    file_store: "FileStore"
    workspace_dir: Optional[str] = None
    # principal_id -> websocket
    connections: Dict[str, Any] = field(default_factory=dict)
    # websocket -> principal_id
    ws_to_principal: Dict[Any, str] = field(default_factory=dict)


# ── MPACServer ─────────────────────────────────────────────────

class MPACServer:
    """MPAC Coordinator + FileStore over WebSocket.

    Two deployment modes:

    - **single-session** (default, backward compatible): construct with a
      ``session_id``; everything behaves exactly as in mpac 0.1.x. Back-compat
      shortcuts ``self.coordinator`` / ``self.file_store`` / ``self.connections``
      / ``self.ws_to_principal`` are available.

    - **multi_session**: pass ``multi_session=True`` (and omit ``session_id``).
      The server lazily creates one ``SessionCoordinator`` + ``FileStore`` per
      session id that appears in the URL path ``/session/<id>``. Sessions are
      fully isolated — no cross-session broadcast, no shared state. This mode
      is the substrate for Authenticated-profile multi-tenant deployments.

    Optional ``credential_verifier`` is passed through to every
    ``SessionCoordinator`` created by this server, enabling the Authenticated
    profile per Section 23.1.4 of SPEC.md.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        host: str = "0.0.0.0",
        port: int = 8766,
        workspace_dir: str | None = None,
        multi_session: bool = False,
        credential_verifier: Optional[CredentialVerifier] = None,
        **kwargs,
    ):
        self.host = host
        self.port = port
        self.multi_session = multi_session
        self.credential_verifier = credential_verifier
        # Stash kwargs so we can pass the same coordinator config through to
        # every SessionCoordinator we create (eagerly in single-session mode,
        # lazily in multi_session mode).
        self._coordinator_kwargs: Dict[str, Any] = {
            "execution_model": kwargs.get("execution_model", "post_commit"),
            "compliance_profile": kwargs.get("compliance_profile", "core"),
            "security_profile": kwargs.get("security_profile", "open"),
            "unavailability_timeout_sec": kwargs.get("unavailability_timeout_sec", 90.0),
            "resolution_timeout_sec": kwargs.get("resolution_timeout_sec", 300.0),
            "intent_claim_grace_sec": kwargs.get("intent_claim_grace_sec", 0.0),
            "role_policy": kwargs.get("role_policy"),
        }
        self._sessions: Dict[str, _SessionState] = {}
        self.transcript: list[dict] = []  # global transcript across all sessions
        self.start_time = time.time()

        if multi_session:
            if session_id is not None:
                raise ValueError(
                    "MPACServer(multi_session=True) must NOT be given a session_id; "
                    "sessions are created on demand from URL paths."
                )
            # Back-compat attributes are intentionally None — consumers that
            # need a specific session should look it up via self._sessions.
            self.session_id = None
            self.workspace_dir = None
        else:
            if session_id is None:
                raise ValueError(
                    "MPACServer requires a session_id unless multi_session=True."
                )
            state = self._create_session_state(session_id, workspace_dir)
            self._sessions[session_id] = state
            # Back-compat shortcuts: in single-session mode existing callers
            # can still reach into self.coordinator / self.file_store / etc.
            self.session_id = session_id
            self.workspace_dir = workspace_dir
            self.coordinator = state.coordinator
            self.file_store = state.file_store
            self.connections = state.connections
            self.ws_to_principal = state.ws_to_principal

    def _create_session_state(
        self, session_id: str, workspace_dir: Optional[str]
    ) -> _SessionState:
        """Instantiate a SessionCoordinator + FileStore for a new session."""
        coordinator = SessionCoordinator(
            session_id,
            credential_verifier=self.credential_verifier,
            **self._coordinator_kwargs,
        )
        file_store = FileStore()
        if workspace_dir:
            log.info(f"Loading workspace for session {session_id} from {workspace_dir}")
            file_store.load_directory(workspace_dir)
        return _SessionState(
            session_id=session_id,
            coordinator=coordinator,
            file_store=file_store,
            workspace_dir=workspace_dir,
        )

    def _extract_session_id(self, path: str) -> Optional[str]:
        """Extract the session id from a URL path like '/session/<id>'."""
        if not path or not path.startswith("/session/"):
            return None
        remainder = path[len("/session/") :]
        # Strip anything after the session id (sub-paths, query strings)
        session_id = remainder.split("/", 1)[0].split("?", 1)[0]
        return session_id or None

    def _get_or_create_session(self, session_id: str) -> _SessionState:
        """Return the session state, creating it on first access."""
        state = self._sessions.get(session_id)
        if state is None:
            state = self._create_session_state(session_id, workspace_dir=None)
            self._sessions[session_id] = state
            log.info(f"[multi_session] created new session {session_id}")
        return state

    async def handler(self, websocket):
        """Handle a single agent connection.

        In multi_session mode we read the URL path from the WebSocket handshake
        to pick the right session_id; in single-session mode we always use the
        one session created at construction time.
        """
        # ── Session dispatch ──
        if self.multi_session:
            try:
                path = websocket.request.path  # websockets >=14 API
            except AttributeError:
                path = getattr(websocket, "path", None)  # defensive fallback
            session_id = self._extract_session_id(path or "")
            if session_id is None:
                log.warning(f"[multi_session] rejecting connection with invalid path: {path!r}")
                await websocket.close(
                    code=4004,
                    reason="multi_session server requires a /session/<id> path",
                )
                return
            state = self._get_or_create_session(session_id)
        else:
            state = self._sessions[self.session_id]

        principal_id = None
        try:
            async for raw in websocket:
                data = json.loads(raw)

                # ── Sideband: file operations (non-MPAC) ──
                if data.get("type") == "FILE_LIST":
                    resp = {"type": "FILE_LIST_RESPONSE", "files": state.file_store.list_files()}
                    await websocket.send(json.dumps(resp, ensure_ascii=False))
                    continue

                if data.get("type") == "FILE_READ":
                    result = state.file_store.read(data["path"])
                    if result:
                        content, ref = result
                        resp = {"type": "FILE_CONTENT", "path": data["path"],
                                "content": content, "state_ref": ref}
                    else:
                        resp = {"type": "FILE_ERROR", "path": data["path"],
                                "error": "File not found"}
                    await websocket.send(json.dumps(resp, ensure_ascii=False))
                    continue

                if data.get("type") == "SESSION_SUMMARY":
                    resp = {
                        "type": "SESSION_SUMMARY_RESPONSE",
                        "session": self.session_summary(state.session_id),
                    }
                    await websocket.send(json.dumps(resp, ensure_ascii=False))
                    continue

                # ── MPAC protocol message ──
                msg_type = data.get("message_type", "?")
                sender_id = data.get("sender", {}).get("principal_id", "?")

                if msg_type == "HELLO":
                    principal_id = sender_id
                    state.connections[principal_id] = websocket
                    state.ws_to_principal[websocket] = principal_id
                    log.info(f"<< [{state.session_id}] HELLO from {principal_id}")
                else:
                    log.info(f"<< [{state.session_id}] {msg_type} from {sender_id}")

                self.transcript.append({
                    "ts": time.time() - self.start_time,
                    "session_id": state.session_id,
                    "direction": "inbound",
                    "from": sender_id,
                    "message_type": msg_type,
                    "envelope": data,
                })

                # Process through MPAC coordinator
                responses = state.coordinator.process_message(data)

                # Broadcast inbound messages that other agents should see.
                # The coordinator returns [] on success for these types,
                # so the server must relay the original message explicitly.
                rejected = any(
                    r.get("message_type") == "PROTOCOL_ERROR" for r in responses
                )
                if not rejected and msg_type in (
                    "OP_COMMIT", "INTENT_ANNOUNCE", "INTENT_WITHDRAW",
                    "INTENT_UPDATE", "CONFLICT_ACK",
                    "CONFLICT_ESCALATE", "RESOLUTION",
                ):
                    broadcast_msg = json.loads(json.dumps(data))
                    # Strip bulky file content from OP_COMMIT before broadcast
                    if msg_type == "OP_COMMIT":
                        broadcast_msg.get("payload", {}).pop("file_changes", None)
                    log.info(f">> [{state.session_id}] {msg_type} broadcast from {sender_id}")
                    await self._broadcast(state, json.dumps(broadcast_msg, ensure_ascii=False))

                # If OP_COMMIT succeeded and carries file_changes, update FileStore
                if msg_type == "OP_COMMIT" and not rejected:
                    file_changes = data.get("payload", {}).get("file_changes", {})
                    if file_changes:
                        await self._apply_file_changes(state, file_changes, sender_id)

                # Route responses
                for resp in responses:
                    resp_type = resp.get("message_type", "?")
                    resp_json = json.dumps(resp, ensure_ascii=False)

                    self.transcript.append({
                        "ts": time.time() - self.start_time,
                        "session_id": state.session_id,
                        "direction": "outbound",
                        "message_type": resp_type,
                        "envelope": resp,
                    })

                    # Check if this OP_COMMIT was rejected (PROTOCOL_ERROR)
                    if resp_type == "PROTOCOL_ERROR":
                        log.info(f">> [{state.session_id}] PROTOCOL_ERROR to {sender_id}: "
                                 f"{resp.get('payload', {}).get('error_code', '?')}")
                        await websocket.send(resp_json)

                    elif resp_type == "SESSION_INFO":
                        log.info(f">> [{state.session_id}] SESSION_INFO to {sender_id}")
                        await websocket.send(resp_json)

                    elif resp_type == "CONFLICT_REPORT":
                        conflict = resp.get("payload", {})
                        involved = {conflict.get("principal_a"), conflict.get("principal_b")}
                        log.info(f">> [{state.session_id}] CONFLICT_REPORT to {involved}")
                        for pid in involved:
                            if pid in state.connections:
                                await state.connections[pid].send(resp_json)

                    elif resp_type in ("OP_REJECT", "INTENT_CLAIM_STATUS"):
                        log.info(f">> [{state.session_id}] {resp_type} to {sender_id}")
                        await websocket.send(resp_json)

                    elif resp_type == "SESSION_CLOSE":
                        log.info(f">> [{state.session_id}] SESSION_CLOSE broadcast")
                        await self._broadcast(state, resp_json)

                    else:
                        log.info(f">> [{state.session_id}] {resp_type} broadcast")
                        await self._broadcast(state, resp_json)

        except websockets.exceptions.ConnectionClosed:
            log.info(f"[{state.session_id}] Connection closed: {principal_id or 'unknown'}")
        finally:
            if principal_id:
                state.connections.pop(principal_id, None)
            state.ws_to_principal.pop(websocket, None)

    async def _apply_file_changes(
        self, state: _SessionState, file_changes: dict, sender_id: str
    ):
        """Apply file changes from an OP_COMMIT to the session's FileStore."""
        for path, change in file_changes.items():
            content = change.get("content", "")
            expected_ref = change.get("state_ref_before", "")
            ok, new_ref = state.file_store.write(path, content, expected_ref)
            if ok:
                log.info(f"  [{state.session_id}] FileStore: {path} updated by {sender_id} -> {new_ref}")
                # Notify agents in THIS session only that a file was updated
                notify = json.dumps({
                    "type": "FILE_UPDATED",
                    "path": path,
                    "state_ref": new_ref,
                    "updated_by": sender_id,
                }, ensure_ascii=False)
                await self._broadcast(state, notify)
            else:
                log.warning(f"  [{state.session_id}] FileStore: {path} STALE for {sender_id} "
                            f"(expected {expected_ref}, current {new_ref})")

    async def _broadcast(self, state: _SessionState, message: str):
        """Send a message to all agents connected to one specific session."""
        if state.connections:
            await asyncio.gather(
                *[ws.send(message) for ws in state.connections.values()],
                return_exceptions=True,
            )

    async def heartbeat_loop(self):
        """Periodic liveness + status checks across every active session."""
        while True:
            await asyncio.sleep(10)
            # Snapshot the session list so a session created mid-loop doesn't
            # cause a RuntimeError (dict mutation during iteration).
            for state in list(self._sessions.values()):
                for resp in state.coordinator.check_liveness():
                    await self._broadcast(state, json.dumps(resp, ensure_ascii=False))
                state.coordinator.check_resolution_timeouts()
                for s in state.coordinator.coordinator_status("heartbeat"):
                    await self._broadcast(state, json.dumps(s, ensure_ascii=False))

    async def run(self):
        """Start the WebSocket server (blocking)."""
        log.info(f"MPAC Server starting on ws://{self.host}:{self.port}")
        if self.multi_session:
            log.info("Mode: multi_session (sessions created on demand from /session/<id> URL path)")
        else:
            log.info(f"Mode: single-session {self.session_id}")
            log.info(f"Workspace files: {len(self._sessions[self.session_id].file_store.files)}")

        async with websockets.serve(self.handler, self.host, self.port):
            heartbeat_task = asyncio.create_task(self.heartbeat_loop())
            try:
                await asyncio.Future()  # run forever
            except asyncio.CancelledError:
                heartbeat_task.cancel()

    async def run_background(self) -> tuple:
        """Start server as background tasks. Returns (ws_server, heartbeat_task)."""
        ws_server = await websockets.serve(self.handler, self.host, self.port)
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        log.info(f"MPAC Server on ws://{self.host}:{self.port} (background)")
        if self.multi_session:
            log.info("Mode: multi_session")
        else:
            log.info(f"Workspace files: {len(self._sessions[self.session_id].file_store.files)}")
        return ws_server, heartbeat_task

    def save_transcript(self, path: str):
        """Save message transcript to JSON file."""
        with open(path, "w") as f:
            json.dump(self.transcript, f, indent=2, ensure_ascii=False)
        log.info(f"Transcript saved: {path} ({len(self.transcript)} messages)")

    def print_workspace_state(self):
        """Print current state of all files in every active session's workspace."""
        log.info("=== Workspace State ===")
        for state in self._sessions.values():
            prefix = f"  [{state.session_id}] " if self.multi_session else "  "
            for path, info in sorted(state.file_store.files.items()):
                log.info(f"{prefix}{path}: {info['state_ref']} ({len(info['content'])} bytes)")

    def session_summary(self, session_id: Optional[str] = None) -> dict:
        """Return a compact session snapshot for sidecar-style local queries.

        In single-session mode ``session_id`` is optional and defaults to the
        server's single session. In multi_session mode it must be supplied to
        pick which session to summarize.
        """
        if session_id is None:
            if self.multi_session:
                raise ValueError(
                    "session_summary() requires a session_id when multi_session=True"
                )
            session_id = self.session_id
        state = self._sessions.get(session_id)
        if state is None:
            return {
                "session_id": session_id,
                "error": "session_not_found",
                "workspace_dir": None,
                "participant_count": 0,
                "active_intent_count": 0,
                "open_conflict_count": 0,
                "participants": [],
                "active_intents": [],
                "open_conflicts": [],
            }
        snapshot = state.coordinator.snapshot()
        active_intent_states = {"ANNOUNCED", "ACTIVE", "SUSPENDED"}
        open_conflict_states = {"OPEN", "ACKED", "ESCALATED"}

        participants = [
            {
                "principal_id": participant["principal_id"],
                "display_name": participant["display_name"],
                "roles": participant.get("roles", []),
                "status": participant.get("status"),
                "is_available": participant.get("is_available", False),
                "last_seen": participant.get("last_seen"),
            }
            for participant in snapshot.get("participants", [])
        ]
        active_intents = [
            {
                "intent_id": intent["intent_id"],
                "principal_id": intent["principal_id"],
                "objective": intent["objective"],
                "state": intent["state"],
                "scope": intent.get("scope", {}),
                "claimed_by": intent.get("claimed_by"),
            }
            for intent in snapshot.get("intents", [])
            if intent.get("state") in active_intent_states
        ]
        open_conflicts = [
            {
                "conflict_id": conflict["conflict_id"],
                "category": conflict["category"],
                "severity": conflict["severity"],
                "state": conflict["state"],
                "principal_a": conflict["principal_a"],
                "principal_b": conflict["principal_b"],
                "intent_a": conflict["intent_a"],
                "intent_b": conflict["intent_b"],
            }
            for conflict in snapshot.get("conflicts", [])
            if conflict.get("state") in open_conflict_states
        ]

        return {
            "session_id": state.session_id,
            "workspace_dir": state.workspace_dir,
            "captured_at": snapshot.get("captured_at"),
            "participant_count": len(participants),
            "active_intent_count": len(active_intents),
            "open_conflict_count": len(open_conflicts),
            "participants": participants,
            "active_intents": active_intents,
            "open_conflicts": open_conflicts,
        }
