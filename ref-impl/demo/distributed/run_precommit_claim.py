#!/usr/bin/env python3
"""
MPAC Demo: Pre-Commit Execution Model + INTENT_CLAIM Fault Recovery

Exercises 6 previously uncovered message types:
  INTENT_UPDATE, INTENT_WITHDRAW, INTENT_CLAIM, INTENT_CLAIM_STATUS,
  OP_PROPOSE, OP_REJECT

Scenario: 3 agents (Alice, Bob, Charlie) do a coordinated API refactoring
in pre-commit mode. Bob's proposal gets authorized and committed; Charlie's
proposal is rejected after he withdraws his intent; Alice "crashes" and Bob
claims her suspended work via INTENT_CLAIM.

Requires: pip install websockets httpx anthropic
           local_config.json with Anthropic API key
"""
import sys, os, json, asyncio, uuid, logging, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))

from ws_coordinator import WSCoordinator
from ws_agent import WSAgent, _client, _model, _cfg

from mpac.models import Scope, MessageType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("precommit_claim")

HOST, PORT = "localhost", 8770
SESSION_ID = f"sess-precommit-{uuid.uuid4().hex[:6]}"
EXECUTOR = ThreadPoolExecutor(max_workers=6)

PROJECT_CONTEXT = """
An API gateway project with these files:
- api/endpoints.py    — REST endpoint definitions
- api/middleware.py   — request/response middleware
- models/user.py      — user data model and validation
- models/session.py   — session management model
- utils/validators.py — shared input validators
- tests/test_api.py   — API integration tests

Current task: refactor the authentication flow. The auth logic is scattered
across endpoints.py, middleware.py, and validators.py. The user model needs
a new `last_login` field. Tests need updating to match.
"""

# ── Extended Agent with new message helpers ─────────────────────

class ExtendedWSAgent(WSAgent):
    """WSAgent extended with pre-commit and claim support."""

    def __init__(self, name, role_description, roles=None, **kwargs):
        super().__init__(name, role_description, **kwargs)
        if roles:
            self.participant.roles = roles
            self.participant.capabilities.extend([
                "intent.update", "intent.withdraw", "intent.claim",
            ])

    async def do_propose(self, intent_id, op_plan):
        """Send OP_PROPOSE and wait for COORDINATOR_STATUS authorization."""
        msg = self.participant.propose_op(
            self.session_id,
            op_plan["op_id"],
            intent_id,
            op_plan["target"],
            op_plan["op_kind"],
        )
        await self.send(msg)
        # Wait for authorization or rejection
        deadline = time.time() + 10.0
        while time.time() < deadline:
            resp = await self.recv(timeout=5.0)
            if resp is None:
                continue
            mt = resp.get("message_type", "")
            if mt == "COORDINATOR_STATUS" and resp.get("payload", {}).get("event") == "authorization":
                self.log.info(f"  OP_PROPOSE authorized: {op_plan['op_id']}")
                return resp
            if mt == "OP_REJECT":
                self.log.info(f"  OP_PROPOSE rejected: {resp['payload'].get('reason')}")
                return resp
            if mt == "PROTOCOL_ERROR":
                self.log.info(f"  OP_PROPOSE error: {resp['payload'].get('error_code')}")
                return resp
            # put other messages back
            if mt == "CONFLICT_REPORT":
                self.conflicts_received.append(resp)
            elif mt != "COORDINATOR_STATUS":
                await self.inbox.put(resp)
        return None

    async def do_precommit_commit(self, intent_id, op_plan):
        """Send OP_COMMIT as pre-commit completion (after authorization)."""
        msg = self.participant.commit_op(
            self.session_id,
            op_plan["op_id"],
            intent_id,
            op_plan["target"],
            op_plan["op_kind"],
            state_ref_before=op_plan.get("state_ref_before"),
            state_ref_after=op_plan.get("state_ref_after"),
        )
        self.my_ops.append(op_plan)
        await self.send(msg)
        await asyncio.sleep(0.5)

    async def do_intent_update(self, intent_id, objective=None, new_files=None):
        """Send INTENT_UPDATE."""
        scope = Scope(kind="file_set", resources=new_files) if new_files else None
        msg = self.participant.update_intent(
            self.session_id, intent_id, objective=objective, scope=scope,
        )
        await self.send(msg)
        await asyncio.sleep(0.5)

    async def do_intent_withdraw(self, intent_id, reason=None):
        """Send INTENT_WITHDRAW."""
        msg = self.participant.withdraw_intent(self.session_id, intent_id, reason=reason)
        await self.send(msg)
        await asyncio.sleep(0.3)

    async def do_intent_claim(self, claim_id, original_intent_id, original_principal_id,
                               new_intent_id, objective, files, justification=None):
        """Send INTENT_CLAIM and wait for INTENT_CLAIM_STATUS."""
        scope = Scope(kind="file_set", resources=files)
        msg = self.participant.claim_intent(
            self.session_id, claim_id, original_intent_id,
            original_principal_id, new_intent_id, objective, scope,
            justification=justification,
        )
        await self.send(msg)
        # Wait for approval — may come immediately or after grace period
        deadline = time.time() + 15.0
        while time.time() < deadline:
            resp = await self.recv(timeout=5.0)
            if resp is None:
                continue
            mt = resp.get("message_type", "")
            if mt == "INTENT_CLAIM_STATUS":
                decision = resp.get("payload", {}).get("decision", "?")
                self.log.info(f"  INTENT_CLAIM decision: {decision}")
                return resp
            if mt == "CONFLICT_REPORT":
                self.conflicts_received.append(resp)
            elif mt != "COORDINATOR_STATUS":
                await self.inbox.put(resp)
        return None

    async def do_conflict_ack(self, conflict_id, ack_type="seen"):
        """Send CONFLICT_ACK."""
        msg = self.participant.ack_conflict(self.session_id, conflict_id, ack_type)
        await self.send(msg)


def phase(n, title):
    log.info(f"\n{'='*60}")
    log.info(f"  PHASE {n}: {title}")
    log.info(f"{'='*60}\n")


async def run_precommit_claim():
    # ── Phase 0: Start coordinator ──────────────────────────────
    phase(0, "Start coordinator (pre-commit + governance)")

    coordinator = WSCoordinator(
        SESSION_ID, HOST, PORT,
        execution_model="pre_commit",
        compliance_profile="governance",
        unavailability_timeout_sec=60.0,   # long enough for normal phases
        resolution_timeout_sec=300.0,
        intent_claim_grace_sec=0.0,
    )
    server_task = asyncio.create_task(coordinator.run())
    await asyncio.sleep(1.0)
    log.info(f"Coordinator running on ws://{HOST}:{PORT}")
    log.info(f"Execution model: pre_commit | Compliance: governance")

    # ── Phase 1: Agents connect ─────────────────────────────────
    phase(1, "Agents connect (HELLO → SESSION_INFO)")

    alice = ExtendedWSAgent("Alice", "API designer — redesigns endpoint structure",
                            roles=["owner"])
    bob = ExtendedWSAgent("Bob", "Backend engineer — implements data models and logic",
                          roles=["owner"])
    charlie = ExtendedWSAgent("Charlie", "Test engineer — writes integration tests",
                              roles=["owner"])

    uri = f"ws://{HOST}:{PORT}"
    await asyncio.gather(
        alice.connect(uri, SESSION_ID),
        bob.connect(uri, SESSION_ID),
        charlie.connect(uri, SESSION_ID),
    )

    for agent in [alice, bob, charlie]:
        resp = await agent.do_hello()
        if resp:
            em = resp["payload"].get("execution_model", "?")
            log.info(f"  {agent.name} joined — execution_model={em}")

    # ── Phase 2: Intent decisions via Claude ─────────────────────
    phase(2, "Intent decisions via Claude (parallel)")

    loop = asyncio.get_event_loop()

    alice_intent = await loop.run_in_executor(
        EXECUTOR, alice.decide_intent, PROJECT_CONTEXT, [])

    # Ensure Alice targets endpoints and middleware
    if "api/endpoints.py" not in alice_intent.get("files", []):
        alice_intent["files"] = ["api/endpoints.py", "api/middleware.py"]
    alice_intent["intent_id"] = f"intent-alice-{uuid.uuid4().hex[:6]}"

    bob_intent = await loop.run_in_executor(
        EXECUTOR, bob.decide_intent, PROJECT_CONTEXT,
        [{"agent": "Alice", "objective": alice_intent["objective"],
          "files": alice_intent["files"]}])
    # Ensure Bob targets user model (overlaps on middleware)
    if "models/user.py" not in bob_intent.get("files", []):
        bob_intent["files"] = ["models/user.py", "api/middleware.py"]
    bob_intent["intent_id"] = f"intent-bob-{uuid.uuid4().hex[:6]}"

    charlie_intent = await loop.run_in_executor(
        EXECUTOR, charlie.decide_intent, PROJECT_CONTEXT,
        [{"agent": "Alice", "objective": alice_intent["objective"],
          "files": alice_intent["files"]},
         {"agent": "Bob", "objective": bob_intent["objective"],
          "files": bob_intent["files"]}])
    # Ensure Charlie targets tests + endpoints (overlaps with Alice)
    if "tests/test_api.py" not in charlie_intent.get("files", []):
        charlie_intent["files"] = ["tests/test_api.py", "api/endpoints.py"]
    charlie_intent["intent_id"] = f"intent-charlie-{uuid.uuid4().hex[:6]}"

    for name, intent in [("Alice", alice_intent), ("Bob", bob_intent), ("Charlie", charlie_intent)]:
        log.info(f"  {name}: {intent['objective'][:60]}...")
        log.info(f"         files: {intent['files']}")

    # ── Phase 3: INTENT_ANNOUNCE → conflict detection ────────────
    phase(3, "INTENT_ANNOUNCE → conflict detection")

    for agent, intent in [(alice, alice_intent), (bob, bob_intent), (charlie, charlie_intent)]:
        await agent.do_announce_intent(intent)
        log.info(f"  {agent.name} announced: {intent['intent_id']}")

    # Collect conflict reports
    for agent in [alice, bob, charlie]:
        await agent.drain_inbox(duration=2.0)

    all_conflicts = []
    for agent in [alice, bob, charlie]:
        for c in agent.conflicts_received:
            cid = c["payload"].get("conflict_id", "?")
            if cid not in [x["payload"]["conflict_id"] for x in all_conflicts]:
                all_conflicts.append(c)
        log.info(f"  {agent.name} received {len(agent.conflicts_received)} conflict(s)")

    log.info(f"  Total unique conflicts: {len(all_conflicts)}")

    # ── Phase 4: INTENT_UPDATE — Alice expands scope ─────────────
    phase(4, "INTENT_UPDATE — Alice expands scope")

    new_files = alice_intent["files"] + ["utils/validators.py"]
    alice_intent["files"] = new_files
    await alice.do_intent_update(
        alice_intent["intent_id"],
        objective="Refactor auth flow across endpoints, middleware AND validators",
        new_files=new_files,
    )
    log.info(f"  Alice expanded scope to: {new_files}")

    # Drain for any new conflict reports from scope expansion
    for agent in [alice, bob, charlie]:
        await agent.drain_inbox(duration=1.5)

    # ── Phase 5: OP_PROPOSE → authorization → OP_COMMIT (Bob) ───
    phase(5, "OP_PROPOSE → authorization → OP_COMMIT (Bob, pre-commit)")

    bob_op = await loop.run_in_executor(EXECUTOR, bob.plan_operation, bob_intent)
    bob_op["op_id"] = f"op-bob-{uuid.uuid4().hex[:6]}"
    bob_op["target"] = bob_intent["files"][0]  # models/user.py
    log.info(f"  Bob proposes: {bob_op['op_id']} on {bob_op['target']}")

    auth_resp = await bob.do_propose(bob_intent["intent_id"], bob_op)
    if auth_resp and auth_resp.get("message_type") == "COORDINATOR_STATUS":
        log.info(f"  Bob's proposal authorized by coordinator")
        # Now Bob commits (pre-commit completion)
        await bob.do_precommit_commit(bob_intent["intent_id"], bob_op)
        log.info(f"  Bob committed: {bob_op['op_id']}")
    else:
        log.warning(f"  Bob's proposal was not authorized — unexpected")

    # ── Phase 6: Resolve conflicts ───────────────────────────────
    phase(6, "Resolve conflicts")

    for conflict in all_conflicts:
        cid = conflict["payload"]["conflict_id"]
        log.info(f"  Resolving {cid}")
        coordinator.coordinator.resolve_as_coordinator(
            cid,
            decision="approved",
            rationale="Resolved in favor of primary engineers; test intent deferred",
        )
        log.info(f"  Resolved: {cid}")

    # Drain resolution broadcasts
    for agent in [alice, bob, charlie]:
        await agent.drain_inbox(duration=1.5)

    # ── Phase 7: INTENT_WITHDRAW + OP_REJECT (Charlie) ───────────
    phase(7, "INTENT_WITHDRAW + OP_REJECT (Charlie)")

    await charlie.do_intent_withdraw(
        charlie_intent["intent_id"],
        reason="Primary engineers took priority on overlapping files",
    )
    log.info(f"  Charlie withdrew: {charlie_intent['intent_id']}")

    # Charlie tries to propose against his withdrawn intent → should be rejected
    charlie_op = {
        "op_id": f"op-charlie-{uuid.uuid4().hex[:6]}",
        "target": "tests/test_api.py",
        "op_kind": "replace",
        "summary": "Update tests",
        "state_ref_before": f"sha256:{uuid.uuid4().hex[:12]}",
        "state_ref_after": f"sha256:{uuid.uuid4().hex[:12]}",
    }
    log.info(f"  Charlie attempts OP_PROPOSE on withdrawn intent...")
    reject_resp = await charlie.do_propose(charlie_intent["intent_id"], charlie_op)
    if reject_resp:
        mt = reject_resp.get("message_type", "")
        if mt == "OP_REJECT":
            log.info(f"  OP_REJECT received: {reject_resp['payload'].get('reason', '?')}")
        elif mt == "PROTOCOL_ERROR":
            log.info(f"  PROTOCOL_ERROR received: {reject_resp['payload'].get('error_code', '?')}")
        else:
            log.info(f"  Response: {mt}")
    else:
        log.info(f"  No response (timeout)")

    # ── Phase 8: Alice crashes ───────────────────────────────────
    phase(8, "Alice crashes — liveness timeout → intent SUSPENDED")

    # Send heartbeats from Bob and Charlie to keep them alive
    for agent in [bob, charlie]:
        await agent.do_heartbeat("working")

    log.info(f"  Closing Alice's connection to simulate crash...")
    await alice.close()
    await asyncio.sleep(1.0)

    # Directly trigger unavailability detection by backdating Alice's last_seen
    alice_pid = alice.principal_id
    alice_info = coordinator.coordinator.participants.get(alice_pid)
    if alice_info:
        alice_info.last_seen = datetime.now(timezone.utc) - timedelta(seconds=120)
        log.info(f"  Backdated Alice's last_seen to trigger unavailability")

    # Run liveness check and broadcast results
    liveness_responses = coordinator.coordinator.check_liveness()
    for resp_dict in liveness_responses:
        coordinator.transcript.append(resp_dict)
        # Broadcast to connected agents
        for ws in list(coordinator.connections.values()):
            try:
                await ws.send(json.dumps(resp_dict, ensure_ascii=False))
            except Exception:
                pass
        log.info(f"  Broadcast: {resp_dict.get('message_type')}")

    await asyncio.sleep(1.0)

    alice_info = coordinator.coordinator.participants.get(alice_pid)
    if alice_info:
        log.info(f"  Alice available: {alice_info.is_available}")

    # Check intent states
    for iid, intent in coordinator.coordinator.intents.items():
        if intent.principal_id == alice_pid:
            log.info(f"  Alice's intent {iid}: state={intent.state_machine.current_state}")

    # Bob and Charlie receive PARTICIPANT_UNAVAILABLE notification
    for agent in [bob, charlie]:
        await agent.drain_inbox(duration=2.0)

    # ── Phase 9: INTENT_CLAIM — Bob claims Alice's work ──────────
    phase(9, "INTENT_CLAIM — Bob claims Alice's suspended intent")

    # Find Alice's suspended intent
    alice_suspended_intent = None
    for iid, intent in coordinator.coordinator.intents.items():
        if intent.principal_id == alice_pid and str(intent.state_machine.current_state) != "IntentState.WITHDRAWN":
            alice_suspended_intent = iid
            break

    if alice_suspended_intent:
        # Heartbeat to ensure Bob and Charlie are seen as available
        for agent in [bob, charlie]:
            await agent.do_heartbeat("working")
        await asyncio.sleep(0.5)

        claim_id = f"claim-bob-{uuid.uuid4().hex[:6]}"
        new_intent_id = f"intent-bob-claimed-{uuid.uuid4().hex[:6]}"
        log.info(f"  Bob claiming Alice's intent: {alice_suspended_intent}")

        claim_resp = await bob.do_intent_claim(
            claim_id=claim_id,
            original_intent_id=alice_suspended_intent,
            original_principal_id=alice_pid,
            new_intent_id=new_intent_id,
            objective=f"Continue Alice's auth refactor (claimed after crash)",
            files=alice_intent["files"],
            justification="Alice crashed; continuing her work to meet deadline",
        )

        if claim_resp:
            decision = claim_resp.get("payload", {}).get("decision", "?")
            log.info(f"  Claim decision: {decision}")
            if decision == "approved":
                log.info(f"  New intent: {new_intent_id} is now ACTIVE for Bob")
        else:
            log.warning(f"  No INTENT_CLAIM_STATUS received")
    else:
        log.warning(f"  No suspended intent found for Alice")
        new_intent_id = None

    # ── Phase 10: Bob works on claimed scope ─────────────────────
    phase(10, "Bob works on claimed scope (propose + commit)")

    if new_intent_id and alice_suspended_intent:
        claimed_op = await loop.run_in_executor(
            EXECUTOR, bob.plan_operation,
            {"intent_id": new_intent_id, "files": alice_intent["files"],
             "objective": "Continue auth refactor on claimed scope"},
        )
        claimed_op["op_id"] = f"op-bob-claimed-{uuid.uuid4().hex[:6]}"
        claimed_op["target"] = alice_intent["files"][0]

        log.info(f"  Bob proposes on claimed scope: {claimed_op['target']}")
        auth_resp = await bob.do_propose(new_intent_id, claimed_op)
        if auth_resp and auth_resp.get("message_type") == "COORDINATOR_STATUS":
            log.info(f"  Proposal authorized — committing")
            await bob.do_precommit_commit(new_intent_id, claimed_op)
            log.info(f"  Bob committed on claimed scope: {claimed_op['op_id']}")

    # ── Phase 11: Verification + cleanup ─────────────────────────
    phase(11, "Verification + cleanup")

    # State snapshot
    snapshot = coordinator.coordinator.snapshot()
    log.info(f"  Lamport clock: {snapshot['lamport_clock']}")
    log.info(f"  Intents:")
    for intent in snapshot.get("intents", []):
        log.info(f"    {intent['intent_id']}: state={intent['state']}, owner={intent['principal_id']}")
    log.info(f"  Operations:")
    for op in snapshot.get("operations", []):
        log.info(f"    {op['op_id']}: state={op['state']}, target={op.get('target', '?')}")

    # Message type coverage check
    transcript = coordinator.transcript
    msg_types = set(t.get("message_type") for t in transcript if "message_type" in t)
    target_types = {"INTENT_UPDATE", "INTENT_WITHDRAW", "INTENT_CLAIM",
                    "INTENT_CLAIM_STATUS", "OP_PROPOSE", "OP_REJECT"}
    covered = target_types & msg_types
    missing = target_types - msg_types
    log.info(f"\n  Target message types covered: {sorted(covered)}")
    if missing:
        log.warning(f"  Missing: {sorted(missing)}")
    else:
        log.info(f"  ALL 6 target message types exercised!")

    # Goodbye
    for agent in [bob, charlie]:
        await agent.do_goodbye("session_complete")
    log.info(f"  Bob and Charlie disconnected")

    # Save transcript
    transcript_path = os.path.join(os.path.dirname(__file__), "precommit_claim_transcript.json")
    coordinator.save_transcript(transcript_path)
    log.info(f"  Transcript saved to {transcript_path}")

    # Cleanup
    server_task.cancel()
    log.info(f"\n{'='*60}")
    log.info(f"  DEMO COMPLETE")
    log.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(run_precommit_claim())
