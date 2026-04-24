# MPAC v0.1.4 Protocol Gap Analysis

**Date**: 2026-04-03
**Scope**: Protocol-level design gaps identified after completing ~85% reference implementation coverage
**Context**: With 16/17 message types implemented, full state machine lifecycle, liveness detection, arbiter workflow, and intent claim all working in Python + TypeScript, these gaps represent structural limitations in the protocol specification itself — not implementation backlogs.

---

## Gap 1: Single Coordinator — No Fault Tolerance or Handover

**Severity**: High
**Affected Sections**: 8.1 (Session Coordinator), 8.1.1 (Coordinator Fault Recovery)

### Problem

The protocol assumes a single Session Coordinator. Section 8.1.1 (added in v0.1.4) defines SHOULD-level state persistence and restart behavior, but does not address:

1. **How participants detect coordinator failure.** There is no COORDINATOR_HEARTBEAT or health-check mechanism. Participants only notice coordinator unavailability when their messages go unanswered — but there is no defined timeout or error code for this case.
2. **Coordinator handover.** If a new coordinator takes over, the protocol does not specify how session state (intents, operations, conflicts, participant registry, Lamport clock) is transferred. There is no leader election, no state snapshot format, no handover message type.
3. **Split-brain.** If two coordinators briefly coexist (e.g., during network partition), participants may receive conflicting SESSION_INFO, CONFLICT_REPORT, or RESOLUTION messages. The protocol has no mechanism to detect or resolve this.

### Recommendation

- Define a COORDINATOR_STATUS or COORDINATOR_HANDOVER message type
- Specify a minimum state snapshot format (JSON) that enables coordinator restart or migration
- Define participant behavior during coordinator unavailability: buffer messages? reconnect? timeout and leave session?
- Consider whether coordinator election is in-scope or should be delegated to infrastructure (e.g., Raft, etcd)

---

## Gap 2: Security Model Lacks Operational Trust Establishment

**Severity**: High
**Affected Sections**: 23 (Security Profiles), 14.1 (HELLO)

### Problem

The three security profiles (Open / Authenticated / Strict) define what guarantees exist but not how they are established:

1. **Identity verification.** HELLO carries `principal_id`, but the protocol does not specify who validates this identity. In the Open profile this is acceptable; in Authenticated/Strict profiles, there is no credential exchange, certificate presentation, or capability token mechanism.
2. **Trust bootstrapping in cross-organization scenarios.** MPAC's core value proposition is coordination across trust boundaries. But two agents from different organizations have no protocol-level mechanism to establish mutual trust. The spec says Authenticated profile requires signed messages — but signed with what key? How does the verifier obtain the signer's public key?
3. **Lamport clock integrity.** Lamport clocks provide causal ordering but no tamper resistance. A malicious participant can forge clock values to appear "later" in the causal chain, potentially overriding legitimate operations. The protocol has no mechanism to detect or prevent this.
4. **Role assertion validation.** Section 23.1.2 mentions role assertion validation but does not define who assigns roles or how role claims are verified.

### Recommendation

- Define a credential exchange extension for the HELLO/SESSION_INFO handshake (e.g., JWT bearer token, mTLS certificate fingerprint, or capability URI)
- Specify a key distribution mechanism or at least define the interface (e.g., "the coordinator MUST verify principal identity via an implementation-defined `IdentityProvider` interface")
- Consider adding HMAC or signature fields to the watermark to prevent clock forgery
- Define role assignment: is it coordinator-granted, self-declared, or externally provisioned?

---

## Gap 3: Scope Expressiveness — Semantic Conflicts Are Invisible

**Severity**: Medium
**Affected Sections**: 15.2 (Scope), 15.2.1 (Overlap Determination)

### Problem

Scope currently supports three kinds: `file_set`, `entity_set`, `task_set`. Overlap detection is based on exact match or path prefix. This misses an important class of real-world conflicts:

1. **Semantic dependencies.** Agent A modifies a database schema; Agent B writes queries against that schema. They touch different files but the changes are logically coupled. The protocol cannot detect this.
2. **Interface-level conflicts.** Agent A changes a function signature in `auth.py`; Agent B calls that function from `routes.py`. File-level scopes don't overlap, but the changes are incompatible.
3. **No "impact declaration."** Agents cannot express "my change may affect X" beyond listing files. There is no mechanism for declaring downstream dependencies or transitive impact.

### Recommendation

- Add a `dependency_set` or `impact_declaration` field to Scope, allowing agents to declare resources they *read from* or *depend on* (not just write to)
- Define a `semantic` scope kind with free-form tags (e.g., `["auth-api", "user-model"]`) and overlap when tags intersect
- Consider a two-tier scope: `write_scope` (what I modify) + `read_scope` (what I depend on); conflict when one agent's write_scope overlaps another's read_scope

---

## Gap 4: No Post-Commit Rollback or Undo Semantics

**Severity**: Medium
**Affected Sections**: 16 (Operation Layer), 18.4 (Resolution: Rejecting Committed Operations)

### Problem

Once an operation reaches COMMITTED, the protocol has no structured way to undo it:

1. **OP_SUPERSEDE replaces but doesn't revert.** It creates a new operation that overrides the previous one, but there is no semantic link saying "this undoes that." The distinction between "supersede with new work" and "rollback to previous state" is lost.
2. **Post-commit conflict.** If Agent A commits, and Agent B subsequently discovers A's commit broke something, B can file CONFLICT_REPORT — but the resolution can only "reject" A's committed operation with a SHOULD-level rollback expectation. There is no OP_ROLLBACK message, no way to request revert, and no mechanism to track whether rollback actually happened.
3. **Cascading commit conflicts.** If operations O1 and O2 both commit, and they turn out to be incompatible, the resolution must pick one to keep and one to rollback. But the protocol doesn't model this as a distinct scenario from pre-commit conflict.

### Recommendation

- Consider an OP_ROLLBACK message type (or extend OP_SUPERSEDE with a `rollback: true` flag and `reverts_op_id` reference)
- Upgrade Section 18.4's rollback expectation from SHOULD to MUST for Governance Profile
- Define a `post_commit_conflict` subtype in CONFLICT_REPORT to distinguish from pre-commit scope overlap
- Add rollback confirmation tracking: after resolution orders rollback, the affected agent MUST send OP_COMMIT with `reverts: <original_op_id>` to confirm

---

## Gap 5: Session Lifecycle — No Close, No Archival

**Severity**: Medium
**Affected Sections**: 8 (Session Layer), 14 (Message Definitions)

### Problem

Sessions have a beginning (HELLO → SESSION_INFO) but no defined end:

1. **No SESSION_CLOSE message.** There is no way for the coordinator to formally end a session, or for participants to know a session is over.
2. **Unbounded state accumulation.** Long-running sessions accumulate intents, operations, conflicts, and Lamport clock values indefinitely. There is no garbage collection, archival, or compaction mechanism.
3. **Ambiguous session completion.** When all intents are resolved and all operations committed, is the session done? The protocol doesn't say. Participants may keep sending heartbeats to an effectively dead session.
4. **No audit export.** For compliance scenarios, there is no defined format for exporting a complete session transcript (all messages in causal order) for auditing.

### Recommendation

- Add SESSION_CLOSE message type (coordinator → all participants): includes session summary, final Lamport clock value, and disposition of any remaining active intents/operations
- Define session completion conditions: all intents terminal + all operations terminal + all conflicts closed → session MAY auto-close
- Define a session transcript format (ordered array of MessageEnvelopes) for audit export
- Consider a session TTL at the session level (separate from intent TTL)

---

## Gap 6: No Cross-Session Coordination

**Severity**: Low (but high for enterprise adoption)
**Affected Sections**: None (not currently addressed in spec)

### Problem

The protocol is entirely session-scoped. If the same agent participates in multiple concurrent sessions, there is no mechanism to detect or handle cross-session conflicts:

1. **Scope collision.** Agent A locks `auth.py` in Session 1. In Session 2 (different coordinator, different participants), Agent B also targets `auth.py`. Neither coordinator knows about the other session's scope.
2. **Resource contention.** In enterprise environments, multiple teams may run independent MPAC sessions on overlapping codebases. Without cross-session awareness, the protocol provides coordination within silos but not across them.
3. **Agent overcommitment.** An agent participating in 5 sessions may commit to conflicting work across sessions without any mechanism to detect this.

### Recommendation

- Define an optional Session Registry service that tracks active sessions and their aggregate scopes
- Add a `session_scope` field to SESSION_INFO that declares the session's overall resource domain
- Consider a CROSS_SESSION_CONFLICT message type for the registry to alert coordinators of inter-session overlap
- Alternatively, define this as out-of-scope and recommend infrastructure-level solutions (e.g., distributed lock manager)

---

## Priority Assessment

| Gap | Severity | Impact on Adoption | Recommended Version |
|-----|----------|-------------------|---------------------|
| 1. Coordinator Fault Tolerance | High | Blocks production deployment | v0.1.5 |
| 2. Security Trust Establishment | High | Blocks cross-org use cases | v0.1.5 |
| 5. Session Lifecycle | Medium | Creates operational ambiguity | v0.1.5 |
| 3. Scope Expressiveness | Medium | Limits conflict detection quality | v0.2.0 |
| 4. Post-Commit Rollback | Medium | Limits governance completeness | v0.2.0 |
| 6. Cross-Session Coordination | Low | Limits enterprise scalability | v0.2.0+ |

---

## Relationship to Implementation Gaps

These protocol-level gaps are distinct from the remaining *implementation* gaps in the reference code:

| Implementation Gap | Status | Related Protocol Gap |
|-------------------|--------|---------------------|
| OP_SUPERSEDE handler | Not yet implemented | Gap 4 (supersede vs. rollback distinction) |
| Signature verification | Not yet implemented | Gap 2 (no trust establishment to verify against) |
| Frozen scope enforcement | Not yet implemented | None (protocol is well-defined here) |
| Coordinator failover | Cannot implement | Gap 1 (protocol undefined) |
| Session close | Cannot implement | Gap 5 (no SESSION_CLOSE message) |
| Cross-session conflict | Cannot implement | Gap 6 (no cross-session mechanism) |

The implementation can proceed on OP_SUPERSEDE and frozen scope enforcement independently. The remaining items are blocked on protocol-level decisions.
