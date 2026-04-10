"""MPAC reference implementation."""

from .models import (
    Principal,
    Sender,
    Watermark,
    Scope,
    Basis,
    Outcome,
    GovernancePolicy,
    LivenessPolicy,
    Session,
    MessageType,
    IntentState,
    OperationState,
    ConflictState,
    ScopeKind,
    SecurityProfile,
    ComplianceProfile,
    Role,
    ConflictCategory,
    Severity,
    Decision,
    ErrorCode,
)

from .envelope import MessageEnvelope
from .watermark import LamportClock
from .scope import scope_overlap, normalize_path
from .state_machines import (
    IntentStateMachine,
    OperationStateMachine,
    ConflictStateMachine,
)
from .coordinator import SessionCoordinator
from .participant import Participant

__all__ = [
    # Models
    "Principal",
    "Sender",
    "Watermark",
    "Scope",
    "Basis",
    "Outcome",
    "GovernancePolicy",
    "LivenessPolicy",
    "Session",
    "MessageType",
    "IntentState",
    "OperationState",
    "ConflictState",
    "ScopeKind",
    "SecurityProfile",
    "ComplianceProfile",
    "Role",
    "ConflictCategory",
    "Severity",
    "Decision",
    "ErrorCode",
    # Components
    "MessageEnvelope",
    "LamportClock",
    "scope_overlap",
    "normalize_path",
    "IntentStateMachine",
    "OperationStateMachine",
    "ConflictStateMachine",
    "SessionCoordinator",
    "Participant",
]

__version__ = "0.1.13"
