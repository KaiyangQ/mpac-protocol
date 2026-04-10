"""State machines for MPAC entities."""
from .models import IntentState, OperationState, ConflictState


class IntentStateMachine:
    """State machine for Intent lifecycle."""

    # Valid transitions
    _transitions = {
        IntentState.ANNOUNCED: [IntentState.ACTIVE, IntentState.WITHDRAWN],
        IntentState.ACTIVE: [
            IntentState.EXPIRED,
            IntentState.WITHDRAWN,
            IntentState.SUPERSEDED,
            IntentState.SUSPENDED,
            IntentState.TRANSFERRED,
        ],
        IntentState.EXPIRED: [],
        IntentState.WITHDRAWN: [],
        IntentState.SUPERSEDED: [],
        IntentState.SUSPENDED: [
            IntentState.ACTIVE,
            IntentState.WITHDRAWN,
            IntentState.EXPIRED,
            IntentState.TRANSFERRED,
        ],
        IntentState.TRANSFERRED: [],
    }

    def __init__(self, initial_state: IntentState = IntentState.ANNOUNCED):
        """Initialize with initial state."""
        self.current_state = initial_state

    def transition(self, event: str) -> IntentState:
        """Attempt state transition.

        Args:
            event: Target state name (string form of IntentState)

        Returns:
            New state

        Raises:
            ValueError: If transition is invalid
        """
        try:
            target_state = IntentState[event] if isinstance(event, str) else event
        except (KeyError, AttributeError):
            raise ValueError(f"Unknown target state: {event}")

        if target_state not in self._transitions[self.current_state]:
            raise ValueError(
                f"Invalid transition from {self.current_state.value} to {target_state.value}"
            )

        self.current_state = target_state
        return self.current_state

    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self.current_state in [
            IntentState.EXPIRED,
            IntentState.WITHDRAWN,
            IntentState.SUPERSEDED,
            IntentState.TRANSFERRED,
        ]


class OperationStateMachine:
    """State machine for Operation lifecycle."""

    # Valid transitions
    _transitions = {
        OperationState.PROPOSED: [
            OperationState.COMMITTED,
            OperationState.REJECTED,
            OperationState.ABANDONED,
            OperationState.FROZEN,
        ],
        OperationState.COMMITTED: [OperationState.FROZEN, OperationState.SUPERSEDED],
        OperationState.REJECTED: [],
        OperationState.ABANDONED: [],
        OperationState.FROZEN: [OperationState.PROPOSED, OperationState.REJECTED, OperationState.ABANDONED],
        OperationState.SUPERSEDED: [],
    }

    def __init__(self, initial_state: OperationState = OperationState.PROPOSED):
        """Initialize with initial state."""
        self.current_state = initial_state

    def transition(self, event: str) -> OperationState:
        """Attempt state transition.

        Args:
            event: Target state name (string form of OperationState)

        Returns:
            New state

        Raises:
            ValueError: If transition is invalid
        """
        try:
            target_state = OperationState[event] if isinstance(event, str) else event
        except (KeyError, AttributeError):
            raise ValueError(f"Unknown target state: {event}")

        if target_state not in self._transitions[self.current_state]:
            raise ValueError(
                f"Invalid transition from {self.current_state.value} to {target_state.value}"
            )

        self.current_state = target_state
        return self.current_state

    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self.current_state in [
            OperationState.REJECTED,
            OperationState.ABANDONED,
            OperationState.COMMITTED,
            OperationState.SUPERSEDED,
        ]


class ConflictStateMachine:
    """State machine for Conflict lifecycle."""

    # Valid transitions
    _transitions = {
        ConflictState.OPEN: [
            ConflictState.ACKED,
            ConflictState.ESCALATED,
            ConflictState.DISMISSED,
        ],
        ConflictState.ACKED: [
            ConflictState.RESOLVED,
            ConflictState.ESCALATED,
            ConflictState.DISMISSED,
        ],
        ConflictState.ESCALATED: [
            ConflictState.RESOLVED,
            ConflictState.DISMISSED,
        ],
        ConflictState.DISMISSED: [],
        ConflictState.RESOLVED: [ConflictState.CLOSED],
        ConflictState.CLOSED: [],
    }

    def __init__(self, initial_state: ConflictState = ConflictState.OPEN):
        """Initialize with initial state."""
        self.current_state = initial_state

    def transition(self, event: str) -> ConflictState:
        """Attempt state transition.

        Args:
            event: Target state name (string form of ConflictState)

        Returns:
            New state

        Raises:
            ValueError: If transition is invalid
        """
        try:
            target_state = ConflictState[event] if isinstance(event, str) else event
        except (KeyError, AttributeError):
            raise ValueError(f"Unknown target state: {event}")

        if target_state not in self._transitions[self.current_state]:
            raise ValueError(
                f"Invalid transition from {self.current_state.value} to {target_state.value}"
            )

        self.current_state = target_state
        return self.current_state

    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self.current_state in [ConflictState.DISMISSED, ConflictState.CLOSED]
