#!/usr/bin/env python3
"""
Two-machine demo — GUEST side.

Joins an existing MPAC session running on another machine. The host runs
the matching ``examples/two_machine_demo/host/run.py`` and tells the
guest the WebSocket address (``ws://<host-ip>:8766`` for LAN, or a
``wss://`` ngrok URL for the open Internet).

Quick start::

    pip install mpac_protocol
    cp config.example.json config.json   # then edit and add your API key
    python run.py ws://192.168.1.42:8766

If you omit the URL, it defaults to ``ws://localhost:8766`` (useful for
testing both sides on a single machine in two terminals).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from mpac_protocol import MPACAgent

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _normalize_uri(uri: str) -> str:
    uri = uri.strip()
    if not uri.startswith("ws://") and not uri.startswith("wss://"):
        uri = "ws://" + uri
    return uri


def _load_config(config_path: str) -> dict:
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
        description="MPAC two-machine demo — guest side",
    )
    parser.add_argument(
        "uri", nargs="?", default="ws://localhost:8766",
        help="Coordinator WebSocket URI given by the host "
             "(default: ws://localhost:8766)",
    )
    parser.add_argument(
        "--session-id", default="collab-session-001",
        help="MPAC session id — must match the host's (default: collab-session-001)",
    )
    parser.add_argument(
        "--name", default="Bob",
        help="Display name for the local agent (default: Bob)",
    )
    parser.add_argument(
        "--config", default=os.path.join(SCRIPT_DIR, "config.json"),
        help="Path to config.json with the Anthropic API key",
    )
    args = parser.parse_args()

    cfg = _load_config(args.config)
    anthropic_cfg = cfg["anthropic"]
    coordinator_uri = _normalize_uri(args.uri)

    print()
    print("  ============================================")
    print("    MPAC two-machine demo — GUEST")
    print("  ============================================")
    print(f"  Connecting to: {coordinator_uri}")
    print(f"  Session id:    {args.session_id}")
    print()

    agent = MPACAgent(
        name=args.name,
        api_key=anthropic_cfg["api_key"],
        model=anthropic_cfg.get("model", "claude-sonnet-4-6"),
        role_description=f"Collaborative AI agent operated by {args.name} (guest)",
    )

    # Transport-specific headers (e.g. ngrok free-tier browser warning)
    headers = {}
    if "ngrok" in coordinator_uri:
        headers["ngrok-skip-browser-warning"] = "true"

    try:
        await agent.connect(coordinator_uri, args.session_id,
                            extra_headers=headers or None)
    except Exception as e:
        print(f"\n  ERROR: cannot connect to {coordinator_uri}")
        print(f"  {e}")
        print()
        print("  Things to check:")
        print("    1. Is the host running and on the same network?")
        print("    2. Did you copy the address from the host correctly?")
        print("    3. Firewall blocking the port?")
        return

    try:
        await agent.run_interactive()
    except (KeyboardInterrupt, EOFError):
        pass

    await agent.close()
    print(f"\n  {args.name} disconnected.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Guest stopped.")
