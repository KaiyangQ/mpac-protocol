#!/usr/bin/env python3
"""
MPAC End-to-End Test — Agents ACTUALLY modify code files.

This is the real deal:
1. Coordinator runs on WebSocket
2. Two agents connect, read REAL source files, decide what to fix
3. They announce intents through MPAC — conflict detected on auth.py
4. After coordinator resolves the conflict, agents generate REAL code fixes via Claude
5. Agents write the fixed code back to disk
6. We diff the results to prove the protocol coordinated real work

The test project (test_project/src/) has intentional bugs that both agents will try to fix.

NOTE: This demo calls the Anthropic API (~6-10 requests per run).
      You will need a valid API key in local_config.json.
"""
import sys, os, json, asyncio, logging, time, shutil, difflib, hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))

import websockets
from ws_coordinator import WSCoordinator
from ws_agent import WSAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-18s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("e2e")

HOST = "localhost"
PORT = 8767
SESSION_ID = "e2e-real-code-001"
COORDINATOR_URI = f"ws://{HOST}:{PORT}"

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_SRC = os.path.join(SCRIPT_DIR, "test_project", "src")
WORK_DIR = os.path.join("/tmp", "mpac_e2e_workdir")


def phase(title: str):
    log.info("")
    log.info("=" * 70)
    log.info(f"  {title}")
    log.info("=" * 70)
    log.info("")


def file_hash(path: str) -> str:
    """SHA-256 hash of file contents."""
    with open(path, "r") as f:
        return hashlib.sha256(f.read().encode()).hexdigest()[:16]


def read_file(path: str) -> str:
    """Read a file and return contents."""
    with open(path, "r") as f:
        return f.read()


def write_file(path: str, content: str):
    """Write content to a file."""
    with open(path, "w") as f:
        f.write(content)


def show_diff(original: str, modified: str, filename: str):
    """Show unified diff between original and modified content."""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    diff_text = "".join(diff)
    if diff_text:
        log.info(f"  Diff for {filename}:")
        for line in diff_text.splitlines():
            log.info(f"    {line}")
    else:
        log.info(f"  {filename}: no changes")
    return diff_text


# ═══════════════════════════════════════════════════════════════
#  Enhanced agent — can read/write real files
# ═══════════════════════════════════════════════════════════════

import anthropic

_cfg_path = os.path.join(SCRIPT_DIR, '..', '..', '..', 'local_config.json')
with open(_cfg_path) as f:
    _cfg = json.load(f)["anthropic"]

_client = anthropic.Anthropic(api_key=_cfg["api_key"])
_model = _cfg.get("model", "claude-sonnet-4-6")


def ask_claude_for_fix(agent_name: str, role: str, file_path: str, file_content: str,
                       objective: str, other_agent_work: str = "") -> str:
    """Ask Claude to generate a fixed version of a source file."""
    system = f"""You are {agent_name}, an AI coding agent. {role}

You are given a Python source file with known bugs. Your job is to fix the bugs
according to your objective. Return ONLY the complete fixed file — no explanations,
no markdown fences, no commentary. Just the Python code."""

    coordination_note = ""
    if other_agent_work:
        coordination_note = f"""
IMPORTANT COORDINATION NOTE:
Another agent is also working on this codebase. Here is what they are doing:
{other_agent_work}

You must NOT conflict with their work. Focus ONLY on your specific objective.
If the other agent is also modifying this file, make your changes compatible."""

    user = f"""OBJECTIVE: {objective}
{coordination_note}
FILE: {file_path}

CURRENT CONTENT:
```python
{file_content}
```

Return the complete fixed file. Only fix what matches your objective — don't touch unrelated code."""

    resp = _client.messages.create(
        model=_model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    result = resp.content[0].text

    # Strip markdown fences and explanation text if Claude wraps them
    import re
    blocks = list(re.finditer(
        r"```(?:python|py)?\s*\n(.*?)```",
        result, re.DOTALL,
    ))
    if blocks:
        best = max(blocks, key=lambda m: len(m.group(1)))
        result = best.group(1).rstrip("\n")
    elif result.startswith("```"):
        lines = result.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        elif lines[0].startswith("```"):
            lines = lines[1:]
        result = "\n".join(lines)

    return result


# ═══════════════════════════════════════════════════════════════
#  Main scenario
# ═══════════════════════════════════════════════════════════════

async def run_e2e():
    # ──── Phase 0: Setup — copy source to working directory ────
    phase("Phase 0: Setup Working Directory")

    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)
    shutil.copytree(PROJECT_SRC, WORK_DIR)
    log.info(f"Copied {PROJECT_SRC} → {WORK_DIR}")

    # Record original hashes
    original_hashes = {}
    original_contents = {}
    for root, dirs, files in os.walk(WORK_DIR):
        for fname in files:
            if fname.endswith(".py"):
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, WORK_DIR)
                original_hashes[rel] = file_hash(fpath)
                original_contents[rel] = read_file(fpath)
                log.info(f"  {rel}: {original_hashes[rel]}")

    # ──── Phase 1: Start coordinator ────
    phase("Phase 1: Start WebSocket Coordinator")

    coordinator = WSCoordinator(SESSION_ID, HOST, PORT)
    ws_server = await websockets.serve(coordinator.handler, HOST, PORT)
    heartbeat_task = asyncio.create_task(coordinator.heartbeat_loop())
    log.info(f"Coordinator on ws://{HOST}:{PORT}")

    await asyncio.sleep(0.5)

    # ──── Phase 2: Agents connect and HELLO ────
    phase("Phase 2: Agents Connect")

    alice = WSAgent(
        name="Alice",
        role_description="Security engineer — fixes auth bugs, token validation, timing attacks",
    )
    bob = WSAgent(
        name="Bob",
        role_description="Code quality engineer — eliminates duplication, refactors shared logic",
    )

    await asyncio.gather(
        alice.connect(COORDINATOR_URI, SESSION_ID),
        bob.connect(COORDINATOR_URI, SESSION_ID),
    )
    await asyncio.gather(alice.do_hello(), bob.do_hello())
    log.info("Both agents joined session")

    # ──── Phase 3: Read real files, decide intents ────
    phase("Phase 3: Agents Read Files & Decide Intents")

    # Build file listing for agents to see
    file_listing = ""
    for rel, content in sorted(original_contents.items()):
        file_listing += f"\n{'='*40}\nFILE: {rel}\n{'='*40}\n{content}\n"

    project_context = f"""
A Python web application with these source files:
{file_listing}

KNOWN BUGS:
1. auth.py: tokens not checked for expiry (CRITICAL SECURITY BUG)
2. auth.py: timing side-channel in authenticate() leaks username existence
3. auth_middleware.py: duplicates ALL logic from auth.py, now out of sync
4. crypto.py: has constant_time_compare() but it's unused — auth.py uses == instead
5. models.py: User model missing email uniqueness, timestamps, is_active
"""

    log.info("Both agents deciding on intents CONCURRENTLY...")
    t0 = time.time()

    alice_intent_future = asyncio.get_event_loop().run_in_executor(
        None, alice.decide_intent, project_context, []
    )
    bob_intent_future = asyncio.get_event_loop().run_in_executor(
        None, bob.decide_intent, project_context, []
    )

    alice_intent, bob_intent = await asyncio.gather(alice_intent_future, bob_intent_future)
    elapsed = time.time() - t0

    log.info(f"Decisions in {elapsed:.1f}s")
    log.info(f"Alice: {alice_intent.get('objective')}")
    log.info(f"  files: {alice_intent.get('files')}")
    log.info(f"Bob: {bob_intent.get('objective')}")
    log.info(f"  files: {bob_intent.get('files')}")

    alice_files = set(alice_intent.get("files", []))
    bob_files = set(bob_intent.get("files", []))
    overlap = alice_files & bob_files

    # ──── Phase 4: Announce intents, detect conflicts ────
    phase("Phase 4: INTENT_ANNOUNCE → Conflict Detection")

    await asyncio.gather(
        alice.do_announce_intent(alice_intent),
        bob.do_announce_intent(bob_intent),
    )
    await asyncio.gather(alice.drain_inbox(2.0), bob.drain_inbox(2.0))

    all_conflicts = alice.conflicts_received + bob.conflicts_received
    seen_ids = set()
    unique_conflicts = []
    for c in all_conflicts:
        cid = c.get("payload", {}).get("conflict_id", "")
        if cid not in seen_ids:
            seen_ids.add(cid)
            unique_conflicts.append(c)

    if unique_conflicts:
        log.info(f"CONFLICTS DETECTED: {len(unique_conflicts)}")
        for c in unique_conflicts:
            cp = c["payload"]
            log.info(f"  {cp['conflict_id'][:20]}: {cp.get('intent_a')} vs {cp.get('intent_b')}")
    else:
        log.info("No conflicts — agents chose non-overlapping files")

    # ──── Phase 5: Resolve conflicts ────
    if unique_conflicts:
        phase("Phase 5: Conflict Resolution")

        for c in unique_conflicts:
            cp = c["payload"]
            cid = cp["conflict_id"]

            # Agents express positions concurrently
            alice_pos_future = asyncio.get_event_loop().run_in_executor(
                None, alice.decide_on_conflict, cp, alice_intent, bob_intent
            )
            bob_pos_future = asyncio.get_event_loop().run_in_executor(
                None, bob.decide_on_conflict, cp, bob_intent, alice_intent
            )
            alice_pos, bob_pos = await asyncio.gather(alice_pos_future, bob_pos_future)

            log.info(f"Alice: {alice_pos.get('response')} — {alice_pos.get('reasoning', '')[:60]}")
            log.info(f"Bob: {bob_pos.get('response')} — {bob_pos.get('reasoning', '')[:60]}")

            # Coordinator auto-resolves
            rationale = (f"Alice: {alice_pos.get('response')} ({alice_pos.get('reasoning', '')[:40]}). "
                         f"Bob: {bob_pos.get('response')} ({bob_pos.get('reasoning', '')[:40]})")
            coordinator.coordinator.resolve_as_coordinator(cid, "approved", rationale)
            log.info(f"✓ Coordinator resolved {cid[:20]}")

    # ──── Phase 6: REAL CODE EXECUTION ────
    phase("Phase 6: Agents Execute REAL Code Changes")

    # Determine which agent works on which files
    # If there's overlap, both agents know about each other's work
    alice_work_desc = f"Objective: {alice_intent.get('objective')} | Files: {alice_intent.get('files')}"
    bob_work_desc = f"Objective: {bob_intent.get('objective')} | Files: {bob_intent.get('files')}"

    changes_made = {}  # filename -> {"agent": ..., "before_hash": ..., "after_hash": ...}
    rebase_log = []    # track rejections and retries

    def normalize_filename(fname: str) -> str | None:
        """Normalize intent filename to a real path under WORK_DIR."""
        if not fname.startswith("src/") and not fname.startswith("api/") and not fname.startswith("utils/"):
            for prefix in ["", "src/", "api/", "utils/"]:
                candidate = os.path.join(WORK_DIR, prefix + fname) if prefix else os.path.join(WORK_DIR, fname)
                if os.path.exists(candidate):
                    return (prefix + fname) if prefix else fname
        fpath = os.path.join(WORK_DIR, fname)
        if os.path.exists(fpath):
            return fname
        return None

    MAX_REBASE_ATTEMPTS = 2

    async def agent_execute(agent: WSAgent, intent: dict, role: str, other_work: str):
        """Have an agent actually modify files, with rebase on STALE_STATE_REF rejection."""
        agent_name = agent.name
        target_files = intent.get("files", [])
        objective = intent.get("objective", "fix bugs")

        for fname in target_files:
            normalized = normalize_filename(fname)
            if normalized is None:
                log.warning(f"  {agent_name}: File not found: {fname}")
                continue

            fpath = os.path.join(WORK_DIR, normalized)
            rel_path = os.path.relpath(fpath, WORK_DIR)

            attempt = 0
            while attempt <= MAX_REBASE_ATTEMPTS:
                before_content = read_file(fpath)
                before_hash = file_hash(fpath)

                attempt_label = f" (rebase attempt {attempt})" if attempt > 0 else ""
                log.info(f"  {agent_name}: Reading {rel_path} ({before_hash}){attempt_label}...")

                # Build OP_COMMIT with real state_ref
                op_id_suffix = f"-r{attempt}" if attempt > 0 else ""
                op_plan = {
                    "op_id": f"op-{agent_name.lower()}-{rel_path.replace('/', '-').replace('.', '-')}{op_id_suffix}",
                    "target": rel_path,
                    "op_kind": "replace",
                    "state_ref_before": f"sha256:{before_hash}",
                    "state_ref_after": "pending",
                }

                # Ask Claude to generate the fix
                rebase_note = ""
                if attempt > 0:
                    rebase_note = (
                        "\nIMPORTANT: Another agent has ALREADY modified this file. "
                        "The content below reflects their changes. "
                        "You must build ON TOP of their work — preserve their fixes and add yours."
                    )
                log.info(f"  {agent_name}: Asking Claude to fix {rel_path}...")
                fixed_content = await asyncio.get_event_loop().run_in_executor(
                    None, ask_claude_for_fix,
                    agent_name, role, rel_path, before_content,
                    objective + rebase_note, other_work
                )

                # Compute after_hash from the fixed content WITHOUT writing to disk yet
                after_hash = hashlib.sha256(fixed_content.encode()).hexdigest()[:16]
                op_plan["state_ref_after"] = f"sha256:{after_hash}"

                log.info(f"  {agent_name}: Generated fix for {rel_path} ({before_hash} → {after_hash})")

                # Send OP_COMMIT over WebSocket (optimistic — coordinator may reject)
                await agent.do_commit(intent, op_plan)

                # Check for rejection (PROTOCOL_ERROR with STALE_STATE_REF)
                await asyncio.sleep(0.5)
                rejected = False
                try:
                    while not agent.inbox.empty():
                        msg = agent.inbox.get_nowait()
                        msg_type = msg.get("message_type", "")
                        if msg_type == "PROTOCOL_ERROR":
                            error_code = msg.get("payload", {}).get("error_code", "")
                            if error_code == "STALE_STATE_REF":
                                rejected = True
                                rebase_log.append({
                                    "agent": agent_name,
                                    "file": rel_path,
                                    "attempt": attempt,
                                    "stale_ref": before_hash,
                                    "error": msg["payload"].get("message", ""),
                                })
                                log.warning(
                                    f"  {agent_name}: ⚠ STALE_STATE_REF on {rel_path}! "
                                    f"Rebasing (attempt {attempt + 1}/{MAX_REBASE_ATTEMPTS})..."
                                )
                            else:
                                log.error(f"  {agent_name}: PROTOCOL_ERROR: {error_code}")
                        elif msg_type == "CONFLICT_REPORT":
                            agent.conflicts_received.append(msg)
                except asyncio.QueueEmpty:
                    pass

                if not rejected:
                    # Commit accepted — NOW write to disk
                    write_file(fpath, fixed_content)
                    log.info(f"  {agent_name}: Wrote {rel_path} to disk (commit accepted)")
                    changes_made[rel_path] = {
                        "agent": agent_name,
                        "before_hash": before_hash,
                        "after_hash": after_hash,
                        "before_content": original_contents.get(rel_path, before_content),
                        "after_content": fixed_content,
                        "rebase_attempts": attempt,
                    }
                    if attempt > 0:
                        log.info(f"  {agent_name}: ✓ Rebase successful for {rel_path} on attempt {attempt}")
                    break

                attempt += 1
                if attempt > MAX_REBASE_ATTEMPTS:
                    log.error(f"  {agent_name}: ✗ Failed to commit {rel_path} after {MAX_REBASE_ATTEMPTS} rebase attempts")

    # Execute concurrently — state_ref check will catch conflicts
    await asyncio.gather(
        agent_execute(alice, alice_intent, alice.role_description, bob_work_desc),
        agent_execute(bob, bob_intent, bob.role_description, alice_work_desc),
    )

    # ──── Phase 7: Verify results ────
    phase("Phase 7: Verification — Diffs & State")

    log.info(f"Files modified: {len(changes_made)}")

    for rel_path, info in sorted(changes_made.items()):
        log.info(f"\n  {rel_path} (by {info['agent']}):")
        diff_text = show_diff(info["before_content"], info["after_content"], rel_path)
        if not diff_text:
            log.info(f"    (no changes — Claude returned identical content)")

    # Verify coordinator state
    snap = coordinator.coordinator.snapshot()
    log.info(f"\n  Coordinator state:")
    log.info(f"    intents: {len(snap['intents'])}")
    for i in snap["intents"]:
        log.info(f"      {i['intent_id']}: {i['state']}")
    log.info(f"    operations: {len(snap['operations'])}")
    for o in snap["operations"]:
        log.info(f"      {o['op_id']}: {o['state']} (target={o.get('target', '?')})")
    log.info(f"    conflicts: {len(snap['conflicts'])}")
    for c in snap["conflicts"]:
        log.info(f"      {c['conflict_id'][:20]}...: {c['state']}")

    # Check all state_ref_after are real hashes
    ops_with_real_refs = sum(
        1 for o in snap["operations"]
        if o.get("state_ref_after", "").startswith("sha256:")
    )
    log.info(f"\n    Operations with real file hashes: {ops_with_real_refs}/{len(snap['operations'])}")

    # Show optimistic concurrency control results
    if rebase_log:
        log.info(f"\n  Optimistic Concurrency Control (state_ref check):")
        log.info(f"    Stale commits rejected: {len(rebase_log)}")
        for entry in rebase_log:
            log.info(f"      {entry['agent']}: {entry['file']} attempt {entry['attempt']} "
                     f"(stale ref: {entry['stale_ref'][:12]}...)")
        rebased = [f for f, info in changes_made.items() if info.get("rebase_attempts", 0) > 0]
        log.info(f"    Files successfully rebased: {len(rebased)}")
        for f in rebased:
            log.info(f"      {f} (by {changes_made[f]['agent']}, {changes_made[f]['rebase_attempts']} rebase(s))")
    else:
        log.info(f"\n  Optimistic Concurrency: no stale commits (agents chose non-overlapping files)")

    # ──── Phase 8: Cleanup ────
    phase("Phase 8: Disconnect")

    await asyncio.gather(alice.do_goodbye("completed"), bob.do_goodbye("completed"))
    await asyncio.sleep(0.5)
    await asyncio.gather(alice.close(), bob.close())

    heartbeat_task.cancel()
    ws_server.close()
    await ws_server.wait_closed()

    # Save transcript
    transcript_path = os.path.join(SCRIPT_DIR, "e2e_transcript.json")
    coordinator.save_transcript(transcript_path)

    phase("FINAL RESULTS")
    log.info(f"Messages exchanged: {len(coordinator.transcript)}")
    log.info(f"Conflicts detected & resolved: {len(unique_conflicts)}")
    log.info(f"Stale commits rejected (rebase): {len(rebase_log)}")
    log.info(f"Files actually modified: {len(changes_made)}")
    for rel, info in sorted(changes_made.items()):
        rebase_str = f" [rebased x{info['rebase_attempts']}]" if info.get("rebase_attempts", 0) > 0 else ""
        log.info(f"  {rel}: {info['before_hash']} → {info['after_hash']} (by {info['agent']}){rebase_str}")
    log.info(f"Transcript: {transcript_path}")
    log.info(f"Working dir: {WORK_DIR}")

    return {
        "messages": len(coordinator.transcript),
        "conflicts": len(unique_conflicts),
        "stale_rejections": len(rebase_log),
        "files_modified": len(changes_made),
        "changes": {k: {"agent": v["agent"], "before": v["before_hash"], "after": v["after_hash"],
                         "rebases": v.get("rebase_attempts", 0)}
                    for k, v in changes_made.items()},
    }


if __name__ == "__main__":
    result = asyncio.run(run_e2e())
    print(f"\n{'='*70}")
    print(f"  E2E RESULT: {result['messages']} msgs, {result['conflicts']} conflicts, "
          f"{result['stale_rejections']} stale rejections, "
          f"{result['files_modified']} files modified")
    print(f"{'='*70}")
