"""Normalization: ignore_paths + built-in presets used for fp_norm computation."""

from __future__ import annotations

import copy
import re
from typing import Any

from .paths import iter_targets

# Presets are applied by walking the whole tree; matching a *value* replaces it
# with the sentinel ``"<NORMALIZED>"`` so the canonical JSON differs only where
# the preset chose to.

_ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_REQ_ID_RE = re.compile(r"^(?:req|msg|resp)_[A-Za-z0-9]{16,}$")

# Epoch heuristic: 10-digit integer between 2001-09-09 and 2286-11-20
_EPOCH_MIN = 1_000_000_000
_EPOCH_MAX = 9_999_999_999

_NORMALIZED = "<NORMALIZED>"


def _matches_preset(value: Any, presets: frozenset[str]) -> bool:
    if isinstance(value, str):
        if "timestamps" in presets and _ISO8601_RE.match(value):
            return True
        if "uuids" in presets and _UUID_RE.match(value):
            return True
        if "request_ids" in presets and _REQ_ID_RE.match(value):
            return True
    if isinstance(value, int) and not isinstance(value, bool):
        if "timestamps" in presets and _EPOCH_MIN <= value <= _EPOCH_MAX:
            return True
    return False


def _apply_presets(node: Any, presets: frozenset[str]) -> Any:
    if isinstance(node, dict):
        return {k: _apply_presets(v, presets) for k, v in node.items()}
    if isinstance(node, list):
        return [_apply_presets(v, presets) for v in node]
    if _matches_preset(node, presets):
        return _NORMALIZED
    return node


def normalize(
    body: Any,
    ignore_paths: list[str] | None = None,
    presets: list[str] | None = None,
) -> Any:
    """Return a normalized *copy* of ``body`` for fp_norm computation.

    - Preset-matched values become the sentinel string.
    - Fields at ``ignore_paths`` are *removed* (not sentineled) so that presence
      and value both stop mattering.
    """
    if not ignore_paths and not presets:
        return body

    out = copy.deepcopy(body)
    if presets:
        out = _apply_presets(out, frozenset(presets))
    if ignore_paths:
        for path in ignore_paths:
            for container, key in list(iter_targets(out, path)):
                if isinstance(container, list):
                    # Deleting from a list would shift indices; sentinel instead.
                    container[key] = _NORMALIZED
                else:
                    del container[key]
    return out
