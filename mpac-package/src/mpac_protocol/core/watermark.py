"""Lamport clock implementation for MPAC."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Watermark


class LamportClock:
    """Implements a Lamport logical clock."""

    def __init__(self, initial_value: int = 0):
        """Initialize clock with optional initial value."""
        self._value = initial_value

    @property
    def value(self) -> int:
        """Get current clock value."""
        return self._value

    def tick(self) -> int:
        """Increment clock and return new value."""
        self._value += 1
        return self._value

    def update(self, received: int) -> int:
        """Update clock based on received value.

        Implements: max(local, received) + 1

        Args:
            received: The clock value received in a message

        Returns:
            The new clock value
        """
        self._value = max(self._value, received) + 1
        return self._value

    def reset(self, value: int = 0):
        """Reset clock to a specific value (for testing)."""
        self._value = value

    def create_watermark(self) -> "Watermark":
        """Create a spec-compliant Watermark object.

        Returns:
            Watermark with kind=lamport_clock and current ticked value
        """
        from .models import Watermark
        return Watermark(kind="lamport_clock", value=self.tick())
