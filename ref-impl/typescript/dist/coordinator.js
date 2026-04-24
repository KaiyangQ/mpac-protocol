import { v4 as uuidv4 } from "uuid";
import { createEnvelope } from "./envelope.js";
import { ComplianceProfile, ConflictCategory, ConflictState, MessageType, OperationState, ScopeKind, SecurityProfile, Severity, IntentState, } from "./models.js";
import { scopeOverlap, scopeContains } from "./scope.js";
import { ConflictStateMachine, IntentStateMachine, OperationStateMachine } from "./state-machines.js";
import { LamportClock } from "./watermark.js";
const PROTOCOL_VERSION = "0.1.13";
export class SessionCoordinator {
    sessionId;
    coordinatorId;
    coordinatorInstanceId;
    coordinatorEpoch;
    securityProfile;
    complianceProfile;
    executionModel;
    stateRefFormat;
    watermarkKind;
    participants = new Map();
    intents = new Map();
    operations = new Map();
    conflicts = new Map();
    claims = new Map();
    claimIndex = new Map();
    auditLog = [];
    lamportClock;
    recentMessageIds = [];
    seenMessageIds = new Set();
    senderFrontier = {};
    intentExpiryGraceSec;
    heartbeatIntervalSec;
    unavailabilityTimeoutMs;
    resolutionTimeoutMs;
    intentClaimGraceMs;
    sessionClosed;
    sessionStartedAt;
    rolePolicy;
    replayWindowSec;
    backendHealthPolicy;
    constructor(sessionId, securityProfile = SecurityProfile.OPEN, complianceProfile = ComplianceProfile.CORE, intentExpiryGraceSec = 30, unavailabilityTimeoutSec = 90, resolutionTimeoutSec = 300, executionModel = "post_commit", stateRefFormat = "sha256", intentClaimGraceSec = 0, rolePolicy = undefined, replayWindowSec = 300, backendHealthPolicy = undefined) {
        if (executionModel === "pre_commit" && complianceProfile !== ComplianceProfile.GOVERNANCE) {
            throw new Error("pre_commit sessions require Governance Profile compliance");
        }
        this.sessionId = sessionId;
        this.securityProfile = securityProfile;
        this.complianceProfile = complianceProfile;
        this.executionModel = executionModel;
        this.stateRefFormat = stateRefFormat;
        this.watermarkKind = "lamport_clock";
        this.intentExpiryGraceSec = intentExpiryGraceSec;
        this.heartbeatIntervalSec = 30;
        this.unavailabilityTimeoutMs = unavailabilityTimeoutSec * 1000;
        this.resolutionTimeoutMs = resolutionTimeoutSec * 1000;
        this.intentClaimGraceMs = intentClaimGraceSec * 1000;
        this.coordinatorEpoch = 1;
        this.coordinatorId = `service:coordinator-${sessionId}`;
        this.coordinatorInstanceId = `${this.coordinatorId}:epoch-${this.coordinatorEpoch}`;
        this.lamportClock = new LamportClock();
        this.sessionClosed = false;
        this.sessionStartedAt = Date.now();
        this.rolePolicy = rolePolicy;
        this.replayWindowSec = replayWindowSec;
        this.backendHealthPolicy = backendHealthPolicy;
    }
    processMessage(envelope) {
        this.auditLog.push(envelope);
        // Replay protection (Section 23.1.2): reject duplicate message_id
        // AND timestamp window check in Authenticated/Verified profiles
        if (this.securityProfile !== SecurityProfile.OPEN && this.securityProfile !== "open") {
            if (this.seenMessageIds.has(envelope.message_id)) {
                return [this.makeProtocolError("REPLAY_DETECTED", envelope.message_id, `Duplicate message_id '${envelope.message_id}' rejected by replay protection`)];
            }
            // RFC 3339 date-time: YYYY-MM-DDThh:mm:ss[.frac](Z | ±HH:MM)
            const rfc3339Re = /^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+\-]\d{2}:\d{2})$/;
            if (!rfc3339Re.test(envelope.ts ?? "")) {
                return [this.makeProtocolError("REPLAY_DETECTED", envelope.message_id, `Timestamp '${envelope.ts}' is not valid RFC 3339 date-time`)];
            }
            const msgTs = new Date(envelope.ts).getTime();
            if (isNaN(msgTs)) {
                return [this.makeProtocolError("REPLAY_DETECTED", envelope.message_id, `Unparseable timestamp '${envelope.ts}'; RFC 3339 date-time required`)];
            }
            const drift = Math.abs(Date.now() - msgTs) / 1000;
            if (drift > this.replayWindowSec) {
                return [this.makeProtocolError("REPLAY_DETECTED", envelope.message_id, `Message timestamp drift ${drift.toFixed(1)}s exceeds replay window of ${this.replayWindowSec}s`)];
            }
        }
        this.seenMessageIds.add(envelope.message_id);
        this.rememberMessageId(envelope.message_id);
        this.recordSenderFrontier(envelope);
        if (envelope.watermark) {
            this.lamportClock.processWatermark(envelope.watermark);
        }
        const existingParticipant = this.participants.get(envelope.sender.principal_id);
        if (existingParticipant) {
            existingParticipant.last_seen = Date.now();
        }
        if (this.sessionClosed && envelope.message_type !== MessageType.GOODBYE) {
            return [this.makeProtocolError("SESSION_CLOSED", envelope.message_id, `Session ${this.sessionId} has been closed`)];
        }
        // HELLO-first gate: only HELLO is allowed from unregistered senders (Section 14.1)
        const senderRegistered = this.participants.has(envelope.sender.principal_id);
        if (!senderRegistered && envelope.message_type !== MessageType.HELLO) {
            return [this.makeProtocolError("INVALID_REFERENCE", envelope.message_id, `Principal ${envelope.sender.principal_id} must send HELLO before any other message`)];
        }
        let responses = [];
        switch (envelope.message_type) {
            case MessageType.HELLO:
                responses = this.handleHello(envelope);
                break;
            case MessageType.HEARTBEAT:
                responses = this.handleHeartbeat(envelope);
                break;
            case MessageType.GOODBYE:
                responses = this.handleGoodbye(envelope);
                break;
            case MessageType.INTENT_ANNOUNCE:
                responses = this.handleIntentAnnounce(envelope);
                break;
            case MessageType.INTENT_UPDATE:
                responses = this.handleIntentUpdate(envelope);
                break;
            case MessageType.INTENT_WITHDRAW:
                responses = this.handleIntentWithdraw(envelope);
                break;
            case MessageType.INTENT_CLAIM:
                responses = this.handleIntentClaim(envelope);
                break;
            case MessageType.OP_PROPOSE:
                responses = this.handleOpPropose(envelope);
                break;
            case MessageType.OP_COMMIT:
                responses = this.handleOpCommit(envelope);
                break;
            case MessageType.OP_BATCH_COMMIT:
                responses = this.handleOpBatchCommit(envelope);
                break;
            case MessageType.OP_SUPERSEDE:
                responses = this.handleOpSupersede(envelope);
                break;
            case MessageType.CONFLICT_REPORT:
                responses = this.handleConflictReport(envelope);
                break;
            case MessageType.CONFLICT_ACK:
                responses = this.handleConflictAck(envelope);
                break;
            case MessageType.CONFLICT_ESCALATE:
                responses = this.handleConflictEscalate(envelope);
                break;
            case MessageType.RESOLUTION:
                responses = this.handleResolution(envelope);
                break;
            case MessageType.SESSION_CLOSE:
            case MessageType.COORDINATOR_STATUS:
                responses = [];
                break;
            default:
                responses = [];
        }
        responses.push(...this.checkPendingClaims());
        return responses;
    }
    checkExpiry(nowMs = Date.now()) {
        const responses = [];
        for (const intent of this.intents.values()) {
            if (intent.expires_at !== undefined &&
                !intent.stateMachine.isTerminal() &&
                intent.stateMachine.currentState !== IntentState.ANNOUNCED &&
                nowMs >= intent.expires_at) {
                intent.stateMachine.transition("EXPIRED");
                responses.push(...this.cascadeIntentTermination(intent.intent_id));
            }
        }
        responses.push(...this.checkAutoDismiss());
        responses.push(...this.checkPendingClaims(nowMs));
        return responses;
    }
    checkLiveness(nowMs = Date.now()) {
        const responses = [];
        for (const [principalId, info] of this.participants.entries()) {
            if (!info.is_available || info.status === "offline")
                continue;
            if (nowMs - info.last_seen > this.unavailabilityTimeoutMs) {
                info.is_available = false;
                responses.push(...this.handleParticipantUnavailable(principalId));
            }
        }
        responses.push(...this.checkPendingClaims(nowMs));
        return responses;
    }
    checkResolutionTimeouts(nowMs = Date.now()) {
        const responses = [];
        for (const conflict of this.conflicts.values()) {
            if (conflict.stateMachine.currentState !== ConflictState.OPEN && conflict.stateMachine.currentState !== ConflictState.ACKED) {
                continue;
            }
            if (nowMs - conflict.created_at <= this.resolutionTimeoutMs) {
                continue;
            }
            const arbiterId = this.findArbiter();
            if (arbiterId) {
                if (conflict.stateMachine.currentState === ConflictState.OPEN)
                    conflict.stateMachine.transition("ACKED");
                conflict.stateMachine.transition("ESCALATED");
                conflict.escalated_to = arbiterId;
                conflict.escalated_at = nowMs;
                responses.push(this.makeEnvelope(MessageType.CONFLICT_ESCALATE, {
                    conflict_id: conflict.conflict_id,
                    escalate_to: arbiterId,
                    reason: "resolution_timeout",
                }));
            }
            else {
                // No arbiter available — enter frozen scope state (Section 18.6.1 + 18.6.2)
                conflict.scope_frozen = true;
                responses.push(this.makeProtocolError("RESOLUTION_TIMEOUT", conflict.conflict_id, `No arbiter available for conflict ${conflict.conflict_id}; scope is now frozen`));
            }
        }
        return responses;
    }
    handleHello(envelope) {
        const payload = envelope.payload;
        const requestedRoles = (payload.roles ?? ["participant"]);
        // Credential validation for Authenticated/Verified profiles
        if (this.securityProfile !== "open") {
            const credential = payload.credential;
            if (!credential || !credential.type || !credential.value) {
                return [this.makeProtocolError("CREDENTIAL_REJECTED", envelope.message_id, `Security profile '${this.securityProfile}' requires a valid credential in HELLO`)];
            }
        }
        // Role policy evaluation (Section 23.1.5)
        const grantedRoles = this.evaluateRolePolicy(envelope.sender.principal_id, envelope.sender.principal_type, requestedRoles);
        // If no roles were granted, reject the HELLO
        if (grantedRoles.length === 0) {
            return [this.makeProtocolError("AUTHORIZATION_FAILED", envelope.message_id, "No roles could be granted for this principal; check role policy configuration")];
        }
        const principal = {
            principal_id: envelope.sender.principal_id,
            principal_type: envelope.sender.principal_type,
            display_name: payload.display_name,
            roles: grantedRoles,
            capabilities: payload.capabilities ?? [],
            joined_at: new Date().toISOString(),
        };
        const backend = payload.backend;
        this.participants.set(principal.principal_id, {
            principal,
            last_seen: Date.now(),
            status: "idle",
            is_available: true,
            backend_model_id: backend?.model_id,
            backend_provider: backend?.provider,
            backend_provider_status: backend ? "operational" : "unknown",
        });
        const responses = this.handleOwnerRejoin(principal.principal_id);
        responses.push(this.makeEnvelope(MessageType.SESSION_INFO, {
            session_id: this.sessionId,
            protocol_version: PROTOCOL_VERSION,
            security_profile: this.securityProfile,
            compliance_profile: this.complianceProfile,
            watermark_kind: this.watermarkKind,
            execution_model: this.executionModel,
            state_ref_format: this.stateRefFormat,
            governance_policy: {
                require_acknowledgment: true,
                intent_expiry_grace_sec: this.intentExpiryGraceSec,
            },
            liveness_policy: this.buildLivenessPolicy(),
            participant_count: this.participants.size,
            granted_roles: grantedRoles,
            identity_verified: this.securityProfile === SecurityProfile.OPEN || Boolean(payload.credential),
            identity_method: payload.credential?.type,
            identity_issuer: payload.credential?.issuer,
            compatibility_errors: [],
        }));
        return responses;
    }
    handleHeartbeat(envelope) {
        const payload = envelope.payload;
        const pid = envelope.sender.principal_id;
        const info = this.participants.get(pid);
        const responses = [];
        if (!info)
            return responses;
        info.last_seen = Date.now();
        info.status = payload.status ?? "idle";
        if (!info.is_available) {
            info.is_available = true;
            responses.push(...this.handleOwnerRejoin(pid));
        }
        // Backend health monitoring (Section 14.3.1)
        const backendHealth = payload.backend_health;
        if (backendHealth) {
            responses.push(...this.processBackendHealth(pid, info, backendHealth));
        }
        return responses;
    }
    processBackendHealth(pid, info, backendHealth) {
        const responses = [];
        const providerStatus = backendHealth.provider_status ?? "unknown";
        const oldStatus = info.backend_provider_status;
        // Update tracked backend info
        info.backend_model_id = backendHealth.model_id ?? info.backend_model_id;
        info.backend_provider_status = providerStatus;
        // Check for model switch
        const switchedFrom = backendHealth.switched_from;
        if (switchedFrom) {
            const switchError = this.validateBackendSwitch(pid, backendHealth);
            if (switchError)
                return [switchError];
            const modelId = backendHealth.model_id ?? "";
            if (modelId.includes("/")) {
                info.backend_provider = modelId.split("/")[0];
            }
        }
        // Determine action based on backend_health_policy
        const policy = this.backendHealthPolicy;
        if (!policy || !policy.enabled)
            return responses;
        let action;
        if (providerStatus === "down") {
            action = policy.on_down ?? "suspend_and_claim";
        }
        else if (providerStatus === "degraded") {
            action = policy.on_degraded ?? "warn";
        }
        if (action && action !== "ignore" && providerStatus !== oldStatus) {
            // Emit backend_alert
            const alert = this.makeCoordinatorStatusBackendAlert(pid, backendHealth);
            responses.push(alert);
            // suspend_and_claim: suspend agent's active intents
            if (action === "suspend_and_claim") {
                for (const intent of this.intents.values()) {
                    if (intent.principal_id === pid && !intent.stateMachine.isTerminal()) {
                        if (intent.stateMachine.currentState !== "SUSPENDED") {
                            try {
                                intent.stateMachine.transition("SUSPENDED");
                                responses.push(this.makeEnvelope(MessageType.INTENT_UPDATE, {
                                    intent_id: intent.intent_id,
                                    objective: `[SUSPENDED: backend ${providerStatus}] ${intent.objective}`,
                                }));
                            }
                            catch (_) {
                                // Intent may not support this transition
                            }
                        }
                    }
                }
            }
        }
        return responses;
    }
    validateBackendSwitch(pid, backendHealth) {
        const policy = this.backendHealthPolicy;
        if (!policy || !policy.enabled)
            return null;
        const autoSwitch = policy.auto_switch ?? "allowed";
        if (autoSwitch === "forbidden") {
            return this.makeProtocolError("BACKEND_SWITCH_DENIED", undefined, "Backend model switching is forbidden by session policy (auto_switch=forbidden)");
        }
        const allowedProviders = policy.allowed_providers;
        if (allowedProviders) {
            const newModelId = backendHealth.model_id ?? "";
            const newProvider = newModelId.includes("/") ? newModelId.split("/")[0] : "";
            if (newProvider && !allowedProviders.includes(newProvider)) {
                return this.makeProtocolError("BACKEND_SWITCH_DENIED", undefined, `Provider '${newProvider}' is not in allowed_providers: ${JSON.stringify(allowedProviders)}`);
            }
        }
        return null;
    }
    buildLivenessPolicy() {
        const policy = {
            heartbeat_interval_sec: this.heartbeatIntervalSec,
            unavailability_timeout_sec: this.unavailabilityTimeoutMs / 1000,
            intent_claim_grace_period_sec: this.intentClaimGraceMs / 1000,
            resolution_timeout_sec: this.resolutionTimeoutMs / 1000,
        };
        if (this.backendHealthPolicy) {
            policy.backend_health_policy = this.backendHealthPolicy;
        }
        return policy;
    }
    makeCoordinatorStatusBackendAlert(affectedPrincipal, backendHealth) {
        const openConflicts = [...this.conflicts.values()].filter((c) => c.stateMachine.currentState !== "CLOSED" && c.stateMachine.currentState !== "DISMISSED").length;
        return this.makeEnvelope(MessageType.COORDINATOR_STATUS, {
            event: "backend_alert",
            coordinator_id: this.coordinatorId,
            session_health: openConflicts === 0 ? "healthy" : "degraded",
            active_participants: [...this.participants.values()].filter((p) => p.is_available).length,
            open_conflicts: openConflicts,
            affected_principal: affectedPrincipal,
            backend_detail: {
                model_id: backendHealth.model_id ?? "",
                provider_status: backendHealth.provider_status ?? "unknown",
                status_detail: backendHealth.status_detail ?? null,
                alternatives: backendHealth.alternatives ?? [],
            },
        });
    }
    handleGoodbye(envelope) {
        const payload = envelope.payload;
        const principalId = envelope.sender.principal_id;
        const disposition = payload.intent_disposition ?? "withdraw";
        const responses = [];
        const info = this.participants.get(principalId);
        if (info) {
            info.is_available = false;
            info.status = "offline";
        }
        let activeIntentIds = (payload.active_intents ?? []);
        if (activeIntentIds.length === 0) {
            activeIntentIds = [...this.intents.values()]
                .filter((intent) => intent.principal_id === principalId && !intent.stateMachine.isTerminal() && intent.stateMachine.currentState !== IntentState.ANNOUNCED)
                .map((intent) => intent.intent_id);
        }
        for (const intentId of activeIntentIds) {
            const intent = this.intents.get(intentId);
            if (!intent)
                continue;
            // Ownership guard: only the intent owner can affect their own intents
            if (intent.principal_id !== principalId)
                continue;
            try {
                if (disposition === "transfer") {
                    if (intent.stateMachine.currentState === IntentState.ACTIVE)
                        intent.stateMachine.transition("SUSPENDED");
                }
                else if (disposition !== "expire") {
                    intent.stateMachine.transition("WITHDRAWN");
                    responses.push(...this.cascadeIntentTermination(intentId));
                }
            }
            catch {
                // Ignore invalid transitions.
            }
        }
        for (const operation of this.operations.values()) {
            if (operation.principal_id !== principalId)
                continue;
            if (operation.stateMachine.currentState === OperationState.PROPOSED) {
                operation.stateMachine.transition("ABANDONED");
            }
            else if (operation.stateMachine.currentState === OperationState.FROZEN) {
                operation.stateMachine.transition("ABANDONED");
            }
        }
        responses.push(...this.checkAutoDismiss());
        return responses;
    }
    handleIntentAnnounce(envelope) {
        const payload = envelope.payload;
        // Frozen-scope enforcement for INTENT_ANNOUNCE (Section 18.6.2):
        // - Fully contained in frozen scope → MUST reject
        // - Partially overlapping → SHOULD accept with warning
        let frozenAction = null;
        let frozenConflict;
        if (payload.scope) {
            const check = this.checkFrozenScopeForIntent(payload.scope);
            frozenAction = check.action;
            frozenConflict = check.conflict;
            if (frozenAction === "reject") {
                return [this.makeProtocolError("SCOPE_FROZEN", envelope.message_id, `Scope fully contained in frozen conflict ${frozenConflict.conflict_id}; new intents blocked until conflict is resolved`)];
            }
        }
        const ttlSec = payload.ttl_sec ?? (payload.expiry_ms !== undefined ? Number(payload.expiry_ms) / 1000 : undefined);
        const stateMachine = new IntentStateMachine();
        stateMachine.transition("ACTIVE");
        const receivedAt = Date.now();
        const intent = {
            intent_id: payload.intent_id,
            principal_id: envelope.sender.principal_id,
            objective: payload.objective,
            scope: payload.scope,
            stateMachine,
            received_at: receivedAt,
            ttl_sec: ttlSec,
            expires_at: ttlSec !== undefined ? receivedAt + Number(ttlSec) * 1000 : undefined,
            last_message_id: envelope.message_id,
        };
        this.intents.set(intent.intent_id, intent);
        const responses = this.detectScopeOverlaps(intent);
        // Partial overlap warning (Section 18.6.2: SHOULD accept but MUST warn)
        if (frozenAction === "warn" && frozenConflict) {
            responses.push(this.makeProtocolError("SCOPE_FROZEN", envelope.message_id, `Warning: intent scope partially overlaps frozen conflict ${frozenConflict.conflict_id}; overlapping portion is frozen`));
        }
        return responses;
    }
    handleIntentUpdate(envelope) {
        const payload = envelope.payload;
        const intent = this.intents.get(payload.intent_id);
        if (!intent || intent.principal_id !== envelope.sender.principal_id)
            return [];
        if (intent.stateMachine.currentState !== IntentState.ACTIVE)
            return [];
        let scopeChanged = false;
        if (payload.objective !== undefined)
            intent.objective = payload.objective;
        if (payload.scope !== undefined) {
            intent.scope = payload.scope;
            scopeChanged = true;
        }
        if (payload.ttl_sec !== undefined) {
            intent.ttl_sec = Number(payload.ttl_sec);
            intent.expires_at = Date.now() + intent.ttl_sec * 1000;
        }
        intent.last_message_id = envelope.message_id;
        return scopeChanged ? this.detectScopeOverlaps(intent, true) : [];
    }
    handleIntentWithdraw(envelope) {
        const payload = envelope.payload;
        const intent = this.intents.get(payload.intent_id);
        if (!intent || intent.principal_id !== envelope.sender.principal_id)
            return [];
        try {
            intent.stateMachine.transition("WITHDRAWN");
        }
        catch {
            return [];
        }
        return [...this.cascadeIntentTermination(payload.intent_id), ...this.checkAutoDismiss()];
    }
    handleIntentClaim(envelope) {
        const payload = envelope.payload;
        const originalIntentId = payload.original_intent_id;
        const original = this.intents.get(originalIntentId);
        if (!original) {
            return [this.makeProtocolError("INVALID_REFERENCE", envelope.message_id, `Intent ${originalIntentId} does not exist`)];
        }
        if (this.claims.has(originalIntentId)) {
            return [this.makeProtocolError("CLAIM_CONFLICT", envelope.message_id, `Intent ${originalIntentId} already has an accepted pending claim`)];
        }
        if (original.claimed_by && original.stateMachine.currentState === IntentState.TRANSFERRED) {
            return [this.makeProtocolError("CLAIM_CONFLICT", envelope.message_id, `Intent ${originalIntentId} has already been transferred to another claimant`)];
        }
        if (original.stateMachine.currentState !== IntentState.SUSPENDED) {
            return [this.makeProtocolError("INVALID_REFERENCE", envelope.message_id, `Intent ${originalIntentId} is not SUSPENDED`)];
        }
        const claim = {
            claim_id: payload.claim_id,
            original_intent_id: originalIntentId,
            original_principal_id: payload.original_principal_id,
            new_intent_id: payload.new_intent_id,
            claimer_principal_id: envelope.sender.principal_id,
            objective: payload.objective,
            scope: payload.scope,
            justification: payload.justification,
            submitted_at: Date.now(),
            decision: "pending",
        };
        original.claimed_by = claim.claimer_principal_id;
        this.claims.set(originalIntentId, claim);
        this.claimIndex.set(claim.claim_id, claim);
        return [];
    }
    handleOpPropose(envelope) {
        const payload = envelope.payload;
        // Frozen-scope enforcement: reject OP_PROPOSE if target overlaps an active conflict
        if (payload.target) {
            const targetScope = { kind: "file_set", resources: [payload.target] };
            const frozen = this.isScopeFrozen(targetScope);
            if (frozen) {
                return [this.makeProtocolError("SCOPE_FROZEN", envelope.message_id, `Target '${payload.target}' overlaps active conflict ${frozen.conflict_id}; scope is frozen`)];
            }
        }
        const operation = this.registerOperationFromPayload(payload, envelope.sender.principal_id, OperationState.PROPOSED);
        const responses = this.validateOperationAgainstIntent(operation);
        if (this.executionModel === "pre_commit" && operation.stateMachine.currentState === OperationState.PROPOSED) {
            responses.push(...this.authorizeOperation(operation));
        }
        return responses;
    }
    handleOpCommit(envelope) {
        const payload = envelope.payload;
        const opId = payload.op_id;
        if (this.executionModel === "pre_commit") {
            let operation = this.operations.get(opId);
            if (!operation) {
                operation = this.registerOperationFromPayload(payload, envelope.sender.principal_id, OperationState.PROPOSED);
                const responses = this.validateOperationAgainstIntent(operation);
                if (operation.stateMachine.currentState === OperationState.PROPOSED) {
                    responses.push(...this.authorizeOperation(operation));
                }
                return responses;
            }
            if (operation.stateMachine.currentState === OperationState.FROZEN) {
                return [this.makeProtocolError("SCOPE_FROZEN", envelope.message_id, `Operation ${opId} is frozen until its intent is restored`)];
            }
            if (operation.authorized_at === undefined) {
                return [this.makeProtocolError("AUTHORIZATION_FAILED", envelope.message_id, `Operation ${opId} has not been authorized for execution`)];
            }
            if (operation.stateMachine.currentState === OperationState.PROPOSED) {
                operation.target = payload.target ?? operation.target;
                operation.op_kind = payload.op_kind ?? operation.op_kind;
                operation.state_ref_before = payload.state_ref_before;
                operation.state_ref_after = payload.state_ref_after;
                operation.stateMachine.transition("COMMITTED");
            }
            return [];
        }
        // Post-commit: frozen-scope enforcement before committing
        if (payload.target) {
            const targetScope = { kind: "file_set", resources: [payload.target] };
            const frozen = this.isScopeFrozen(targetScope);
            if (frozen) {
                return [this.makeProtocolError("SCOPE_FROZEN", envelope.message_id, `Target '${payload.target}' overlaps active conflict ${frozen.conflict_id}; scope is frozen`)];
            }
        }
        this.commitOperationEntry(payload, envelope.sender.principal_id);
        return [];
    }
    handleOpBatchCommit(envelope) {
        const payload = envelope.payload;
        const batchId = payload.batch_id;
        const atomicity = payload.atomicity ?? "all_or_nothing";
        const operations = (payload.operations ?? []);
        const intentId = payload.intent_id;
        if (operations.length === 0) {
            return [this.makeProtocolError("MALFORMED_MESSAGE", envelope.message_id, `Batch ${batchId} must contain at least one operation entry`)];
        }
        // Frozen-scope check: target-based (Section 18.6.2)
        // Check every entry's target against frozen scopes — intent_id is optional
        for (const entry of operations) {
            const entryTarget = entry.target;
            if (entryTarget) {
                const targetScope = { kind: ScopeKind.FILE_SET, resources: [entryTarget] };
                const frozen = this.isScopeFrozen(targetScope);
                if (frozen) {
                    return [this.makeProtocolError("SCOPE_FROZEN", envelope.message_id, `Target '${entryTarget}' overlaps with frozen conflict ${frozen.conflict_id}; batch blocked`)];
                }
            }
        }
        if (this.executionModel === "pre_commit") {
            const existing = operations.map((entry) => this.operations.get(entry.op_id));
            if (existing.every(Boolean)) {
                for (const op of existing) {
                    if (!op || op.batch_id !== batchId) {
                        return [this.makeProtocolError("INVALID_REFERENCE", envelope.message_id, `Batch ${batchId} references unknown or mismatched operations`)];
                    }
                    if (op.authorized_at === undefined) {
                        return [this.makeProtocolError("AUTHORIZATION_FAILED", envelope.message_id, `Batch ${batchId} has not been authorized for execution`)];
                    }
                }
                for (const [index, op] of existing.entries()) {
                    if (!op)
                        continue;
                    op.state_ref_before = operations[index].state_ref_before;
                    op.state_ref_after = operations[index].state_ref_after;
                    if (op.stateMachine.currentState === OperationState.PROPOSED) {
                        op.stateMachine.transition("COMMITTED");
                    }
                }
                return [];
            }
            const created = [];
            const rejectedOps = [];
            for (const entry of operations) {
                const effectiveEntry = { ...entry, intent_id: entry.intent_id ?? intentId };
                if (intentId && effectiveEntry.intent_id !== intentId) {
                    rejectedOps.push(effectiveEntry.op_id);
                    continue;
                }
                const op = this.registerOperationFromPayload(effectiveEntry, envelope.sender.principal_id, OperationState.PROPOSED, batchId);
                created.push(op);
                this.validateOperationAgainstIntent(op).forEach(() => undefined);
                if (op.stateMachine.currentState !== OperationState.PROPOSED) {
                    rejectedOps.push(op.op_id);
                }
            }
            if (atomicity === "all_or_nothing" && rejectedOps.length > 0) {
                // Rollback: remove already-registered operations from coordinator state
                for (const op of created) {
                    this.operations.delete(op.op_id);
                }
                return [this.makeBatchReject(batchId, rejectedOps, "batch_validation_failed")];
            }
            const responses = [];
            for (const op of created) {
                if (op.stateMachine.currentState === OperationState.PROPOSED) {
                    responses.push(...this.authorizeOperation(op, batchId));
                }
            }
            return responses;
        }
        const rejectedOps = [];
        for (const entry of operations) {
            const effectiveEntry = { ...entry, intent_id: entry.intent_id ?? intentId };
            if (intentId && effectiveEntry.intent_id !== intentId) {
                rejectedOps.push(effectiveEntry.op_id);
                continue;
            }
            const temp = this.buildOperation(effectiveEntry, envelope.sender.principal_id, OperationState.COMMITTED, batchId);
            const validation = this.validateOperationAgainstIntent(temp, false);
            if (validation.length > 0) {
                rejectedOps.push(temp.op_id);
            }
        }
        if (atomicity === "all_or_nothing" && rejectedOps.length > 0) {
            return [this.makeBatchReject(batchId, rejectedOps, "batch_validation_failed")];
        }
        for (const entry of operations) {
            const effectiveEntry = { ...entry, intent_id: entry.intent_id ?? intentId };
            if (rejectedOps.includes(effectiveEntry.op_id))
                continue;
            this.commitOperationEntry(effectiveEntry, envelope.sender.principal_id, batchId);
        }
        return [];
    }
    handleOpSupersede(envelope) {
        const payload = envelope.payload;
        const oldOp = this.operations.get(payload.supersedes_op_id);
        if (!oldOp) {
            return [this.makeProtocolError("INVALID_REFERENCE", envelope.message_id, `Operation ${payload.supersedes_op_id} does not exist`)];
        }
        if (oldOp.stateMachine.currentState !== OperationState.COMMITTED) {
            return [this.makeProtocolError("INVALID_REFERENCE", envelope.message_id, `Operation ${payload.supersedes_op_id} is not COMMITTED (state: ${oldOp.stateMachine.currentState})`)];
        }
        oldOp.stateMachine.transition("SUPERSEDED");
        const newOp = this.buildOperation({
            op_id: payload.op_id,
            intent_id: payload.intent_id ?? oldOp.intent_id,
            target: payload.target ?? oldOp.target,
            op_kind: payload.op_kind ?? oldOp.op_kind,
            state_ref_before: oldOp.state_ref_after,
            state_ref_after: payload.state_ref_after,
        }, envelope.sender.principal_id, OperationState.COMMITTED);
        this.operations.set(newOp.op_id, newOp);
        this.trackOperationConflicts(newOp.intent_id, newOp.op_id);
        return [];
    }
    handleConflictReport(envelope) {
        const payload = envelope.payload;
        const conflictId = payload.conflict_id;
        if (!this.conflicts.has(conflictId)) {
            const involvedPrincipals = (payload.involved_principals ?? []);
            this.conflicts.set(conflictId, {
                conflict_id: conflictId,
                category: payload.category ?? ConflictCategory.SCOPE_OVERLAP,
                severity: payload.severity ?? Severity.MEDIUM,
                principal_a: payload.principal_a ?? involvedPrincipals[0] ?? "",
                principal_b: payload.principal_b ?? involvedPrincipals[1] ?? "",
                intent_a: payload.intent_a ?? "",
                intent_b: payload.intent_b ?? "",
                stateMachine: new ConflictStateMachine(),
                related_intents: [payload.intent_a, payload.intent_b].filter(Boolean),
                related_ops: [],
                created_at: Date.now(),
                scope_frozen: false,
            });
        }
        return [];
    }
    handleConflictAck(envelope) {
        const conflict = this.conflicts.get(envelope.payload.conflict_id);
        if (conflict && conflict.stateMachine.currentState === ConflictState.OPEN) {
            conflict.stateMachine.transition("ACKED");
        }
        return [];
    }
    handleConflictEscalate(envelope) {
        const payload = envelope.payload;
        const conflict = this.conflicts.get(payload.conflict_id);
        if (!conflict)
            return [];
        if (conflict.stateMachine.currentState === ConflictState.OPEN)
            conflict.stateMachine.transition("ACKED");
        if (conflict.stateMachine.currentState === ConflictState.ACKED)
            conflict.stateMachine.transition("ESCALATED");
        conflict.escalated_to = payload.escalate_to;
        conflict.escalated_at = Date.now();
        return [];
    }
    handleResolution(envelope) {
        const payload = envelope.payload;
        const conflict = this.conflicts.get(payload.conflict_id);
        if (!conflict) {
            return [this.makeProtocolError("INVALID_REFERENCE", envelope.message_id, `Conflict ${payload.conflict_id} does not exist`)];
        }
        if (conflict.resolution_id || conflict.stateMachine.isTerminal()) {
            return [this.makeProtocolError("RESOLUTION_CONFLICT", envelope.message_id, `Conflict ${payload.conflict_id} already has an accepted resolution`)];
        }
        if (!this.isAuthorizedResolver(conflict, envelope.sender.principal_id)) {
            return [this.makeProtocolError("AUTHORIZATION_FAILED", envelope.message_id, `Principal ${envelope.sender.principal_id} is not authorized to resolve conflict ${payload.conflict_id}`)];
        }
        const outcome = (payload.outcome ?? {});
        const rejected = Array.isArray(outcome.rejected) ? outcome.rejected : [];
        const committedRejections = rejected.filter((id) => {
            const op = this.operations.get(id);
            return op?.stateMachine.currentState === OperationState.COMMITTED;
        });
        if (committedRejections.length > 0 && !outcome.rollback) {
            return [this.makeProtocolError("MALFORMED_MESSAGE", envelope.message_id, "Resolutions rejecting committed operations must declare outcome.rollback")];
        }
        if (payload.decision === "dismissed") {
            if (conflict.stateMachine.currentState === ConflictState.OPEN ||
                conflict.stateMachine.currentState === ConflictState.ACKED ||
                conflict.stateMachine.currentState === ConflictState.ESCALATED) {
                conflict.stateMachine.transition("DISMISSED");
            }
        }
        else {
            if (conflict.stateMachine.currentState === ConflictState.OPEN)
                conflict.stateMachine.transition("ACKED");
            if (conflict.stateMachine.currentState === ConflictState.ACKED) {
                conflict.stateMachine.transition("RESOLVED");
                conflict.stateMachine.transition("CLOSED");
            }
            else if (conflict.stateMachine.currentState === ConflictState.ESCALATED) {
                conflict.stateMachine.transition("RESOLVED");
                conflict.stateMachine.transition("CLOSED");
            }
        }
        conflict.resolution_id = payload.resolution_id ?? uuidv4();
        conflict.resolved_by = envelope.sender.principal_id;
        return [];
    }
    cascadeIntentTermination(intentId) {
        const intent = this.intents.get(intentId);
        if (!intent)
            return [];
        const responses = [];
        for (const operation of this.operations.values()) {
            if (operation.intent_id !== intentId)
                continue;
            if (operation.stateMachine.currentState === OperationState.PROPOSED) {
                operation.stateMachine.transition("REJECTED");
                responses.push(this.makeOpReject(operation.op_id, "intent_terminated", intent.last_message_id));
            }
            else if (operation.stateMachine.currentState === OperationState.FROZEN) {
                operation.stateMachine.transition("REJECTED");
                responses.push(this.makeOpReject(operation.op_id, "intent_terminated", intent.last_message_id));
            }
        }
        return responses;
    }
    checkAutoDismiss() {
        const responses = [];
        for (const conflict of this.conflicts.values()) {
            if (conflict.stateMachine.isTerminal())
                continue;
            const allIntentsTerminal = conflict.related_intents.every((intentId) => {
                const intent = this.intents.get(intentId);
                return !intent || intent.stateMachine.isTerminal();
            });
            if (!allIntentsTerminal)
                continue;
            let hasCommitted = false;
            let allOpsTerminal = true;
            for (const opId of conflict.related_ops) {
                const operation = this.operations.get(opId);
                if (!operation)
                    continue;
                if (operation.stateMachine.currentState === OperationState.COMMITTED) {
                    hasCommitted = true;
                    break;
                }
                if (![OperationState.REJECTED, OperationState.ABANDONED, OperationState.SUPERSEDED].includes(operation.stateMachine.currentState)) {
                    allOpsTerminal = false;
                    break;
                }
            }
            if (hasCommitted || !allOpsTerminal)
                continue;
            conflict.stateMachine.transition("DISMISSED");
            conflict.resolution_id = uuidv4();
            conflict.resolved_by = this.coordinatorId;
            responses.push(this.makeEnvelope(MessageType.RESOLUTION, {
                resolution_id: conflict.resolution_id,
                conflict_id: conflict.conflict_id,
                decision: "dismissed",
                rationale: "all_related_entities_terminated",
            }));
        }
        return responses;
    }
    handleParticipantUnavailable(principalId) {
        const responses = [
            this.makeEnvelope(MessageType.PROTOCOL_ERROR, {
                error_code: "PARTICIPANT_UNAVAILABLE",
                refers_to: principalId,
                description: `Participant ${principalId} is unavailable (no heartbeat for >${this.unavailabilityTimeoutMs / 1000}s)`,
            }),
        ];
        for (const intent of this.intents.values()) {
            if (intent.principal_id !== principalId)
                continue;
            if (intent.stateMachine.currentState === IntentState.ACTIVE) {
                intent.stateMachine.transition("SUSPENDED");
                for (const operation of this.operations.values()) {
                    if (operation.intent_id === intent.intent_id && operation.stateMachine.currentState === OperationState.PROPOSED) {
                        operation.stateMachine.transition("FROZEN");
                    }
                }
            }
        }
        for (const operation of this.operations.values()) {
            if (operation.principal_id !== principalId)
                continue;
            if (operation.stateMachine.currentState === OperationState.PROPOSED) {
                operation.stateMachine.transition("ABANDONED");
            }
            else if (operation.stateMachine.currentState === OperationState.FROZEN) {
                operation.stateMachine.transition("ABANDONED");
            }
        }
        return responses;
    }
    makeEnvelope(messageType, payload) {
        return createEnvelope(messageType, this.sessionId, {
            principal_id: this.coordinatorId,
            principal_type: "service",
            sender_instance_id: this.coordinatorInstanceId,
        }, Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined)), this.lamportClock.createWatermark(), this.coordinatorEpoch);
    }
    makeOpReject(opId, reason, refersTo) {
        return this.makeEnvelope(MessageType.OP_REJECT, {
            op_id: opId,
            reason,
            refers_to: refersTo,
        });
    }
    makeBatchReject(batchId, rejectedOps, reason) {
        return this.makeEnvelope(MessageType.OP_REJECT, {
            op_id: batchId,
            reason,
            rejected_ops: rejectedOps,
        });
    }
    makeProtocolError(errorCode, refersTo, description) {
        return this.makeEnvelope(MessageType.PROTOCOL_ERROR, {
            error_code: errorCode,
            refers_to: refersTo,
            description,
        });
    }
    rememberMessageId(messageId) {
        this.recentMessageIds.push(messageId);
        if (this.recentMessageIds.length > 200) {
            this.recentMessageIds = this.recentMessageIds.slice(-200);
        }
    }
    recordSenderFrontier(envelope) {
        const key = `${envelope.sender.principal_id}|${envelope.sender.sender_instance_id}`;
        let lamportValue;
        if (envelope.watermark) {
            lamportValue = envelope.watermark.kind === "lamport_clock"
                ? Number(envelope.watermark.value)
                : envelope.watermark.lamport_value;
        }
        this.senderFrontier[key] = {
            last_ts: envelope.ts,
            last_lamport: lamportValue,
        };
    }
    buildOperation(payload, principalId, state, batchId) {
        const stateMachine = new OperationStateMachine();
        if (state === OperationState.COMMITTED)
            stateMachine.transition("COMMITTED");
        else if (state === OperationState.REJECTED)
            stateMachine.transition("REJECTED");
        else if (state === OperationState.ABANDONED)
            stateMachine.transition("ABANDONED");
        else if (state === OperationState.FROZEN)
            stateMachine.transition("FROZEN");
        return {
            op_id: payload.op_id,
            intent_id: payload.intent_id ?? "",
            principal_id: principalId,
            target: payload.target ?? "",
            op_kind: payload.op_kind ?? "",
            stateMachine,
            state_ref_before: payload.state_ref_before,
            state_ref_after: payload.state_ref_after,
            batch_id: batchId,
            created_at: Date.now(),
        };
    }
    registerOperationFromPayload(payload, principalId, state, batchId) {
        const operation = this.buildOperation(payload, principalId, state, batchId);
        this.operations.set(operation.op_id, operation);
        this.trackOperationConflicts(operation.intent_id, operation.op_id);
        return operation;
    }
    commitOperationEntry(payload, principalId, batchId) {
        const opId = payload.op_id;
        let operation = this.operations.get(opId);
        if (!operation) {
            operation = this.registerOperationFromPayload(payload, principalId, OperationState.COMMITTED, batchId);
        }
        else {
            operation.intent_id = payload.intent_id ?? operation.intent_id;
            operation.target = payload.target ?? operation.target;
            operation.op_kind = payload.op_kind ?? operation.op_kind;
            operation.state_ref_before = payload.state_ref_before;
            operation.state_ref_after = payload.state_ref_after;
            if (operation.stateMachine.currentState === OperationState.PROPOSED) {
                operation.stateMachine.transition("COMMITTED");
            }
        }
        this.trackOperationConflicts(operation.intent_id, opId);
        return operation;
    }
    validateOperationAgainstIntent(operation, persist = true) {
        const intent = this.intents.get(operation.intent_id);
        if (!intent)
            return [];
        if (intent.stateMachine.isTerminal()) {
            if (persist && operation.stateMachine.currentState === OperationState.PROPOSED) {
                operation.stateMachine.transition("REJECTED");
            }
            return [this.makeOpReject(operation.op_id, "intent_terminated", intent.last_message_id)];
        }
        if (intent.stateMachine.currentState === IntentState.SUSPENDED) {
            if (persist && operation.stateMachine.currentState === OperationState.PROPOSED) {
                operation.stateMachine.transition("FROZEN");
            }
        }
        return [];
    }
    authorizeOperation(operation, batchId) {
        if (operation.authorized_at !== undefined)
            return [];
        operation.authorized_at = Date.now();
        operation.authorized_by = this.coordinatorId;
        const openConflicts = [...this.conflicts.values()].filter((c) => c.stateMachine.currentState !== ConflictState.CLOSED && c.stateMachine.currentState !== ConflictState.DISMISSED).length;
        return [this.makeEnvelope(MessageType.COORDINATOR_STATUS, {
                event: "authorization",
                coordinator_id: this.coordinatorId,
                session_health: openConflicts === 0 ? "healthy" : "degraded",
                authorized_op_id: operation.op_id,
                authorized_batch_id: batchId,
                authorized_by: operation.authorized_by,
            })];
    }
    trackOperationConflicts(intentId, opId) {
        if (!intentId)
            return;
        for (const conflict of this.conflicts.values()) {
            if ((conflict.intent_a === intentId || conflict.intent_b === intentId) && !conflict.related_ops.includes(opId)) {
                conflict.related_ops.push(opId);
            }
        }
    }
    /**
     * Check whether a scope overlaps with a conflict whose scope has been frozen.
     *
     * Per Section 18.6.2, scopes enter frozen state only after resolution_timeout_sec
     * expires (via checkResolutionTimeouts), NOT immediately on conflict creation.
     */
    isScopeFrozen(scope) {
        for (const conflict of this.conflicts.values()) {
            if (conflict.stateMachine.isTerminal())
                continue;
            if (!conflict.scope_frozen)
                continue;
            const intentA = this.intents.get(conflict.intent_a);
            const intentB = this.intents.get(conflict.intent_b);
            if ((intentA && scopeOverlap(scope, intentA.scope)) || (intentB && scopeOverlap(scope, intentB.scope))) {
                return conflict;
            }
        }
        return undefined;
    }
    /**
     * For INTENT_ANNOUNCE: distinguish full containment (MUST reject) from partial overlap (SHOULD accept with warning).
     * Per Section 18.6.2.
     */
    checkFrozenScopeForIntent(scope) {
        for (const conflict of this.conflicts.values()) {
            if (conflict.stateMachine.isTerminal())
                continue;
            if (!conflict.scope_frozen)
                continue;
            const intentA = this.intents.get(conflict.intent_a);
            const intentB = this.intents.get(conflict.intent_b);
            const overlapsA = intentA ? scopeOverlap(scope, intentA.scope) : false;
            const overlapsB = intentB ? scopeOverlap(scope, intentB.scope) : false;
            if (!overlapsA && !overlapsB)
                continue;
            // Build union scope of frozen conflict's intents
            const unionScope = this.buildFrozenUnionScope(intentA, intentB);
            if (unionScope && scopeContains(unionScope, scope)) {
                return { action: "reject", conflict };
            }
            else {
                return { action: "warn", conflict };
            }
        }
        return { action: null };
    }
    buildFrozenUnionScope(intentA, intentB) {
        const scopes = [];
        if (intentA)
            scopes.push(intentA.scope);
        if (intentB)
            scopes.push(intentB.scope);
        if (scopes.length === 0)
            return undefined;
        if (scopes.length === 1)
            return scopes[0];
        const [a, b] = scopes;
        if (a.kind !== b.kind)
            return a; // Conservative fallback
        switch (a.kind) {
            case ScopeKind.FILE_SET: {
                const resources = [...new Set([...(a.resources ?? []), ...(b.resources ?? [])])];
                return { kind: ScopeKind.FILE_SET, resources };
            }
            case ScopeKind.ENTITY_SET: {
                const entities = [...new Set([...(a.entities ?? []), ...(b.entities ?? [])])];
                return { kind: ScopeKind.ENTITY_SET, entities };
            }
            case ScopeKind.TASK_SET: {
                const task_ids = [...new Set([...(a.task_ids ?? []), ...(b.task_ids ?? [])])];
                return { kind: ScopeKind.TASK_SET, task_ids };
            }
        }
        return a;
    }
    detectScopeOverlaps(intent, skipExistingConflicts = false) {
        const responses = [];
        for (const other of this.intents.values()) {
            if (other.intent_id === intent.intent_id)
                continue;
            if (other.stateMachine.currentState !== IntentState.ACTIVE && other.stateMachine.currentState !== IntentState.SUSPENDED)
                continue;
            if (!scopeOverlap(intent.scope, other.scope))
                continue;
            if (skipExistingConflicts) {
                const existing = [...this.conflicts.values()].some((conflict) => {
                    if (conflict.stateMachine.isTerminal())
                        return false;
                    return ((conflict.intent_a === intent.intent_id && conflict.intent_b === other.intent_id) ||
                        (conflict.intent_b === intent.intent_id && conflict.intent_a === other.intent_id));
                });
                if (existing)
                    continue;
            }
            const conflictId = uuidv4();
            this.conflicts.set(conflictId, {
                conflict_id: conflictId,
                category: ConflictCategory.SCOPE_OVERLAP,
                severity: Severity.MEDIUM,
                principal_a: intent.principal_id,
                principal_b: other.principal_id,
                intent_a: intent.intent_id,
                intent_b: other.intent_id,
                stateMachine: new ConflictStateMachine(),
                related_intents: [intent.intent_id, other.intent_id],
                related_ops: [],
                created_at: Date.now(),
                scope_frozen: false,
            });
            responses.push(this.makeEnvelope(MessageType.CONFLICT_REPORT, {
                conflict_id: conflictId,
                category: ConflictCategory.SCOPE_OVERLAP,
                severity: Severity.MEDIUM,
                involved_principals: [intent.principal_id, other.principal_id],
                principal_a: intent.principal_id,
                principal_b: other.principal_id,
                intent_a: intent.intent_id,
                intent_b: other.intent_id,
            }));
        }
        return responses;
    }
    handleOwnerRejoin(principalId) {
        const responses = [];
        for (const claim of [...this.claims.values()]) {
            if (claim.original_principal_id === principalId && claim.decision === "pending") {
                responses.push(...this.withdrawClaim(claim, "original_owner_rejoined"));
            }
        }
        for (const intent of this.intents.values()) {
            if (intent.principal_id !== principalId)
                continue;
            if (intent.stateMachine.currentState === IntentState.SUSPENDED && !intent.claimed_by) {
                intent.stateMachine.transition("ACTIVE");
                for (const operation of this.operations.values()) {
                    if (operation.intent_id === intent.intent_id && operation.stateMachine.currentState === OperationState.FROZEN) {
                        operation.stateMachine.transition("PROPOSED");
                    }
                }
            }
        }
        return responses;
    }
    findArbiter() {
        for (const [principalId, info] of this.participants.entries()) {
            if (!info.is_available)
                continue;
            if ((info.principal.roles ?? []).includes("arbiter"))
                return principalId;
        }
        return undefined;
    }
    findClaimApprover(claimerPrincipalId) {
        for (const [principalId, info] of this.participants.entries()) {
            if (principalId === claimerPrincipalId || !info.is_available)
                continue;
            const roles = new Set((info.principal.roles ?? []).map(String));
            if (roles.has("owner") || roles.has("arbiter"))
                return principalId;
        }
        return undefined;
    }
    approveClaim(claim, approvedBy) {
        const original = this.intents.get(claim.original_intent_id);
        if (!original)
            return this.rejectClaim(claim, "original_intent_missing");
        claim.decision = "approved";
        claim.approved_by = approvedBy;
        original.claimed_by = claim.claimer_principal_id;
        if (original.stateMachine.currentState === IntentState.SUSPENDED) {
            original.stateMachine.transition("TRANSFERRED");
        }
        const stateMachine = new IntentStateMachine();
        stateMachine.transition("ACTIVE");
        const newIntent = {
            intent_id: claim.new_intent_id,
            principal_id: claim.claimer_principal_id,
            objective: claim.objective,
            scope: claim.scope,
            stateMachine,
            received_at: Date.now(),
            last_message_id: claim.claim_id,
        };
        this.intents.set(newIntent.intent_id, newIntent);
        this.claims.delete(claim.original_intent_id);
        const responses = [
            this.makeEnvelope(MessageType.INTENT_CLAIM_STATUS, {
                claim_id: claim.claim_id,
                original_intent_id: claim.original_intent_id,
                new_intent_id: claim.new_intent_id,
                decision: "approved",
                approved_by: approvedBy,
            }),
        ];
        responses.push(...this.cascadeIntentTermination(claim.original_intent_id));
        responses.push(...this.detectScopeOverlaps(newIntent));
        return responses;
    }
    rejectClaim(claim, reason) {
        claim.decision = "rejected";
        this.claims.delete(claim.original_intent_id);
        return [this.makeEnvelope(MessageType.INTENT_CLAIM_STATUS, {
                claim_id: claim.claim_id,
                original_intent_id: claim.original_intent_id,
                decision: "rejected",
                reason,
            })];
    }
    withdrawClaim(claim, reason) {
        const original = this.intents.get(claim.original_intent_id);
        if (original && original.stateMachine.currentState === IntentState.SUSPENDED) {
            original.claimed_by = undefined;
            original.stateMachine.transition("ACTIVE");
            for (const operation of this.operations.values()) {
                if (operation.intent_id === original.intent_id && operation.stateMachine.currentState === OperationState.FROZEN) {
                    operation.stateMachine.transition("PROPOSED");
                }
            }
        }
        claim.decision = "withdrawn";
        this.claims.delete(claim.original_intent_id);
        return [this.makeEnvelope(MessageType.INTENT_CLAIM_STATUS, {
                claim_id: claim.claim_id,
                original_intent_id: claim.original_intent_id,
                decision: "withdrawn",
                reason,
            })];
    }
    checkPendingClaims(nowMs = Date.now()) {
        const responses = [];
        for (const claim of [...this.claims.values()]) {
            if (claim.decision !== "pending")
                continue;
            const original = this.intents.get(claim.original_intent_id);
            if (!original) {
                responses.push(...this.rejectClaim(claim, "original_intent_missing"));
                continue;
            }
            if (original.stateMachine.currentState !== IntentState.SUSPENDED) {
                responses.push(...this.rejectClaim(claim, "intent_no_longer_suspended"));
                continue;
            }
            if (this.complianceProfile === ComplianceProfile.GOVERNANCE) {
                const approver = this.findClaimApprover(claim.claimer_principal_id);
                if (!approver)
                    continue;
                responses.push(...this.approveClaim(claim, approver));
                continue;
            }
            if (nowMs - claim.submitted_at >= this.intentClaimGraceMs) {
                responses.push(...this.approveClaim(claim));
            }
        }
        return responses;
    }
    evaluateRolePolicy(principalId, principalType, requestedRoles) {
        if (!this.rolePolicy) {
            if (this.securityProfile === SecurityProfile.OPEN || this.securityProfile === "open") {
                return requestedRoles;
            }
            // Authenticated/Verified without a role policy is a configuration error
            // (Section 23.1.5: "a role policy MUST be defined")
            // Return empty to signal rejection; caller handles the error
            return [];
        }
        const defaultRole = this.rolePolicy.default_role ?? "participant";
        const assignments = this.rolePolicy.role_assignments ?? {};
        const constraints = this.rolePolicy.role_constraints ?? {};
        const allowed = new Set(assignments[principalId] ?? [defaultRole]);
        const granted = [];
        for (const role of requestedRoles) {
            if (!allowed.has(role))
                continue;
            const constraint = constraints[role];
            if (constraint) {
                const allowedTypes = constraint.allowed_principal_types;
                if (allowedTypes && !allowedTypes.includes(principalType))
                    continue;
                const maxCount = constraint.max_count;
                if (maxCount !== undefined) {
                    let currentCount = 0;
                    for (const p of this.participants.values()) {
                        if (p.principal.principal_id !== principalId && p.principal.roles?.includes(role))
                            currentCount++;
                    }
                    if (currentCount >= maxCount)
                        continue;
                }
            }
            granted.push(role);
        }
        return granted.length > 0 ? granted : [defaultRole];
    }
    isAuthorizedResolver(conflict, principalId) {
        if (principalId === this.coordinatorId)
            return true;
        const participant = this.participants.get(principalId);
        const roles = new Set((participant?.principal.roles ?? []).map(String));
        if (conflict.stateMachine.currentState === ConflictState.ESCALATED) {
            return principalId === conflict.escalated_to || roles.has("arbiter");
        }
        // Pre-escalation: only owner or arbiter roles may resolve; being a related
        // principal (contributor) is not sufficient per SPEC Section 18.4 / 23.1.3
        return roles.has("owner") || roles.has("arbiter");
    }
    recoverFromSnapshot(snapshotData) {
        this.lamportClock = new LamportClock(snapshotData.lamport_clock ?? 0);
        this.sessionClosed = snapshotData.session_closed ?? false;
        this.coordinatorEpoch = Number(snapshotData.coordinator_epoch ?? 1) + 1;
        this.coordinatorInstanceId = `${this.coordinatorId}:epoch-${this.coordinatorEpoch}`;
        this.recentMessageIds = [...(snapshotData.anti_replay?.recent_message_ids ?? [])];
        this.seenMessageIds = new Set(this.recentMessageIds);
        this.senderFrontier = { ...(snapshotData.anti_replay?.sender_frontier ?? {}) };
        this.participants.clear();
        for (const participant of snapshotData.participants ?? []) {
            this.participants.set(participant.principal_id, {
                principal: {
                    principal_id: participant.principal_id,
                    principal_type: participant.principal_type ?? "agent",
                    display_name: participant.display_name,
                    roles: participant.roles ?? ["participant"],
                    capabilities: participant.capabilities ?? [],
                },
                last_seen: participant.last_seen ? new Date(participant.last_seen).getTime() : Date.now(),
                status: participant.status ?? "idle",
                is_available: participant.is_available ?? true,
                backend_model_id: participant.backend_model_id,
                backend_provider: participant.backend_provider,
                backend_provider_status: participant.backend_provider_status ?? "unknown",
            });
        }
        this.intents.clear();
        for (const intentData of snapshotData.intents ?? []) {
            const stateMachine = new IntentStateMachine();
            const targetState = intentData.state;
            if (targetState === "ACTIVE")
                stateMachine.transition("ACTIVE");
            else if (targetState === "EXPIRED") {
                stateMachine.transition("ACTIVE");
                stateMachine.transition("EXPIRED");
            }
            else if (targetState === "WITHDRAWN") {
                stateMachine.transition("ACTIVE");
                stateMachine.transition("WITHDRAWN");
            }
            else if (targetState === "SUPERSEDED") {
                stateMachine.transition("ACTIVE");
                stateMachine.transition("SUPERSEDED");
            }
            else if (targetState === "SUSPENDED") {
                stateMachine.transition("ACTIVE");
                stateMachine.transition("SUSPENDED");
            }
            else if (targetState === "TRANSFERRED") {
                stateMachine.transition("ACTIVE");
                stateMachine.transition("TRANSFERRED");
            }
            this.intents.set(intentData.intent_id, {
                intent_id: intentData.intent_id,
                principal_id: intentData.principal_id ?? "",
                objective: intentData.objective ?? "",
                scope: intentData.scope ?? { kind: "file_set" },
                stateMachine,
                received_at: intentData.received_at ? new Date(intentData.received_at).getTime() : Date.now(),
                ttl_sec: intentData.ttl_sec,
                expires_at: intentData.expires_at ? new Date(intentData.expires_at).getTime() : undefined,
                last_message_id: intentData.last_message_id,
                claimed_by: intentData.claimed_by,
            });
        }
        this.operations.clear();
        for (const opData of snapshotData.operations ?? []) {
            const stateMachine = new OperationStateMachine();
            const targetState = opData.state;
            if (targetState === "COMMITTED")
                stateMachine.transition("COMMITTED");
            else if (targetState === "REJECTED")
                stateMachine.transition("REJECTED");
            else if (targetState === "ABANDONED")
                stateMachine.transition("ABANDONED");
            else if (targetState === "FROZEN")
                stateMachine.transition("FROZEN");
            else if (targetState === "SUPERSEDED") {
                stateMachine.transition("COMMITTED");
                stateMachine.transition("SUPERSEDED");
            }
            this.operations.set(opData.op_id, {
                op_id: opData.op_id,
                intent_id: opData.intent_id ?? "",
                principal_id: opData.principal_id ?? "",
                target: opData.target ?? "",
                op_kind: opData.op_kind ?? "",
                stateMachine,
                state_ref_before: opData.state_ref_before,
                state_ref_after: opData.state_ref_after,
                batch_id: opData.batch_id,
                authorized_at: opData.authorized_at ? new Date(opData.authorized_at).getTime() : undefined,
                authorized_by: opData.authorized_by,
                created_at: opData.created_at ? new Date(opData.created_at).getTime() : Date.now(),
            });
        }
        this.conflicts.clear();
        for (const conflictData of snapshotData.conflicts ?? []) {
            const stateMachine = new ConflictStateMachine();
            const targetState = conflictData.state;
            if (targetState === "ACKED")
                stateMachine.transition("ACKED");
            else if (targetState === "ESCALATED") {
                stateMachine.transition("ACKED");
                stateMachine.transition("ESCALATED");
            }
            else if (targetState === "RESOLVED") {
                stateMachine.transition("ACKED");
                stateMachine.transition("RESOLVED");
            }
            else if (targetState === "CLOSED") {
                stateMachine.transition("ACKED");
                stateMachine.transition("RESOLVED");
                stateMachine.transition("CLOSED");
            }
            else if (targetState === "DISMISSED")
                stateMachine.transition("DISMISSED");
            this.conflicts.set(conflictData.conflict_id, {
                conflict_id: conflictData.conflict_id,
                category: conflictData.category ?? ConflictCategory.SCOPE_OVERLAP,
                severity: conflictData.severity ?? Severity.MEDIUM,
                principal_a: conflictData.principal_a ?? "",
                principal_b: conflictData.principal_b ?? "",
                intent_a: conflictData.intent_a ?? "",
                intent_b: conflictData.intent_b ?? "",
                stateMachine,
                related_intents: conflictData.related_intents ?? [],
                related_ops: conflictData.related_ops ?? [],
                created_at: conflictData.created_at ? new Date(conflictData.created_at).getTime() : Date.now(),
                escalated_to: conflictData.escalated_to,
                escalated_at: conflictData.escalated_at ? new Date(conflictData.escalated_at).getTime() : undefined,
                resolution_id: conflictData.resolution_id,
                resolved_by: conflictData.resolved_by,
                scope_frozen: conflictData.scope_frozen ?? false,
            });
        }
        this.claims.clear();
        this.claimIndex.clear();
        for (const claimData of snapshotData.pending_claims ?? []) {
            const claim = {
                claim_id: claimData.claim_id,
                original_intent_id: claimData.original_intent_id,
                original_principal_id: claimData.original_principal_id ?? "",
                new_intent_id: claimData.new_intent_id,
                claimer_principal_id: claimData.claimer_principal_id,
                objective: claimData.objective ?? "",
                scope: claimData.scope ?? { kind: "file_set" },
                justification: claimData.justification,
                submitted_at: claimData.submitted_at ? new Date(claimData.submitted_at).getTime() : Date.now(),
                decision: claimData.decision ?? "pending",
                approved_by: claimData.approved_by,
            };
            this.claims.set(claim.original_intent_id, claim);
            this.claimIndex.set(claim.claim_id, claim);
        }
    }
    replayAuditLog(messages) {
        const responses = [];
        for (const message of messages) {
            responses.push(...this.processMessage(message));
        }
        return responses;
    }
    getAuditLog() {
        return [...this.auditLog];
    }
    closeSession(reason = "manual") {
        if (this.sessionClosed)
            return [];
        this.sessionClosed = true;
        for (const intent of this.intents.values()) {
            if (!intent.stateMachine.isTerminal() && intent.stateMachine.currentState !== IntentState.ANNOUNCED) {
                try {
                    intent.stateMachine.transition("WITHDRAWN");
                }
                catch { }
            }
        }
        for (const operation of this.operations.values()) {
            if (operation.stateMachine.currentState === OperationState.PROPOSED || operation.stateMachine.currentState === OperationState.FROZEN) {
                try {
                    operation.stateMachine.transition("ABANDONED");
                }
                catch { }
            }
        }
        return [this.makeEnvelope(MessageType.SESSION_CLOSE, {
                reason,
                final_lamport_clock: this.lamportClock.value,
                summary: this.buildSessionSummary(),
                active_intents_disposition: "withdraw_all",
            })];
    }
    checkAutoClose() {
        if (this.sessionClosed || this.intents.size === 0)
            return [];
        for (const intent of this.intents.values()) {
            if (!intent.stateMachine.isTerminal())
                return [];
        }
        for (const operation of this.operations.values()) {
            if (operation.stateMachine.currentState === OperationState.PROPOSED || operation.stateMachine.currentState === OperationState.FROZEN)
                return [];
        }
        for (const conflict of this.conflicts.values()) {
            if (conflict.stateMachine.currentState !== ConflictState.CLOSED && conflict.stateMachine.currentState !== ConflictState.DISMISSED)
                return [];
        }
        return this.closeSession("completed");
    }
    coordinatorStatus(event = "heartbeat") {
        const openConflicts = [...this.conflicts.values()].filter((conflict) => conflict.stateMachine.currentState !== ConflictState.CLOSED && conflict.stateMachine.currentState !== ConflictState.DISMISSED).length;
        const activeParticipants = [...this.participants.values()].filter((participant) => participant.is_available).length;
        return [this.makeEnvelope(MessageType.COORDINATOR_STATUS, {
                event,
                coordinator_id: this.coordinatorId,
                session_health: openConflicts === 0 ? "healthy" : "degraded",
                active_participants: activeParticipants,
                open_conflicts: openConflicts,
                snapshot_lamport_clock: this.lamportClock.value,
            })];
    }
    snapshot() {
        return {
            snapshot_version: 2,
            session_id: this.sessionId,
            protocol_version: PROTOCOL_VERSION,
            captured_at: new Date().toISOString(),
            coordinator_epoch: this.coordinatorEpoch,
            lamport_clock: this.lamportClock.value,
            anti_replay: {
                replay_window_sec: 300,
                recent_message_ids: [...this.recentMessageIds],
                sender_frontier: { ...this.senderFrontier },
            },
            participants: [...this.participants.values()].map((info) => ({
                principal_id: info.principal.principal_id,
                principal_type: info.principal.principal_type,
                display_name: info.principal.display_name,
                roles: info.principal.roles,
                capabilities: info.principal.capabilities,
                status: info.status,
                is_available: info.is_available,
                last_seen: new Date(info.last_seen).toISOString(),
            })),
            intents: [...this.intents.values()].map((intent) => ({
                intent_id: intent.intent_id,
                principal_id: intent.principal_id,
                objective: intent.objective,
                state: intent.stateMachine.currentState,
                scope: intent.scope,
                received_at: new Date(intent.received_at).toISOString(),
                ttl_sec: intent.ttl_sec,
                expires_at: intent.expires_at ? new Date(intent.expires_at).toISOString() : null,
                last_message_id: intent.last_message_id,
                claimed_by: intent.claimed_by,
            })),
            operations: [...this.operations.values()].map((operation) => ({
                op_id: operation.op_id,
                intent_id: operation.intent_id,
                principal_id: operation.principal_id,
                state: operation.stateMachine.currentState,
                target: operation.target,
                op_kind: operation.op_kind,
                state_ref_before: operation.state_ref_before,
                state_ref_after: operation.state_ref_after,
                batch_id: operation.batch_id,
                authorized_at: operation.authorized_at ? new Date(operation.authorized_at).toISOString() : null,
                authorized_by: operation.authorized_by,
                created_at: new Date(operation.created_at).toISOString(),
            })),
            conflicts: [...this.conflicts.values()].map((conflict) => ({
                conflict_id: conflict.conflict_id,
                category: conflict.category,
                severity: conflict.severity,
                principal_a: conflict.principal_a,
                principal_b: conflict.principal_b,
                intent_a: conflict.intent_a,
                intent_b: conflict.intent_b,
                state: conflict.stateMachine.currentState,
                related_intents: conflict.related_intents,
                related_ops: conflict.related_ops,
                created_at: new Date(conflict.created_at).toISOString(),
                escalated_to: conflict.escalated_to,
                escalated_at: conflict.escalated_at ? new Date(conflict.escalated_at).toISOString() : null,
                resolution_id: conflict.resolution_id,
                resolved_by: conflict.resolved_by,
                scope_frozen: conflict.scope_frozen,
            })),
            pending_claims: [...this.claims.values()].map((claim) => ({
                claim_id: claim.claim_id,
                original_intent_id: claim.original_intent_id,
                original_principal_id: claim.original_principal_id,
                new_intent_id: claim.new_intent_id,
                claimer_principal_id: claim.claimer_principal_id,
                objective: claim.objective,
                scope: claim.scope,
                justification: claim.justification,
                submitted_at: new Date(claim.submitted_at).toISOString(),
                decision: claim.decision,
                approved_by: claim.approved_by,
            })),
            session_closed: this.sessionClosed,
        };
    }
    buildSessionSummary() {
        // Intent breakdown (Section 9.6.2)
        let completedIntents = 0, expiredIntents = 0, withdrawnIntents = 0;
        for (const intent of this.intents.values()) {
            const st = intent.stateMachine.currentState;
            if (st === IntentState.EXPIRED)
                expiredIntents++;
            else if (st === IntentState.WITHDRAWN)
                withdrawnIntents++;
            else if (st === IntentState.SUPERSEDED || st === IntentState.TRANSFERRED)
                completedIntents++;
        }
        // Operation breakdown
        let committedOps = 0, rejectedOps = 0, abandonedOps = 0;
        for (const op of this.operations.values()) {
            const st = op.stateMachine.currentState;
            if (st === OperationState.COMMITTED)
                committedOps++;
            else if (st === OperationState.REJECTED)
                rejectedOps++;
            else if (st === OperationState.ABANDONED)
                abandonedOps++;
        }
        // Conflict breakdown
        let resolvedConflicts = 0;
        for (const c of this.conflicts.values()) {
            if (c.stateMachine.currentState === ConflictState.RESOLVED || c.stateMachine.currentState === ConflictState.CLOSED) {
                resolvedConflicts++;
            }
        }
        return {
            total_intents: this.intents.size,
            completed_intents: completedIntents,
            expired_intents: expiredIntents,
            withdrawn_intents: withdrawnIntents,
            total_operations: this.operations.size,
            committed_operations: committedOps,
            rejected_operations: rejectedOps,
            abandoned_operations: abandonedOps,
            total_conflicts: this.conflicts.size,
            resolved_conflicts: resolvedConflicts,
            total_participants: this.participants.size,
            duration_sec: Math.floor((Date.now() - this.sessionStartedAt) / 1000),
        };
    }
    getParticipant(id) { return this.participants.get(id); }
    getIntent(id) { return this.intents.get(id); }
    getOperation(id) { return this.operations.get(id); }
    getConflict(id) { return this.conflicts.get(id); }
    getParticipants() { return [...this.participants.values()]; }
    getIntents() { return [...this.intents.values()]; }
    getOperations() { return [...this.operations.values()]; }
    getConflicts() { return [...this.conflicts.values()]; }
}
//# sourceMappingURL=coordinator.js.map