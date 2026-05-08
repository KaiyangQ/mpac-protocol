"""Structured intent semantics duplicate-candidate checks.

The coordinator must not decide that two natural-language objectives are
"the same." It can, however, surface an advisory when structured hints make
duplicate work likely, so the deferred agent re-reads and verifies before
writing.
"""
from __future__ import annotations

from mpac_protocol.core.coordinator import SessionCoordinator
from mpac_protocol.core.models import MessageType, Scope
from mpac_protocol.core.participant import Participant


def _make(pid: str, session_id: str):
    p = Participant(
        principal_id=pid,
        principal_type="agent",
        display_name=pid,
        roles=["contributor"],
        capabilities=["intent.broadcast"],
    )
    return p, p.hello(session_id)


def _stale_payload(responses):
    errors = [
        r.get("payload", {})
        for r in responses
        if r.get("message_type") == MessageType.PROTOCOL_ERROR.value
    ]
    assert len(errors) == 1
    assert errors[0].get("error_code") == "STALE_INTENT"
    return errors[0]


def test_same_file_race_with_same_structured_symbol_flags_duplicate_candidate():
    session_id = "sess-semantics-1"
    coord = SessionCoordinator(session_id, security_profile="open")
    alice, hello_alice = _make("alice", session_id)
    bob, hello_bob = _make("bob", session_id)
    coord.process_message(hello_alice)
    coord.process_message(hello_bob)

    alice_scope = Scope(
        kind="file_set",
        resources=["notes_app/db.py"],
        extensions={
            "intent_semantics": {
                "action": "add_symbol",
                "targets": [
                    {"file": "notes_app/db.py", "symbol": "notes_app.db.sort_by_recent"}
                ],
                "postconditions": [
                    {
                        "kind": "behavior",
                        "text": "returns notes sorted by created_at descending",
                    }
                ],
            }
        },
    )
    bob_scope = Scope(
        kind="file_set",
        resources=["notes_app/db.py"],
        extensions={
            "intent_semantics": {
                "action": "add_symbol",
                "targets": [
                    {"file": "notes_app/db.py", "symbol": "notes_app.db.sort_by_recent"}
                ],
                "postconditions": [
                    {
                        "kind": "behavior",
                        "text": "returns notes sorted by created_at descending",
                    }
                ],
            }
        },
    )

    coord.process_message(alice.announce_intent(
        session_id, "intent-alice", "add sort_by_recent", alice_scope
    ))
    payload = _stale_payload(coord.process_message(bob.announce_intent(
        session_id, "intent-bob", "add recent sorter", bob_scope
    )))

    candidate = payload.get("duplicate_candidate")
    assert candidate is not None
    assert candidate["candidate"] is True
    assert candidate["confidence"] == "high"
    assert candidate["reason"] == "same_symbol_and_action"
    assert candidate["other_intent_id"] == "intent-alice"
    assert candidate["matched_symbols"] == ["notes_app.db.sort_by_recent"]
    assert candidate["verification_required"] is True


def test_same_file_race_with_different_symbols_does_not_flag_duplicate_candidate():
    session_id = "sess-semantics-2"
    coord = SessionCoordinator(session_id, security_profile="open")
    alice, hello_alice = _make("alice", session_id)
    bob, hello_bob = _make("bob", session_id)
    coord.process_message(hello_alice)
    coord.process_message(hello_bob)

    coord.process_message(alice.announce_intent(
        session_id,
        "intent-alice",
        "add sorter",
        Scope(
            kind="file_set",
            resources=["notes_app/db.py"],
            extensions={
                "intent_semantics": {
                    "action": "add_symbol",
                    "targets": [{"file": "notes_app/db.py", "symbol": "notes_app.db.sort_by_recent"}],
                }
            },
        ),
    ))
    payload = _stale_payload(coord.process_message(bob.announce_intent(
        session_id,
        "intent-bob",
        "add finder",
        Scope(
            kind="file_set",
            resources=["notes_app/db.py"],
            extensions={
                "intent_semantics": {
                    "action": "add_symbol",
                    "targets": [{"file": "notes_app/db.py", "symbol": "notes_app.db.find_by_title"}],
                }
            },
        ),
    )))

    assert "duplicate_candidate" not in payload


def test_affects_symbols_alone_can_flag_medium_confidence_duplicate_candidate():
    session_id = "sess-semantics-3"
    coord = SessionCoordinator(session_id, security_profile="open")
    alice, hello_alice = _make("alice", session_id)
    bob, hello_bob = _make("bob", session_id)
    coord.process_message(hello_alice)
    coord.process_message(hello_bob)

    scope = Scope(
        kind="file_set",
        resources=["notes_app/db.py"],
        extensions={"affects_symbols": ["notes_app.db.sort_by_recent"]},
    )
    coord.process_message(alice.announce_intent(
        session_id, "intent-alice", "add sorter", scope
    ))
    payload = _stale_payload(coord.process_message(bob.announce_intent(
        session_id, "intent-bob", "add sorter", scope
    )))

    candidate = payload.get("duplicate_candidate")
    assert candidate is not None
    assert candidate["confidence"] == "medium"
    assert candidate["reason"] == "same_symbol"
    assert candidate["matched_symbols"] == ["notes_app.db.sort_by_recent"]


def test_objective_symbol_hint_flags_duplicate_when_agent_omits_semantics():
    """Relay agents sometimes omit structured hints but put the function
    name in the objective. Keep obvious same-function races discoverable.
    """
    session_id = "sess-semantics-objective"
    coord = SessionCoordinator(session_id, security_profile="open")
    alice, hello_alice = _make("alice", session_id)
    bob, hello_bob = _make("bob", session_id)
    coord.process_message(hello_alice)
    coord.process_message(hello_bob)

    plain_scope = Scope(kind="file_set", resources=["notes_app/db.py"])
    coord.process_message(alice.announce_intent(
        session_id,
        "intent-alice",
        "add sort_by_recent() function",
        plain_scope,
    ))
    payload = _stale_payload(coord.process_message(bob.announce_intent(
        session_id,
        "intent-bob",
        "add sort_by_recent function to db.py",
        plain_scope,
    )))

    candidate = payload.get("duplicate_candidate")
    assert candidate is not None
    assert candidate["reason"] == "same_symbol"
    assert candidate["matched_symbols"] == ["notes_app.db.sort_by_recent"]


def test_same_postcondition_without_symbol_flags_duplicate_candidate():
    session_id = "sess-semantics-4"
    coord = SessionCoordinator(session_id, security_profile="open")
    alice, hello_alice = _make("alice", session_id)
    bob, hello_bob = _make("bob", session_id)
    coord.process_message(hello_alice)
    coord.process_message(hello_bob)

    semantics = {
        "action": "add_behavior",
        "postconditions": [
            {
                "kind": "behavior",
                "text": "returns notes sorted by created_at descending",
            }
        ],
    }

    coord.process_message(alice.announce_intent(
        session_id,
        "intent-alice",
        "add recent sorting behavior",
        Scope(
            kind="file_set",
            resources=["notes_app/db.py"],
            extensions={"intent_semantics": semantics},
        ),
    ))
    payload = _stale_payload(coord.process_message(bob.announce_intent(
        session_id,
        "intent-bob",
        "make notes sort newest first",
        Scope(
            kind="file_set",
            resources=["notes_app/db.py"],
            extensions={"intent_semantics": semantics},
        ),
    )))

    candidate = payload.get("duplicate_candidate")
    assert candidate is not None
    assert candidate["reason"] == "same_postcondition_and_action"
    assert candidate["matched_symbols"] == []
    assert candidate["matched_postconditions"] == [
        "returns notes sorted by created_at descending"
    ]
