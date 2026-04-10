#!/usr/bin/env python3
"""Read TypeScript-generated MPAC messages and process through Python coordinator."""
import sys, os, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from mpac.coordinator import SessionCoordinator
from mpac.envelope import MessageEnvelope

SESSION_ID = "interop-test-session-001"
INTEROP_DIR = os.path.join(os.path.dirname(__file__), "interop_messages")


def validate_envelope(envelope: dict) -> list:
    """Validate envelope against MPAC v0.1.4 spec."""
    issues = []
    required = ["protocol", "version", "message_type", "message_id", "session_id", "sender", "ts", "payload"]
    for field in required:
        if field not in envelope or envelope[field] is None:
            issues.append(f"missing {field}")

    if envelope.get("protocol") != "MPAC":
        issues.append(f"protocol={envelope.get('protocol')}, expected MPAC")

    sender = envelope.get("sender", {})
    if not sender.get("principal_id"):
        issues.append("missing sender.principal_id")
    if not sender.get("principal_type"):
        issues.append("missing sender.principal_type")

    # Validate watermark format if present
    wm = envelope.get("watermark")
    if wm:
        if "kind" not in wm:
            issues.append("watermark missing 'kind' (spec requires kind/value format)")
        if "value" not in wm:
            issues.append("watermark missing 'value'")
        # Legacy format detection
        if "clock" in wm or "session_id" in wm or "sender_id" in wm:
            issues.append("watermark uses legacy format (clock/session_id/sender_id), spec requires kind/value")

    # Validate OP_PROPOSE/OP_COMMIT field names
    msg_type = envelope.get("message_type")
    payload = envelope.get("payload", {})
    if msg_type in ("OP_PROPOSE", "OP_COMMIT"):
        if "operation_id" in payload and "op_id" not in payload:
            issues.append(f"payload uses 'operation_id', spec requires 'op_id'")
        if "operation_kind" in payload and "op_kind" not in payload:
            issues.append(f"payload uses 'operation_kind', spec requires 'op_kind'")

    # Validate INTENT_ANNOUNCE scope field names
    if msg_type == "INTENT_ANNOUNCE":
        scope = payload.get("scope", {})
        kind = scope.get("kind")
        if kind == "file_set" and "file_set" in scope and "resources" not in scope:
            issues.append("scope uses 'file_set' array, spec requires 'resources'")
        if kind == "entity_set" and "entity_set" in scope and "entities" not in scope:
            issues.append("scope uses 'entity_set' array, spec requires 'entities'")
        if kind == "task_set" and "task_set" in scope and "task_ids" not in scope:
            issues.append("scope uses 'task_set' array, spec requires 'task_ids'")

    return issues


def main():
    print("=== Python Consuming TS Messages ===\n")

    ts_files = sorted(glob.glob(os.path.join(INTEROP_DIR, "ts_*.json")))
    if not ts_files:
        print("No TS messages found. Run process_messages_ts.mjs first.")
        return 1

    # Filter out results files
    ts_files = [f for f in ts_files if "results" not in f]

    coordinator = SessionCoordinator(SESSION_ID)
    all_issues = []
    results = {}

    for filepath in ts_files:
        name = os.path.basename(filepath).replace("ts_", "").replace(".json", "")
        with open(filepath) as f:
            envelope = json.load(f)

        print(f"  Processing {os.path.basename(filepath)}:")
        print(f"    message_type: {envelope.get('message_type')}")
        print(f"    sender: {envelope.get('sender', {}).get('principal_id')}")

        # Validate wire format
        issues = validate_envelope(envelope)
        if issues:
            print(f"    ⚠ Wire format issues: {'; '.join(issues)}")
            all_issues.append({"file": os.path.basename(filepath), "issues": issues})

        # Try to process
        try:
            responses = coordinator.process_message(envelope)
            print(f"    ✓ Processed OK, {len(responses)} response(s)")
            results[name] = {"success": True, "response_count": len(responses)}
        except Exception as e:
            print(f"    ✗ Error: {e}")
            results[name] = {"success": False, "error": str(e)}
            all_issues.append({"file": os.path.basename(filepath), "error": str(e)})

    # Compare: also validate Python's own messages
    print("\n=== Validating Python Messages ===\n")
    py_files = sorted(glob.glob(os.path.join(INTEROP_DIR, "py_*.json")))
    py_files = [f for f in py_files if "results" not in f]
    py_issues = []
    for filepath in py_files:
        with open(filepath) as f:
            envelope = json.load(f)
        issues = validate_envelope(envelope)
        if issues:
            print(f"  ⚠ {os.path.basename(filepath)}: {'; '.join(issues)}")
            py_issues.append({"file": os.path.basename(filepath), "issues": issues})
        else:
            print(f"  ✓ {os.path.basename(filepath)}: OK")

    # Summary
    print("\n" + "=" * 60)
    print("INTEROP SUMMARY")
    print("=" * 60)
    print(f"TS → Python: {len(ts_files)} messages, {sum(1 for r in results.values() if r.get('success'))} succeeded, {len(all_issues)} with issues")
    print(f"Python self-check: {len(py_files)} messages, {len(py_issues)} with issues")

    if all_issues:
        print("\nTS → Python issues:")
        for item in all_issues:
            detail = "; ".join(item.get("issues", [])) or item.get("error", "")
            print(f"  {item['file']}: {detail}")

    if py_issues:
        print("\nPython self-check issues:")
        for item in py_issues:
            print(f"  {item['file']}: {'; '.join(item['issues'])}")

    # Write results
    output = {
        "ts_to_python_results": results,
        "ts_to_python_issues": all_issues,
        "python_self_check_issues": py_issues,
    }
    outpath = os.path.join(INTEROP_DIR, "py_consuming_results.json")
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull results: {outpath}")

    return 1 if (all_issues or py_issues) else 0


if __name__ == "__main__":
    sys.exit(main())
