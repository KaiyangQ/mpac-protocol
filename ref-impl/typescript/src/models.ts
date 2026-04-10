export enum MessageType {
  HELLO = "HELLO",
  SESSION_INFO = "SESSION_INFO",
  HEARTBEAT = "HEARTBEAT",
  GOODBYE = "GOODBYE",
  SESSION_CLOSE = "SESSION_CLOSE",
  COORDINATOR_STATUS = "COORDINATOR_STATUS",
  INTENT_ANNOUNCE = "INTENT_ANNOUNCE",
  INTENT_UPDATE = "INTENT_UPDATE",
  INTENT_WITHDRAW = "INTENT_WITHDRAW",
  INTENT_CLAIM = "INTENT_CLAIM",
  INTENT_CLAIM_STATUS = "INTENT_CLAIM_STATUS",
  OP_PROPOSE = "OP_PROPOSE",
  OP_BATCH_COMMIT = "OP_BATCH_COMMIT",
  OP_COMMIT = "OP_COMMIT",
  OP_REJECT = "OP_REJECT",
  OP_SUPERSEDE = "OP_SUPERSEDE",
  CONFLICT_REPORT = "CONFLICT_REPORT",
  CONFLICT_ACK = "CONFLICT_ACK",
  CONFLICT_ESCALATE = "CONFLICT_ESCALATE",
  RESOLUTION = "RESOLUTION",
  PROTOCOL_ERROR = "PROTOCOL_ERROR",
}

export enum IntentState {
  ANNOUNCED = "ANNOUNCED",
  ACTIVE = "ACTIVE",
  EXPIRED = "EXPIRED",
  WITHDRAWN = "WITHDRAWN",
  SUPERSEDED = "SUPERSEDED",
  SUSPENDED = "SUSPENDED",
  TRANSFERRED = "TRANSFERRED",
}

export enum OperationState {
  PROPOSED = "PROPOSED",
  COMMITTED = "COMMITTED",
  REJECTED = "REJECTED",
  ABANDONED = "ABANDONED",
  FROZEN = "FROZEN",
  SUPERSEDED = "SUPERSEDED",
}

export enum ConflictState {
  OPEN = "OPEN",
  ACKED = "ACKED",
  ESCALATED = "ESCALATED",
  DISMISSED = "DISMISSED",
  RESOLVED = "RESOLVED",
  CLOSED = "CLOSED",
}

export enum ScopeKind {
  FILE_SET = "file_set",
  ENTITY_SET = "entity_set",
  TASK_SET = "task_set",
}

export enum SecurityProfile {
  OPEN = "open",
  AUTHENTICATED = "authenticated",
  VERIFIED = "verified",
}

export enum ComplianceProfile {
  CORE = "core",
  GOVERNANCE = "governance",
  SEMANTIC = "semantic",
}

export enum CredentialType {
  BEARER_TOKEN = "bearer_token",
  MTLS_FINGERPRINT = "mtls_fingerprint",
  API_KEY = "api_key",
  X509_CHAIN = "x509_chain",
  CUSTOM = "custom",
}

export enum CoordinatorEvent {
  HEARTBEAT = "heartbeat",
  RECOVERED = "recovered",
  HANDOVER = "handover",
  ASSUMED = "assumed",
  AUTHORIZATION = "authorization",
  BACKEND_ALERT = "backend_alert",
}

export enum SessionHealth {
  HEALTHY = "healthy",
  DEGRADED = "degraded",
  RECOVERING = "recovering",
}

export enum SessionCloseReason {
  COMPLETED = "completed",
  TIMEOUT = "timeout",
  POLICY = "policy",
  COORDINATOR_SHUTDOWN = "coordinator_shutdown",
  MANUAL = "manual",
}

export enum Role {
  OBSERVER = "observer",
  CONTRIBUTOR = "contributor",
  REVIEWER = "reviewer",
  OWNER = "owner",
  ARBITER = "arbiter",
}

export enum ConflictCategory {
  SCOPE_OVERLAP = "scope_overlap",
  CONCURRENT_WRITE = "concurrent_write",
  SEMANTIC_GOAL_CONFLICT = "semantic_goal_conflict",
  ASSUMPTION_CONTRADICTION = "assumption_contradiction",
  POLICY_VIOLATION = "policy_violation",
  AUTHORITY_CONFLICT = "authority_conflict",
  DEPENDENCY_BREAKAGE = "dependency_breakage",
  RESOURCE_CONTENTION = "resource_contention",
}

export enum Severity {
  INFO = "info",
  LOW = "low",
  MEDIUM = "medium",
  HIGH = "high",
  CRITICAL = "critical",
}

export enum Decision {
  APPROVED = "approved",
  REJECTED = "rejected",
  DISMISSED = "dismissed",
  HUMAN_OVERRIDE = "human_override",
  POLICY_OVERRIDE = "policy_override",
  MERGED = "merged",
}

export enum ErrorCode {
  MALFORMED_MESSAGE = "MALFORMED_MESSAGE",
  UNKNOWN_MESSAGE_TYPE = "UNKNOWN_MESSAGE_TYPE",
  INVALID_REFERENCE = "INVALID_REFERENCE",
  VERSION_MISMATCH = "VERSION_MISMATCH",
  CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED",
  AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED",
  PARTICIPANT_UNAVAILABLE = "PARTICIPANT_UNAVAILABLE",
  RESOLUTION_TIMEOUT = "RESOLUTION_TIMEOUT",
  SCOPE_FROZEN = "SCOPE_FROZEN",
  CLAIM_CONFLICT = "CLAIM_CONFLICT",
  RESOLUTION_CONFLICT = "RESOLUTION_CONFLICT",
  COORDINATOR_CONFLICT = "COORDINATOR_CONFLICT",
  STATE_DIVERGENCE = "STATE_DIVERGENCE",
  SESSION_CLOSED = "SESSION_CLOSED",
  CREDENTIAL_REJECTED = "CREDENTIAL_REJECTED",
  REPLAY_DETECTED = "REPLAY_DETECTED",
  CAUSAL_GAP = "CAUSAL_GAP",
  INTENT_BACKOFF = "INTENT_BACKOFF",
  BACKEND_SWITCH_DENIED = "BACKEND_SWITCH_DENIED",
}

export enum BackendProviderStatus {
  OPERATIONAL = "operational",
  DEGRADED = "degraded",
  DOWN = "down",
  UNKNOWN = "unknown",
}

export enum BackendSwitchReason {
  PROVIDER_DOWN = "provider_down",
  PROVIDER_DEGRADED = "provider_degraded",
  MANUAL = "manual",
  COST_OPTIMIZATION = "cost_optimization",
}

export enum BackendHealthAction {
  IGNORE = "ignore",
  WARN = "warn",
  SUSPEND_AND_CLAIM = "suspend_and_claim",
}

export enum AutoSwitchPolicy {
  ALLOWED = "allowed",
  NOTIFY_FIRST = "notify_first",
  FORBIDDEN = "forbidden",
}

export interface Principal {
  principal_id: string;
  principal_type: string;
  display_name?: string;
  roles?: Array<Role | string>;
  capabilities?: string[];
  joined_at?: string;
}

export interface Sender {
  principal_id: string;
  principal_type: string;
  sender_instance_id: string;
}

export interface Watermark {
  kind: string;
  value: number | Record<string, number> | string;
  lamport_value?: number;
}

export interface Scope {
  kind: ScopeKind | string;
  resources?: string[];
  entities?: string[];
  task_ids?: string[];
  pattern?: string;
  expression?: string;
  language?: string;
  canonical_uris?: string[];
  extensions?: Record<string, unknown>;
}

export interface Basis {
  kind?: string;
  rule_id?: string;
  matcher?: string;
  match_type?: string;
  confidence?: number;
  matched_pair?: {
    left: { source_intent_id: string; content: string };
    right: { source_intent_id: string; content: string };
  };
  explanation?: string;
  intent_id?: string;
  op_id?: string;
  prior_scope?: Scope;
  prior_outcome?: Outcome;
}

export interface Outcome {
  accepted?: string[];
  rejected?: string[];
  merged?: string[];
  rollback?: string;
}

export interface GovernancePolicy {
  require_acknowledgment?: boolean;
  intent_expiry_grace_sec?: number;
}

export interface LivenessPolicy {
  heartbeat_interval_sec?: number;
  unavailability_timeout_sec?: number;
  intent_claim_grace_period_sec?: number;
  resolution_timeout_sec?: number;
}

export interface SessionConfig {
  session_id: string;
  security_profile?: SecurityProfile;
  compliance_profile?: ComplianceProfile;
  execution_model?: "pre_commit" | "post_commit";
  state_ref_format?: string;
  governance_policy?: GovernancePolicy;
  liveness_policy?: LivenessPolicy;
}

export interface HelloPayload {
  display_name?: string;
  roles?: Array<Role | string>;
  capabilities?: string[];
  credential?: Credential;
}

export interface SessionInfoPayload {
  session_id: string;
  protocol_version: string;
  security_profile: SecurityProfile | string;
  compliance_profile: ComplianceProfile | string;
  watermark_kind: string;
  execution_model: "pre_commit" | "post_commit";
  state_ref_format: string;
  governance_policy?: GovernancePolicy;
  liveness_policy?: LivenessPolicy;
  participant_count?: number;
  granted_roles: string[];
  identity_verified?: boolean;
  identity_method?: string;
  compatibility_errors?: string[];
}

export interface IntentAnnouncePayload {
  intent_id: string;
  objective: string;
  scope: Scope;
  ttl_sec?: number;
  expiry_ms?: number;
}

export interface IntentClaimStatusPayload {
  claim_id: string;
  original_intent_id: string;
  new_intent_id?: string;
  decision: "approved" | "rejected" | "withdrawn";
  reason?: string;
  approved_by?: string;
}

export interface OpProposePayload {
  op_id: string;
  intent_id?: string;
  target: string;
  op_kind: string;
  change_ref?: string;
  summary?: string;
}

export interface OpCommitPayload {
  op_id: string;
  intent_id?: string;
  target: string;
  op_kind: string;
  state_ref_before?: string;
  state_ref_after?: string;
  change_ref?: string;
  summary?: string;
}

export interface BatchOperationEntry {
  op_id: string;
  intent_id?: string;
  target: string;
  op_kind: string;
  state_ref_before?: string;
  state_ref_after?: string;
  change_ref?: string;
  summary?: string;
}

export interface OpBatchCommitPayload {
  batch_id: string;
  intent_id?: string;
  atomicity: "all_or_nothing" | "best_effort";
  operations: BatchOperationEntry[];
  summary?: string;
}

export interface ConflictReportPayload {
  conflict_id: string;
  category: ConflictCategory | string;
  severity: Severity | string;
  principal_a?: string;
  principal_b?: string;
  intent_a?: string;
  intent_b?: string;
  involved_principals?: string[];
  scope_a?: Scope;
  scope_b?: Scope;
  basis?: Basis;
  details?: string;
}

export interface ResolutionPayload {
  resolution_id?: string;
  conflict_id: string;
  decision: Decision | string;
  rationale?: string;
  outcome?: Outcome;
}

export interface IntentWithdrawPayload {
  intent_id: string;
  reason?: string;
}

export interface OpRejectPayload {
  op_id: string;
  reason: string;
  refers_to?: string;
  rejected_ops?: string[];
}

export interface ProtocolErrorPayload {
  error_code: ErrorCode | string;
  description: string;
  refers_to?: string;
}

export interface Credential {
  type: string;
  value: string;
  issuer?: string;
  expires_at?: string;
}
