#!/usr/bin/env python3
"""
Guest site: Agent Bob joins an existing MPAC session (interactive).

Usage:
    cd examples/two_machine_demo/guest
    pip install ../../../mpac-package
    python run.py [coordinator_uri]

Default: ws://localhost:8766
"""
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
with open(os.path.join(SCRIPT_DIR, "config.json")) as f:
    cfg = json.load(f)["anthropic"]

SESSION_ID = "collab-session-001"
COORDINATOR_URI = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8766"


async def main():
    print()
    print("  ============================================")
    print("    MPAC Collaborative Workspace — Join (B)")
    print("  ============================================")
    print(f"  Connecting to: {COORDINATOR_URI}")
    print()

    bob = MPACAgent(
        name="Bob",
        api_key=cfg["api_key"],
        model=cfg.get("model", "claude-sonnet-4-6"),
        role_description="API quality engineer focused on logging, validation, and error handling",
    )
    await bob.connect(COORDINATOR_URI, SESSION_ID)

    try:
        await bob.run_interactive()
    except (KeyboardInterrupt, EOFError):
        pass

    await bob.close()
    print("\n  Bob disconnected.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Agent stopped.")
