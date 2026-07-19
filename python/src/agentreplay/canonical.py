"""Canonical JSON serialization (RFC 8785 JCS approximation).

Notes
-----
- CPython's ``json.dumps`` with ``sort_keys=True`` and ``separators=(",", ":")``
  produces a near-JCS form that matches TS ``JSON.stringify`` on canonical
  key-sorted objects for all values used by the v0.1 target APIs.
- Non-finite floats are rejected (`allow_nan=False`) because JCS forbids them.
- Unicode is emitted verbatim (``ensure_ascii=False``) to match JCS §3.2.1.
"""

from __future__ import annotations

import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Return an RFC 8785 (JCS)-style canonical JSON string for ``obj``.

    The serialization is stable across processes / OSes / Python versions.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
