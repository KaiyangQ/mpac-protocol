"""Tests for Authenticated profile + multi-session mode (Phase 3).

Covers the Phase 2 coordinator.py and server.py changes:

- ``VerifyResult`` dataclass and ``credential_verifier`` hook on
  ``SessionCoordinator`` (Section 23.1.4).
- ``MPACServer`` multi_session mode with lazy session creation and
  per-session state isolation.
- Backward compatibility of the single-session / Open profile path —
  existing mpac 0.1.0 callers must see no behavior change.
- The pre-existing HELLO-first gate, to verify the invariant that the
  Authenticated profile builds on.

These tests do NOT spin up a real WebSocket server. They exercise
``SessionCoordinator.process_message`` and the ``MPACServer`` attribute
surface directly — which is enough for the protocol-layer invariants.
End-to-end WebSocket tests live in ``mpac-mcp/tests``.
"""
from __future__ import annotations

import pytest

from mpac_protocol.core.coordinator import (
    CredentialVerifier,
    SessionCoordinator,
    VerifyResult,
)
from mpac_protocol.core.participant import Participant
from mpac_protocol.server import MPACServer


# ─── Helpers ─────────────────────────────────────────────────


def _make_participant(principal_id: str, *, credential=None) -> Participant:
    return Participant(
        principal_id=principal_id,
        principal_type="agent",
        display_name=principal_id,
        roles=["contributor"],
        capabilities=["intent.broadcast", "op.commit"],
        credential=credential,
    )


def _hello(principal_id: str, session_id: str, *, credential=None) -> dict:
    """Build a HELLO envelope dict via Participant (mimics bridge behavior)."""
    return _make_participant(principal_id, credential=credential).hello(session_id)


def _pick_type(responses, message_type):
    for r in responses:
        if r.get("message_type") == message_type:
            return r
    return None


# ─── VerifyResult dataclass API ──────────────────────────────


class TestVerifyResult:
    def test_accept_factory_defaults(self):
        r = VerifyResult.accept()
        assert r.accepted is True
        assert r.reason is None
        assert r.granted_roles is None

    def test_accept_with_granted_roles(self):
        r = VerifyResult.accept(granted_roles=["contributor", "reviewer"])
        assert r.accepted is True
        assert r.granted_roles == ["contributor", "reviewer"]

    def test_reject_factory(self):
        r = VerifyResult.reject("bad token")
        assert r.accepted is False
        assert r.reason == "bad token"


# ─── Single-session backward compatibility ───────────────────


class TestSingleSessionBackwardCompat:
    def test_back_compat_shortcuts_exposed(self):
        """self.coordinator/file_store/connections alias the lone session."""
        srv = MPACServer(session_id="demo", host="127.0.0.1", port=9999)
        assert srv.multi_session is False
        assert srv.session_id == "demo"
        assert srv.coordinator is srv._sessions["demo"].coordinator
        assert srv.file_store is srv._sessions["demo"].file_store
        assert srv.connections is srv._sessions["demo"].connections
        assert srv.ws_to_principal is srv._sessions["demo"].ws_to_principal

    def test_missing_session_id_raises(self):
        with pytest.raises(ValueError, match="requires a session_id"):
            MPACServer()

    def test_open_profile_hello_without_credential_succeeds(self):
        """Open profile ignores the credential field — HELLO works with or without it."""
        srv = MPACServer(session_id="demo", host="127.0.0.1", port=9999)
        responses = srv.coordinator.process_message(_hello("alice", "demo"))
        assert _pick_type(responses, "SESSION_INFO") is not None

    def test_session_summary_default_arg_in_single_mode(self):
        """In single-session mode session_id is optional — defaults to the lone session."""
        srv = MPACServer(session_id="demo", host="127.0.0.1", port=9999)
        summary = srv.session_summary()
        assert summary["session_id"] == "demo"


# ─── Multi-session isolation ─────────────────────────────────


class TestMultiSessionIsolation:
    def test_rejects_session_id_in_multi_mode(self):
        with pytest.raises(ValueError, match="must NOT be given a session_id"):
            MPACServer(session_id="demo", multi_session=True)

    def test_starts_with_no_sessions(self):
        srv = MPACServer(multi_session=True, host="127.0.0.1", port=9999)
        assert srv._sessions == {}
        assert srv.session_id is None

    def test_lazy_session_creation_is_independent(self):
        srv = MPACServer(multi_session=True, host="127.0.0.1", port=9999)
        a = srv._get_or_create_session("proj-alpha")
        b = srv._get_or_create_session("proj-beta")
        assert "proj-alpha" in srv._sessions
        assert "proj-beta" in srv._sessions
        assert a is not b
        assert a.coordinator is not b.coordinator
        assert a.file_store is not b.file_store
        assert a.connections is not b.connections

    def test_get_or_create_is_idempotent(self):
        srv = MPACServer(multi_session=True, host="127.0.0.1", port=9999)
        first = srv._get_or_create_session("proj-alpha")
        second = srv._get_or_create_session("proj-alpha")
        assert first is second

    def test_data_isolation_abcd_invariant(self):
        """The core ABCD invariant: messages to session A don't leak into session B."""
        srv = MPACServer(multi_session=True, host="127.0.0.1", port=9999)
        state_a = srv._get_or_create_session("proj-alpha")
        state_b = srv._get_or_create_session("proj-beta")

        # Alice joins proj-alpha; Bob joins proj-beta
        state_a.coordinator.process_message(_hello("alice", "proj-alpha"))
        state_b.coordinator.process_message(_hello("bob", "proj-beta"))

        summary_a = srv.session_summary("proj-alpha")
        summary_b = srv.session_summary("proj-beta")

        pids_a = sorted(p["principal_id"] for p in summary_a["participants"])
        pids_b = sorted(p["principal_id"] for p in summary_b["participants"])
        assert pids_a == ["alice"], f"proj-alpha should only have alice, got {pids_a}"
        assert pids_b == ["bob"], f"proj-beta should only have bob, got {pids_b}"

    def test_session_summary_requires_session_id_in_multi_mode(self):
        srv = MPACServer(multi_session=True, host="127.0.0.1", port=9999)
        with pytest.raises(ValueError, match="requires a session_id when multi_session"):
            srv.session_summary()

    def test_session_summary_unknown_session_returns_error_stub(self):
        srv = MPACServer(multi_session=True, host="127.0.0.1", port=9999)
        summary = srv.session_summary("ghost")
        assert summary.get("error") == "session_not_found"
        assert summary.get("participant_count") == 0

    def test_extract_session_id_from_url_path(self):
        srv = MPACServer(multi_session=True, host="127.0.0.1", port=9999)
        assert srv._extract_session_id("/session/proj-alpha") == "proj-alpha"
        assert srv._extract_session_id("/session/proj-alpha/sub") == "proj-alpha"
        assert srv._extract_session_id("/session/proj-alpha?k=v") == "proj-alpha"
        assert srv._extract_session_id("/other/x") is None
        assert srv._extract_session_id("") is None
        assert srv._extract_session_id("/session/") is None


# ─── Credential verifier hook (Section 23.1.4) ───────────────


def _accept_with_contributor(cred, session_id):
    """Default verifier for tests — accepts anything, grants contributor role."""
    return VerifyResult.accept(granted_roles=["contributor"])


class TestCredentialVerifier:
    def test_existence_check_runs_before_verifier(self):
        """Missing credential → CREDENTIAL_REJECTED even without a verifier."""
        coord = SessionCoordinator("demo", security_profile="authenticated")
        responses = coord.process_message(_hello("alice", "demo", credential=None))
        err = _pick_type(responses, "PROTOCOL_ERROR")
        assert err is not None
        assert err["payload"]["error_code"] == "CREDENTIAL_REJECTED"

    def test_verifier_accepts_valid_credential(self):
        coord = SessionCoordinator(
            "demo",
            security_profile="authenticated",
            credential_verifier=_accept_with_contributor,
        )
        env = _hello(
            "alice", "demo",
            credential={"type": "bearer_token", "value": "any-value"},
        )
        responses = coord.process_message(env)
        assert _pick_type(responses, "SESSION_INFO") is not None

    def test_verifier_rejects_with_reason(self):
        def always_reject(cred, session_id):
            return VerifyResult.reject("no such token in the table")

        coord = SessionCoordinator(
            "demo",
            security_profile="authenticated",
            credential_verifier=always_reject,
        )
        env = _hello(
            "alice", "demo",
            credential={"type": "bearer_token", "value": "bad"},
        )
        responses = coord.process_message(env)
        err = _pick_type(responses, "PROTOCOL_ERROR")
        assert err is not None
        assert err["payload"]["error_code"] == "CREDENTIAL_REJECTED"
        assert "no such token" in err["payload"]["description"]

    def test_cross_session_rejection_abcd_invariant(self):
        """Token bound to proj-alpha MUST NOT be able to join proj-beta.

        This is the core security invariant of the Authenticated profile —
        the product-level guarantee that lets "互不相识的两组用户" safely
        share one hosted coordinator.
        """
        def scoped_verifier(cred, session_id):
            if cred.get("value") == "alpha-tok" and session_id == "proj-alpha":
                return VerifyResult.accept(granted_roles=["contributor"])
            if cred.get("value") == "beta-tok" and session_id == "proj-beta":
                return VerifyResult.accept(granted_roles=["contributor"])
            return VerifyResult.reject(
                f"token not authorized for session {session_id!r}"
            )

        # alpha-tok accepted on proj-alpha ✓
        coord_alpha = SessionCoordinator(
            "proj-alpha",
            security_profile="authenticated",
            credential_verifier=scoped_verifier,
        )
        env_ok = _hello(
            "alice", "proj-alpha",
            credential={"type": "bearer_token", "value": "alpha-tok"},
        )
        assert _pick_type(coord_alpha.process_message(env_ok), "SESSION_INFO") is not None

        # beta-tok on proj-alpha → REJECTED (a different attacker, same coordinator)
        coord_alpha2 = SessionCoordinator(
            "proj-alpha",
            security_profile="authenticated",
            credential_verifier=scoped_verifier,
        )
        env_bad = _hello(
            "attacker", "proj-alpha",
            credential={"type": "bearer_token", "value": "beta-tok"},
        )
        err = _pick_type(coord_alpha2.process_message(env_bad), "PROTOCOL_ERROR")
        assert err is not None
        assert err["payload"]["error_code"] == "CREDENTIAL_REJECTED"
        assert "not authorized" in err["payload"]["description"]

    def test_verifier_granted_roles_override_role_policy(self):
        """When the verifier supplies granted_roles, role_policy is bypassed."""
        def verifier_grants_owner(cred, session_id):
            return VerifyResult.accept(granted_roles=["owner"])

        coord = SessionCoordinator(
            "demo",
            security_profile="authenticated",
            credential_verifier=verifier_grants_owner,
        )
        env = _hello(
            "alice", "demo",
            credential={"type": "bearer_token", "value": "tok"},
        )
        responses = coord.process_message(env)
        info = _pick_type(responses, "SESSION_INFO")
        assert info is not None
        assert info["payload"]["granted_roles"] == ["owner"]

    def test_open_profile_ignores_verifier(self):
        """A verifier attached to an Open profile coordinator is NOT called."""
        calls = []

        def tracking_verifier(cred, session_id):
            calls.append((cred, session_id))
            return VerifyResult.reject("should not be called")

        coord = SessionCoordinator(
            "demo",
            security_profile="open",
            credential_verifier=tracking_verifier,
        )
        # HELLO with no credential — open profile accepts it
        responses = coord.process_message(_hello("alice", "demo"))
        assert _pick_type(responses, "SESSION_INFO") is not None
        assert calls == [], f"verifier should not have been called, but was: {calls}"


# ─── HELLO-first gate (pre-existing, re-verified) ────────────


class TestHelloFirstGate:
    def test_unregistered_sender_heartbeat_rejected(self):
        """A principal that never sent HELLO cannot send HEARTBEAT."""
        coord = SessionCoordinator("demo", security_profile="open")
        p = _make_participant("alice")
        env = p.heartbeat("demo")  # skip HELLO
        responses = coord.process_message(env)
        err = _pick_type(responses, "PROTOCOL_ERROR")
        assert err is not None
        assert err["payload"]["error_code"] == "INVALID_REFERENCE"
        assert "must send HELLO" in err["payload"]["description"]

    def test_hello_then_heartbeat_allowed(self):
        """After HELLO registers the principal, subsequent messages are allowed."""
        coord = SessionCoordinator("demo", security_profile="open")
        p = _make_participant("alice")
        coord.process_message(p.hello("demo"))
        responses = coord.process_message(p.heartbeat("demo"))
        assert _pick_type(responses, "PROTOCOL_ERROR") is None
