"""In-house JSON diff used for divergence reports (see implementation-notes §4.2)."""

from __future__ import annotations

from typing import Any


def json_diff(expected: Any, actual: Any, path: str = "") -> list[dict[str, Any]]:
    """Return a flat list of change records.

    Each record: ``{"path": "a.b[0]", "op": "changed"|"added"|"removed",
    "expected": ..., "actual": ...}``.
    """
    changes: list[dict[str, Any]] = []
    _walk(expected, actual, path, changes)
    return changes


def _walk(expected: Any, actual: Any, path: str, changes: list[dict[str, Any]]) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k in expected.keys() | actual.keys():
            sub = f"{path}.{k}" if path else k
            if k not in actual:
                changes.append({"path": sub, "op": "removed", "expected": expected[k]})
            elif k not in expected:
                changes.append({"path": sub, "op": "added", "actual": actual[k]})
            else:
                _walk(expected[k], actual[k], sub, changes)
    elif isinstance(expected, list) and isinstance(actual, list):
        n = max(len(expected), len(actual))
        for i in range(n):
            sub = f"{path}[{i}]"
            if i >= len(actual):
                changes.append({"path": sub, "op": "removed", "expected": expected[i]})
            elif i >= len(expected):
                changes.append({"path": sub, "op": "added", "actual": actual[i]})
            else:
                _walk(expected[i], actual[i], sub, changes)
    else:
        if expected != actual:
            changes.append(
                {"path": path or "$", "op": "changed", "expected": expected, "actual": actual}
            )
