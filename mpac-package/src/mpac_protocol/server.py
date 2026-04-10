from __future__ import annotations
"""
MPAC Server — Coordinator + shared file workspace.

Runs a WebSocket server that:
1. Routes MPAC protocol messages (HELLO, INTENT, OP_COMMIT, etc.)
2. Hosts a shared file workspace that agents read/write through sideband messages
"""
import json
import asyncio
import hashlib
import logging
import os
import time

import websockets

from .core.coordinator import SessionCoordinator

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


# ── MPACServer ─────────────────────────────────────────────────

class MPACServer:
    """MPAC Coordinator + FileStore over WebSocket."""

    def __init__(
        self,
        session_id: str,
        host: str = "0.0.0.0",
        port: int = 8766,
        workspace_dir: str | None = None,
        **kwargs,
    ):
        self.session_id = session_id
        self.host = host
        self.port = port
        self.coordinator = SessionCoordinator(
            session_id,
            execution_model=kwargs.get("execution_model", "post_commit"),
            compliance_profile=kwargs.get("compliance_profile", "core"),
            security_profile=kwargs.get("security_profile", "open"),
            unavailability_timeout_sec=kwargs.get("unavailability_timeout_sec", 90.0),
            resolution_timeout_sec=kwargs.get("resolution_timeout_sec", 300.0),
            intent_claim_grace_sec=kwargs.get("intent_claim_grace_sec", 0.0),
            role_policy=kwargs.get("role_policy"),
        )
        self.file_store = FileStore()
        if workspace_dir:
            log.info(f"Loading workspace from {workspace_dir}")
            self.file_store.load_directory(workspace_dir)

        self.connections: dict[str, websockets.WebSocketServerProtocol] = {}
        self.ws_to_principal: dict[websockets.WebSocketServerProtocol, str] = {}
        self.transcript: list[dict] = []
        self.start_time = time.time()

    async def handler(self, websocket):
        """Handle a single agent connection."""
        principal_id = None
        try:
            async for raw in websocket:
                data = json.loads(raw)

                # ── Sideband: file operations (non-MPAC) ──
                if data.get("type") == "FILE_LIST":
                    resp = {"type": "FILE_LIST_RESPONSE", "files": self.file_store.list_files()}
                    await websocket.send(json.dumps(resp, ensure_ascii=False))
                    continue

                if data.get("type") == "FILE_READ":
                    result = self.file_store.read(data["path"])
                    if result:
                        content, ref = result
                        resp = {"type": "FILE_CONTENT", "path": data["path"],
                                "content": content, "state_ref": ref}
                    else:
                        resp = {"type": "FILE_ERROR", "path": data["path"],
                                "error": "File not found"}
                    await websocket.send(json.dumps(resp, ensure_ascii=False))
                    continue

                # ── MPAC protocol message ──
                msg_type = data.get("message_type", "?")
                sender_id = data.get("sender", {}).get("principal_id", "?")

                if msg_type == "HELLO":
                    principal_id = sender_id
                    self.connections[principal_id] = websocket
                    self.ws_to_principal[websocket] = principal_id
                    log.info(f"<< HELLO from {principal_id}")
                else:
                    log.info(f"<< {msg_type} from {sender_id}")

                self.transcript.append({
                    "ts": time.time() - self.start_time,
                    "direction": "inbound",
                    "from": sender_id,
                    "message_type": msg_type,
                    "envelope": data,
                })

                # Process through MPAC coordinator
                responses = self.coordinator.process_message(data)

                # If OP_COMMIT succeeded and carries file_changes, update FileStore
                if msg_type == "OP_COMMIT":
                    file_changes = data.get("payload", {}).get("file_changes", {})
                    if file_changes:
                        await self._apply_file_changes(file_changes, sender_id)

                # Route responses
                for resp in responses:
                    resp_type = resp.get("message_type", "?")
                    resp_json = json.dumps(resp, ensure_ascii=False)

                    self.transcript.append({
                        "ts": time.time() - self.start_time,
                        "direction": "outbound",
                        "message_type": resp_type,
                        "envelope": resp,
                    })

                    # Check if this OP_COMMIT was rejected (PROTOCOL_ERROR)
                    if resp_type == "PROTOCOL_ERROR":
                        log.info(f">> PROTOCOL_ERROR to {sender_id}: "
                                 f"{resp.get('payload', {}).get('error_code', '?')}")
                        await websocket.send(resp_json)

                    elif resp_type == "SESSION_INFO":
                        log.info(f">> SESSION_INFO to {sender_id}")
                        await websocket.send(resp_json)

                    elif resp_type == "CONFLICT_REPORT":
                        conflict = resp.get("payload", {})
                        involved = {conflict.get("principal_a"), conflict.get("principal_b")}
                        log.info(f">> CONFLICT_REPORT to {involved}")
                        for pid in involved:
                            if pid in self.connections:
                                await self.connections[pid].send(resp_json)

                    elif resp_type in ("OP_REJECT", "INTENT_CLAIM_STATUS"):
                        log.info(f">> {resp_type} to {sender_id}")
                        await websocket.send(resp_json)

                    elif resp_type == "SESSION_CLOSE":
                        log.info(f">> SESSION_CLOSE broadcast")
                        await self._broadcast(resp_json)

                    else:
                        log.info(f">> {resp_type} broadcast")
                        await self._broadcast(resp_json)

        except websockets.exceptions.ConnectionClosed:
            log.info(f"Connection closed: {principal_id or 'unknown'}")
        finally:
            if principal_id:
                self.connections.pop(principal_id, None)
            self.ws_to_principal.pop(websocket, None)

    async def _apply_file_changes(self, file_changes: dict, sender_id: str):
        """Apply file changes from an OP_COMMIT to the FileStore and notify agents."""
        for path, change in file_changes.items():
            content = change.get("content", "")
            expected_ref = change.get("state_ref_before", "")
            ok, new_ref = self.file_store.write(path, content, expected_ref)
            if ok:
                log.info(f"  FileStore: {path} updated by {sender_id} -> {new_ref}")
                # Notify all agents that a file was updated
                notify = json.dumps({
                    "type": "FILE_UPDATED",
                    "path": path,
                    "state_ref": new_ref,
                    "updated_by": sender_id,
                }, ensure_ascii=False)
                await self._broadcast(notify)
            else:
                log.warning(f"  FileStore: {path} STALE for {sender_id} "
                            f"(expected {expected_ref}, current {new_ref})")

    async def _broadcast(self, message: str):
        """Send message to all connected agents."""
        if self.connections:
            await asyncio.gather(
                *[ws.send(message) for ws in self.connections.values()],
                return_exceptions=True,
            )

    async def heartbeat_loop(self):
        """Periodic liveness + status checks."""
        while True:
            await asyncio.sleep(10)
            for resp in self.coordinator.check_liveness():
                await self._broadcast(json.dumps(resp, ensure_ascii=False))
            self.coordinator.check_resolution_timeouts()
            for s in self.coordinator.coordinator_status("heartbeat"):
                await self._broadcast(json.dumps(s, ensure_ascii=False))

    async def run(self):
        """Start the WebSocket server (blocking)."""
        log.info(f"MPAC Server starting on ws://{self.host}:{self.port}")
        log.info(f"Session: {self.session_id}")
        log.info(f"Workspace files: {len(self.file_store.files)}")

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
        log.info(f"Workspace files: {len(self.file_store.files)}")
        return ws_server, heartbeat_task

    def save_transcript(self, path: str):
        """Save message transcript to JSON file."""
        with open(path, "w") as f:
            json.dump(self.transcript, f, indent=2, ensure_ascii=False)
        log.info(f"Transcript saved: {path} ({len(self.transcript)} messages)")

    def print_workspace_state(self):
        """Print current state of all files in workspace."""
        log.info("=== Workspace State ===")
        for path, info in sorted(self.file_store.files.items()):
            log.info(f"  {path}: {info['state_ref']} ({len(info['content'])} bytes)")
