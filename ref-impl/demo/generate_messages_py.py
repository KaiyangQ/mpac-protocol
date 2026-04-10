#!/usr/bin/env python3
"""Generate MPAC messages from Python participant → JSON files for cross-language testing."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from mpac.models import Scope, Sender, Watermark
from mpac.participant import Participant
from mpac.coordinator import SessionCoordinator

SESSION_ID = "interop-test-session-001"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "interop_messages")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Create participants
    alice = Participant("agent:alice", "agent", "Alice Coder", ["contributor"], ["intent.broadcast", "op.commit"])
    bob = Participant("agent:bob", "agent", "Bob Reviewer", ["contributor", "reviewer"], ["intent.broadcast", "op.commit"])

    # 1. HELLO messages
    hello_alice = alice.hello(SESSION_ID)
    hello_bob = bob.hello(SESSION_ID)

    # 2. INTENT_ANNOUNCE — non-overlapping
    intent_a = alice.announce_intent(
        SESSION_ID, "intent-alice-001", "Refactor auth module",
        Scope(kind="file_set", resources=["src/auth.py", "src/auth_utils.py"])
    )
    intent_b = bob.announce_intent(
        SESSION_ID, "intent-bob-001", "Update database schema",
        Scope(kind="file_set", resources=["src/db.py", "src/migrations.py"])
    )

    # 3. INTENT_ANNOUNCE — overlapping (conflict scenario)
    intent_c = bob.announce_intent(
        SESSION_ID, "intent-bob-002", "Fix auth bug",
        Scope(kind="file_set", resources=["src/auth.py", "src/auth_test.py"])
    )

    # 4. OP_PROPOSE + OP_COMMIT
    op_propose = alice.propose_op(SESSION_ID, "op-alice-001", "intent-alice-001", "src/auth.py", "replace")
    op_commit = alice.commit_op(
        SESSION_ID, "op-alice-001", "intent-alice-001", "src/auth.py", "replace",
        state_ref_before="sha256:abc123", state_ref_after="sha256:def456"
    )

    # Write all messages
    messages = {
        "hello_alice": hello_alice,
        "hello_bob": hello_bob,
        "intent_announce_alice": intent_a,
        "intent_announce_bob_no_overlap": intent_b,
        "intent_announce_bob_overlap": intent_c,
        "op_propose_alice": op_propose,
        "op_commit_alice": op_commit,
    }

    for name, msg in messages.items():
        path = os.path.join(OUTPUT_DIR, f"py_{name}.json")
        with open(path, "w") as f:
            json.dump(msg, f, indent=2)
        print(f"  wrote {path}")

    # Also run through Python coordinator to produce expected results
    coord = SessionCoordinator(SESSION_ID)
    results = {}
    for name, msg in messages.items():
        responses = coord.process_message(msg)
        results[name] = {
            "input": msg,
            "responses": responses,
            "response_count": len(responses),
        }

    path = os.path.join(OUTPUT_DIR, "py_coordinator_results.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  wrote {path}")

    print(f"\nGenerated {len(messages)} messages + coordinator results")
    return 0

if __name__ == "__main__":
    sys.exit(main())
