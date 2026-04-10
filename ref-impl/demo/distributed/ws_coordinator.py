#!/usr/bin/env python3
"""
MPAC WebSocket Coordinator Server.

Runs the SessionCoordinator as a standalone WebSocket server.
Agents connect as clients, send MPAC envelopes as JSON, and
receive responses + broadcast messages over the wire.

This is the first real transport layer for MPAC.
"""
import sys, os, json, asyncio, logging, time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))

import websockets
from mpac.coordinator import SessionCoordinator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [COORDINATOR] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("coordinator")


class WSCoordinator:
    """WebSocket server wrapping MPAC SessionCoordinator."""

    def __init__(self, session_id: str, host: str = "localhost", port: int = 8765, **kwargs):
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
        # Map principal_id -> websocket connection
        self.connections: dict[str, websockets.WebSocketServerProtocol] = {}
        # Map websocket -> principal_id (reverse lookup)
        self.ws_to_principal: dict[websockets.WebSocketServerProtocol, str] = {}
        # Transcript for post-analysis
        self.transcript: list[dict] = []
        self.start_time = time.time()

    async def handler(self, websocket):
        """Handle a single agent connection."""
        principal_id = None
        try:
            async for raw in websocket:
                envelope = json.loads(raw)
                msg_type = envelope.get("message_type", "?")
                sender_id = envelope.get("sender", {}).get("principal_id", "?")

                # Track connection mapping on HELLO
                if msg_type == "HELLO":
                    principal_id = sender_id
                    self.connections[principal_id] = websocket
                    self.ws_to_principal[websocket] = principal_id
                    log.info(f"← HELLO from {principal_id}")
                else:
                    log.info(f"← {msg_type} from {sender_id}")

                # Log inbound
                self.transcript.append({
                    "ts": time.time() - self.start_time,
                    "direction": "inbound",
                    "from": sender_id,
                    "message_type": msg_type,
                    "envelope": envelope,
                })

                # Process through coordinator
                responses = self.coordinator.process_message(envelope)

                # Route responses
                for resp in responses:
                    resp_type = resp.get("message_type", "?")
                    resp_json = json.dumps(resp, ensure_ascii=False)

                    # Log outbound
                    self.transcript.append({
                        "ts": time.time() - self.start_time,
                        "direction": "outbound",
                        "message_type": resp_type,
                        "envelope": resp,
                    })

                    if resp_type == "SESSION_INFO":
                        # Reply only to sender
                        log.info(f"→ SESSION_INFO to {sender_id}")
                        await websocket.send(resp_json)

                    elif resp_type == "PROTOCOL_ERROR":
                        # Reply to sender
                        log.info(f"→ PROTOCOL_ERROR to {sender_id}: {resp.get('payload', {}).get('error_code', '?')}")
                        await websocket.send(resp_json)

                    elif resp_type == "CONFLICT_REPORT":
                        # Broadcast to all involved parties
                        conflict = resp.get("payload", {})
                        involved = {conflict.get("principal_a"), conflict.get("principal_b")}
                        log.info(f"→ CONFLICT_REPORT broadcast to {involved}")
                        for pid in involved:
                            if pid in self.connections:
                                await self.connections[pid].send(resp_json)

                    elif resp_type in ("OP_REJECT", "INTENT_CLAIM_STATUS"):
                        # Reply to sender
                        log.info(f"→ {resp_type} to {sender_id}")
                        await websocket.send(resp_json)

                    elif resp_type == "SESSION_CLOSE":
                        # Broadcast to all
                        log.info(f"→ SESSION_CLOSE broadcast to all")
                        await self._broadcast(resp_json)

                    else:
                        # Default: broadcast to all
                        log.info(f"→ {resp_type} broadcast")
                        await self._broadcast(resp_json)

        except websockets.exceptions.ConnectionClosed:
            log.info(f"Connection closed: {principal_id or 'unknown'}")
        finally:
            if principal_id:
                self.connections.pop(principal_id, None)
            self.ws_to_principal.pop(websocket, None)

    async def _broadcast(self, message: str):
        """Send message to all connected agents."""
        if self.connections:
            await asyncio.gather(
                *[ws.send(message) for ws in self.connections.values()],
                return_exceptions=True,
            )

    async def heartbeat_loop(self):
        """Periodically run coordinator liveness checks and broadcast status."""
        while True:
            await asyncio.sleep(10)  # check every 10 seconds

            # Liveness check
            liveness_responses = self.coordinator.check_liveness()
            for resp in liveness_responses:
                resp_json = json.dumps(resp, ensure_ascii=False)
                log.info(f"→ LIVENESS: {resp.get('payload', {}).get('error_code', '?')}")
                await self._broadcast(resp_json)

            # Resolution timeout check
            self.coordinator.check_resolution_timeouts()

            # Coordinator status heartbeat
            status_msgs = self.coordinator.coordinator_status("heartbeat")
            for s in status_msgs:
                s_json = json.dumps(s, ensure_ascii=False)
                log.info(f"→ COORDINATOR_STATUS: health={s.get('payload', {}).get('session_health', '?')}")
                await self._broadcast(s_json)

    async def run(self):
        """Start the WebSocket server."""
        log.info(f"Starting coordinator on ws://{self.host}:{self.port}")
        log.info(f"Session: {self.session_id}")

        async with websockets.serve(self.handler, self.host, self.port):
            # Run heartbeat loop in background
            heartbeat_task = asyncio.create_task(self.heartbeat_loop())
            try:
                await asyncio.Future()  # run forever
            except asyncio.CancelledError:
                heartbeat_task.cancel()

    def save_transcript(self, path: str):
        """Save transcript to file."""
        with open(path, "w") as f:
            json.dump(self.transcript, f, indent=2, ensure_ascii=False)
        log.info(f"Transcript saved: {path} ({len(self.transcript)} messages)")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="MPAC WebSocket Coordinator")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--session-id", default="ws-session-001")
    args = parser.parse_args()

    server = WSCoordinator(args.session_id, args.host, args.port)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
