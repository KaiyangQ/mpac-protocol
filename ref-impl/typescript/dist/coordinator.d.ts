import { MessageEnvelope } from "./envelope.js";
import { ComplianceProfile, ConflictCategory, Principal, Scope, SecurityProfile, Severity } from "./models.js";
import { ConflictStateMachine, IntentStateMachine, OperationStateMachine } from "./state-machines.js";
interface Intent {
    intent_id: string;
    principal_id: string;
    objective: string;
    scope: Scope;
    stateMachine: IntentStateMachine;
    received_at: number;
    ttl_sec?: number;
    expires_at?: number;
    last_message_id?: string;
    claimed_by?: string;
}
interface Operation {
    op_id: string;
    intent_id: string;
    principal_id: string;
    target: string;
    op_kind: string;
    stateMachine: OperationStateMachine;
    state_ref_before?: string;
    state_ref_after?: string;
    batch_id?: string;
    authorized_at?: number;
    authorized_by?: string;
    created_at: number;
}
interface Conflict {
    conflict_id: string;
    category: ConflictCategory | string;
    severity: Severity | string;
    principal_a: string;
    principal_b: string;
    intent_a: string;
    intent_b: string;
    stateMachine: ConflictStateMachine;
    related_intents: string[];
    related_ops: string[];
    created_at: number;
    escalated_to?: string;
    escalated_at?: number;
    resolution_id?: string;
    resolved_by?: string;
    scope_frozen: boolean;
}
interface ParticipantInfo {
    principal: Principal;
    last_seen: number;
    status: string;
    is_available: boolean;
    backend_model_id?: string;
    backend_provider?: string;
    backend_provider_status: string;
}
export declare class SessionCoordinator {
    private sessionId;
    private coordinatorId;
    private coordinatorInstanceId;
    private coordinatorEpoch;
    private securityProfile;
    private complianceProfile;
    private executionModel;
    private stateRefFormat;
    private watermarkKind;
    private participants;
    private intents;
    private operations;
    private conflicts;
    private claims;
    private claimIndex;
    private auditLog;
    private lamportClock;
    private recentMessageIds;
    private seenMessageIds;
    private senderFrontier;
    private intentExpiryGraceSec;
    private heartbeatIntervalSec;
    private unavailabilityTimeoutMs;
    private resolutionTimeoutMs;
    private intentClaimGraceMs;
    private sessionClosed;
    private sessionStartedAt;
    private rolePolicy;
    private replayWindowSec;
    private backendHealthPolicy;
    constructor(sessionId: string, securityProfile?: SecurityProfile | string, complianceProfile?: ComplianceProfile | string, intentExpiryGraceSec?: number, unavailabilityTimeoutSec?: number, resolutionTimeoutSec?: number, executionModel?: "pre_commit" | "post_commit", stateRefFormat?: string, intentClaimGraceSec?: number, rolePolicy?: any, replayWindowSec?: number, backendHealthPolicy?: any);
    processMessage(envelope: MessageEnvelope): MessageEnvelope[];
    checkExpiry(nowMs?: number): MessageEnvelope[];
    checkLiveness(nowMs?: number): MessageEnvelope[];
    checkResolutionTimeouts(nowMs?: number): MessageEnvelope[];
    private handleHello;
    private handleHeartbeat;
    private processBackendHealth;
    private validateBackendSwitch;
    private buildLivenessPolicy;
    private makeCoordinatorStatusBackendAlert;
    private handleGoodbye;
    private handleIntentAnnounce;
    private handleIntentUpdate;
    private handleIntentWithdraw;
    private handleIntentClaim;
    private handleOpPropose;
    private handleOpCommit;
    private handleOpBatchCommit;
    private handleOpSupersede;
    private handleConflictReport;
    private handleConflictAck;
    private handleConflictEscalate;
    private handleResolution;
    private cascadeIntentTermination;
    private checkAutoDismiss;
    private handleParticipantUnavailable;
    private makeEnvelope;
    private makeOpReject;
    private makeBatchReject;
    private makeProtocolError;
    private rememberMessageId;
    private recordSenderFrontier;
    private buildOperation;
    private registerOperationFromPayload;
    private commitOperationEntry;
    private validateOperationAgainstIntent;
    private authorizeOperation;
    private trackOperationConflicts;
    /**
     * Check whether a scope overlaps with a conflict whose scope has been frozen.
     *
     * Per Section 18.6.2, scopes enter frozen state only after resolution_timeout_sec
     * expires (via checkResolutionTimeouts), NOT immediately on conflict creation.
     */
    private isScopeFrozen;
    /**
     * For INTENT_ANNOUNCE: distinguish full containment (MUST reject) from partial overlap (SHOULD accept with warning).
     * Per Section 18.6.2.
     */
    private checkFrozenScopeForIntent;
    private buildFrozenUnionScope;
    private detectScopeOverlaps;
    private handleOwnerRejoin;
    private findArbiter;
    private findClaimApprover;
    private approveClaim;
    private rejectClaim;
    private withdrawClaim;
    private checkPendingClaims;
    private evaluateRolePolicy;
    private isAuthorizedResolver;
    recoverFromSnapshot(snapshotData: any): void;
    replayAuditLog(messages: MessageEnvelope[]): MessageEnvelope[];
    getAuditLog(): MessageEnvelope[];
    closeSession(reason?: string): MessageEnvelope[];
    checkAutoClose(): MessageEnvelope[];
    coordinatorStatus(event?: string): MessageEnvelope[];
    snapshot(): any;
    private buildSessionSummary;
    getParticipant(id: string): ParticipantInfo | undefined;
    getIntent(id: string): Intent | undefined;
    getOperation(id: string): Operation | undefined;
    getConflict(id: string): Conflict | undefined;
    getParticipants(): ParticipantInfo[];
    getIntents(): Intent[];
    getOperations(): Operation[];
    getConflicts(): Conflict[];
}
export {};
//# sourceMappingURL=coordinator.d.ts.map