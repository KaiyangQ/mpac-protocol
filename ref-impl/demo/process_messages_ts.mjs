#!/usr/bin/env node
/**
 * Read Python-generated MPAC messages and process through TypeScript coordinator.
 * Outputs results as JSON for comparison.
 */
import { readFileSync, writeFileSync, readdirSync, mkdirSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const INTEROP_DIR = join(__dirname, "interop_messages");
const DIST_DIR = join(__dirname, "..", "typescript", "dist");

const SESSION_ID = "interop-test-session-001";

async function main() {
  // Import TS implementation (compiled)
  const { SessionCoordinator } = await import(join(DIST_DIR, "coordinator.js"));
  const { Participant } = await import(join(DIST_DIR, "participant.js"));
  const { envelopeFromJSON, envelopeToJSON } = await import(join(DIST_DIR, "envelope.js"));
  console.log("=== TypeScript Interop Test ===\n");

  // ---- PART 1: Process Python-generated messages through TS coordinator ----
  console.log("Part 1: Processing Python messages through TS coordinator...\n");

  const pyFiles = readdirSync(INTEROP_DIR)
    .filter(f => f.startsWith("py_") && f.endsWith(".json") && !f.includes("results"))
    .sort();

  const coordinator = new SessionCoordinator(SESSION_ID);
  const results = {};
  const issues = [];

  for (const file of pyFiles) {
    const name = file.replace("py_", "").replace(".json", "");
    const raw = readFileSync(join(INTEROP_DIR, file), "utf-8");
    const envelope = JSON.parse(raw);

    console.log(`  Processing ${file}:`);
    console.log(`    message_type: ${envelope.message_type}`);
    console.log(`    sender: ${envelope.sender?.principal_id}`);

    // Validate envelope structure
    const envelopeIssues = validateEnvelope(envelope);
    if (envelopeIssues.length > 0) {
      console.log(`    ⚠ Envelope issues: ${envelopeIssues.join(", ")}`);
      issues.push({ file, issues: envelopeIssues });
    }

    // Try to process through coordinator
    try {
      const responses = coordinator.processMessage(envelope);
      console.log(`    ✓ Processed OK, ${responses.length} response(s)`);
      results[name] = {
        success: true,
        response_count: responses.length,
        responses: responses,
      };
    } catch (err) {
      console.log(`    ✗ Error: ${err.message}`);
      results[name] = {
        success: false,
        error: err.message,
      };
      issues.push({ file, error: err.message });
    }
  }

  // ---- PART 2: Generate TS messages for Python to consume ----
  console.log("\nPart 2: Generating TS messages...\n");

  const models = await import(join(DIST_DIR, "models.js"));
  const Role = models.Role;
  const ScopeKind = models.ScopeKind;

  const alice = new Participant("agent:alice-ts", "agent", "Alice TS", [Role.CONTRIBUTOR], ["intent.broadcast", "op.commit"]);
  const bob = new Participant("agent:bob-ts", "agent", "Bob TS", [Role.CONTRIBUTOR, Role.REVIEWER], ["intent.broadcast", "op.commit"]);

  const tsMessages = {
    hello_alice: alice.hello(SESSION_ID),
    hello_bob: bob.hello(SESSION_ID),
    intent_announce_alice: alice.announceIntent(SESSION_ID, "intent-alice-ts-001", "Refactor auth module", { kind: ScopeKind.FILE_SET, resources: ["src/auth.py", "src/auth_utils.py"] }),
    intent_announce_bob_no_overlap: bob.announceIntent(SESSION_ID, "intent-bob-ts-001", "Update database schema", { kind: ScopeKind.FILE_SET, resources: ["src/db.py", "src/migrations.py"] }),
    intent_announce_bob_overlap: bob.announceIntent(SESSION_ID, "intent-bob-ts-002", "Fix auth bug", { kind: ScopeKind.FILE_SET, resources: ["src/auth.py", "src/auth_test.py"] }),
    op_propose_alice: alice.proposeOp(SESSION_ID, "op-alice-ts-001", "intent-alice-ts-001", "src/auth.py", "replace"),
    op_commit_alice: alice.commitOp(SESSION_ID, "op-alice-ts-001", "intent-alice-ts-001", "src/auth.py", "replace", "sha256:abc123", "sha256:def456"),
  };

  for (const [name, msg] of Object.entries(tsMessages)) {
    const path = join(INTEROP_DIR, `ts_${name}.json`);
    writeFileSync(path, JSON.stringify(msg, null, 2));
    console.log(`  wrote ${path}`);
  }

  // ---- PART 3: Summary ----
  console.log("\n=== Interop Summary ===");
  console.log(`Python messages processed: ${pyFiles.length}`);
  console.log(`Issues found: ${issues.length}`);

  if (issues.length > 0) {
    console.log("\nIssues detail:");
    for (const issue of issues) {
      console.log(`  ${issue.file}: ${issue.issues?.join(", ") || issue.error}`);
    }
  }

  // Write full results
  const outputPath = join(INTEROP_DIR, "ts_processing_results.json");
  writeFileSync(outputPath, JSON.stringify({ results, issues, ts_messages_generated: Object.keys(tsMessages).length }, null, 2));
  console.log(`\nFull results: ${outputPath}`);
}

function validateEnvelope(envelope) {
  const issues = [];
  if (envelope.protocol !== "MPAC") issues.push(`protocol=${envelope.protocol}, expected MPAC`);
  if (!envelope.version) issues.push("missing version");
  if (!envelope.message_type) issues.push("missing message_type");
  if (!envelope.message_id) issues.push("missing message_id");
  if (!envelope.session_id) issues.push("missing session_id");
  if (!envelope.sender) issues.push("missing sender");
  else {
    if (!envelope.sender.principal_id) issues.push("missing sender.principal_id");
    if (!envelope.sender.principal_type) issues.push("missing sender.principal_type");
  }
  if (!envelope.ts) issues.push("missing ts");
  if (envelope.payload === undefined) issues.push("missing payload");

  // Validate watermark if present
  if (envelope.watermark) {
    if (!envelope.watermark.kind) issues.push("watermark missing kind");
    if (envelope.watermark.value === undefined) issues.push("watermark missing value");
  }

  return issues;
}

main().catch(err => {
  console.error("Fatal:", err);
  process.exit(1);
});
