#!/usr/bin/env python3
"""
Host site: Start MPAC coordinator with workspace + interactive Agent Alice.

Usage:
    cd examples/two_machine_demo/host
    pip install ../../../mpac-package
    python run.py
"""
import asyncio
import json
import logging
import os

from mpac_protocol import MPACServer, MPACAgent

logging.basicConfig(
    level=logging.WARNING,  # Quiet — interactive UI handles output
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SCRIPT_DIR, "config.json")) as f:
    cfg = json.load(f)["anthropic"]

SESSION_ID = "collab-session-001"
HOST = "0.0.0.0"
PORT = 8766
WORKSPACE = os.path.join(SCRIPT_DIR, "workspace")


async def main():
    print()
    print("  ============================================")
    print("    MPAC Collaborative Workspace — Host (A)")
    print("  ============================================")
    print()

    # 1. Start coordinator
    server = MPACServer(
        session_id=SESSION_ID,
        host=HOST,
        port=PORT,
        workspace_dir=WORKSPACE,
    )
    ws_server, heartbeat_task = await server.run_background()

    # Show connection info
    # Get local IP for sharing
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"

    print(f"  Coordinator running!")
    print(f"  Session: {SESSION_ID}")
    print()
    print(f"  +--------------------------------------------------+")
    print(f"  | Share this address with collaborators:            |")
    print(f"  |                                                    |")
    print(f"  |   ws://{local_ip}:{PORT:<5d}                        |")
    print(f"  |                                                    |")
    print(f"  | (Same WiFi)  They run:                            |")
    print(f"  |   python run.py ws://{local_ip}:{PORT}             |")
    print(f"  +--------------------------------------------------+")

    await asyncio.sleep(1)

    # 2. Start interactive agent
    alice = MPACAgent(
        name="Alice",
        api_key=cfg["api_key"],
        model=cfg.get("model", "claude-sonnet-4-6"),
        role_description="Security engineer focused on authentication and authorization bugs",
    )
    await alice.connect(f"ws://localhost:{PORT}", SESSION_ID)

    try:
        await alice.run_interactive()
    except (KeyboardInterrupt, EOFError):
        pass

    await alice.close()

    # Save final state
    output_dir = os.path.join(SCRIPT_DIR, "output")
    os.makedirs(output_dir, exist_ok=True)
    server.file_store.save_to_directory(output_dir)
    server.save_transcript(os.path.join(output_dir, "transcript.json"))
    print(f"\n  Results saved to {output_dir}/")

    heartbeat_task.cancel()
    ws_server.close()
    await ws_server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Server stopped.")
