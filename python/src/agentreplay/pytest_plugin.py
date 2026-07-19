"""pytest plugin: fixture ``agentreplay`` and marker ``@pytest.mark.agentreplay(...)``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

from .cassette import Cassette


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "agentreplay(**kwargs): configure the agent-replay cassette for this test.",
    )


def _cassette_dir(config) -> Path:
    return Path(config.rootpath) / "tests" / "cassettes"


def _default_name(nodeid: str) -> str:
    return nodeid.replace("/", "__").replace("::", "__") + ".jsonl"


if pytest is not None:

    @pytest.fixture
    def agentreplay(request) -> Iterator[Cassette]:
        marker = request.node.get_closest_marker("agentreplay")
        kwargs: dict[str, Any] = dict(marker.kwargs) if marker else {}
        path = kwargs.pop("path", None)
        if path is None:
            path = str(_cassette_dir(request.config) / _default_name(request.node.nodeid))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        c = Cassette(path, **kwargs)
        c.__enter__()
        try:
            yield c
        finally:
            c.__exit__(None, None, None)
