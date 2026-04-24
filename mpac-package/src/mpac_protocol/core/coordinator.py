"""Session coordinator for MPAC."""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional
import re
import uuid

# RFC 3339 date-time: YYYY-MM-DDThh:mm:ss[.frac](Z | ±HH:MM)
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+\-]\d{2}:\d{2})$"
)

from .envelope import MessageEnvelope
from .models import (
    ComplianceProfile,
    ConflictState,
    IntentState,
    MessageType,
    OperationState,
    Principal,
    Scope,
    Sender,
)
from .scope import (
    compute_dependency_detail as _compute_dependency_detail,
    scope_contains,
    scope_dependency_conflict,
    scope_overlap,
)
from .state_machines import (
    ConflictStateMachine,
    IntentStateMachine,
    OperationStateMachine,
)
from .watermark import LamportClock


PROTOCOL_VERSION = "0.1.13"


# ────────────────────────────────────────────────────────────────
# Authenticated profile: credential verification API (Section 23.1.4)
# ────────────────────────────────────────────────────────────────


@dataclass
class VerifyResult:
    """Outcome of a credential verification attempt.

    Returned by a ``CredentialVerifier`` callable to tell the coordinator
    whether a HELLO should be accepted under the Authenticated/Verified
    security profile, and optionally which roles the credential grants.
    """

    accepted: bool
    reason: Optional[str] = None
    granted_roles: Optional[List[str]] = None

    @classmethod
    def accept(cls, granted_roles: Optional[List[str]] = None) -> "VerifyResult":
        """Accept the credential; optionally override granted roles."""
        return cls(accepted=True, granted_roles=granted_roles)

    @classmethod
    def reject(cls, reason: str) -> "VerifyResult":
        """Reject the credential with a human-readable reason."""
        return cls(accepted=False, reason=reason)


# Signature of a credential verifier. Given the HELLO ``credential`` payload
# and the session id being joined, return a ``VerifyResult``. Verifiers are
# synchronous — HELLO processing runs inside ``SessionCoordinator.process_message``
# which is itself synchronous.
CredentialVerifier = Callable[[Dict[str, Any], str], VerifyResult]


def _now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """Serialize UTC timestamps in RFC 3339 form."""
    return dt.isoformat().replace("+00:00", "Z")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse RFC 3339 timestamps used by snapshots."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Intent:
    """Internal representation of an intent."""

    intent_id: str
    principal_id: str
    objective: str
    scope: Scope
    state_machine: IntentStateMachine
    received_at: datetime = field(default_factory=_now)
    ttl_sec: Optional[float] = None
    expires_at: Optional[datetime] = None
    last_message_id: Optional[str] = None
    claimed_by: Optional[str] = None


@dataclass
class Operation:
    """Internal representation of an operation."""

    op_id: str
    intent_id: str
    principal_id: str
    target: str
    op_kind: str
    state_machine: OperationStateMachine
    state_ref_before: Optional[str] = None
    state_ref_after: Optional[str] = None
    batch_id: Optional[str] = None
    authorized_at: Optional[datetime] = None
    authorized_by: Optional[str] = None
    created_at: datetime = field(default_factory=_now)


@dataclass
class Conflict:
    """Internal representation of a conflict."""

    conflict_id: str
    category: str
    severity: str
    principal_a: str
    principal_b: str
    intent_a: str
    intent_b: str
    state_machine: ConflictStateMachine
    related_intents: List[str] = field(default_factory=list)
    related_ops: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    escalated_to: Optional[str] = None
    escalated_at: Optional[datetime] = None
    resolution_id: Optional[str] = None
    resolved_by: Optional[str] = None
    scope_frozen: bool = False


@dataclass
class Claim:
    """Internal representation of an intent claim."""

    claim_id: str
    original_intent_id: str
    original_principal_id: str
    new_intent_id: str
    claimer_principal_id: str
    objective: str
    scope: Scope
    justification: Optional[str] = None
    submitted_at: datetime = field(default_factory=_now)
    decision: str = "pending"
    approved_by: Optional[str] = None


@dataclass
class ParticipantInfo:
    """Liveness tracking for a participant."""

    principal: Principal
    last_seen: datetime = field(default_factory=_now)
    status: str = "idle"
    is_available: bool = True
    backend_model_id: Optional[str] = None
    backend_provider: Optional[str] = None
    backend_provider_status: str = "unknown"


class SessionCoordinator:
    """Coordinates MPAC sessions."""

    def __init__(
        self,
        session_id: str,
        security_profile: str = "open",
        compliance_profile: str = "core",
        intent_expiry_grace_sec: float = 30.0,
        heartbeat_interval_sec: float = 30.0,
        unavailability_timeout_sec: float = 90.0,
        resolution_timeout_sec: float = 300.0,
        execution_model: str = "post_commit",
        state_ref_format: str = "sha256",
        intent_claim_grace_sec: float = 0.0,
        role_policy: Optional[Dict[str, Any]] = None,
        replay_window_sec: float = 300.0,
        backend_health_policy: Optional[Dict[str, Any]] = None,
        credential_verifier: Optional[CredentialVerifier] = None,
    ):
        if execution_model == "pre_commit" and compliance_profile != ComplianceProfile.GOVERNANCE.value:
            raise ValueError("pre_commit sessions require Governance Profile compliance")

        self.session_id = session_id
        self.security_profile = security_profile
        self.compliance_profile = compliance_profile
        self.execution_model = execution_model
        self.state_ref_format = state_ref_format
        self.watermark_kind = "lamport_clock"
        self.intent_expiry_grace_sec = intent_expiry_grace_sec
        self.heartbeat_interval_sec = heartbeat_interval_sec
        self.unavailability_timeout_sec = unavailability_timeout_sec
        self.resolution_timeout_sec = resolution_timeout_sec
        self.intent_claim_grace_sec = intent_claim_grace_sec

        self.participants: Dict[str, ParticipantInfo] = {}
        self.intents: Dict[str, Intent] = {}
        self.operations: Dict[str, Operation] = {}
        self.conflicts: Dict[str, Conflict] = {}
        self.claims: Dict[str, Claim] = {}
        self.claim_index: Dict[str, Claim] = {}
        self.audit_log: List[Dict[str, Any]] = []
        self.lamport_clock = LamportClock()
        self.recent_message_ids: List[str] = []
        self._seen_message_ids: set = set()
        self.sender_frontier: Dict[str, Dict[str, Any]] = {}
        self.coordinator_epoch = 1
        self.coordinator_id = f"service:coordinator-{session_id}"
        self.coordinator_instance_id = f"{self.coordinator_id}:epoch-{self.coordinator_epoch}"
        self.session_closed = False
        self.session_started_at = _now()
        self.role_policy: Optional[Dict[str, Any]] = role_policy
        self.replay_window_sec = replay_window_sec
        self._backend_health_policy: Optional[Dict[str, Any]] = backend_health_policy
        self.credential_verifier: Optional[CredentialVerifier] = credential_verifier
        self.lifecycle_policy = {
            "auto_close": False,
            "auto_close_grace_sec": 60,
            "session_ttl_sec": 0,
        }
        # Optimistic concurrency control: track latest state_ref per target
        # Maps target (e.g. file path) -> latest known state_ref_after
        self.target_state_refs: Dict[str, str] = {}

    # ================================================================
    #  Main message processing
    # ================================================================

    def process_message(self, envelope_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process an incoming message and emit zero or more responses."""
        envelope = MessageEnvelope.from_dict(envelope_dict)
        self.audit_log.append(envelope.to_dict())

        # Replay protection (Section 23.1.2): reject duplicate message_id
        # or timestamps outside acceptable window in Authenticated/Verified profiles
        if self.security_profile != "open":
            if envelope.message_id in self._seen_message_ids:
                return [self._make_protocol_error(
                    "REPLAY_DETECTED",
                    envelope.message_id,
                    f"Duplicate message_id '{envelope.message_id}' rejected by replay protection",
                ).to_dict()]
            # Timestamp format + window check (RECOMMENDED: 5 minutes)
            if not _RFC3339_RE.match(envelope.ts or ""):
                return [self._make_protocol_error(
                    "REPLAY_DETECTED",
                    envelope.message_id,
                    f"Timestamp '{envelope.ts}' is not valid RFC 3339 date-time",
                ).to_dict()]
            try:
                msg_ts = datetime.fromisoformat(envelope.ts.replace("Z", "+00:00"))
                drift = abs((_now() - msg_ts).total_seconds())
                if drift > self.replay_window_sec:
                    return [self._make_protocol_error(
                        "REPLAY_DETECTED",
                        envelope.message_id,
                        f"Timestamp '{envelope.ts}' is {int(drift)}s outside the acceptable window ({self.replay_window_sec}s)",
                    ).to_dict()]
            except (ValueError, TypeError):
                return [self._make_protocol_error(
                    "REPLAY_DETECTED",
                    envelope.message_id,
                    f"Unparseable timestamp '{envelope.ts}'; RFC 3339 date-time required",
                ).to_dict()]
        self._seen_message_ids.add(envelope.message_id)

        self._remember_message_id(envelope.message_id)
        self._record_sender_frontier(envelope)

        if envelope.watermark and envelope.watermark.kind == "lamport_clock":
            self.lamport_clock.update(int(envelope.watermark.value))

        pid = envelope.sender.principal_id
        if pid in self.participants:
            self.participants[pid].last_seen = _now()

        if self.session_closed and envelope.message_type != MessageType.GOODBYE.value:
            return [self._make_protocol_error(
                "SESSION_CLOSED",
                envelope.message_id,
                f"Session {self.session_id} has been closed",
            ).to_dict()]

        # HELLO-first gate: only HELLO is allowed from unregistered senders (Section 14.1)
        # The coordinator itself is always allowed (it is a service principal, not a participant).
        if pid not in self.participants and pid != self.coordinator_id and envelope.message_type != MessageType.HELLO.value:
            return [self._make_protocol_error(
                "INVALID_REFERENCE",
                envelope.message_id,
                f"Principal {pid} must send HELLO before any other message",
            ).to_dict()]

        handlers = {
            MessageType.HELLO.value: self._handle_hello,
            MessageType.HEARTBEAT.value: self._handle_heartbeat,
            MessageType.GOODBYE.value: self._handle_goodbye,
            MessageType.INTENT_ANNOUNCE.value: self._handle_intent_announce,
            MessageType.INTENT_UPDATE.value: self._handle_intent_update,
            MessageType.INTENT_WITHDRAW.value: self._handle_intent_withdraw,
            MessageType.INTENT_CLAIM.value: self._handle_intent_claim,
            MessageType.OP_PROPOSE.value: self._handle_op_propose,
            MessageType.OP_COMMIT.value: self._handle_op_commit,
            MessageType.OP_BATCH_COMMIT.value: self._handle_op_batch_commit,
            MessageType.OP_SUPERSEDE.value: self._handle_op_supersede,
            MessageType.CONFLICT_REPORT.value: self._handle_conflict_report,
            MessageType.CONFLICT_ACK.value: self._handle_conflict_ack,
            MessageType.CONFLICT_ESCALATE.value: self._handle_conflict_escalate,
            MessageType.RESOLUTION.value: self._handle_resolution,
            MessageType.SESSION_CLOSE.value: self._handle_session_close,
            MessageType.COORDINATOR_STATUS.value: lambda _envelope: [],
        }

        responses = handlers.get(envelope.message_type, lambda _envelope: [])(envelope)
        responses.extend(self.check_pending_claims())
        return [response.to_dict() for response in responses]

    # ================================================================
    #  Time-based lifecycle checks
    # ================================================================

    def check_expiry(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Check intents for TTL expiry and cascade termination."""
        now = now or _now()
        responses: List[MessageEnvelope] = []

        for intent in list(self.intents.values()):
            if (
                intent.expires_at is not None
                and not intent.state_machine.is_terminal()
                and intent.state_machine.current_state != IntentState.ANNOUNCED
                and now >= intent.expires_at
            ):
                intent.state_machine.transition("EXPIRED")
                responses.extend(self._cascade_intent_termination(intent.intent_id))

        responses.extend(self._check_auto_dismiss())
        responses.extend(self.check_pending_claims(now))
        return [response.to_dict() for response in responses]

    def check_liveness(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Detect unavailable participants and suspend their active work."""
        now = now or _now()
        threshold = timedelta(seconds=self.unavailability_timeout_sec)
        responses: List[MessageEnvelope] = []

        for pid, info in list(self.participants.items()):
            if not info.is_available or info.status == "offline":
                continue
            if now - info.last_seen > threshold:
                info.is_available = False
                responses.extend(self._handle_participant_unavailable(pid))

        responses.extend(self.check_pending_claims(now))
        return [response.to_dict() for response in responses]

    def check_resolution_timeouts(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Escalate long-running conflicts to an arbiter when available."""
        now = now or _now()
        threshold = timedelta(seconds=self.resolution_timeout_sec)
        responses: List[MessageEnvelope] = []

        for conflict in list(self.conflicts.values()):
            if conflict.state_machine.current_state not in (ConflictState.OPEN, ConflictState.ACKED):
                continue
            if now - conflict.created_at <= threshold:
                continue

            arbiter_id = self._find_arbiter()
            if arbiter_id:
                if conflict.state_machine.current_state == ConflictState.OPEN:
                    conflict.state_machine.transition("ACKED")
                conflict.state_machine.transition("ESCALATED")
                conflict.escalated_to = arbiter_id
                conflict.escalated_at = now
                responses.append(self._make_envelope(
                    MessageType.CONFLICT_ESCALATE.value,
                    {
                        "conflict_id": conflict.conflict_id,
                        "escalate_to": arbiter_id,
                        "reason": "resolution_timeout",
                    },
                ))
            else:
                # No arbiter available — enter frozen scope state (Section 18.6.1 + 18.6.2)
                conflict.scope_frozen = True
                responses.append(self._make_protocol_error(
                    "RESOLUTION_TIMEOUT",
                    conflict.conflict_id,
                    f"No arbiter available for conflict {conflict.conflict_id}; scope is now frozen",
                ))

        return [response.to_dict() for response in responses]

    def check_pending_claims(self, now: Optional[datetime] = None) -> List[MessageEnvelope]:
        """Approve pending claims when their policy conditions are satisfied."""
        now = now or _now()
        responses: List[MessageEnvelope] = []

        for original_intent_id, claim in list(self.claims.items()):
            if claim.decision != "pending":
                continue

            original = self.intents.get(original_intent_id)
            if original is None:
                responses.extend(self._reject_claim(claim, "original_intent_missing"))
                continue

            if original.state_machine.current_state != IntentState.SUSPENDED:
                responses.extend(self._reject_claim(claim, "intent_no_longer_suspended"))
                continue

            if self.compliance_profile == ComplianceProfile.GOVERNANCE.value:
                approver = self._find_claim_approver(claim.claimer_principal_id)
                if approver is None:
                    continue
                responses.extend(self._approve_claim(claim, approver))
                continue

            if (now - claim.submitted_at).total_seconds() >= self.intent_claim_grace_sec:
                responses.extend(self._approve_claim(claim, None))

        return responses

    # ================================================================
    #  Session layer handlers
    # ================================================================

    def _handle_hello(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Register a participant and return session parameters."""
        payload = envelope.payload
        requested_roles = payload.get("roles", ["participant"])

        # Credential validation for Authenticated/Verified profiles (Section 23.1.4)
        verifier_result: Optional[VerifyResult] = None
        if self.security_profile != "open":
            credential = payload.get("credential")
            if not credential or not credential.get("type") or not credential.get("value"):
                return [self._make_protocol_error(
                    "CREDENTIAL_REJECTED",
                    envelope.message_id,
                    f"Security profile '{self.security_profile}' requires a valid credential in HELLO",
                )]

            # If a verifier is configured, actually verify the credential value
            # and (optionally) derive granted roles from it. Without a verifier,
            # the existing "credential field is present" check stands in —
            # preserving backward compatibility with mpac 0.1.0 behavior.
            if self.credential_verifier is not None:
                verifier_result = self.credential_verifier(credential, self.session_id)
                if not verifier_result.accepted:
                    return [self._make_protocol_error(
                        "CREDENTIAL_REJECTED",
                        envelope.message_id,
                        verifier_result.reason
                        or f"Credential rejected for session {self.session_id}",
                    )]

        # Role evaluation: verifier-supplied roles (if any) override role_policy.
        # This lets bearer-token deployments pin roles per-token without
        # maintaining a separate role_policy table.
        if verifier_result is not None and verifier_result.granted_roles is not None:
            granted_roles = verifier_result.granted_roles
        else:
            # Role policy evaluation (Section 23.1.5)
            granted_roles = self._evaluate_role_policy(
                envelope.sender.principal_id, envelope.sender.principal_type, requested_roles,
            )

        # If no roles were granted, reject the HELLO (e.g. no role policy in
        # Authenticated/Verified profile, or all requested roles denied)
        if not granted_roles:
            return [self._make_protocol_error(
                "AUTHORIZATION_FAILED",
                envelope.message_id,
                "No roles could be granted for this principal; check role policy configuration",
            )]

        principal = Principal(
            principal_id=envelope.sender.principal_id,
            principal_type=envelope.sender.principal_type,
            display_name=payload.get("display_name", ""),
            roles=granted_roles,
            capabilities=payload.get("capabilities", []),
        )
        backend = payload.get("backend")
        self.participants[principal.principal_id] = ParticipantInfo(
            principal=principal,
            last_seen=_now(),
            status="idle",
            is_available=True,
            backend_model_id=backend.get("model_id") if backend else None,
            backend_provider=backend.get("provider") if backend else None,
            backend_provider_status="operational" if backend else "unknown",
        )

        responses = self._handle_owner_rejoin(principal.principal_id)
        responses.append(self._make_envelope(
            MessageType.SESSION_INFO.value,
            {
                "session_id": self.session_id,
                "protocol_version": PROTOCOL_VERSION,
                "security_profile": self.security_profile,
                "compliance_profile": self.compliance_profile,
                "watermark_kind": self.watermark_kind,
                "execution_model": self.execution_model,
                "state_ref_format": self.state_ref_format,
                "governance_policy": {
                    "require_acknowledgment": True,
                    "intent_expiry_grace_sec": self.intent_expiry_grace_sec,
                },
                "liveness_policy": self._build_liveness_policy(),
                "participant_count": len(self.participants),
                "granted_roles": granted_roles,
                "identity_verified": self.security_profile == "open" or bool(payload.get("credential")),
                "identity_method": payload.get("credential", {}).get("type") if payload.get("credential") else None,
                "identity_issuer": payload.get("credential", {}).get("issuer") if payload.get("credential") else None,
                "compatibility_errors": [],
            },
        ))
        return responses

    def _handle_heartbeat(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Update liveness status for a participant."""
        pid = envelope.sender.principal_id
        status = envelope.payload.get("status", "idle")
        info = self.participants.get(pid)
        responses: List[MessageEnvelope] = []

        if info:
            info.last_seen = _now()
            info.status = status
            if not info.is_available:
                info.is_available = True
                responses.extend(self._handle_owner_rejoin(pid))

            # Backend health monitoring (Section 14.3.1)
            backend_health = envelope.payload.get("backend_health")
            if backend_health:
                responses.extend(self._process_backend_health(pid, info, backend_health))

        return responses

    def _process_backend_health(
        self, pid: str, info: "ParticipantInfo", backend_health: Dict[str, Any]
    ) -> List[MessageEnvelope]:
        """Evaluate backend health and enforce backend_health_policy."""
        responses: List[MessageEnvelope] = []
        provider_status = backend_health.get("provider_status", "unknown")
        old_status = info.backend_provider_status

        # Update tracked backend info
        info.backend_model_id = backend_health.get("model_id", info.backend_model_id)
        info.backend_provider_status = provider_status

        # Check for model switch
        switched_from = backend_health.get("switched_from")
        if switched_from:
            switch_error = self._validate_backend_switch(pid, backend_health)
            if switch_error:
                return [switch_error]
            info.backend_provider = backend_health.get("model_id", "").split("/")[0] if "/" in backend_health.get("model_id", "") else info.backend_provider

        # Determine action based on backend_health_policy
        policy = self._get_backend_health_policy()
        if not policy or not policy.get("enabled", False):
            return responses

        action = None
        if provider_status == "down":
            action = policy.get("on_down", "suspend_and_claim")
        elif provider_status == "degraded":
            action = policy.get("on_degraded", "warn")

        if action and action != "ignore" and provider_status != old_status:
            # Emit backend_alert
            alert = self._make_coordinator_status(
                event="backend_alert",
                extra={
                    "affected_principal": pid,
                    "backend_detail": {
                        "model_id": backend_health.get("model_id", ""),
                        "provider_status": provider_status,
                        "status_detail": backend_health.get("status_detail"),
                        "alternatives": backend_health.get("alternatives", []),
                    },
                },
            )
            responses.append(alert)

            # suspend_and_claim: suspend agent's active intents
            if action == "suspend_and_claim":
                for intent in self.intents.values():
                    if intent.principal_id == pid and not intent.state_machine.is_terminal():
                        if intent.state_machine.current_state != IntentState.SUSPENDED:
                            try:
                                intent.state_machine.transition("SUSPENDED")
                                responses.append(self._make_envelope(
                                    "INTENT_UPDATE",
                                    {
                                        "intent_id": intent.intent_id,
                                        "objective": f"[SUSPENDED: backend {provider_status}] {intent.objective}",
                                    },
                                ))
                            except Exception:
                                pass  # Intent may not support this transition

        return responses

    def _validate_backend_switch(self, pid: str, backend_health: Dict[str, Any]) -> Optional[MessageEnvelope]:
        """Validate a backend model switch against backend_health_policy."""
        policy = self._get_backend_health_policy()
        if not policy or not policy.get("enabled", False):
            return None

        auto_switch = policy.get("auto_switch", "allowed")
        if auto_switch == "forbidden":
            return self._make_protocol_error(
                "BACKEND_SWITCH_DENIED",
                None,
                f"Backend model switching is forbidden by session policy (auto_switch=forbidden)",
            )

        allowed_providers = policy.get("allowed_providers")
        if allowed_providers:
            new_model_id = backend_health.get("model_id", "")
            new_provider = new_model_id.split("/")[0] if "/" in new_model_id else ""
            if new_provider and new_provider not in allowed_providers:
                return self._make_protocol_error(
                    "BACKEND_SWITCH_DENIED",
                    None,
                    f"Provider '{new_provider}' is not in allowed_providers: {allowed_providers}",
                )

        return None

    def _get_backend_health_policy(self) -> Optional[Dict[str, Any]]:
        """Return the backend_health_policy from session config, or None."""
        return getattr(self, "_backend_health_policy", None)

    def _build_liveness_policy(self) -> Dict[str, Any]:
        """Build the liveness_policy object for SESSION_INFO."""
        policy: Dict[str, Any] = {
            "heartbeat_interval_sec": self.heartbeat_interval_sec,
            "unavailability_timeout_sec": self.unavailability_timeout_sec,
            "intent_claim_grace_period_sec": self.intent_claim_grace_sec,
            "resolution_timeout_sec": self.resolution_timeout_sec,
        }
        if self._backend_health_policy:
            policy["backend_health_policy"] = self._backend_health_policy
        return policy

    def _compute_session_health_str(self) -> str:
        """Compute session health as a string."""
        open_conflicts = sum(
            1 for c in self.conflicts.values()
            if c.state_machine.current_state not in (ConflictState.CLOSED, ConflictState.DISMISSED)
        )
        return "healthy" if open_conflicts == 0 else "degraded"

    def _make_coordinator_status(self, event: str, extra: Optional[Dict[str, Any]] = None) -> MessageEnvelope:
        """Create a COORDINATOR_STATUS message."""
        payload: Dict[str, Any] = {
            "event": event,
            "coordinator_id": self.coordinator_id,
            "session_health": self._compute_session_health_str(),
            "active_participants": sum(1 for p in self.participants.values() if p.is_available),
            "open_conflicts": sum(1 for c in self.conflicts.values() if not c.get("resolved", False)),
        }
        if extra:
            payload.update(extra)
        return self._make_envelope(MessageType.COORDINATOR_STATUS.value, payload)

    def _handle_goodbye(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Apply the participant's requested disposition and mark them offline."""
        pid = envelope.sender.principal_id
        disposition = envelope.payload.get("intent_disposition", "withdraw")
        active_intents = envelope.payload.get("active_intents", [])
        responses: List[MessageEnvelope] = []

        if pid in self.participants:
            self.participants[pid].is_available = False
            self.participants[pid].status = "offline"

        if not active_intents:
            active_intents = [
                intent_id
                for intent_id, intent in self.intents.items()
                if intent.principal_id == pid
                and not intent.state_machine.is_terminal()
                and intent.state_machine.current_state != IntentState.ANNOUNCED
            ]

        for intent_id in active_intents:
            intent = self.intents.get(intent_id)
            if intent is None:
                continue
            # Ownership guard: only the intent owner can affect their own intents
            if intent.principal_id != pid:
                continue
            try:
                if disposition == "transfer":
                    if intent.state_machine.current_state == IntentState.ACTIVE:
                        intent.state_machine.transition("SUSPENDED")
                elif disposition == "expire":
                    continue
                else:
                    target = "WITHDRAWN" if intent.state_machine.current_state != IntentState.SUSPENDED else "WITHDRAWN"
                    intent.state_machine.transition(target)
                    responses.extend(self._cascade_intent_termination(intent_id))
            except ValueError:
                continue

        for operation in self.operations.values():
            if operation.principal_id != pid:
                continue
            if operation.state_machine.current_state == OperationState.PROPOSED:
                operation.state_machine.transition("ABANDONED")
            elif operation.state_machine.current_state == OperationState.FROZEN:
                operation.state_machine.transition("ABANDONED")

        responses.extend(self._check_auto_dismiss())
        return responses

    # ================================================================
    #  Frozen-scope helper
    # ================================================================

    def _is_scope_frozen(self, scope: Scope) -> Optional[Conflict]:
        """Check whether a scope overlaps with a conflict whose scope has been frozen.

        Per Section 18.6.2, scopes enter frozen state only after resolution_timeout_sec
        expires (via check_resolution_timeouts), NOT immediately on conflict creation.
        """
        for conflict in self.conflicts.values():
            if conflict.state_machine.is_terminal():
                continue
            if not conflict.scope_frozen:
                continue
            intent_a = self.intents.get(conflict.intent_a)
            intent_b = self.intents.get(conflict.intent_b)
            if (intent_a and scope_overlap(scope, intent_a.scope)) or \
               (intent_b and scope_overlap(scope, intent_b.scope)):
                return conflict
        return None

    def _check_frozen_scope_for_intent(self, scope: Scope) -> tuple:
        """For INTENT_ANNOUNCE: distinguish full containment (MUST reject) from partial overlap (SHOULD accept with warning).

        Per Section 18.6.2:
        - Fully contained in frozen scope → ("reject", conflict)
        - Partially overlapping → ("warn", conflict)
        - No overlap → (None, None)
        """
        for conflict in self.conflicts.values():
            if conflict.state_machine.is_terminal():
                continue
            if not conflict.scope_frozen:
                continue
            intent_a = self.intents.get(conflict.intent_a)
            intent_b = self.intents.get(conflict.intent_b)

            overlaps_a = intent_a and scope_overlap(scope, intent_a.scope)
            overlaps_b = intent_b and scope_overlap(scope, intent_b.scope)

            if not overlaps_a and not overlaps_b:
                continue

            # Build union scope of the frozen conflict's intents
            union_scope = self._build_frozen_union_scope(intent_a, intent_b)
            if union_scope and scope_contains(union_scope, scope):
                return ("reject", conflict)
            else:
                return ("warn", conflict)
        return (None, None)

    def _build_frozen_union_scope(self, intent_a, intent_b):
        """Build a union scope from two intents' scopes."""
        scopes = [i.scope for i in [intent_a, intent_b] if i is not None]
        if not scopes:
            return None
        if len(scopes) == 1:
            return scopes[0]
        a, b = scopes
        if a.kind != b.kind:
            return a  # Conservative fallback
        if a.kind == "file_set":
            resources = list(set((a.resources or []) + (b.resources or [])))
            return Scope(kind="file_set", resources=resources)
        elif a.kind == "entity_set":
            entities = list(set((a.entities or []) + (b.entities or [])))
            return Scope(kind="entity_set", entities=entities)
        elif a.kind == "task_set":
            task_ids = list(set((a.task_ids or []) + (b.task_ids or [])))
            return Scope(kind="task_set", task_ids=task_ids)
        return a

    # ================================================================
    #  Intent layer handlers
    # ================================================================

    def _handle_intent_announce(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Register a new active intent."""
        scope_data = envelope.payload.get("scope")
        scope = Scope.from_dict(scope_data) if isinstance(scope_data, dict) else scope_data

        # Frozen-scope check for INTENT_ANNOUNCE (Section 18.6.2):
        # - Fully contained in frozen scope → MUST reject
        # - Partially overlapping → SHOULD accept with warning
        frozen_action, frozen_conflict = self._check_frozen_scope_for_intent(scope)
        if frozen_action == "reject":
            return [self._make_protocol_error(
                "SCOPE_FROZEN",
                envelope.message_id,
                f"Scope fully contained in frozen conflict {frozen_conflict.conflict_id}; new intents blocked until conflict is resolved",
            )]

        ttl_sec = envelope.payload.get("ttl_sec")
        if ttl_sec is None and envelope.payload.get("expiry_ms") is not None:
            ttl_sec = float(envelope.payload["expiry_ms"]) / 1000.0

        state_machine = IntentStateMachine()
        state_machine.transition("ACTIVE")
        now = _now()

        intent = Intent(
            intent_id=envelope.payload.get("intent_id"),
            principal_id=envelope.sender.principal_id,
            objective=envelope.payload.get("objective", ""),
            scope=scope,
            state_machine=state_machine,
            received_at=now,
            ttl_sec=float(ttl_sec) if ttl_sec is not None else None,
            expires_at=now + timedelta(seconds=float(ttl_sec)) if ttl_sec is not None else None,
            last_message_id=envelope.message_id,
        )
        self.intents[intent.intent_id] = intent
        responses = self._detect_scope_overlaps(intent)

        # Partial overlap warning (Section 18.6.2: SHOULD accept but MUST warn)
        if frozen_action == "warn":
            responses.append(self._make_protocol_error(
                "SCOPE_FROZEN",
                envelope.message_id,
                f"Warning: intent scope partially overlaps frozen conflict {frozen_conflict.conflict_id}; overlapping portion is frozen",
            ))
        return responses

    def _handle_intent_update(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Update objective, scope, or TTL for an active intent."""
        intent_id = envelope.payload.get("intent_id")
        intent = self.intents.get(intent_id)
        if intent is None or intent.principal_id != envelope.sender.principal_id:
            return []
        if intent.state_machine.current_state != IntentState.ACTIVE:
            return []

        scope_changed = False
        if "objective" in envelope.payload:
            intent.objective = envelope.payload["objective"]
        if "scope" in envelope.payload:
            scope_data = envelope.payload["scope"]
            intent.scope = Scope.from_dict(scope_data) if isinstance(scope_data, dict) else scope_data
            scope_changed = True
        if "ttl_sec" in envelope.payload:
            intent.ttl_sec = float(envelope.payload["ttl_sec"])
            intent.expires_at = _now() + timedelta(seconds=intent.ttl_sec)
        intent.last_message_id = envelope.message_id

        if scope_changed:
            return self._detect_scope_overlaps(intent, skip_existing_conflicts=True)
        return []

    def _handle_intent_withdraw(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Withdraw an intent owned by the sender."""
        intent_id = envelope.payload.get("intent_id")
        intent = self.intents.get(intent_id)
        if intent is None or intent.principal_id != envelope.sender.principal_id:
            return []
        try:
            intent.state_machine.transition("WITHDRAWN")
        except ValueError:
            return []
        responses = self._cascade_intent_termination(intent_id)
        responses.extend(self._check_auto_dismiss())
        return responses

    def _handle_intent_claim(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Register a claim against a suspended intent."""
        original_intent_id = envelope.payload.get("original_intent_id")
        if original_intent_id not in self.intents:
            return [self._make_protocol_error(
                "INVALID_REFERENCE",
                envelope.message_id,
                f"Intent {original_intent_id} does not exist",
            )]

        if original_intent_id in self.claims:
            return [self._make_protocol_error(
                "CLAIM_CONFLICT",
                envelope.message_id,
                f"Intent {original_intent_id} already has an accepted pending claim",
            )]

        original = self.intents[original_intent_id]
        if original.claimed_by is not None and original.state_machine.current_state == IntentState.TRANSFERRED:
            return [self._make_protocol_error(
                "CLAIM_CONFLICT",
                envelope.message_id,
                f"Intent {original_intent_id} has already been transferred to another claimant",
            )]
        if original.state_machine.current_state != IntentState.SUSPENDED:
            return [self._make_protocol_error(
                "INVALID_REFERENCE",
                envelope.message_id,
                f"Intent {original_intent_id} is not SUSPENDED",
            )]

        scope_data = envelope.payload.get("scope")
        scope = Scope.from_dict(scope_data) if isinstance(scope_data, dict) else scope_data
        claim = Claim(
            claim_id=envelope.payload["claim_id"],
            original_intent_id=original_intent_id,
            original_principal_id=envelope.payload["original_principal_id"],
            new_intent_id=envelope.payload["new_intent_id"],
            claimer_principal_id=envelope.sender.principal_id,
            objective=envelope.payload["objective"],
            scope=scope,
            justification=envelope.payload.get("justification"),
        )
        self.claims[original_intent_id] = claim
        self.claim_index[claim.claim_id] = claim
        original.claimed_by = claim.claimer_principal_id
        return []

    # ================================================================
    #  Operation layer handlers
    # ================================================================

    def _handle_op_propose(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Register a proposed operation."""
        # Frozen-scope check: target-based (Section 18.6.2)
        target = envelope.payload.get("target")
        if target:
            target_scope = Scope(kind="file_set", resources=[target])
            frozen_conflict = self._is_scope_frozen(target_scope)
            if frozen_conflict:
                return [self._make_protocol_error(
                    "SCOPE_FROZEN",
                    envelope.message_id,
                    f"Target '{target}' overlaps with frozen conflict {frozen_conflict.conflict_id}; proposals blocked",
                )]

        op = self._register_operation_from_payload(
            payload=envelope.payload,
            principal_id=envelope.sender.principal_id,
            state=OperationState.PROPOSED,
        )
        responses = self._validate_operation_against_intent(op)
        if self.execution_model == "pre_commit" and op.state_machine.current_state == OperationState.PROPOSED:
            responses.extend(self._authorize_operation(op))
        return responses

    def _handle_op_commit(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Handle operation commit according to the session execution model."""
        payload = envelope.payload
        op_id = payload.get("op_id")

        if self.execution_model == "pre_commit":
            operation = self.operations.get(op_id)
            if operation is None:
                operation = self._register_operation_from_payload(
                    payload=payload,
                    principal_id=envelope.sender.principal_id,
                    state=OperationState.PROPOSED,
                )
                responses = self._validate_operation_against_intent(operation)
                if operation.state_machine.current_state == OperationState.PROPOSED:
                    responses.extend(self._authorize_operation(operation))
                return responses

            if operation.state_machine.current_state == OperationState.FROZEN:
                return [self._make_protocol_error(
                    "SCOPE_FROZEN",
                    envelope.message_id,
                    f"Operation {op_id} is frozen until its intent is restored",
                )]

            if operation.authorized_at is None:
                return [self._make_protocol_error(
                    "AUTHORIZATION_FAILED",
                    envelope.message_id,
                    f"Operation {op_id} has not been authorized for execution",
                )]

            if operation.state_machine.current_state == OperationState.PROPOSED:
                operation.state_ref_before = payload.get("state_ref_before")
                operation.state_ref_after = payload.get("state_ref_after")
                operation.target = payload.get("target", operation.target)
                operation.op_kind = payload.get("op_kind", operation.op_kind)
                operation.state_machine.transition("COMMITTED")
            return []

        # Frozen-scope check for post-commit: target-based (Section 18.6.2)
        commit_target = payload.get("target")
        if commit_target:
            target_scope = Scope(kind="file_set", resources=[commit_target])
            frozen_conflict = self._is_scope_frozen(target_scope)
            if frozen_conflict:
                return [self._make_protocol_error(
                    "SCOPE_FROZEN",
                    envelope.message_id,
                    f"Target '{commit_target}' overlaps with frozen conflict {frozen_conflict.conflict_id}; commits blocked",
                )]

        # Optimistic concurrency control: reject if state_ref_before is stale
        if commit_target:
            state_ref_before = payload.get("state_ref_before")
            known_ref = self.target_state_refs.get(commit_target)
            if known_ref is not None and state_ref_before is not None:
                if state_ref_before != known_ref:
                    return [self._make_protocol_error(
                        "STALE_STATE_REF",
                        envelope.message_id,
                        f"Target '{commit_target}' state_ref_before ({state_ref_before[:16]}...) "
                        f"does not match latest known state ({known_ref[:16]}...); "
                        f"another agent has committed a newer version — rebase required",
                    )]

        self._commit_operation_entry(payload, envelope.sender.principal_id)
        return []

    def _handle_op_batch_commit(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Handle grouped operations that share a single batch envelope."""
        payload = envelope.payload
        batch_id = payload.get("batch_id")
        atomicity = payload.get("atomicity", "all_or_nothing")

        # Frozen-scope check: target-based (Section 18.6.2)
        # Check every entry's target against frozen scopes — intent_id is optional
        batch_intent_id = payload.get("intent_id")
        operations = payload.get("operations", [])
        for entry in operations:
            entry_target = entry.get("target")
            if entry_target:
                target_scope = Scope(kind="file_set", resources=[entry_target])
                frozen_conflict = self._is_scope_frozen(target_scope)
                if frozen_conflict:
                    return [self._make_protocol_error(
                        "SCOPE_FROZEN",
                        envelope.message_id,
                        f"Target '{entry_target}' overlaps with frozen conflict {frozen_conflict.conflict_id}; batch blocked",
                    )]
        intent_id = payload.get("intent_id")

        if not operations:
            return [self._make_protocol_error(
                "MALFORMED_MESSAGE",
                envelope.message_id,
                f"Batch {batch_id} must contain at least one operation entry",
            )]

        if self.execution_model == "pre_commit":
            existing = [self.operations.get(entry["op_id"]) for entry in operations]
            if all(existing):
                for op in existing:
                    if op is None or op.batch_id != batch_id:
                        return [self._make_protocol_error(
                            "INVALID_REFERENCE",
                            envelope.message_id,
                            f"Batch {batch_id} references unknown or mismatched operations",
                        )]
                    if op.authorized_at is None:
                        return [self._make_protocol_error(
                            "AUTHORIZATION_FAILED",
                            envelope.message_id,
                            f"Batch {batch_id} has not been authorized for execution",
                        )]
                for op, entry in zip(existing, operations):
                    if op is None:
                        continue
                    op.state_ref_before = entry.get("state_ref_before")
                    op.state_ref_after = entry.get("state_ref_after")
                    if op.state_machine.current_state == OperationState.PROPOSED:
                        op.state_machine.transition("COMMITTED")
                return []

            created: List[Operation] = []
            rejections: List[str] = []
            for entry in operations:
                if intent_id is not None and entry.get("intent_id", intent_id) != intent_id:
                    rejections.append(entry["op_id"])
                    continue
                op = self._register_operation_from_payload(
                    payload={**entry, "intent_id": entry.get("intent_id", intent_id)},
                    principal_id=envelope.sender.principal_id,
                    state=OperationState.PROPOSED,
                    batch_id=batch_id,
                )
                created.append(op)
                if self._validate_operation_against_intent(op):
                    if op.state_machine.current_state != OperationState.PROPOSED:
                        rejections.append(op.op_id)

            if atomicity == "all_or_nothing" and rejections:
                # Rollback: remove already-registered operations from state
                for op in created:
                    self.operations.pop(op.op_id, None)
                return [self._make_batch_reject(batch_id, rejections, "batch_validation_failed")]

            responses: List[MessageEnvelope] = []
            for op in created:
                if op.state_machine.current_state == OperationState.PROPOSED:
                    responses.extend(self._authorize_operation(op, batch_id=batch_id))
            return responses

        rejections: List[str] = []
        responses: List[MessageEnvelope] = []
        committed_entries: List[Dict[str, Any]] = []

        for entry in operations:
            effective_entry = {**entry, "intent_id": entry.get("intent_id", intent_id)}
            if intent_id is not None and effective_entry.get("intent_id") != intent_id:
                rejections.append(entry["op_id"])
                continue

            # Optimistic concurrency control for batch entries
            entry_target = entry.get("target")
            if entry_target:
                state_ref_before = entry.get("state_ref_before")
                known_ref = self.target_state_refs.get(entry_target)
                if known_ref is not None and state_ref_before is not None:
                    if state_ref_before != known_ref:
                        rejections.append(entry["op_id"])
                        responses.append(self._make_protocol_error(
                            "STALE_STATE_REF",
                            envelope.message_id,
                            f"Target '{entry_target}' state_ref_before is stale; rebase required",
                        ))
                        continue

            temp_op = self._build_operation(
                effective_entry,
                envelope.sender.principal_id,
                OperationState.COMMITTED,
                batch_id=batch_id,
            )
            validation_responses = self._validate_operation_against_intent(temp_op, persist=False)
            if validation_responses:
                rejections.append(entry["op_id"])
                responses.extend(validation_responses)
                continue
            committed_entries.append(effective_entry)

        if atomicity == "all_or_nothing" and rejections:
            return [self._make_batch_reject(batch_id, rejections, "batch_validation_failed")]

        for entry in committed_entries:
            self._commit_operation_entry(entry, envelope.sender.principal_id, batch_id=batch_id)

        if atomicity != "all_or_nothing":
            responses = [response for response in responses if response.message_type == MessageType.OP_REJECT.value]
        return responses

    def _handle_op_supersede(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Supersede a previously committed operation."""
        payload = envelope.payload
        supersedes_op_id = payload.get("supersedes_op_id")
        old_op = self.operations.get(supersedes_op_id)
        if old_op is None:
            return [self._make_protocol_error(
                "INVALID_REFERENCE",
                envelope.message_id,
                f"Operation {supersedes_op_id} does not exist",
            )]
        if old_op.state_machine.current_state != OperationState.COMMITTED:
            return [self._make_protocol_error(
                "INVALID_REFERENCE",
                envelope.message_id,
                f"Operation {supersedes_op_id} is not COMMITTED (state: {old_op.state_machine.current_state.value})",
            )]

        old_op.state_machine.transition("SUPERSEDED")
        new_op = self._build_operation(
            {
                "op_id": payload.get("op_id"),
                "intent_id": payload.get("intent_id", old_op.intent_id),
                "target": payload.get("target", old_op.target),
                "op_kind": payload.get("op_kind", old_op.op_kind),
                "state_ref_before": old_op.state_ref_after,
                "state_ref_after": payload.get("state_ref_after"),
            },
            envelope.sender.principal_id,
            OperationState.COMMITTED,
        )
        self.operations[new_op.op_id] = new_op
        self._track_operation_conflicts(new_op.intent_id, new_op.op_id)
        return []

    # ================================================================
    #  Conflict layer handlers
    # ================================================================

    def _handle_conflict_report(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Register a conflict if it is not already known."""
        payload = envelope.payload
        conflict_id = payload.get("conflict_id")
        if conflict_id not in self.conflicts:
            self.conflicts[conflict_id] = Conflict(
                conflict_id=conflict_id,
                category=payload.get("category", "unknown"),
                severity=payload.get("severity", "medium"),
                principal_a=payload.get("principal_a", payload.get("involved_principals", ["", ""])[0]),
                principal_b=payload.get("principal_b", payload.get("involved_principals", ["", ""])[1] if len(payload.get("involved_principals", [])) > 1 else ""),
                intent_a=payload.get("intent_a", ""),
                intent_b=payload.get("intent_b", ""),
                state_machine=ConflictStateMachine(),
                related_intents=[value for value in [payload.get("intent_a"), payload.get("intent_b")] if value],
            )
        return []

    def _handle_conflict_ack(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Move an open conflict into ACKED state."""
        conflict = self.conflicts.get(envelope.payload.get("conflict_id"))
        if conflict and conflict.state_machine.current_state == ConflictState.OPEN:
            conflict.state_machine.transition("ACKED")
        return []

    def _handle_conflict_escalate(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Escalate a conflict to an explicit target."""
        conflict = self.conflicts.get(envelope.payload.get("conflict_id"))
        if conflict is None:
            return []
        if conflict.state_machine.current_state == ConflictState.OPEN:
            conflict.state_machine.transition("ACKED")
        if conflict.state_machine.current_state == ConflictState.ACKED:
            conflict.state_machine.transition("ESCALATED")
        conflict.escalated_to = envelope.payload.get("escalate_to")
        conflict.escalated_at = _now()
        return []

    def _handle_resolution(self, envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Apply the first valid resolution for the conflict's current phase."""
        payload = envelope.payload
        conflict_id = payload.get("conflict_id")
        conflict = self.conflicts.get(conflict_id)
        if conflict is None:
            return [self._make_protocol_error(
                "INVALID_REFERENCE",
                envelope.message_id,
                f"Conflict {conflict_id} does not exist",
            )]

        if conflict.resolution_id is not None or conflict.state_machine.is_terminal():
            return [self._make_protocol_error(
                "RESOLUTION_CONFLICT",
                envelope.message_id,
                f"Conflict {conflict_id} already has an accepted resolution",
            )]

        if not self._is_authorized_resolver(conflict, envelope.sender.principal_id):
            return [self._make_protocol_error(
                "AUTHORIZATION_FAILED",
                envelope.message_id,
                f"Principal {envelope.sender.principal_id} is not authorized to resolve conflict {conflict_id}",
            )]

        outcome = payload.get("outcome") or {}
        rejected_ids = outcome.get("rejected", []) if isinstance(outcome, dict) else []
        committed_rejections = [
            entity_id
            for entity_id in rejected_ids
            if entity_id in self.operations
            and self.operations[entity_id].state_machine.current_state == OperationState.COMMITTED
        ]
        if committed_rejections and not outcome.get("rollback"):
            return [self._make_protocol_error(
                "MALFORMED_MESSAGE",
                envelope.message_id,
                "Resolutions rejecting committed operations must declare outcome.rollback",
            )]

        decision = payload.get("decision")
        if decision == "dismissed":
            if conflict.state_machine.current_state in (ConflictState.OPEN, ConflictState.ACKED, ConflictState.ESCALATED):
                conflict.state_machine.transition("DISMISSED")
        else:
            if conflict.state_machine.current_state == ConflictState.OPEN:
                conflict.state_machine.transition("ACKED")
            if conflict.state_machine.current_state == ConflictState.ACKED:
                conflict.state_machine.transition("RESOLVED")
                conflict.state_machine.transition("CLOSED")
            elif conflict.state_machine.current_state == ConflictState.ESCALATED:
                conflict.state_machine.transition("RESOLVED")
                conflict.state_machine.transition("CLOSED")

        conflict.resolution_id = payload.get("resolution_id", str(uuid.uuid4()))
        conflict.resolved_by = envelope.sender.principal_id
        return []

    def resolve_as_coordinator(
        self,
        conflict_id: str,
        decision: str = "approved",
        rationale: str = "",
    ) -> List[Dict[str, Any]]:
        """Resolve a conflict using the coordinator's own authority.

        The coordinator (as a service principal) always passes the
        ``_is_authorized_resolver`` check.  This method builds a
        RESOLUTION envelope with the coordinator as sender, then
        processes it through the normal ``_handle_resolution`` path
        so all state-machine transitions and side-effects happen
        consistently.

        Returns the list of response envelopes (empty on success,
        PROTOCOL_ERROR on failure).
        """
        resolution_envelope = self._make_envelope(
            MessageType.RESOLUTION.value,
            {
                "conflict_id": conflict_id,
                "decision": decision,
                "rationale": rationale,
                "resolution_id": str(uuid.uuid4()),
            },
        )
        return self.process_message(resolution_envelope.to_dict())

    # ================================================================
    #  Lifecycle cascades
    # ================================================================

    def _cascade_intent_termination(self, intent_id: str) -> List[MessageEnvelope]:
        """Reject dependent operations when their intent becomes terminal."""
        intent = self.intents.get(intent_id)
        if intent is None:
            return []

        responses: List[MessageEnvelope] = []
        for operation in list(self.operations.values()):
            if operation.intent_id != intent_id:
                continue
            if operation.state_machine.current_state == OperationState.PROPOSED:
                operation.state_machine.transition("REJECTED")
                responses.append(self._make_op_reject(operation.op_id, "intent_terminated", intent.last_message_id))
            elif operation.state_machine.current_state == OperationState.FROZEN:
                operation.state_machine.transition("REJECTED")
                responses.append(self._make_op_reject(operation.op_id, "intent_terminated", intent.last_message_id))

        return responses

    def _check_auto_dismiss(self) -> List[MessageEnvelope]:
        """Dismiss conflicts whose related intents and operations are all terminal."""
        responses: List[MessageEnvelope] = []

        for conflict in list(self.conflicts.values()):
            if conflict.state_machine.is_terminal():
                continue

            all_intents_terminal = all(
                self.intents.get(intent_id) is None
                or self.intents[intent_id].state_machine.is_terminal()
                for intent_id in conflict.related_intents
            )
            if not all_intents_terminal:
                continue

            has_committed = False
            all_ops_terminal = True
            for op_id in conflict.related_ops:
                operation = self.operations.get(op_id)
                if operation is None:
                    continue
                if operation.state_machine.current_state == OperationState.COMMITTED:
                    has_committed = True
                    break
                if operation.state_machine.current_state not in (
                    OperationState.REJECTED,
                    OperationState.ABANDONED,
                    OperationState.SUPERSEDED,
                ):
                    all_ops_terminal = False
                    break

            if has_committed or not all_ops_terminal:
                continue

            conflict.state_machine.transition("DISMISSED")
            conflict.resolution_id = str(uuid.uuid4())
            conflict.resolved_by = self.coordinator_id
            responses.append(self._make_envelope(
                MessageType.RESOLUTION.value,
                {
                    "resolution_id": conflict.resolution_id,
                    "conflict_id": conflict.conflict_id,
                    "decision": "dismissed",
                    "rationale": "all_related_entities_terminated",
                },
            ))

        return responses

    def _handle_participant_unavailable(self, principal_id: str) -> List[MessageEnvelope]:
        """Suspend active intents and abandon in-flight proposals for an unavailable participant."""
        responses: List[MessageEnvelope] = [
            self._make_envelope(
                MessageType.PROTOCOL_ERROR.value,
                {
                    "error_code": "PARTICIPANT_UNAVAILABLE",
                    "refers_to": principal_id,
                    "description": f"Participant {principal_id} is unavailable (no heartbeat for >{self.unavailability_timeout_sec}s)",
                },
            )
        ]

        for intent in self.intents.values():
            if intent.principal_id != principal_id:
                continue
            if intent.state_machine.current_state == IntentState.ACTIVE:
                intent.state_machine.transition("SUSPENDED")
                for operation in self.operations.values():
                    if operation.intent_id == intent.intent_id and operation.state_machine.current_state == OperationState.PROPOSED:
                        operation.state_machine.transition("FROZEN")

        for operation in self.operations.values():
            if operation.principal_id != principal_id:
                continue
            if operation.state_machine.current_state == OperationState.PROPOSED:
                operation.state_machine.transition("ABANDONED")
            elif operation.state_machine.current_state == OperationState.FROZEN:
                operation.state_machine.transition("ABANDONED")

        return responses

    # ================================================================
    #  Helpers
    # ================================================================

    def _make_envelope(self, message_type: str, payload: Dict[str, Any]) -> MessageEnvelope:
        """Create a coordinator-authored envelope."""
        return MessageEnvelope.create(
            message_type=message_type,
            session_id=self.session_id,
            sender=Sender(
                principal_id=self.coordinator_id,
                principal_type="service",
                sender_instance_id=self.coordinator_instance_id,
            ),
            payload={k: v for k, v in payload.items() if v is not None},
            watermark=self.lamport_clock.create_watermark(),
            coordinator_epoch=self.coordinator_epoch,
        )

    def _make_op_reject(self, op_id: str, reason: str, refers_to: Optional[str] = None) -> MessageEnvelope:
        """Create an OP_REJECT message."""
        payload: Dict[str, Any] = {"op_id": op_id, "reason": reason}
        if refers_to:
            payload["refers_to"] = refers_to
        return self._make_envelope(MessageType.OP_REJECT.value, payload)

    def _make_batch_reject(self, batch_id: str, rejected_ops: List[str], reason: str) -> MessageEnvelope:
        """Create an OP_REJECT message for a batch."""
        return self._make_envelope(
            MessageType.OP_REJECT.value,
            {
                "op_id": batch_id,
                "reason": reason,
                "rejected_ops": rejected_ops,
            },
        )

    def _make_protocol_error(self, error_code: str, refers_to: Optional[str], description: str) -> MessageEnvelope:
        """Create a PROTOCOL_ERROR message."""
        payload: Dict[str, Any] = {
            "error_code": error_code,
            "description": description,
        }
        if refers_to:
            payload["refers_to"] = refers_to
        return self._make_envelope(MessageType.PROTOCOL_ERROR.value, payload)

    def _remember_message_id(self, message_id: str) -> None:
        """Track recently seen message IDs for snapshot continuity."""
        self.recent_message_ids.append(message_id)
        if len(self.recent_message_ids) > 200:
            self.recent_message_ids = self.recent_message_ids[-200:]

    def _record_sender_frontier(self, envelope: MessageEnvelope) -> None:
        """Track the latest timestamp and Lamport value seen for each sender incarnation."""
        key = f"{envelope.sender.principal_id}|{envelope.sender.sender_instance_id}"
        last_lamport = None
        if envelope.watermark:
            if envelope.watermark.kind == "lamport_clock":
                last_lamport = int(envelope.watermark.value)
            else:
                last_lamport = envelope.watermark.lamport_value
        self.sender_frontier[key] = {
            "last_ts": envelope.ts,
            "last_lamport": last_lamport,
        }

    def _build_operation(
        self,
        payload: Dict[str, Any],
        principal_id: str,
        state: OperationState,
        batch_id: Optional[str] = None,
    ) -> Operation:
        """Build an internal Operation object from payload data."""
        state_machine = OperationStateMachine()
        if state == OperationState.COMMITTED:
            state_machine.transition("COMMITTED")
        elif state == OperationState.REJECTED:
            state_machine.transition("REJECTED")
        elif state == OperationState.ABANDONED:
            state_machine.transition("ABANDONED")
        elif state == OperationState.FROZEN:
            state_machine.transition("FROZEN")

        return Operation(
            op_id=payload.get("op_id"),
            intent_id=payload.get("intent_id", "") or "",
            principal_id=principal_id,
            target=payload.get("target", ""),
            op_kind=payload.get("op_kind", ""),
            state_machine=state_machine,
            state_ref_before=payload.get("state_ref_before"),
            state_ref_after=payload.get("state_ref_after"),
            batch_id=batch_id,
        )

    def _register_operation_from_payload(
        self,
        payload: Dict[str, Any],
        principal_id: str,
        state: OperationState,
        batch_id: Optional[str] = None,
    ) -> Operation:
        """Create and persist an operation object."""
        operation = self._build_operation(payload, principal_id, state, batch_id=batch_id)
        self.operations[operation.op_id] = operation
        self._track_operation_conflicts(operation.intent_id, operation.op_id)
        return operation

    def _commit_operation_entry(
        self,
        payload: Dict[str, Any],
        principal_id: str,
        batch_id: Optional[str] = None,
    ) -> Operation:
        """Persist a committed operation entry."""
        op_id = payload.get("op_id")
        operation = self.operations.get(op_id)
        if operation is None:
            operation = self._register_operation_from_payload(
                payload=payload,
                principal_id=principal_id,
                state=OperationState.COMMITTED,
                batch_id=batch_id,
            )
        else:
            operation.target = payload.get("target", operation.target)
            operation.op_kind = payload.get("op_kind", operation.op_kind)
            operation.intent_id = payload.get("intent_id", operation.intent_id)
            operation.state_ref_before = payload.get("state_ref_before")
            operation.state_ref_after = payload.get("state_ref_after")
            if operation.state_machine.current_state == OperationState.PROPOSED:
                operation.state_machine.transition("COMMITTED")
        self._track_operation_conflicts(operation.intent_id, op_id)

        # Update optimistic concurrency tracking
        target = payload.get("target")
        state_ref_after = payload.get("state_ref_after")
        if target and state_ref_after:
            self.target_state_refs[target] = state_ref_after

        return operation

    def _validate_operation_against_intent(
        self,
        operation: Operation,
        persist: bool = True,
    ) -> List[MessageEnvelope]:
        """Apply intent-state rules to an operation."""
        intent = self.intents.get(operation.intent_id)
        if intent is None:
            return []

        if intent.state_machine.is_terminal():
            if persist and operation.state_machine.current_state == OperationState.PROPOSED:
                operation.state_machine.transition("REJECTED")
            return [self._make_op_reject(operation.op_id, "intent_terminated", intent.last_message_id)]

        if intent.state_machine.current_state == IntentState.SUSPENDED:
            if persist and operation.state_machine.current_state == OperationState.PROPOSED:
                operation.state_machine.transition("FROZEN")
            return []

        return []

    def _authorize_operation(self, operation: Operation, batch_id: Optional[str] = None) -> List[MessageEnvelope]:
        """Mark a proposal as authorized without committing it yet."""
        if operation.authorized_at is not None:
            return []

        operation.authorized_at = _now()
        operation.authorized_by = self.coordinator_id
        open_conflicts = sum(
            1 for c in self.conflicts.values()
            if c.state_machine.current_state not in (ConflictState.CLOSED, ConflictState.DISMISSED)
        )
        payload: Dict[str, Any] = {
            "event": "authorization",
            "coordinator_id": self.coordinator_id,
            "session_health": "healthy" if open_conflicts == 0 else "degraded",
            "authorized_op_id": operation.op_id,
            "authorized_by": operation.authorized_by,
        }
        if batch_id is not None:
            payload["authorized_batch_id"] = batch_id
        return [self._make_envelope(MessageType.COORDINATOR_STATUS.value, payload)]

    def _track_operation_conflicts(self, intent_id: str, op_id: str) -> None:
        """Associate an operation with conflicts involving the same intent."""
        if not intent_id:
            return
        for conflict in self.conflicts.values():
            if intent_id in (conflict.intent_a, conflict.intent_b) and op_id not in conflict.related_ops:
                conflict.related_ops.append(op_id)

    def _detect_scope_overlaps(
        self,
        new_intent: Intent,
        skip_existing_conflicts: bool = False,
    ) -> List[MessageEnvelope]:
        """Create conflicts for overlapping active or suspended intents.

        Two categories are emitted here:

        * ``scope_overlap`` (SPEC.md §15.2.1.1): same-resource overlap,
          the classical case — unchanged since v0.1.x.
        * ``dependency_breakage`` (SPEC.md §17.5 + v0.2.1 detection rule):
          no shared resources but one scope's ``extensions.impact`` (the
          reverse-dep set computed by the client analyzer) includes a file
          the other scope is about to edit. Gracefully a no-op when neither
          side populated ``impact`` — e.g. an 0.2.0 client talking to this
          coordinator.
        """
        responses: List[MessageEnvelope] = []

        for other in self.intents.values():
            if other.intent_id == new_intent.intent_id:
                continue
            if other.state_machine.current_state not in (IntentState.ACTIVE, IntentState.SUSPENDED):
                continue

            overlap = scope_overlap(new_intent.scope, other.scope)
            # Only check for dependency-breakage when there's no direct overlap;
            # same-file overlap already dominates and stays category=scope_overlap.
            dep_conflict = (
                not overlap
                and scope_dependency_conflict(new_intent.scope, other.scope)
            )
            if not overlap and not dep_conflict:
                continue

            if skip_existing_conflicts and any(
                (
                    conflict.intent_a == new_intent.intent_id and conflict.intent_b == other.intent_id
                ) or (
                    conflict.intent_b == new_intent.intent_id and conflict.intent_a == other.intent_id
                )
                for conflict in self.conflicts.values()
                if not conflict.state_machine.is_terminal()
            ):
                continue

            category = "scope_overlap" if overlap else "dependency_breakage"
            conflict_id = str(uuid.uuid4())
            conflict = Conflict(
                conflict_id=conflict_id,
                category=category,
                severity="medium",
                principal_a=new_intent.principal_id,
                principal_b=other.principal_id,
                intent_a=new_intent.intent_id,
                intent_b=other.intent_id,
                state_machine=ConflictStateMachine(),
                related_intents=[new_intent.intent_id, other.intent_id],
            )
            self.conflicts[conflict_id] = conflict

            # v0.2.3: attach symbol-level detail when we can derive it,
            # so the UI can say "Alice's edits to utils.foo affect your
            # main.py" instead of just "dependency conflict".
            payload: Dict[str, Any] = {
                "conflict_id": conflict_id,
                "category": category,
                "severity": "medium",
                "principal_a": new_intent.principal_id,
                "principal_b": other.principal_id,
                "intent_a": new_intent.intent_id,
                "intent_b": other.intent_id,
            }
            if category == "dependency_breakage":
                detail = _compute_dependency_detail(new_intent.scope, other.scope)
                if detail:
                    payload["dependency_detail"] = detail
            responses.append(self._make_envelope(
                MessageType.CONFLICT_REPORT.value,
                payload,
            ))

        return responses

    def _handle_owner_rejoin(self, principal_id: str) -> List[MessageEnvelope]:
        """Restore suspended work when an original owner returns."""
        responses: List[MessageEnvelope] = []

        for original_intent_id, claim in list(self.claims.items()):
            if claim.original_principal_id != principal_id or claim.decision != "pending":
                continue
            responses.extend(self._withdraw_claim(claim, "original_owner_rejoined"))

        for intent in self.intents.values():
            if intent.principal_id != principal_id:
                continue
            if intent.state_machine.current_state == IntentState.SUSPENDED and intent.claimed_by is None:
                intent.state_machine.transition("ACTIVE")
                for operation in self.operations.values():
                    if operation.intent_id == intent.intent_id and operation.state_machine.current_state == OperationState.FROZEN:
                        operation.state_machine.transition("PROPOSED")

        return responses

    def _find_arbiter(self) -> Optional[str]:
        """Return the first available arbiter."""
        for pid, info in self.participants.items():
            if info.is_available and "arbiter" in info.principal.roles:
                return pid
        return None

    def _find_claim_approver(self, claimer_principal_id: str) -> Optional[str]:
        """Return the first available owner or arbiter for governance approval."""
        for pid, info in self.participants.items():
            if pid == claimer_principal_id or not info.is_available:
                continue
            roles = set(info.principal.roles or [])
            if "owner" in roles or "arbiter" in roles:
                return pid
        return None

    def _approve_claim(self, claim: Claim, approved_by: Optional[str]) -> List[MessageEnvelope]:
        """Approve a pending claim and activate the replacement intent."""
        original = self.intents.get(claim.original_intent_id)
        if original is None:
            return self._reject_claim(claim, "original_intent_missing")

        claim.decision = "approved"
        claim.approved_by = approved_by
        original.claimed_by = claim.claimer_principal_id
        if original.state_machine.current_state == IntentState.SUSPENDED:
            original.state_machine.transition("TRANSFERRED")

        state_machine = IntentStateMachine()
        state_machine.transition("ACTIVE")
        new_intent = Intent(
            intent_id=claim.new_intent_id,
            principal_id=claim.claimer_principal_id,
            objective=claim.objective,
            scope=claim.scope,
            state_machine=state_machine,
            last_message_id=claim.claim_id,
        )
        self.intents[claim.new_intent_id] = new_intent

        responses = [
            self._make_envelope(
                MessageType.INTENT_CLAIM_STATUS.value,
                {
                    "claim_id": claim.claim_id,
                    "original_intent_id": claim.original_intent_id,
                    "new_intent_id": claim.new_intent_id,
                    "decision": "approved",
                    "approved_by": approved_by,
                },
            )
        ]
        responses.extend(self._cascade_intent_termination(claim.original_intent_id))
        responses.extend(self._detect_scope_overlaps(new_intent))
        del self.claims[claim.original_intent_id]
        return responses

    def _reject_claim(self, claim: Claim, reason: str) -> List[MessageEnvelope]:
        """Reject a pending claim while keeping the original intent suspended."""
        claim.decision = "rejected"
        if claim.original_intent_id in self.claims:
            del self.claims[claim.original_intent_id]
        return [
            self._make_envelope(
                MessageType.INTENT_CLAIM_STATUS.value,
                {
                    "claim_id": claim.claim_id,
                    "original_intent_id": claim.original_intent_id,
                    "decision": "rejected",
                    "reason": reason,
                },
            )
        ]

    def _withdraw_claim(self, claim: Claim, reason: str) -> List[MessageEnvelope]:
        """Withdraw a pending claim because the original owner returned."""
        original = self.intents.get(claim.original_intent_id)
        if original and original.state_machine.current_state == IntentState.SUSPENDED:
            original.claimed_by = None
            original.state_machine.transition("ACTIVE")
            for operation in self.operations.values():
                if operation.intent_id == original.intent_id and operation.state_machine.current_state == OperationState.FROZEN:
                    operation.state_machine.transition("PROPOSED")

        claim.decision = "withdrawn"
        if claim.original_intent_id in self.claims:
            del self.claims[claim.original_intent_id]
        return [
            self._make_envelope(
                MessageType.INTENT_CLAIM_STATUS.value,
                {
                    "claim_id": claim.claim_id,
                    "original_intent_id": claim.original_intent_id,
                    "decision": "withdrawn",
                    "reason": reason,
                },
            )
        ]

    def _evaluate_role_policy(
        self, principal_id: str, principal_type: str, requested_roles: List[str],
    ) -> List[str]:
        """Evaluate requested roles against the session's role policy (Section 23.1.5).

        In Open profile without a role policy, participants receive the roles they request.
        In Authenticated/Verified profiles, a role policy MUST be defined and the coordinator
        MUST enforce it.  If no policy is configured, the default_role fallback applies.
        """
        if self.role_policy is None:
            if self.security_profile == "open":
                return requested_roles
            # Authenticated/Verified without a role policy is a configuration error
            # (Section 23.1.5: "a role policy MUST be defined")
            # Return empty to signal rejection; caller handles the error
            return []

        default_role = self.role_policy.get("default_role", "participant")
        assignments = self.role_policy.get("role_assignments", {})
        constraints = self.role_policy.get("role_constraints", {})

        # Determine which roles this principal is authorized for
        allowed = set(assignments.get(principal_id, [default_role]))

        granted: List[str] = []
        for role in requested_roles:
            if role not in allowed:
                continue
            constraint = constraints.get(role)
            if constraint:
                allowed_types = constraint.get("allowed_principal_types")
                if allowed_types and principal_type not in allowed_types:
                    continue
                max_count = constraint.get("max_count")
                if max_count is not None:
                    current_count = sum(
                        1 for p in self.participants.values()
                        if p.principal.principal_id != principal_id and role in p.principal.roles
                    )
                    if current_count >= max_count:
                        continue
            granted.append(role)

        return granted if granted else [default_role]

    def _is_authorized_resolver(self, conflict: Conflict, principal_id: str) -> bool:
        """Check whether a resolver is valid for the conflict's current authority phase."""
        if principal_id == self.coordinator_id:
            return True

        info = self.participants.get(principal_id)
        roles = set(info.principal.roles if info else [])

        if conflict.state_machine.current_state == ConflictState.ESCALATED:
            return principal_id == conflict.escalated_to or "arbiter" in roles

        # Pre-escalation: only owner or arbiter roles may resolve; being a related
        # principal (contributor) is not sufficient per SPEC Section 18.4 / 23.1.3
        return "owner" in roles or "arbiter" in roles

    # ================================================================
    #  Fault recovery
    # ================================================================

    def recover_from_snapshot(self, snapshot_data: Dict[str, Any]) -> None:
        """Restore coordinator state from a snapshot."""
        self.lamport_clock = LamportClock(snapshot_data.get("lamport_clock", 0))
        self.session_closed = snapshot_data.get("session_closed", False)
        self.coordinator_epoch = int(snapshot_data.get("coordinator_epoch", 1)) + 1
        self.coordinator_instance_id = f"{self.coordinator_id}:epoch-{self.coordinator_epoch}"

        anti_replay = snapshot_data.get("anti_replay", {})
        self.recent_message_ids = list(anti_replay.get("recent_message_ids", []))
        self._seen_message_ids = set(self.recent_message_ids)
        self.sender_frontier = dict(anti_replay.get("sender_frontier", {}))

        self.participants.clear()
        for participant in snapshot_data.get("participants", []):
            principal = Principal(
                principal_id=participant["principal_id"],
                principal_type=participant.get("principal_type", "agent"),
                display_name=participant.get("display_name", ""),
                roles=participant.get("roles", ["participant"]),
                capabilities=participant.get("capabilities", []),
            )
            self.participants[principal.principal_id] = ParticipantInfo(
                principal=principal,
                last_seen=_parse_dt(participant.get("last_seen")) or _now(),
                status=participant.get("status", "idle"),
                is_available=participant.get("is_available", True),
            )

        self.intents.clear()
        for intent_data in snapshot_data.get("intents", []):
            state_machine = IntentStateMachine(IntentState.ANNOUNCED)
            target_state = intent_data.get("state", "ACTIVE")
            if target_state == "ACTIVE":
                state_machine.transition("ACTIVE")
            elif target_state == "EXPIRED":
                state_machine.transition("ACTIVE")
                state_machine.transition("EXPIRED")
            elif target_state == "WITHDRAWN":
                state_machine.transition("ACTIVE")
                state_machine.transition("WITHDRAWN")
            elif target_state == "SUPERSEDED":
                state_machine.transition("ACTIVE")
                state_machine.transition("SUPERSEDED")
            elif target_state == "SUSPENDED":
                state_machine.transition("ACTIVE")
                state_machine.transition("SUSPENDED")
            elif target_state == "TRANSFERRED":
                state_machine.transition("ACTIVE")
                state_machine.transition("TRANSFERRED")

            scope_data = intent_data.get("scope", {"kind": "file_set"})
            scope = Scope.from_dict(scope_data) if isinstance(scope_data, dict) else scope_data
            self.intents[intent_data["intent_id"]] = Intent(
                intent_id=intent_data["intent_id"],
                principal_id=intent_data.get("principal_id", ""),
                objective=intent_data.get("objective", ""),
                scope=scope,
                state_machine=state_machine,
                received_at=_parse_dt(intent_data.get("received_at")) or _now(),
                ttl_sec=intent_data.get("ttl_sec"),
                expires_at=_parse_dt(intent_data.get("expires_at")),
                last_message_id=intent_data.get("last_message_id"),
                claimed_by=intent_data.get("claimed_by"),
            )

        self.operations.clear()
        for op_data in snapshot_data.get("operations", []):
            state_machine = OperationStateMachine()
            target_state = op_data.get("state", "PROPOSED")
            if target_state == "COMMITTED":
                state_machine.transition("COMMITTED")
            elif target_state == "REJECTED":
                state_machine.transition("REJECTED")
            elif target_state == "ABANDONED":
                state_machine.transition("ABANDONED")
            elif target_state == "FROZEN":
                state_machine.transition("FROZEN")
            elif target_state == "SUPERSEDED":
                state_machine.transition("COMMITTED")
                state_machine.transition("SUPERSEDED")

            self.operations[op_data["op_id"]] = Operation(
                op_id=op_data["op_id"],
                intent_id=op_data.get("intent_id", ""),
                principal_id=op_data.get("principal_id", ""),
                target=op_data.get("target", ""),
                op_kind=op_data.get("op_kind", ""),
                state_machine=state_machine,
                state_ref_before=op_data.get("state_ref_before"),
                state_ref_after=op_data.get("state_ref_after"),
                batch_id=op_data.get("batch_id"),
                authorized_at=_parse_dt(op_data.get("authorized_at")),
                authorized_by=op_data.get("authorized_by"),
                created_at=_parse_dt(op_data.get("created_at")) or _now(),
            )

        self.conflicts.clear()
        for conflict_data in snapshot_data.get("conflicts", []):
            state_machine = ConflictStateMachine()
            target_state = conflict_data.get("state", "OPEN")
            if target_state == "ACKED":
                state_machine.transition("ACKED")
            elif target_state == "ESCALATED":
                state_machine.transition("ACKED")
                state_machine.transition("ESCALATED")
            elif target_state == "RESOLVED":
                state_machine.transition("ACKED")
                state_machine.transition("RESOLVED")
            elif target_state == "CLOSED":
                state_machine.transition("ACKED")
                state_machine.transition("RESOLVED")
                state_machine.transition("CLOSED")
            elif target_state == "DISMISSED":
                state_machine.transition("DISMISSED")

            self.conflicts[conflict_data["conflict_id"]] = Conflict(
                conflict_id=conflict_data["conflict_id"],
                category=conflict_data.get("category", "scope_overlap"),
                severity=conflict_data.get("severity", "medium"),
                principal_a=conflict_data.get("principal_a", ""),
                principal_b=conflict_data.get("principal_b", ""),
                intent_a=conflict_data.get("intent_a", ""),
                intent_b=conflict_data.get("intent_b", ""),
                state_machine=state_machine,
                related_intents=conflict_data.get("related_intents", []),
                related_ops=conflict_data.get("related_ops", []),
                created_at=_parse_dt(conflict_data.get("created_at")) or _now(),
                escalated_to=conflict_data.get("escalated_to"),
                escalated_at=_parse_dt(conflict_data.get("escalated_at")),
                resolution_id=conflict_data.get("resolution_id"),
                resolved_by=conflict_data.get("resolved_by"),
                scope_frozen=conflict_data.get("scope_frozen", False),
            )

        self.claims.clear()
        self.claim_index.clear()
        for claim_data in snapshot_data.get("pending_claims", []):
            scope_data = claim_data.get("scope", {"kind": "file_set"})
            scope = Scope.from_dict(scope_data) if isinstance(scope_data, dict) else scope_data
            claim = Claim(
                claim_id=claim_data["claim_id"],
                original_intent_id=claim_data["original_intent_id"],
                original_principal_id=claim_data.get("original_principal_id", ""),
                new_intent_id=claim_data["new_intent_id"],
                claimer_principal_id=claim_data["claimer_principal_id"],
                objective=claim_data.get("objective", ""),
                scope=scope,
                justification=claim_data.get("justification"),
                submitted_at=_parse_dt(claim_data.get("submitted_at")) or _now(),
                decision=claim_data.get("decision", "pending"),
                approved_by=claim_data.get("approved_by"),
            )
            self.claims[claim.original_intent_id] = claim
            self.claim_index[claim.claim_id] = claim

    def replay_audit_log(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Replay messages captured after a snapshot."""
        responses: List[Dict[str, Any]] = []
        for message in messages:
            responses.extend(self.process_message(message))
        return responses

    # ================================================================
    #  Session lifecycle
    # ================================================================

    def close_session(self, reason: str = "manual") -> List[Dict[str, Any]]:
        """Close the session and emit a SESSION_CLOSE message."""
        if self.session_closed:
            return []

        self.session_closed = True
        for intent in self.intents.values():
            if not intent.state_machine.is_terminal() and intent.state_machine.current_state != IntentState.ANNOUNCED:
                try:
                    intent.state_machine.transition("WITHDRAWN")
                except ValueError:
                    pass

        for operation in self.operations.values():
            if operation.state_machine.current_state in (OperationState.PROPOSED, OperationState.FROZEN):
                try:
                    operation.state_machine.transition("ABANDONED")
                except ValueError:
                    pass

        message = self._make_envelope(
            MessageType.SESSION_CLOSE.value,
            {
                "reason": reason,
                "final_lamport_clock": self.lamport_clock.value,
                "summary": self._build_session_summary(),
                "active_intents_disposition": "withdraw_all",
            },
        )
        return [message.to_dict()]

    def _handle_session_close(self, _envelope: MessageEnvelope) -> List[MessageEnvelope]:
        """Ignore participant-authored SESSION_CLOSE messages."""
        return []

    def check_auto_close(self) -> List[Dict[str, Any]]:
        """Close the session when all tracked work has settled."""
        if self.session_closed or not self.intents:
            return []

        if any(not intent.state_machine.is_terminal() for intent in self.intents.values()):
            return []
        if any(operation.state_machine.current_state in (OperationState.PROPOSED, OperationState.FROZEN) for operation in self.operations.values()):
            return []
        if any(conflict.state_machine.current_state not in (ConflictState.CLOSED, ConflictState.DISMISSED) for conflict in self.conflicts.values()):
            return []
        return self.close_session("completed")

    def coordinator_status(self, event: str = "heartbeat") -> List[Dict[str, Any]]:
        """Emit a COORDINATOR_STATUS message."""
        open_conflicts = sum(
            1
            for conflict in self.conflicts.values()
            if conflict.state_machine.current_state not in (ConflictState.CLOSED, ConflictState.DISMISSED)
        )
        active_participants = sum(1 for info in self.participants.values() if info.is_available)
        message = self._make_envelope(
            MessageType.COORDINATOR_STATUS.value,
            {
                "event": event,
                "coordinator_id": self.coordinator_id,
                "session_health": "healthy" if open_conflicts == 0 else "degraded",
                "active_participants": active_participants,
                "open_conflicts": open_conflicts,
                "snapshot_lamport_clock": self.lamport_clock.value,
            },
        )
        return [message.to_dict()]

    def snapshot(self) -> Dict[str, Any]:
        """Capture a v0.1.13-compatible coordinator snapshot."""
        return {
            "snapshot_version": 2,
            "session_id": self.session_id,
            "protocol_version": PROTOCOL_VERSION,
            "captured_at": _iso(_now()),
            "coordinator_epoch": self.coordinator_epoch,
            "lamport_clock": self.lamport_clock.value,
            "anti_replay": {
                "replay_window_sec": 300,
                "recent_message_ids": list(self.recent_message_ids),
                "sender_frontier": dict(self.sender_frontier),
            },
            "participants": [
                {
                    "principal_id": info.principal.principal_id,
                    "principal_type": info.principal.principal_type,
                    "display_name": info.principal.display_name,
                    "roles": info.principal.roles,
                    "capabilities": info.principal.capabilities,
                    "status": info.status,
                    "is_available": info.is_available,
                    "last_seen": _iso(info.last_seen),
                }
                for info in self.participants.values()
            ],
            "intents": [
                {
                    "intent_id": intent.intent_id,
                    "principal_id": intent.principal_id,
                    "objective": intent.objective,
                    "state": intent.state_machine.current_state.value,
                    "scope": intent.scope.to_dict() if hasattr(intent.scope, "to_dict") else intent.scope,
                    "received_at": _iso(intent.received_at),
                    "ttl_sec": intent.ttl_sec,
                    "expires_at": _iso(intent.expires_at) if intent.expires_at else None,
                    "last_message_id": intent.last_message_id,
                    "claimed_by": intent.claimed_by,
                }
                for intent in self.intents.values()
            ],
            "operations": [
                {
                    "op_id": operation.op_id,
                    "intent_id": operation.intent_id,
                    "principal_id": operation.principal_id,
                    "state": operation.state_machine.current_state.value,
                    "target": operation.target,
                    "op_kind": operation.op_kind,
                    "state_ref_before": operation.state_ref_before,
                    "state_ref_after": operation.state_ref_after,
                    "batch_id": operation.batch_id,
                    "authorized_at": _iso(operation.authorized_at) if operation.authorized_at else None,
                    "authorized_by": operation.authorized_by,
                    "created_at": _iso(operation.created_at),
                }
                for operation in self.operations.values()
            ],
            "conflicts": [
                {
                    "conflict_id": conflict.conflict_id,
                    "category": conflict.category,
                    "severity": conflict.severity,
                    "principal_a": conflict.principal_a,
                    "principal_b": conflict.principal_b,
                    "intent_a": conflict.intent_a,
                    "intent_b": conflict.intent_b,
                    "state": conflict.state_machine.current_state.value,
                    "related_intents": conflict.related_intents,
                    "related_ops": conflict.related_ops,
                    "created_at": _iso(conflict.created_at),
                    "escalated_to": conflict.escalated_to,
                    "escalated_at": _iso(conflict.escalated_at) if conflict.escalated_at else None,
                    "resolution_id": conflict.resolution_id,
                    "resolved_by": conflict.resolved_by,
                    "scope_frozen": conflict.scope_frozen,
                }
                for conflict in self.conflicts.values()
            ],
            "pending_claims": [
                {
                    "claim_id": claim.claim_id,
                    "original_intent_id": claim.original_intent_id,
                    "original_principal_id": claim.original_principal_id,
                    "new_intent_id": claim.new_intent_id,
                    "claimer_principal_id": claim.claimer_principal_id,
                    "objective": claim.objective,
                    "scope": claim.scope.to_dict() if hasattr(claim.scope, "to_dict") else claim.scope,
                    "justification": claim.justification,
                    "submitted_at": _iso(claim.submitted_at),
                    "decision": claim.decision,
                    "approved_by": claim.approved_by,
                }
                for claim in self.claims.values()
            ],
            "session_closed": self.session_closed,
        }

    def _build_session_summary(self) -> Dict[str, Any]:
        """Summarize the session lifecycle for SESSION_CLOSE (Section 9.6.2)."""
        duration_sec = int((_now() - self.session_started_at).total_seconds())

        # Intent breakdown
        completed = expired = withdrawn = 0
        for intent in self.intents.values():
            st = intent.state_machine.current_state
            if st == IntentState.EXPIRED:
                expired += 1
            elif st == IntentState.WITHDRAWN:
                withdrawn += 1
            elif st in (IntentState.SUPERSEDED, IntentState.TRANSFERRED):
                completed += 1
            elif st == IntentState.ACTIVE and intent.state_machine.is_terminal():
                completed += 1

        # Operation breakdown
        committed = rejected = abandoned = 0
        for op in self.operations.values():
            st = op.state_machine.current_state
            if st == OperationState.COMMITTED:
                committed += 1
            elif st == OperationState.REJECTED:
                rejected += 1
            elif st == OperationState.ABANDONED:
                abandoned += 1

        # Conflict breakdown
        resolved = sum(
            1 for c in self.conflicts.values()
            if c.state_machine.current_state in (ConflictState.RESOLVED, ConflictState.CLOSED)
        )

        return {
            "total_intents": len(self.intents),
            "completed_intents": completed,
            "expired_intents": expired,
            "withdrawn_intents": withdrawn,
            "total_operations": len(self.operations),
            "committed_operations": committed,
            "rejected_operations": rejected,
            "abandoned_operations": abandoned,
            "total_conflicts": len(self.conflicts),
            "resolved_conflicts": resolved,
            "total_participants": len(self.participants),
            "duration_sec": duration_sec,
        }
