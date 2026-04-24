import { MessageEnvelope } from "./envelope.js";
import { Role, Scope } from "./models.js";
export declare class Participant {
    private principalId;
    private principalType;
    private displayName;
    private roles;
    private capabilities;
    private lamportClock;
    private credential?;
    private senderInstanceId;
    constructor(principalId: string, principalType: string, displayName: string, roles?: Array<Role | string>, capabilities?: string[], credential?: {
        type: string;
        value: string;
        issuer?: string;
        expires_at?: string;
    });
    private sender;
    private make;
    hello(sessionId: string, backend?: {
        model_id: string;
        provider: string;
    }): MessageEnvelope;
    heartbeat(sessionId: string, status?: string, activeIntentId?: string, summary?: string, backendHealth?: Record<string, unknown>): MessageEnvelope;
    goodbye(sessionId: string, reason?: string, activeIntents?: string[], intentDisposition?: string): MessageEnvelope;
    announceIntent(sessionId: string, intentId: string, objective: string, scope: Scope, ttlSec?: number): MessageEnvelope;
    updateIntent(sessionId: string, intentId: string, opts?: {
        objective?: string;
        scope?: Scope;
        ttl_sec?: number;
    }): MessageEnvelope;
    withdrawIntent(sessionId: string, intentId: string, reason?: string): MessageEnvelope;
    claimIntent(sessionId: string, claimId: string, originalIntentId: string, originalPrincipalId: string, newIntentId: string, objective: string, scope: Scope, justification?: string): MessageEnvelope;
    proposeOp(sessionId: string, opId: string, intentId: string, target: string, opKind: string): MessageEnvelope;
    commitOp(sessionId: string, opId: string, intentId: string, target: string, opKind: string, stateRefBefore?: string, stateRefAfter?: string): MessageEnvelope;
    batchCommitOp(sessionId: string, batchId: string, operations: Array<Record<string, unknown>>, atomicity?: "all_or_nothing" | "best_effort", intentId?: string, summary?: string): MessageEnvelope;
    supersedeOp(sessionId: string, opId: string, supersedesOpId: string, target: string, intentId?: string, reason?: string, stateRefAfter?: string): MessageEnvelope;
    reportConflict(sessionId: string, conflictId: string, category: string, severity: string, involvedPrincipals: string[], scopeA: Scope, scopeB: Scope, details?: string): MessageEnvelope;
    ackConflict(sessionId: string, conflictId: string, ackType?: string): MessageEnvelope;
    escalateConflict(sessionId: string, conflictId: string, escalateTo: string, reason: string, context?: string): MessageEnvelope;
    resolveConflict(sessionId: string, conflictId: string, decision: string, rationale?: string, outcome?: unknown): MessageEnvelope;
    processMessage(envelope: MessageEnvelope): void;
    getClockValue(): number;
    getInfo(): {
        principal_id: string;
        principal_type: string;
        display_name: string;
        roles: string[];
        capabilities: string[];
        sender_instance_id: string;
    };
}
//# sourceMappingURL=participant.d.ts.map