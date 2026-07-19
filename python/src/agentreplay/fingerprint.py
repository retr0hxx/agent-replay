"""Fingerprint computation for request matching."""

from __future__ import annotations

import hashlib
from typing import Any

from .canonical import canonical_json
from .normalization import normalize


def fingerprint(
    method: str,
    host: str,
    path: str,
    body: Any,
    *,
    ignore_paths: list[str] | None = None,
    presets: list[str] | None = None,
) -> str:
    """Return the sha256 hex fingerprint prefixed with 'sha256:'.

    ``method`` is uppercased, ``host`` is lowercased, ``path`` is used verbatim.
    ``body`` is expected to already have redaction rules applied by the caller.
    """
    normalized = normalize(body, ignore_paths=ignore_paths, presets=presets)
    canon = canonical_json(normalized)
    payload = f"{method.upper()}\n{host.lower()}\n{path}\n{canon}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
