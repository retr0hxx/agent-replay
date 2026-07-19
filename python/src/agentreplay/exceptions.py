"""Exception hierarchy for agent-replay."""

from __future__ import annotations


class AgentReplayError(Exception):
    """Base class so users can `except AgentReplayError` to catch any library error."""


class CassetteMissError(AgentReplayError):
    """Raised in replay mode when no matching interaction is found and on_miss='error'."""


class DivergenceError(AgentReplayError):
    """Raised when divergence='error' and a request divergence is detected."""


class NonTargetHostError(AgentReplayError):
    """Raised when a request is made to a host that is neither a known LLM provider nor listed in allow_passthrough_hosts."""


class CassetteFormatError(AgentReplayError):
    """Raised when a cassette file is malformed."""
