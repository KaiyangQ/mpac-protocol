"""Specialized tests for v0.1.13 Backend Health Monitoring.

Covers 12 scenarios:
1. HELLO with backend declaration stores backend info in ParticipantInfo
2. HEARTBEAT with backend_health updates tracked provider status
3. Degraded provider emits backend_alert (on_degraded=warn)
4. Down provider emits backend_alert (on_down=suspend_and_claim) and suspends intents
5. Model switch with allowed provider passes validation
6. Model switch with disallowed provider returns BACKEND_SWITCH_DENIED
7. auto_switch=forbidden rejects any model switch
8. SESSION_INFO includes backend_health_policy in liveness_policy
9. No alert emitted when provider status unchanged (repeat heartbeat)
10. Policy disabled (enabled=false) suppresses alerts
11. No backend_health in heartbeat — no alerts, no errors
12. Provider recovery: down → operational clears suspension concern
"""
from mpac.coordinator import SessionCoordinator
from mpac.models import (
    ErrorCode,
    IntentState,
    MessageType,
    Scope,
)
from mpac.participant import Participant


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

BACKEND_HEALTH_POLICY = {
    "enabled": True,
    "check_source": "https://aistatus.cc/api/check",
    "check_interval_sec": 60,
    "on_degraded": "warn",
    "on_down": "suspend_and_claim",
    "auto_switch": "allowed",
    "allowed_providers": ["anthropic", "openai", "google"],
}

ALICE_BACKEND = {"model_id": "anthropic/claude-sonnet-4.6", "provider": "anthropic"}
BOB_BACKEND = {"model_id": "openai/gpt-4o", "provider": "openai"}

SID = "test-backend-health"


def _make_session(sid=SID, policy=None):
    """Create a coordinator with backend health policy."""
    return SessionCoordinator(
        sid,
        backend_health_policy=policy if policy is not None else BACKEND_HEALTH_POLICY,
    )


def _join(coord, participant, sid=SID, backend=None):
    """Join a participant to the session."""
    responses = coord.process_message(participant.hello(sid, backend=backend))
    return responses


def _hb(coord, participant, sid=SID, status="idle", active_intent_id=None, summary=None, backend_health=None):
    """Send a heartbeat."""
    msg = participant.heartbeat(sid, status, active_intent_id, summary, backend_health)
    return coord.process_message(msg)


# ---------------------------------------------------------------------------
#  1. HELLO with backend declaration
# ---------------------------------------------------------------------------

class TestHelloBackendDeclaration:
    def test_backend_stored_in_participant_info(self):
        """HELLO with backend field stores model_id and provider in ParticipantInfo."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        info = coord.participants["agent:alice"]
        assert info.backend_model_id == "anthropic/claude-sonnet-4.6"
        assert info.backend_provider == "anthropic"

    def test_hello_without_backend_leaves_none(self):
        """HELLO without backend field leaves backend fields as None/default."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice)

        info = coord.participants["agent:alice"]
        assert info.backend_model_id is None
        assert info.backend_provider is None
        assert info.backend_provider_status == "unknown"


# ---------------------------------------------------------------------------
#  2. HEARTBEAT with backend_health updates tracking
# ---------------------------------------------------------------------------

class TestHeartbeatBackendHealth:
    def test_provider_status_updated(self):
        """backend_health in heartbeat updates ParticipantInfo.backend_provider_status."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:00:00Z",
        })

        info = coord.participants["agent:alice"]
        assert info.backend_provider_status == "operational"


# ---------------------------------------------------------------------------
#  3. Degraded → backend_alert (warn)
# ---------------------------------------------------------------------------

class TestDegradedAlert:
    def test_degraded_emits_backend_alert(self):
        """on_degraded=warn emits a COORDINATOR_STATUS(backend_alert) without suspending intents."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        # Set baseline status to operational
        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:00:00Z",
        })

        # Create an intent
        scope = Scope(kind="file_set", resources=["src/main.py"])
        coord.process_message(alice.announce_intent(SID, "intent-1", "Fix main", scope))

        # Report degraded
        responses = _hb(coord, alice, status="working", active_intent_id="intent-1", backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "degraded",
            "status_detail": "Elevated error rates",
            "checked_at": "2026-04-07T10:01:00Z",
        })

        # Should emit backend_alert
        alerts = [r for r in responses if r["message_type"] == "COORDINATOR_STATUS"]
        assert len(alerts) >= 1
        alert = alerts[0]
        assert alert["payload"]["event"] == "backend_alert"
        assert alert["payload"]["affected_principal"] == "agent:alice"
        assert alert["payload"]["backend_detail"]["provider_status"] == "degraded"

        # Intent should NOT be suspended (on_degraded=warn, not suspend_and_claim)
        intent = coord.intents["intent-1"]
        assert intent.state_machine.current_state == IntentState.ACTIVE


# ---------------------------------------------------------------------------
#  4. Down → backend_alert + suspend_and_claim
# ---------------------------------------------------------------------------

class TestDownSuspendAndClaim:
    def test_down_suspends_active_intent(self):
        """on_down=suspend_and_claim emits backend_alert AND suspends the agent's active intents."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:00:00Z",
        })

        scope = Scope(kind="file_set", resources=["src/main.py"])
        coord.process_message(alice.announce_intent(SID, "intent-1", "Fix main", scope))

        # Report down
        responses = _hb(coord, alice, status="blocked", active_intent_id="intent-1", backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "down",
            "status_detail": "Major outage",
            "checked_at": "2026-04-07T10:01:00Z",
        })

        # Should have backend_alert
        alert_msgs = [r for r in responses if r["message_type"] == "COORDINATOR_STATUS"]
        assert len(alert_msgs) >= 1

        # Intent should be suspended
        intent = coord.intents["intent-1"]
        assert intent.state_machine.current_state == IntentState.SUSPENDED


# ---------------------------------------------------------------------------
#  5. Model switch with allowed provider
# ---------------------------------------------------------------------------

class TestModelSwitchAllowed:
    def test_switch_to_allowed_provider_passes(self):
        """Switching to a provider in allowed_providers does not return BACKEND_SWITCH_DENIED."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:00:00Z",
        })

        # Switch to google (in allowed_providers)
        responses = _hb(coord, alice, backend_health={
            "model_id": "google/gemini-2.5-pro",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:01:00Z",
            "switched_from": "anthropic/claude-sonnet-4.6",
            "switch_reason": "provider_down",
        })

        errors = [r for r in responses if r["message_type"] == "PROTOCOL_ERROR"]
        assert len(errors) == 0

        # Backend provider should be updated
        info = coord.participants["agent:alice"]
        assert info.backend_model_id == "google/gemini-2.5-pro"


# ---------------------------------------------------------------------------
#  6. Model switch with disallowed provider → BACKEND_SWITCH_DENIED
# ---------------------------------------------------------------------------

class TestModelSwitchDenied:
    def test_switch_to_disallowed_provider_returns_error(self):
        """Switching to a provider NOT in allowed_providers returns BACKEND_SWITCH_DENIED."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:00:00Z",
        })

        # Switch to deepseek (NOT in allowed_providers)
        responses = _hb(coord, alice, backend_health={
            "model_id": "deepseek/deepseek-v3",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:01:00Z",
            "switched_from": "anthropic/claude-sonnet-4.6",
            "switch_reason": "manual",
        })

        errors = [r for r in responses if r["message_type"] == "PROTOCOL_ERROR"]
        assert len(errors) == 1
        err_payload = errors[0]["payload"]
        assert err_payload["error_code"] == "BACKEND_SWITCH_DENIED"
        assert "deepseek" in err_payload["description"]


# ---------------------------------------------------------------------------
#  7. auto_switch=forbidden rejects any model switch
# ---------------------------------------------------------------------------

class TestAutoSwitchForbidden:
    def test_forbidden_rejects_switch(self):
        """auto_switch=forbidden returns BACKEND_SWITCH_DENIED for any switched_from."""
        policy = {**BACKEND_HEALTH_POLICY, "auto_switch": "forbidden"}
        coord = _make_session(policy=policy)
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:00:00Z",
        })

        # Try switching to an allowed provider — still forbidden
        responses = _hb(coord, alice, backend_health={
            "model_id": "openai/gpt-4o",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:01:00Z",
            "switched_from": "anthropic/claude-sonnet-4.6",
            "switch_reason": "provider_down",
        })

        errors = [r for r in responses if r["message_type"] == "PROTOCOL_ERROR"]
        assert len(errors) == 1
        err_payload = errors[0]["payload"]
        assert err_payload["error_code"] == "BACKEND_SWITCH_DENIED"
        assert "forbidden" in err_payload["description"].lower()


# ---------------------------------------------------------------------------
#  8. SESSION_INFO includes backend_health_policy
# ---------------------------------------------------------------------------

class TestSessionInfoPolicy:
    def test_session_info_contains_backend_health_policy(self):
        """SESSION_INFO response includes backend_health_policy in liveness_policy."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        responses = _join(coord, alice, backend=ALICE_BACKEND)

        # Find SESSION_INFO response
        session_infos = [r for r in responses if r["message_type"] == "SESSION_INFO"]
        assert len(session_infos) == 1
        payload = session_infos[0]["payload"]

        liveness = payload.get("liveness_policy", {})
        bhp = liveness.get("backend_health_policy")
        assert bhp is not None
        assert bhp["enabled"] is True
        assert bhp["on_degraded"] == "warn"
        assert bhp["on_down"] == "suspend_and_claim"


# ---------------------------------------------------------------------------
#  9. No alert on repeated same status
# ---------------------------------------------------------------------------

class TestNoAlertOnRepeat:
    def test_repeated_degraded_no_second_alert(self):
        """Sending degraded twice in a row only emits one alert (status unchanged)."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:00:00Z",
        })

        # First degraded → should alert
        r1 = _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "degraded",
            "checked_at": "2026-04-07T10:01:00Z",
        })
        alerts1 = [r for r in r1 if
                   r["message_type"] == "COORDINATOR_STATUS"]
        assert len(alerts1) >= 1

        # Second degraded → should NOT alert again
        r2 = _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "degraded",
            "checked_at": "2026-04-07T10:02:00Z",
        })
        alerts2 = [r for r in r2 if
                   r["message_type"] == "COORDINATOR_STATUS"]
        assert len(alerts2) == 0


# ---------------------------------------------------------------------------
#  10. Policy disabled suppresses alerts
# ---------------------------------------------------------------------------

class TestPolicyDisabled:
    def test_disabled_policy_no_alerts(self):
        """When backend_health_policy.enabled=false, no alerts are emitted."""
        policy = {**BACKEND_HEALTH_POLICY, "enabled": False}
        coord = _make_session(policy=policy)
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:00:00Z",
        })

        scope = Scope(kind="file_set", resources=["src/main.py"])
        coord.process_message(alice.announce_intent(SID, "intent-1", "Fix main", scope))

        responses = _hb(coord, alice, status="blocked", backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "down",
            "checked_at": "2026-04-07T10:01:00Z",
        })

        alerts = [r for r in responses if
                  r["message_type"] == "COORDINATOR_STATUS"]
        assert len(alerts) == 0

        # Intent should remain active
        assert coord.intents["intent-1"].state_machine.current_state == IntentState.ACTIVE


# ---------------------------------------------------------------------------
#  11. No backend_health in heartbeat — no alerts, no errors
# ---------------------------------------------------------------------------

class TestNoBackendHealth:
    def test_heartbeat_without_backend_health(self):
        """A plain heartbeat (no backend_health) produces no backend-related responses."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        responses = _hb(coord, alice, status="idle")
        alerts = [r for r in responses if
                  r["message_type"] == "COORDINATOR_STATUS"]
        errors = [r for r in responses if r["message_type"] == "PROTOCOL_ERROR"]
        assert len(alerts) == 0
        assert len(errors) == 0


# ---------------------------------------------------------------------------
#  12. Provider recovery: down → operational
# ---------------------------------------------------------------------------

class TestProviderRecovery:
    def test_recovery_after_down(self):
        """After reporting down then operational, the participant is tracked as operational."""
        coord = _make_session()
        alice = Participant("agent:alice", "agent", "Alice", ["contributor"])
        _join(coord, alice, backend=ALICE_BACKEND)

        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:00:00Z",
        })

        # Go down
        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "down",
            "checked_at": "2026-04-07T10:01:00Z",
        })
        assert coord.participants["agent:alice"].backend_provider_status == "down"

        # Recover
        _hb(coord, alice, backend_health={
            "model_id": "anthropic/claude-sonnet-4.6",
            "provider_status": "operational",
            "checked_at": "2026-04-07T10:05:00Z",
        })
        assert coord.participants["agent:alice"].backend_provider_status == "operational"
