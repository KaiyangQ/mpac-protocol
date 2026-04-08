#!/usr/bin/env python3
"""
MPAC Live Demo — Two AI agents (Claude) coordinate through the MPAC protocol.

Scenario: A Python web project needs refactoring. Two agents independently decide
what to work on, announce intents, and the coordinator detects conflicts when
their scopes overlap. The agents then negotiate through the protocol.

NOTE: This demo calls the Anthropic API (~6 requests per run).
      You will need a valid API key in local_config.json.
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from ai_agent import AIAgent
from mpac.coordinator import SessionCoordinator
from mpac.models import Scope

SESSION_ID = "live-ai-session-001"

PROJECT_CONTEXT = """
A Python web application (Flask) with the following structure:

  src/
    app.py              — Flask app factory, route registration
    auth.py             — Authentication: login, logout, token validation
    auth_middleware.py   — Request authentication middleware
    models.py           — SQLAlchemy models: User, Session, Permission
    database.py         — Database connection, migration helpers
    api/
      users.py          — User CRUD API endpoints
      admin.py          — Admin panel API endpoints
    utils/
      validators.py     — Input validation utilities
      crypto.py         — Password hashing, token generation

Known issues:
1. auth.py has a security bug: tokens aren't validated for expiry
2. models.py User model is missing email uniqueness constraint
3. api/users.py has N+1 query problem on GET /users
4. auth_middleware.py duplicates logic from auth.py
5. validators.py lacks proper email format checking
"""

# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def print_phase(title):
    w = 64
    print(f"\n{'═' * w}")
    print(f"  {title}")
    print(f"{'═' * w}\n")

def print_message(label, envelope, indent=2):
    prefix = " " * indent
    mt = envelope.get("message_type", "?")
    sender = envelope.get("sender", {}).get("principal_id", "?")
    print(f"{prefix}[{mt}] from {sender}")
    payload = envelope.get("payload", {})
    for k, v in payload.items():
        val_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        if len(val_str) > 100:
            val_str = val_str[:97] + "..."
        print(f"{prefix}  {k}: {val_str}")

def print_agent_decision(agent_name, decision, label="Decision"):
    print(f"  🤖 {agent_name} {label}:")
    for k, v in decision.items():
        val_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        print(f"      {k}: {val_str}")


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    print_phase("MPAC Live Demo — AI Agent Coordination")
    print(f"  Session: {SESSION_ID}")
    print(f"  Scenario: Two AI agents independently decide how to fix a Python web app.")
    print(f"  Protocol: MPAC v0.1.10 with coordinator-managed conflict detection.\n")

    # ---- Setup ----
    coordinator = SessionCoordinator(SESSION_ID)

    agent_a = AIAgent(
        name="Alice",
        role_description="You are a security-focused engineer. You care most about auth, tokens, and access control.",
        session_id=SESSION_ID,
    )
    agent_b = AIAgent(
        name="Bob",
        role_description="You are a code quality engineer. You care about eliminating duplication. You noticed auth_middleware.py duplicates logic from auth.py, and models.py User model is incomplete. You want to refactor auth and models.",
        session_id=SESSION_ID,
    )

    transcript = []  # full message log

    def process(envelope, label=""):
        """Send envelope to coordinator, log everything."""
        transcript.append({"direction": "→ coordinator", "label": label, "envelope": envelope})
        responses = coordinator.process_message(envelope)
        for r in responses:
            transcript.append({"direction": "← coordinator", "label": "response", "envelope": r})
            print_message("  Response", r, indent=4)
        return responses

    # ════════════════ Phase 1: Join Session ════════════════
    print_phase("Phase 1: Session Join")

    for agent in [agent_a, agent_b]:
        print(f"  {agent.name} sends HELLO...")
        hello = agent.send_hello()
        print_message(f"  {agent.name}", hello)
        responses = process(hello, f"{agent.name} HELLO")
        print()

    # ════════════════ Phase 2: Intents ════════════════
    print_phase("Phase 2: AI Agents Decide & Announce Intents")

    print("  Asking Alice (security engineer) what she wants to work on...\n")
    alice_intent = agent_a.decide_intent(PROJECT_CONTEXT, [])
    print_agent_decision("Alice", alice_intent, "intent decision")
    print()

    alice_intent_msg = agent_a.send_intent(alice_intent)
    print_message("  Alice INTENT_ANNOUNCE", alice_intent_msg)
    alice_responses = process(alice_intent_msg, "Alice intent")
    print()

    # Bob sees Alice's intent before deciding
    alice_summary = {
        "agent": "Alice",
        "objective": alice_intent["objective"],
        "files": alice_intent.get("files", []),
    }

    print("  Asking Bob (performance engineer) what he wants to work on...\n")
    bob_intent = agent_b.decide_intent(PROJECT_CONTEXT, [alice_summary])
    print_agent_decision("Bob", bob_intent, "intent decision")
    print()

    bob_intent_msg = agent_b.send_intent(bob_intent)
    print_message("  Bob INTENT_ANNOUNCE", bob_intent_msg)
    bob_responses = process(bob_intent_msg, "Bob intent")
    print()

    # ════════════════ Phase 3: Conflict? ════════════════
    conflicts = [r for r in bob_responses if r.get("message_type") == "CONFLICT_REPORT"]

    if conflicts:
        print_phase("Phase 3: CONFLICT DETECTED — Agents Negotiate")

        for conflict_msg in conflicts:
            conflict_payload = conflict_msg.get("payload", {})
            conflict_id = conflict_payload.get("conflict_id", "unknown")
            print(f"  ⚠️  Conflict {conflict_id}")
            print(f"      Category: {conflict_payload.get('category')}")
            print(f"      Intents: {conflict_payload.get('intent_a')} vs {conflict_payload.get('intent_b')}")
            print()

            # Ask both agents how they want to handle this
            print("  Asking Alice how she wants to handle the conflict...\n")
            alice_response = agent_a.decide_on_conflict(conflict_payload, alice_intent, bob_intent)
            print_agent_decision("Alice", alice_response, "conflict response")
            print()

            print("  Asking Bob how he wants to handle the conflict...\n")
            bob_response = agent_b.decide_on_conflict(conflict_payload, bob_intent, alice_intent)
            print_agent_decision("Bob", bob_response, "conflict response")
            print()

            # Determine resolution based on agent responses
            alice_choice = alice_response.get("response", "proceed")
            bob_choice = bob_response.get("response", "proceed")

            print(f"  Resolution logic: Alice={alice_choice}, Bob={bob_choice}")

            if alice_choice == "yield":
                decision = "approved"  # approve Bob's intent
                rationale = f"Alice yielded. Reason: {alice_response.get('reasoning', 'N/A')}"
            elif bob_choice == "yield":
                decision = "approved"  # approve Alice's intent
                rationale = f"Bob yielded. Reason: {bob_response.get('reasoning', 'N/A')}"
            else:
                decision = "approved"  # both proceed, coordinator approves both
                rationale = f"Both agents chose to proceed. Alice: {alice_response.get('reasoning', 'N/A')}. Bob: {bob_response.get('reasoning', 'N/A')}"

            # Send RESOLUTION
            resolution = agent_a.participant.resolve_conflict(SESSION_ID, conflict_id, decision)
            print()
            print_message("  RESOLUTION", resolution)
            process(resolution, "resolution")
            print()
    else:
        print_phase("Phase 3: No Conflict — Clean Partition")
        print("  Both agents chose non-overlapping scopes. Protocol allows parallel execution.\n")

    # ════════════════ Phase 4: Operations ════════════════
    print_phase("Phase 4: AI Agents Plan & Commit Operations")

    print("  Asking Alice to plan her code operation...\n")
    alice_op = agent_a.plan_operation(alice_intent)
    print_agent_decision("Alice", alice_op, "operation plan")
    print()

    alice_commit = agent_a.send_op_commit(alice_intent, alice_op)
    print_message("  Alice OP_COMMIT", alice_commit)
    process(alice_commit, "Alice commit")
    print()

    print("  Asking Bob to plan his code operation...\n")
    bob_op = agent_b.plan_operation(bob_intent)
    print_agent_decision("Bob", bob_op, "operation plan")
    print()

    bob_commit = agent_b.send_op_commit(bob_intent, bob_op)
    print_message("  Bob OP_COMMIT", bob_commit)
    process(bob_commit, "Bob commit")
    print()

    # ════════════════ Phase 5: OP_SUPERSEDE ════════════════
    print_phase("Phase 5: OP_SUPERSEDE — Alice Revises Her Operation")

    print("  Alice realizes her first commit needs a revision...")
    print(f"  Superseding op: {alice_op.get('op_id', 'op-alice-?')}\n")

    supersede_msg = agent_a.participant.supersede_op(
        SESSION_ID,
        op_id=f"{alice_op.get('op_id', 'op-alice')}-v2",
        supersedes_op_id=alice_op.get("op_id", ""),
        target=alice_op.get("target", "src/auth.py"),
        intent_id=alice_intent.get("intent_id"),
        reason="revised_approach",
        state_ref_after=f"sha256:{alice_op.get('op_id', 'v2')[:8]}-revised",
    )
    print_message("  OP_SUPERSEDE", supersede_msg)
    supersede_responses = process(supersede_msg, "Alice OP_SUPERSEDE")

    if not supersede_responses:
        print("  ✓ OP_SUPERSEDE accepted — old op SUPERSEDED, new op COMMITTED")
    else:
        print(f"  ✗ Unexpected response: {supersede_responses}")

    # Verify states
    old_op_id = alice_op.get("op_id", "")
    new_op_id = f"{old_op_id}-v2"
    old_op_obj = coordinator.operations.get(old_op_id)
    new_op_obj = coordinator.operations.get(new_op_id)
    if old_op_obj:
        print(f"  Old op ({old_op_id}): state={old_op_obj.state_machine.current_state.value}")
    if new_op_obj:
        print(f"  New op ({new_op_id}): state={new_op_obj.state_machine.current_state.value}")
    print()

    # ════════════════ Phase 6: Coordinator Status ════════════════
    print_phase("Phase 6: Coordinator Status")

    status_msgs = coordinator.coordinator_status("heartbeat")
    for s in status_msgs:
        print_message("  COORDINATOR_STATUS", s)
        transcript.append({"direction": "← coordinator", "label": "coordinator_status", "envelope": s})
    print()

    # ════════════════ Phase 7: State Snapshot ════════════════
    print_phase("Phase 7: State Snapshot")

    snap = coordinator.snapshot()
    print(f"  snapshot_version: {snap['snapshot_version']}")
    print(f"  protocol_version: {snap['protocol_version']}")
    print(f"  lamport_clock: {snap['lamport_clock']}")
    print(f"  participants: {len(snap['participants'])}")
    print(f"  intents: {len(snap['intents'])}")
    for intent in snap['intents']:
        print(f"    {intent['intent_id']}: state={intent['state']}")
    print(f"  operations: {len(snap['operations'])}")
    for op in snap['operations']:
        print(f"    {op['op_id']}: state={op['state']}")
    print(f"  conflicts: {len(snap['conflicts'])}")
    for c in snap['conflicts']:
        print(f"    {c['conflict_id'][:12]}...: state={c['state']}")
    print()

    # ════════════════ Phase 8: Fault Recovery ════════════════
    print_phase("Phase 8: Fault Recovery — Snapshot + Audit Log Replay")

    # Take snapshot + capture audit log position
    pre_crash_snap = coordinator.snapshot()
    audit_log_len_at_snap = len(coordinator.audit_log)
    print(f"  Snapshot taken: {len(pre_crash_snap['participants'])} participants, "
          f"{len(pre_crash_snap['intents'])} intents, "
          f"{len(pre_crash_snap['operations'])} operations")
    print(f"  Audit log position at snapshot: message #{audit_log_len_at_snap}")
    print()

    # Simulate new coordinator recovering from crash
    print("  💥 Simulating coordinator crash...")
    print("  🔄 New coordinator recovering from snapshot...\n")

    recovered = SessionCoordinator(SESSION_ID)
    recovered.recover_from_snapshot(pre_crash_snap)

    # Verify recovery
    recovered_snap = recovered.snapshot()
    print(f"  Recovered state:")
    print(f"    participants: {len(recovered_snap['participants'])}")
    print(f"    intents: {len(recovered_snap['intents'])}")
    print(f"    operations: {len(recovered_snap['operations'])}")
    print(f"    conflicts: {len(recovered_snap['conflicts'])}")
    print(f"    lamport_clock: {recovered_snap['lamport_clock']}")

    # Verify operation states survived recovery
    all_ops_match = True
    for orig_op in pre_crash_snap["operations"]:
        rec_op = recovered.operations.get(orig_op["op_id"])
        if rec_op is None or rec_op.state_machine.current_state.value != orig_op["state"]:
            all_ops_match = False
            break

    if all_ops_match:
        print("  ✓ All operation states correctly recovered (including SUPERSEDED)")
    else:
        print("  ✗ Operation state mismatch after recovery")

    # Verify the recovered coordinator can process new messages
    print("\n  Testing recovered coordinator accepts new messages...")
    test_heartbeat = agent_a.participant.heartbeat(SESSION_ID, status="idle")
    hb_responses = recovered.process_message(test_heartbeat)
    if not hb_responses:  # heartbeat produces no response
        print("  ✓ Recovered coordinator processing messages normally")
    else:
        print(f"  ✗ Unexpected response from recovered coordinator")
    print()

    # ════════════════ Phase 9: Session Close ════════════════
    print_phase("Phase 9: Session Close")

    close_msgs = coordinator.close_session("completed")
    for c in close_msgs:
        print_message("  SESSION_CLOSE", c)
        transcript.append({"direction": "← coordinator", "label": "session_close", "envelope": c})
        summary = c.get("payload", {}).get("summary", {})
        print(f"\n  Session summary:")
        for k, v in summary.items():
            print(f"    {k}: {v}")
    print()

    # Verify session is closed — try sending a message
    print("  Verifying session is closed...")
    test_msg = agent_a.participant.announce_intent(
        SESSION_ID, "intent-test-after-close", "should fail",
        Scope(kind="file_set", resources=["test.py"]),
    )
    reject = coordinator.process_message(test_msg)
    if reject and reject[0].get("payload", {}).get("error_code") == "SESSION_CLOSED":
        print("  ✓ Post-close message correctly rejected with SESSION_CLOSED error")
    else:
        print("  ✗ Post-close message was NOT rejected (unexpected)")
    print()

    # ════════════════ Summary ════════════════
    print_phase("Session Summary")
    print(f"  Total MPAC messages exchanged: {len(transcript)}")
    print(f"  Conflicts detected: {len(conflicts)}")
    print(f"  Alice's work: {alice_intent.get('objective', 'N/A')}")
    print(f"    Files: {alice_intent.get('files', [])}")
    print(f"  Bob's work: {bob_intent.get('objective', 'N/A')}")
    print(f"    Files: {bob_intent.get('files', [])}")

    # Overlap analysis
    alice_files = set(alice_intent.get("files", []))
    bob_files = set(bob_intent.get("files", []))
    overlap = alice_files & bob_files
    if overlap:
        print(f"\n  Overlapping files: {sorted(overlap)}")
        print(f"  Conflict was {'detected and resolved' if conflicts else 'NOT detected (bug?)'}.")
    else:
        print(f"\n  No file overlap — agents naturally partitioned work.")

    print(f"\n  v0.1.10 features exercised:")
    print(f"    ✓ COORDINATOR_STATUS heartbeat")
    print(f"    ✓ State snapshot ({len(snap['participants'])} participants, {len(snap['intents'])} intents, {len(snap['operations'])} ops)")
    print(f"    ✓ OP_SUPERSEDE (Alice revised her commit)")
    print(f"    ✓ Fault recovery (snapshot → crash → recover → verify)")
    print(f"    ✓ SESSION_CLOSE with summary")
    print(f"    ✓ Post-close message rejection")

    # Write full transcript
    transcript_path = os.path.join(os.path.dirname(__file__), "ai_demo_transcript.json")
    with open(transcript_path, "w") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    print(f"\n  Full transcript: {transcript_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
