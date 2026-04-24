"""MPAC Protocol — Multi-Principal Agent Coordination."""

from .server import MPACServer

try:
    from .agent import MPACAgent
except ImportError:
    # MPACAgent requires the 'anthropic' SDK which is only needed when
    # running a full LLM-backed agent, not when using the coordinator,
    # server, or MCP bridge layers.
    MPACAgent = None  # type: ignore[assignment,misc]

__version__ = "0.1.0"
__all__ = ["MPACServer", "MPACAgent"]
