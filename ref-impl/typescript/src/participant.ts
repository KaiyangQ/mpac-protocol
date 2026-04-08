import { v4 as uuidv4 } from "uuid";
import { createEnvelope, MessageEnvelope } from "./envelope.js";
import { LamportClock } from "./watermark.js";
import { MessageType, Role, Scope, Sender } from "./models.js";

export class Participant {
  private principalId: string;
  private principalType: string;
  private displayName: string;
  private roles: Array<Role | string>;
  private capabilities: string[];
  private lamportClock: LamportClock;
  private credential?: { type: string; value: string; issuer?: string; expires_at?: string };
  private senderInstanceId: string;

  constructor(
    principalId: string,
    principalType: string,
    displayName: string,
    roles: Array<Role | string> = ["participant"],
    capabilities: string[] = [],
    credential?: { type: string; value: string; issuer?: string; expires_at?: string },
  ) {
    this.principalId = principalId;
    this.principalType = principalType;
    this.displayName = displayName;
    this.roles = roles;
    this.capabilities = capabilities;
    this.lamportClock = new LamportClock();
    this.credential = credential;
    this.senderInstanceId = `${this.principalId}:${uuidv4()}`;
  }

  private sender(): Sender {
    return {
      principal_id: this.principalId,
      principal_type: this.principalType,
      sender_instance_id: this.senderInstanceId,
    };
  }

  private make(messageType: MessageType, sessionId: string, payload: Record<string, unknown>): MessageEnvelope {
    return createEnvelope(messageType, sessionId, this.sender(), payload, this.lamportClock.createWatermark());
  }

  hello(sessionId: string, backend?: { model_id: string; provider: string }): MessageEnvelope {
    const payload: Record<string, unknown> = {
      display_name: this.displayName,
      roles: this.roles,
      capabilities: this.capabilities,
    };
    if (this.credential) payload.credential = this.credential;
    if (backend) payload.backend = backend;
    return this.make(MessageType.HELLO, sessionId, payload);
  }

  heartbeat(sessionId: string, status = "idle", activeIntentId?: string, summary?: string, backendHealth?: Record<string, unknown>): MessageEnvelope {
    const payload: Record<string, unknown> = { status };
    if (activeIntentId) payload.active_intent_id = activeIntentId;
    if (summary) payload.summary = summary;
    if (backendHealth) payload.backend_health = backendHealth;
    return this.make(MessageType.HEARTBEAT, sessionId, payload);
  }

  goodbye(sessionId: string, reason = "user_exit", activeIntents?: string[], intentDisposition = "withdraw"): MessageEnvelope {
    const payload: Record<string, unknown> = { reason, intent_disposition: intentDisposition };
    if (activeIntents) payload.active_intents = activeIntents;
    return this.make(MessageType.GOODBYE, sessionId, payload);
  }

  announceIntent(sessionId: string, intentId: string, objective: string, scope: Scope, ttlSec?: number): MessageEnvelope {
    const payload: Record<string, unknown> = { intent_id: intentId, objective, scope };
    if (ttlSec !== undefined) payload.ttl_sec = ttlSec;
    return this.make(MessageType.INTENT_ANNOUNCE, sessionId, payload);
  }

  updateIntent(sessionId: string, intentId: string, opts: { objective?: string; scope?: Scope; ttl_sec?: number } = {}): MessageEnvelope {
    const payload: Record<string, unknown> = { intent_id: intentId };
    if (opts.objective !== undefined) payload.objective = opts.objective;
    if (opts.scope !== undefined) payload.scope = opts.scope;
    if (opts.ttl_sec !== undefined) payload.ttl_sec = opts.ttl_sec;
    return this.make(MessageType.INTENT_UPDATE, sessionId, payload);
  }

  withdrawIntent(sessionId: string, intentId: string, reason?: string): MessageEnvelope {
    const payload: Record<string, unknown> = { intent_id: intentId };
    if (reason) payload.reason = reason;
    return this.make(MessageType.INTENT_WITHDRAW, sessionId, payload);
  }

  claimIntent(
    sessionId: string,
    claimId: string,
    originalIntentId: string,
    originalPrincipalId: string,
    newIntentId: string,
    objective: string,
    scope: Scope,
    justification?: string,
  ): MessageEnvelope {
    const payload: Record<string, unknown> = {
      claim_id: claimId,
      original_intent_id: originalIntentId,
      original_principal_id: originalPrincipalId,
      new_intent_id: newIntentId,
      objective,
      scope,
    };
    if (justification) payload.justification = justification;
    return this.make(MessageType.INTENT_CLAIM, sessionId, payload);
  }

  proposeOp(sessionId: string, opId: string, intentId: string, target: string, opKind: string): MessageEnvelope {
    return this.make(MessageType.OP_PROPOSE, sessionId, {
      op_id: opId,
      intent_id: intentId,
      target,
      op_kind: opKind,
    });
  }

  commitOp(
    sessionId: string,
    opId: string,
    intentId: string,
    target: string,
    opKind: string,
    stateRefBefore?: string,
    stateRefAfter?: string,
  ): MessageEnvelope {
    return this.make(MessageType.OP_COMMIT, sessionId, {
      op_id: opId,
      intent_id: intentId,
      target,
      op_kind: opKind,
      state_ref_before: stateRefBefore,
      state_ref_after: stateRefAfter,
    });
  }

  batchCommitOp(
    sessionId: string,
    batchId: string,
    operations: Array<Record<string, unknown>>,
    atomicity: "all_or_nothing" | "best_effort" = "all_or_nothing",
    intentId?: string,
    summary?: string,
  ): MessageEnvelope {
    const payload: Record<string, unknown> = {
      batch_id: batchId,
      atomicity,
      operations,
    };
    if (intentId) payload.intent_id = intentId;
    if (summary) payload.summary = summary;
    return this.make(MessageType.OP_BATCH_COMMIT, sessionId, payload);
  }

  supersedeOp(
    sessionId: string,
    opId: string,
    supersedesOpId: string,
    target: string,
    intentId?: string,
    reason?: string,
    stateRefAfter?: string,
  ): MessageEnvelope {
    const payload: Record<string, unknown> = {
      op_id: opId,
      supersedes_op_id: supersedesOpId,
      target,
    };
    if (intentId) payload.intent_id = intentId;
    if (reason) payload.reason = reason;
    if (stateRefAfter) payload.state_ref_after = stateRefAfter;
    return this.make(MessageType.OP_SUPERSEDE, sessionId, payload);
  }

  reportConflict(
    sessionId: string,
    conflictId: string,
    category: string,
    severity: string,
    involvedPrincipals: string[],
    scopeA: Scope,
    scopeB: Scope,
    details?: string,
  ): MessageEnvelope {
    const payload: Record<string, unknown> = {
      conflict_id: conflictId,
      category,
      severity,
      involved_principals: involvedPrincipals,
      scope_a: scopeA,
      scope_b: scopeB,
      basis: {},
    };
    if (details) payload.details = details;
    return this.make(MessageType.CONFLICT_REPORT, sessionId, payload);
  }

  ackConflict(sessionId: string, conflictId: string, ackType = "seen"): MessageEnvelope {
    return this.make(MessageType.CONFLICT_ACK, sessionId, { conflict_id: conflictId, ack_type: ackType });
  }

  escalateConflict(sessionId: string, conflictId: string, escalateTo: string, reason: string, context?: string): MessageEnvelope {
    const payload: Record<string, unknown> = { conflict_id: conflictId, escalate_to: escalateTo, reason };
    if (context) payload.context = context;
    return this.make(MessageType.CONFLICT_ESCALATE, sessionId, payload);
  }

  resolveConflict(sessionId: string, conflictId: string, decision: string, rationale?: string, outcome?: unknown): MessageEnvelope {
    const payload: Record<string, unknown> = { conflict_id: conflictId, decision };
    if (rationale) payload.rationale = rationale;
    if (outcome) payload.outcome = outcome;
    return this.make(MessageType.RESOLUTION, sessionId, payload);
  }

  processMessage(envelope: MessageEnvelope): void {
    if (envelope.watermark) {
      this.lamportClock.processWatermark(envelope.watermark);
    }
  }

  getClockValue(): number {
    return this.lamportClock.value;
  }

  getInfo() {
    return {
      principal_id: this.principalId,
      principal_type: this.principalType,
      display_name: this.displayName,
      roles: this.roles,
      capabilities: this.capabilities,
      sender_instance_id: this.senderInstanceId,
    };
  }
}
