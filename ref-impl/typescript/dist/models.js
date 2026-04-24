export var MessageType;
(function (MessageType) {
    MessageType["HELLO"] = "HELLO";
    MessageType["SESSION_INFO"] = "SESSION_INFO";
    MessageType["HEARTBEAT"] = "HEARTBEAT";
    MessageType["GOODBYE"] = "GOODBYE";
    MessageType["SESSION_CLOSE"] = "SESSION_CLOSE";
    MessageType["COORDINATOR_STATUS"] = "COORDINATOR_STATUS";
    MessageType["INTENT_ANNOUNCE"] = "INTENT_ANNOUNCE";
    MessageType["INTENT_UPDATE"] = "INTENT_UPDATE";
    MessageType["INTENT_WITHDRAW"] = "INTENT_WITHDRAW";
    MessageType["INTENT_CLAIM"] = "INTENT_CLAIM";
    MessageType["INTENT_CLAIM_STATUS"] = "INTENT_CLAIM_STATUS";
    MessageType["OP_PROPOSE"] = "OP_PROPOSE";
    MessageType["OP_BATCH_COMMIT"] = "OP_BATCH_COMMIT";
    MessageType["OP_COMMIT"] = "OP_COMMIT";
    MessageType["OP_REJECT"] = "OP_REJECT";
    MessageType["OP_SUPERSEDE"] = "OP_SUPERSEDE";
    MessageType["CONFLICT_REPORT"] = "CONFLICT_REPORT";
    MessageType["CONFLICT_ACK"] = "CONFLICT_ACK";
    MessageType["CONFLICT_ESCALATE"] = "CONFLICT_ESCALATE";
    MessageType["RESOLUTION"] = "RESOLUTION";
    MessageType["PROTOCOL_ERROR"] = "PROTOCOL_ERROR";
})(MessageType || (MessageType = {}));
export var IntentState;
(function (IntentState) {
    IntentState["ANNOUNCED"] = "ANNOUNCED";
    IntentState["ACTIVE"] = "ACTIVE";
    IntentState["EXPIRED"] = "EXPIRED";
    IntentState["WITHDRAWN"] = "WITHDRAWN";
    IntentState["SUPERSEDED"] = "SUPERSEDED";
    IntentState["SUSPENDED"] = "SUSPENDED";
    IntentState["TRANSFERRED"] = "TRANSFERRED";
})(IntentState || (IntentState = {}));
export var OperationState;
(function (OperationState) {
    OperationState["PROPOSED"] = "PROPOSED";
    OperationState["COMMITTED"] = "COMMITTED";
    OperationState["REJECTED"] = "REJECTED";
    OperationState["ABANDONED"] = "ABANDONED";
    OperationState["FROZEN"] = "FROZEN";
    OperationState["SUPERSEDED"] = "SUPERSEDED";
})(OperationState || (OperationState = {}));
export var ConflictState;
(function (ConflictState) {
    ConflictState["OPEN"] = "OPEN";
    ConflictState["ACKED"] = "ACKED";
    ConflictState["ESCALATED"] = "ESCALATED";
    ConflictState["DISMISSED"] = "DISMISSED";
    ConflictState["RESOLVED"] = "RESOLVED";
    ConflictState["CLOSED"] = "CLOSED";
})(ConflictState || (ConflictState = {}));
export var ScopeKind;
(function (ScopeKind) {
    ScopeKind["FILE_SET"] = "file_set";
    ScopeKind["ENTITY_SET"] = "entity_set";
    ScopeKind["TASK_SET"] = "task_set";
})(ScopeKind || (ScopeKind = {}));
export var SecurityProfile;
(function (SecurityProfile) {
    SecurityProfile["OPEN"] = "open";
    SecurityProfile["AUTHENTICATED"] = "authenticated";
    SecurityProfile["VERIFIED"] = "verified";
})(SecurityProfile || (SecurityProfile = {}));
export var ComplianceProfile;
(function (ComplianceProfile) {
    ComplianceProfile["CORE"] = "core";
    ComplianceProfile["GOVERNANCE"] = "governance";
    ComplianceProfile["SEMANTIC"] = "semantic";
})(ComplianceProfile || (ComplianceProfile = {}));
export var CredentialType;
(function (CredentialType) {
    CredentialType["BEARER_TOKEN"] = "bearer_token";
    CredentialType["MTLS_FINGERPRINT"] = "mtls_fingerprint";
    CredentialType["API_KEY"] = "api_key";
    CredentialType["X509_CHAIN"] = "x509_chain";
    CredentialType["CUSTOM"] = "custom";
})(CredentialType || (CredentialType = {}));
export var CoordinatorEvent;
(function (CoordinatorEvent) {
    CoordinatorEvent["HEARTBEAT"] = "heartbeat";
    CoordinatorEvent["RECOVERED"] = "recovered";
    CoordinatorEvent["HANDOVER"] = "handover";
    CoordinatorEvent["ASSUMED"] = "assumed";
    CoordinatorEvent["AUTHORIZATION"] = "authorization";
    CoordinatorEvent["BACKEND_ALERT"] = "backend_alert";
})(CoordinatorEvent || (CoordinatorEvent = {}));
export var SessionHealth;
(function (SessionHealth) {
    SessionHealth["HEALTHY"] = "healthy";
    SessionHealth["DEGRADED"] = "degraded";
    SessionHealth["RECOVERING"] = "recovering";
})(SessionHealth || (SessionHealth = {}));
export var SessionCloseReason;
(function (SessionCloseReason) {
    SessionCloseReason["COMPLETED"] = "completed";
    SessionCloseReason["TIMEOUT"] = "timeout";
    SessionCloseReason["POLICY"] = "policy";
    SessionCloseReason["COORDINATOR_SHUTDOWN"] = "coordinator_shutdown";
    SessionCloseReason["MANUAL"] = "manual";
})(SessionCloseReason || (SessionCloseReason = {}));
export var Role;
(function (Role) {
    Role["OBSERVER"] = "observer";
    Role["CONTRIBUTOR"] = "contributor";
    Role["REVIEWER"] = "reviewer";
    Role["OWNER"] = "owner";
    Role["ARBITER"] = "arbiter";
})(Role || (Role = {}));
export var ConflictCategory;
(function (ConflictCategory) {
    ConflictCategory["SCOPE_OVERLAP"] = "scope_overlap";
    ConflictCategory["CONCURRENT_WRITE"] = "concurrent_write";
    ConflictCategory["SEMANTIC_GOAL_CONFLICT"] = "semantic_goal_conflict";
    ConflictCategory["ASSUMPTION_CONTRADICTION"] = "assumption_contradiction";
    ConflictCategory["POLICY_VIOLATION"] = "policy_violation";
    ConflictCategory["AUTHORITY_CONFLICT"] = "authority_conflict";
    ConflictCategory["DEPENDENCY_BREAKAGE"] = "dependency_breakage";
    ConflictCategory["RESOURCE_CONTENTION"] = "resource_contention";
})(ConflictCategory || (ConflictCategory = {}));
export var Severity;
(function (Severity) {
    Severity["INFO"] = "info";
    Severity["LOW"] = "low";
    Severity["MEDIUM"] = "medium";
    Severity["HIGH"] = "high";
    Severity["CRITICAL"] = "critical";
})(Severity || (Severity = {}));
export var Decision;
(function (Decision) {
    Decision["APPROVED"] = "approved";
    Decision["REJECTED"] = "rejected";
    Decision["DISMISSED"] = "dismissed";
    Decision["HUMAN_OVERRIDE"] = "human_override";
    Decision["POLICY_OVERRIDE"] = "policy_override";
    Decision["MERGED"] = "merged";
})(Decision || (Decision = {}));
export var ErrorCode;
(function (ErrorCode) {
    ErrorCode["MALFORMED_MESSAGE"] = "MALFORMED_MESSAGE";
    ErrorCode["UNKNOWN_MESSAGE_TYPE"] = "UNKNOWN_MESSAGE_TYPE";
    ErrorCode["INVALID_REFERENCE"] = "INVALID_REFERENCE";
    ErrorCode["VERSION_MISMATCH"] = "VERSION_MISMATCH";
    ErrorCode["CAPABILITY_UNSUPPORTED"] = "CAPABILITY_UNSUPPORTED";
    ErrorCode["AUTHORIZATION_FAILED"] = "AUTHORIZATION_FAILED";
    ErrorCode["PARTICIPANT_UNAVAILABLE"] = "PARTICIPANT_UNAVAILABLE";
    ErrorCode["RESOLUTION_TIMEOUT"] = "RESOLUTION_TIMEOUT";
    ErrorCode["SCOPE_FROZEN"] = "SCOPE_FROZEN";
    ErrorCode["CLAIM_CONFLICT"] = "CLAIM_CONFLICT";
    ErrorCode["RESOLUTION_CONFLICT"] = "RESOLUTION_CONFLICT";
    ErrorCode["COORDINATOR_CONFLICT"] = "COORDINATOR_CONFLICT";
    ErrorCode["STATE_DIVERGENCE"] = "STATE_DIVERGENCE";
    ErrorCode["SESSION_CLOSED"] = "SESSION_CLOSED";
    ErrorCode["CREDENTIAL_REJECTED"] = "CREDENTIAL_REJECTED";
    ErrorCode["REPLAY_DETECTED"] = "REPLAY_DETECTED";
    ErrorCode["CAUSAL_GAP"] = "CAUSAL_GAP";
    ErrorCode["INTENT_BACKOFF"] = "INTENT_BACKOFF";
    ErrorCode["BACKEND_SWITCH_DENIED"] = "BACKEND_SWITCH_DENIED";
})(ErrorCode || (ErrorCode = {}));
export var BackendProviderStatus;
(function (BackendProviderStatus) {
    BackendProviderStatus["OPERATIONAL"] = "operational";
    BackendProviderStatus["DEGRADED"] = "degraded";
    BackendProviderStatus["DOWN"] = "down";
    BackendProviderStatus["UNKNOWN"] = "unknown";
})(BackendProviderStatus || (BackendProviderStatus = {}));
export var BackendSwitchReason;
(function (BackendSwitchReason) {
    BackendSwitchReason["PROVIDER_DOWN"] = "provider_down";
    BackendSwitchReason["PROVIDER_DEGRADED"] = "provider_degraded";
    BackendSwitchReason["MANUAL"] = "manual";
    BackendSwitchReason["COST_OPTIMIZATION"] = "cost_optimization";
})(BackendSwitchReason || (BackendSwitchReason = {}));
export var BackendHealthAction;
(function (BackendHealthAction) {
    BackendHealthAction["IGNORE"] = "ignore";
    BackendHealthAction["WARN"] = "warn";
    BackendHealthAction["SUSPEND_AND_CLAIM"] = "suspend_and_claim";
})(BackendHealthAction || (BackendHealthAction = {}));
export var AutoSwitchPolicy;
(function (AutoSwitchPolicy) {
    AutoSwitchPolicy["ALLOWED"] = "allowed";
    AutoSwitchPolicy["NOTIFY_FIRST"] = "notify_first";
    AutoSwitchPolicy["FORBIDDEN"] = "forbidden";
})(AutoSwitchPolicy || (AutoSwitchPolicy = {}));
//# sourceMappingURL=models.js.map