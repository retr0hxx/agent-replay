"""agent-replay: record & replay LLM API calls for deterministic agent tests."""

from __future__ import annotations

from .cassette import Cassette, cassette
from .exceptions import (
    AgentReplayError,
    CassetteMissError,
    DivergenceError,
    NonTargetHostError,
    CassetteFormatError,
)
from .divergence import Report

__version__ = "0.1.0"

__all__ = [
    "cassette",
    "Cassette",
    "Report",
    "AgentReplayError",
    "CassetteMissError",
    "DivergenceError",
    "NonTargetHostError",
    "CassetteFormatError",
    "__version__",
]
