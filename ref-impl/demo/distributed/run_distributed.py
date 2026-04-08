#!/usr/bin/env python3
"""
MPAC Distributed Demo — Coordinator + Agents over WebSocket.

Architecture:
  - Coordinator runs as a WebSocket server (separate async task, simulating separate process)
  - Each agent runs as a separate async task, connecting via WebSocket
  - Agents make decisions CONCURRENTLY via Claude API
  - Scenario forces scope overlap to test conflict detection over the wire

This is the first test where MPAC messages travel over a real network transport.

NOTE: This demo calls the Anthropic API (~6 requests per run).
      You will need a valid API key in local_config.json.
"""
import sys, os, json, asyncio, logging, time, signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))

from ws_coordinator import WSCoordinator
from ws_agent import WSAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-18s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")

HOST = "localhost"
PORT = 8766
SESSION_ID = "ws-distributed-001"
COORDINATOR_URI = f"ws://{HOST}:{PORT}"

# ═══════════════════════════════════════════════════════════════
#  Project context — designed to force both agents toward auth.py
# ═══════════════════════════════════════════════════════════════

PROJECT_CONTEXT = """
A Python web application (Flask) with the following structure:

  src/
    app.py              — Flask app factory, route registration
    auth.py             — Authentication: login, logout, token validation  ← CRITICAL BUG HERE
    auth_middleware.py   — Request authentication middleware (duplicates auth.py logic)
    models.py           — SQLAlchemy models: User, Session, Permission
    database.py         — Database connection, migration helpers
    api/
      users.py          — User CRUD API endpoints
      admin.py          — Admin panel API endpoints
    utils/
      validators.py     — Input validation utilities
      crypto.py         — Password hashing, token generation

URGENT issues (both relate to auth.py):
1. auth.py has a critical security bug: tokens aren't validated for expiry — ANY expired token is accepted
2. auth.py's login function has a timing side-channel that leaks whether a username exists
3. auth_middleware.py duplicates ALL logic from auth.py and is now dangerously out of sync
4. crypto.py uses the same auth token generation as auth.py and must stay consistent
"""

# ═══════════════════════════════════════════════════════════════
#  Output helpers
# ═══════════════════════════════════════════════════════════════

def phase(title: str):
    w = 70
    log.info("")
    log.info("═" * w)
    log.info(f"  {title}")
    log.info("═" * w)
    log.info("")


# ═══════════════════════════════════════════════════════════════
#  Main scenario
# ═══════════════════════════════════════════════════════════════

async def run_scenario():
    """Run the full distributed scenario."""

    # ──── Phase 0: Start coordinator ────
    phase("Phase 0: Starting WebSocket Coordinator")

    coordinator = WSCoordinator(SESSION_ID, HOST, PORT)

    # Start coordinator server in background
    server = await asyncio.start_server(lambda r, w: None, HOST, 0)  # dummy, just to check port
    server.close()

    import websockets as ws_lib
    ws_server = await ws_lib.serve(coordinator.handler, HOST, PORT)
    heartbeat_task = asyncio.create_task(coordinator.heartbeat_loop())
    log.info(f"Coordinator running on ws://{HOST}:{PORT}")

    await asyncio.sleep(0.5)  # let server start

    # ──── Phase 1: Create agents ────
    phase("Phase 1: Agents Connect via WebSocket")

    alice = WSAgent(
        name="Alice",
        role_description=(
            "You are a security-focused engineer. You care most about auth, tokens, "
            "and access control. The auth.py token expiry bug is your TOP PRIORITY. "
            "You also want to fix the timing side-channel in auth.py login."
        ),
    )
    bob = WSAgent(
        name="Bob",
        role_description=(
            "You are a code quality engineer focused on eliminating dangerous code duplication. "
            "auth_middleware.py duplicates ALL logic from auth.py and is now out of sync — "
            "this is a security risk. You MUST refactor auth.py to extract shared logic, "
            "then update auth_middleware.py to use it. auth.py is your primary target."
        ),
    )

    # Both agents connect concurrently
    await asyncio.gather(
        alice.connect(COORDINATOR_URI, SESSION_ID),
        bob.connect(COORDINATOR_URI, SESSION_ID),
    )

    # ──── Phase 2: Both HELLO concurrently ────
    phase("Phase 2: Concurrent HELLO")

    await asyncio.gather(
        alice.do_hello(),
        bob.do_hello(),
    )

    log.info(f"Alice session_info: participants={alice.session_info['payload'].get('participant_count')}")
    log.info(f"Bob session_info: participants={bob.session_info['payload'].get('participant_count')}")

    # ──── Phase 3: Both decide intent CONCURRENTLY via Claude ────
    phase("Phase 3: Concurrent Intent Decisions (Claude API)")

    log.info("Both agents asking Claude what to work on IN PARALLEL...")
    t0 = time.time()

    # This is the key difference from the old demo:
    # both agents call Claude API at the same time, no coordination
    alice_intent_future = asyncio.get_event_loop().run_in_executor(
        None, alice.decide_intent, PROJECT_CONTEXT, []
    )
    bob_intent_future = asyncio.get_event_loop().run_in_executor(
        None, bob.decide_intent, PROJECT_CONTEXT, []
    )

    alice_intent, bob_intent = await asyncio.gather(alice_intent_future, bob_intent_future)
    elapsed = time.time() - t0

    log.info(f"Decisions made in {elapsed:.1f}s (parallel)")
    log.info(f"Alice intent: {alice_intent.get('objective', '?')}")
    log.info(f"  files: {alice_intent.get('files', [])}")
    log.info(f"Bob intent: {bob_intent.get('objective', '?')}")
    log.info(f"  files: {bob_intent.get('files', [])}")

    # Check overlap
    alice_files = set(alice_intent.get("files", []))
    bob_files = set(bob_intent.get("files", []))
    overlap = alice_files & bob_files
    if overlap:
        log.info(f"*** FILE OVERLAP DETECTED (pre-protocol): {sorted(overlap)} ***")
    else:
        log.info("No file overlap in decisions (agents avoided each other)")

    # ──── Phase 4: Both announce intents concurrently ────
    phase("Phase 4: Concurrent INTENT_ANNOUNCE over WebSocket")

    await asyncio.gather(
        alice.do_announce_intent(alice_intent),
        bob.do_announce_intent(bob_intent),
    )

    # Drain inboxes to collect any conflict reports
    await asyncio.gather(
        alice.drain_inbox(2.0),
        bob.drain_inbox(2.0),
    )

    alice_conflicts = alice.conflicts_received
    bob_conflicts = bob.conflicts_received

    log.info(f"Alice received {len(alice_conflicts)} conflict report(s)")
    log.info(f"Bob received {len(bob_conflicts)} conflict report(s)")

    # ──── Phase 5: Handle conflicts if any ────
    all_conflicts = alice_conflicts + bob_conflicts
    # Deduplicate by conflict_id
    seen_ids = set()
    unique_conflicts = []
    for c in all_conflicts:
        cid = c.get("payload", {}).get("conflict_id", "")
        if cid not in seen_ids:
            seen_ids.add(cid)
            unique_conflicts.append(c)

    if unique_conflicts:
        phase(f"Phase 5: CONFLICT NEGOTIATION ({len(unique_conflicts)} conflict(s))")

        for conflict_msg in unique_conflicts:
            cp = conflict_msg.get("payload", {})
            conflict_id = cp.get("conflict_id", "?")
            log.info(f"Conflict {conflict_id}: {cp.get('category')} | severity={cp.get('severity')}")
            log.info(f"  {cp.get('intent_a')} vs {cp.get('intent_b')}")

            # Both agents decide how to handle the conflict — concurrently
            log.info("Both agents deciding on conflict resolution IN PARALLEL...")

            alice_decision_future = asyncio.get_event_loop().run_in_executor(
                None, alice.decide_on_conflict, cp, alice_intent, bob_intent
            )
            bob_decision_future = asyncio.get_event_loop().run_in_executor(
                None, bob.decide_on_conflict, cp, bob_intent, alice_intent
            )

            alice_decision, bob_decision = await asyncio.gather(
                alice_decision_future, bob_decision_future
            )

            log.info(f"Alice: {alice_decision.get('response')} — {alice_decision.get('reasoning', '')[:80]}")
            log.info(f"Bob: {bob_decision.get('response')} — {bob_decision.get('reasoning', '')[:80]}")

            # ── Coordinator auto-resolve ──
            # Both agents have expressed their positions. The coordinator
            # (as a service principal with built-in authority) now issues
            # the RESOLUTION. This avoids the problem where contributor-role
            # agents cannot resolve conflicts themselves.
            alice_choice = alice_decision.get("response", "proceed")
            bob_choice = bob_decision.get("response", "proceed")

            if alice_choice == "yield":
                rationale = f"Alice yielded: {alice_decision.get('reasoning', 'N/A')}"
            elif bob_choice == "yield":
                rationale = f"Bob yielded: {bob_decision.get('reasoning', 'N/A')}"
            else:
                rationale = (f"Both agents chose to {alice_choice}/{bob_choice}. "
                             f"Alice: {alice_decision.get('reasoning', 'N/A')[:60]}. "
                             f"Bob: {bob_decision.get('reasoning', 'N/A')[:60]}")

            log.info(f"Coordinator auto-resolving conflict {conflict_id}...")
            resolve_responses = coordinator.coordinator.resolve_as_coordinator(
                conflict_id, decision="approved", rationale=rationale
            )

            if resolve_responses:
                # Unexpected errors
                for r in resolve_responses:
                    log.warning(f"  Resolve error: {r.get('payload', {}).get('error_code', '?')}")
            else:
                log.info(f"✓ Conflict {conflict_id} resolved by coordinator")

            # Broadcast resolution result to agents
            status_msgs = coordinator.coordinator.coordinator_status("conflict_resolved")
            for s in status_msgs:
                s_json = json.dumps(s, ensure_ascii=False)
                await coordinator._broadcast(s_json)

    else:
        phase("Phase 5: No Conflict Detected")
        log.info("Agents chose non-overlapping scopes — no conflict to negotiate.")

    # ──── Phase 6: Both plan and commit operations concurrently ────
    phase("Phase 6: Concurrent Operation Planning & Commit")

    log.info("Both agents planning operations IN PARALLEL via Claude...")

    alice_op_future = asyncio.get_event_loop().run_in_executor(
        None, alice.plan_operation, alice_intent
    )
    bob_op_future = asyncio.get_event_loop().run_in_executor(
        None, bob.plan_operation, bob_intent
    )

    alice_op, bob_op = await asyncio.gather(alice_op_future, bob_op_future)

    log.info(f"Alice op: {alice_op.get('op_id')} → {alice_op.get('target')} ({alice_op.get('op_kind')})")
    log.info(f"Bob op: {bob_op.get('op_id')} → {bob_op.get('target')} ({bob_op.get('op_kind')})")

    # Commit concurrently
    await asyncio.gather(
        alice.do_commit(alice_intent, alice_op),
        bob.do_commit(bob_intent, bob_op),
    )

    log.info("Both OP_COMMITs sent over WebSocket")

    # ──── Phase 7: Heartbeat check ────
    phase("Phase 7: Heartbeat Over WebSocket")

    await asyncio.gather(
        alice.do_heartbeat("idle"),
        bob.do_heartbeat("idle"),
    )
    log.info("Both agents sent HEARTBEAT over WebSocket")

    # Wait for coordinator status broadcast
    await asyncio.sleep(1.0)

    # ──── Phase 8: Graceful disconnect ────
    phase("Phase 8: GOODBYE & Disconnect")

    await asyncio.gather(
        alice.do_goodbye("completed"),
        bob.do_goodbye("completed"),
    )

    await asyncio.sleep(1.0)

    await asyncio.gather(
        alice.close(),
        bob.close(),
    )

    # ──── Phase 9: Results ────
    phase("RESULTS")

    transcript_path = os.path.join(os.path.dirname(__file__), "ws_demo_transcript.json")
    coordinator.save_transcript(transcript_path)

    log.info(f"Total messages over WebSocket: {len(coordinator.transcript)}")
    log.info(f"Conflicts detected: {len(unique_conflicts)}")
    log.info(f"Alice: {alice_intent.get('objective', '?')}")
    log.info(f"  files: {alice_intent.get('files', [])}")
    log.info(f"Bob: {bob_intent.get('objective', '?')}")
    log.info(f"  files: {bob_intent.get('files', [])}")

    if overlap:
        log.info(f"File overlap: {sorted(overlap)}")
        log.info(f"Conflict {'WAS' if unique_conflicts else 'WAS NOT'} detected by coordinator")

    # Verify coordinator state
    snap = coordinator.coordinator.snapshot()
    log.info(f"\nFinal coordinator state:")
    log.info(f"  participants: {len(snap['participants'])}")
    log.info(f"  intents: {len(snap['intents'])}")
    for i in snap['intents']:
        log.info(f"    {i['intent_id']}: {i['state']}")
    log.info(f"  operations: {len(snap['operations'])}")
    for o in snap['operations']:
        log.info(f"    {o['op_id']}: {o['state']}")
    log.info(f"  conflicts: {len(snap['conflicts'])}")
    for c in snap['conflicts']:
        log.info(f"    {c['conflict_id'][:20]}...: {c['state']}")

    # ──── Cleanup ────
    heartbeat_task.cancel()
    ws_server.close()
    await ws_server.wait_closed()

    log.info("\nDone. Coordinator shut down.")

    # Return summary for programmatic use
    return {
        "total_messages": len(coordinator.transcript),
        "conflicts": len(unique_conflicts),
        "alice_files": list(alice_files),
        "bob_files": list(bob_files),
        "overlap": list(overlap),
        "transcript_path": transcript_path,
    }


if __name__ == "__main__":
    result = asyncio.run(run_scenario())
    print(f"\n{'='*70}")
    print(f"  SUMMARY: {result['total_messages']} messages, {result['conflicts']} conflicts")
    print(f"  Overlap: {result['overlap'] or 'none'}")
    print(f"  Transcript: {result['transcript_path']}")
    print(f"{'='*70}")
