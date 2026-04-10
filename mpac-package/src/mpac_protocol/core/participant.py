"""Participant client for MPAC protocol."""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import uuid

from .models import Sender, Scope, Watermark, MessageType
from .envelope import MessageEnvelope
from .watermark import LamportClock


class Participant:
    """MPAC protocol participant."""

    def __init__(
        self,
        principal_id: str,
        principal_type: str,
        display_name: str,
        roles: List[str] = None,
        capabilities: List[str] = None,
        credential: Optional[Dict[str, Any]] = None,
    ):
        self.principal_id = principal_id
        self.principal_type = principal_type
        self.display_name = display_name
        self.roles = roles or ["participant"]
        self.capabilities = capabilities or []
        self.credential = credential  # {"type": "...", "value": "...", ...}
        self.lamport_clock = LamportClock()
        self.sender_instance_id = f"{self.principal_id}:{uuid.uuid4()}"

    def _sender(self) -> Sender:
        return Sender(
            principal_id=self.principal_id,
            principal_type=self.principal_type,
            sender_instance_id=self.sender_instance_id,
        )

    def _make(self, message_type: str, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        envelope = MessageEnvelope.create(
            message_type=message_type,
            session_id=session_id,
            sender=self._sender(),
            payload=payload,
            watermark=self.lamport_clock.create_watermark(),
        )
        return envelope.to_dict()

    # ================================================================
    #  Session layer
    # ================================================================

    def hello(
        self,
        session_id: str,
        backend: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Send HELLO to join session.

        Args:
            session_id: Target session.
            backend: Optional backend declaration, e.g.
                     {"model_id": "anthropic/claude-sonnet-4.6", "provider": "anthropic"}
        """
        payload = {
            "display_name": self.display_name,
            "roles": self.roles,
            "capabilities": self.capabilities,
        }
        if self.credential:
            payload["credential"] = self.credential
        if backend:
            payload["backend"] = backend
        return self._make(MessageType.HELLO.value, session_id, payload)

    def heartbeat(
        self,
        session_id: str,
        status: str = "idle",
        active_intent_id: Optional[str] = None,
        summary: Optional[str] = None,
        backend_health: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send HEARTBEAT (Section 14.4).

        Args:
            session_id: Target session.
            status: Agent status (idle/working/blocked).
            active_intent_id: Currently active intent.
            summary: Human-readable status summary.
            backend_health: Optional backend health report, e.g.
                {"model_id": "anthropic/claude-sonnet-4.6",
                 "provider_status": "operational",
                 "checked_at": "2026-04-07T10:00:00Z"}
        """
        payload: Dict[str, Any] = {"status": status}
        if active_intent_id:
            payload["active_intent_id"] = active_intent_id
        if summary:
            payload["summary"] = summary
        if backend_health:
            payload["backend_health"] = backend_health
        return self._make(MessageType.HEARTBEAT.value, session_id, payload)

    def goodbye(
        self,
        session_id: str,
        reason: str = "user_exit",
        active_intents: Optional[List[str]] = None,
        intent_disposition: str = "withdraw",
    ) -> Dict[str, Any]:
        """Send GOODBYE to cleanly leave session (Section 14.4)."""
        payload: Dict[str, Any] = {
            "reason": reason,
            "intent_disposition": intent_disposition,
        }
        if active_intents:
            payload["active_intents"] = active_intents
        return self._make(MessageType.GOODBYE.value, session_id, payload)

    # ================================================================
    #  Intent layer
    # ================================================================

    def announce_intent(
        self,
        session_id: str,
        intent_id: str,
        objective: str,
        scope: Scope,
        ttl_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Announce an intent (Section 15.3)."""
        payload: Dict[str, Any] = {
            "intent_id": intent_id,
            "objective": objective,
            "scope": scope.to_dict(),
        }
        if ttl_sec is not None:
            payload["ttl_sec"] = ttl_sec
        return self._make(MessageType.INTENT_ANNOUNCE.value, session_id, payload)

    def update_intent(
        self,
        session_id: str,
        intent_id: str,
        objective: Optional[str] = None,
        scope: Optional[Scope] = None,
        ttl_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update an active intent (Section 15.4)."""
        payload: Dict[str, Any] = {"intent_id": intent_id}
        if objective is not None:
            payload["objective"] = objective
        if scope is not None:
            payload["scope"] = scope.to_dict()
        if ttl_sec is not None:
            payload["ttl_sec"] = ttl_sec
        return self._make(MessageType.INTENT_UPDATE.value, session_id, payload)

    def withdraw_intent(
        self,
        session_id: str,
        intent_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Withdraw an intent (Section 15.5)."""
        payload: Dict[str, Any] = {"intent_id": intent_id}
        if reason:
            payload["reason"] = reason
        return self._make(MessageType.INTENT_WITHDRAW.value, session_id, payload)

    def claim_intent(
        self,
        session_id: str,
        claim_id: str,
        original_intent_id: str,
        original_principal_id: str,
        new_intent_id: str,
        objective: str,
        scope: Scope,
        justification: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Claim a suspended intent (Section 14.5.4)."""
        payload: Dict[str, Any] = {
            "claim_id": claim_id,
            "original_intent_id": original_intent_id,
            "original_principal_id": original_principal_id,
            "new_intent_id": new_intent_id,
            "objective": objective,
            "scope": scope.to_dict(),
        }
        if justification:
            payload["justification"] = justification
        return self._make(MessageType.INTENT_CLAIM.value, session_id, payload)

    # ================================================================
    #  Operation layer
    # ================================================================

    def propose_op(
        self,
        session_id: str,
        op_id: str,
        intent_id: str,
        target: str,
        op_kind: str,
    ) -> Dict[str, Any]:
        """Propose an operation (Section 16.1)."""
        return self._make(MessageType.OP_PROPOSE.value, session_id, {
            "op_id": op_id,
            "intent_id": intent_id,
            "target": target,
            "op_kind": op_kind,
        })

    def commit_op(
        self,
        session_id: str,
        op_id: str,
        intent_id: str,
        target: str,
        op_kind: str,
        state_ref_before: Optional[str] = None,
        state_ref_after: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Commit an operation (Section 16.2)."""
        return self._make(MessageType.OP_COMMIT.value, session_id, {
            "op_id": op_id,
            "intent_id": intent_id,
            "target": target,
            "op_kind": op_kind,
            "state_ref_before": state_ref_before,
            "state_ref_after": state_ref_after,
        })

    def batch_commit_op(
        self,
        session_id: str,
        batch_id: str,
        operations: List[Dict[str, Any]],
        atomicity: str = "all_or_nothing",
        intent_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Commit or propose a batch of operations (Section 16.8)."""
        payload: Dict[str, Any] = {
            "batch_id": batch_id,
            "atomicity": atomicity,
            "operations": operations,
        }
        if intent_id is not None:
            payload["intent_id"] = intent_id
        if summary:
            payload["summary"] = summary
        return self._make(MessageType.OP_BATCH_COMMIT.value, session_id, payload)

    def supersede_op(
        self,
        session_id: str,
        op_id: str,
        supersedes_op_id: str,
        target: str,
        intent_id: Optional[str] = None,
        reason: Optional[str] = None,
        state_ref_after: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Supersede a previously committed operation (Section 16.5)."""
        payload: Dict[str, Any] = {
            "op_id": op_id,
            "supersedes_op_id": supersedes_op_id,
            "target": target,
        }
        if intent_id:
            payload["intent_id"] = intent_id
        if reason:
            payload["reason"] = reason
        if state_ref_after:
            payload["state_ref_after"] = state_ref_after
        return self._make(MessageType.OP_SUPERSEDE.value, session_id, payload)

    # ================================================================
    #  Conflict layer
    # ================================================================

    def report_conflict(
        self,
        session_id: str,
        conflict_id: str,
        category: str,
        severity: str,
        principal_a: str,
        principal_b: str,
        intent_a: str,
        intent_b: str,
    ) -> Dict[str, Any]:
        """Report a conflict (Section 17.1)."""
        return self._make(MessageType.CONFLICT_REPORT.value, session_id, {
            "conflict_id": conflict_id,
            "category": category,
            "severity": severity,
            "principal_a": principal_a,
            "principal_b": principal_b,
            "intent_a": intent_a,
            "intent_b": intent_b,
        })

    def ack_conflict(
        self,
        session_id: str,
        conflict_id: str,
        ack_type: str = "seen",
    ) -> Dict[str, Any]:
        """Acknowledge a conflict (Section 17.3)."""
        return self._make(MessageType.CONFLICT_ACK.value, session_id, {
            "conflict_id": conflict_id,
            "ack_type": ack_type,
        })

    def escalate_conflict(
        self,
        session_id: str,
        conflict_id: str,
        escalate_to: str,
        reason: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Escalate a conflict (Section 17.5)."""
        payload: Dict[str, Any] = {
            "conflict_id": conflict_id,
            "escalate_to": escalate_to,
            "reason": reason,
        }
        if context:
            payload["context"] = context
        return self._make(MessageType.CONFLICT_ESCALATE.value, session_id, payload)

    def resolve_conflict(
        self,
        session_id: str,
        conflict_id: str,
        decision: str,
        rationale: Optional[str] = None,
        outcome: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve a conflict (Section 17.7)."""
        payload: Dict[str, Any] = {
            "conflict_id": conflict_id,
            "decision": decision,
        }
        if rationale:
            payload["rationale"] = rationale
        if outcome:
            payload["outcome"] = outcome
        return self._make(MessageType.RESOLUTION.value, session_id, payload)
