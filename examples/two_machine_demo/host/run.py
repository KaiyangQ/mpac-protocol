#!/usr/bin/env python3
"""
Two-machine demo — HOST side.

Starts an MPAC coordinator that shares a directory with remote agents,
and runs an interactive local agent in the same process so the host
participates in the session too.

Quick start (LAN, both machines on the same WiFi)::

    pip install mpac_protocol            # or: pip install ../../../mpac-package
    cp config.example.json config.json   # then edit and add your API key
    python run.py                        # shares ./workspace by default

Pointing at a different directory::

    python run.py --workspace ~/my_project

The script prints the LAN address that the guest should connect to. If
you are not on the same WiFi, expose the port with ngrok or a similar
tunnel and give the wss:// URL to the guest instead.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import socket
import sys

from mpac_protocol import MPACServer, MPACAgent

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _detect_lan_ip() -> str:
    """Best-effort detection of the host's outward-facing LAN IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "localhost"


def _load_config(config_path: str) -> dict:
    """Read config.json. Fail loudly if it's missing or has no API key."""
    if not os.path.exists(config_path):
        sys.exit(
            f"\n  ERROR: {config_path} not found.\n"
            f"  Copy config.example.json to config.json and fill in your API key.\n"
        )
    with open(config_path) as f:
        cfg = json.load(f)
    api_key = cfg.get("anthropic", {}).get("api_key", "")
    if not api_key:
        sys.exit(
            f"\n  ERROR: anthropic.api_key is empty in {config_path}.\n"
            f"  Get a key at https://console.anthropic.com/settings/keys\n"
        )
    return cfg


async def main():
    parser = argparse.ArgumentParser(
        description="MPAC two-machine demo — host side",
    )
    parser.add_argument(
        "--workspace",
        default=os.path.join(SCRIPT_DIR, "workspace"),
        help="Directory to share with agents (default: ./workspace)",
    )
    parser.add_argument(
        "--port", type=int, default=8766,
        help="WebSocket port to listen on (default: 8766)",
    )
    parser.add_argument(
        "--session-id", default="collab-session-001",
        help="MPAC session id (default: collab-session-001)",
    )
    parser.add_argument(
        "--name", default="Alice",
        help="Display name for the local agent (default: Alice)",
    )
    parser.add_argument(
        "--config", default=os.path.join(SCRIPT_DIR, "config.json"),
        help="Path to config.json with the Anthropic API key",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.workspace):
        sys.exit(f"\n  ERROR: workspace directory not found: {args.workspace}\n")

    cfg = _load_config(args.config)
    anthropic_cfg = cfg["anthropic"]

    print()
    print("  ============================================")
    print("    MPAC two-machine demo — HOST")
    print("  ============================================")
    print()
    print(f"  Sharing workspace: {args.workspace}")
    print(f"  Session id:        {args.session_id}")
    print()

    server = MPACServer(
        session_id=args.session_id,
        host="0.0.0.0",
        port=args.port,
        workspace_dir=args.workspace,
    )
    ws_server, heartbeat_task = await server.run_background()

    lan_ip = _detect_lan_ip()
    print(f"  Coordinator running on ws://0.0.0.0:{args.port}")
    print()
    print(f"  +----------------------------------------------------+")
    print(f"  | Share this with the guest:                         |")
    print(f"  |                                                    |")
    print(f"  |   ws://{lan_ip}:{args.port}                              ")
    print(f"  |                                                    |")
    print(f"  | They run:                                          |")
    print(f"  |   python run.py ws://{lan_ip}:{args.port}                ")
    print(f"  +----------------------------------------------------+")
    print()
    print(f"  (For non-LAN connections, run ngrok and share the wss://)")
    print()

    await asyncio.sleep(1)

    agent = MPACAgent(
        name=args.name,
        api_key=anthropic_cfg["api_key"],
        model=anthropic_cfg.get("model", "claude-sonnet-4-6"),
        role_description=f"Collaborative AI agent operated by {args.name} (host)",
    )
    await agent.connect(f"ws://localhost:{args.port}", args.session_id)

    try:
        await agent.run_interactive()
    except (KeyboardInterrupt, EOFError):
        pass

    await agent.close()

    output_dir = os.path.join(SCRIPT_DIR, "output")
    os.makedirs(output_dir, exist_ok=True)
    server.file_store.save_to_directory(output_dir)
    server.save_transcript(os.path.join(output_dir, "transcript.json"))
    print(f"\n  Final workspace state and transcript saved to {output_dir}/")

    heartbeat_task.cancel()
    ws_server.close()
    await ws_server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Host stopped.")
