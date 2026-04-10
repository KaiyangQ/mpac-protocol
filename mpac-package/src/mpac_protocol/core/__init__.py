"""MPAC protocol core — copied from reference implementation."""

from .models import (
    Principal, Sender, Watermark, Scope, Basis, Outcome,
    GovernancePolicy, LivenessPolicy, Session,
    MessageType, IntentState, OperationState, ConflictState,
    ScopeKind, SecurityProfile, ComplianceProfile, Role,
    ConflictCategory, Severity, Decision, ErrorCode,
)
from .envelope import MessageEnvelope
from .watermark import LamportClock
from .scope import scope_overlap, normalize_path
from .state_machines import IntentStateMachine, OperationStateMachine, ConflictStateMachine
from .coordinator import SessionCoordinator
from .participant import Participant
