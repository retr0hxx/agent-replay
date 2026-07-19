"""Redaction: unconditional header stripping + user-defined body redaction."""

from __future__ import annotations

import copy
from typing import Any

from .paths import iter_targets

# Auth-bearing headers we ALWAYS strip before writing a cassette.
# Matched case-insensitively; see implementation-notes §2.3.
_AUTH_HEADERS = frozenset(
    h.lower()
    for h in [
        "authorization",
        "x-api-key",
        "openai-organization",
        "openai-project",
        "anthropic-version",
        "anthropic-beta",
        "cookie",
        "set-cookie",
        "proxy-authorization",
    ]
)


def strip_auth_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` with auth-bearing keys removed."""
    return {k: v for k, v in headers.items() if k.lower() not in _AUTH_HEADERS}


def default_header_allowlist() -> frozenset[str]:
    """When ``include_headers`` is set, this is the base allow-list to intersect.

    Currently empty (i.e. nothing is stored unless the user explicitly opts in).
    """
    return frozenset()


def apply_redaction(body: Any, rules: list[dict[str, Any]]) -> Any:
    """Return a deep-copied ``body`` with all ``rules`` applied.

    Each rule is ``{"path": "...", "replace": <value>}``. Missing paths are silently
    ignored (idempotent when rules don't match).
    """
    if not rules:
        return body
    out = copy.deepcopy(body)
    for rule in rules:
        path = rule["path"]
        replacement = rule.get("replace", "***")
        for container, key in list(iter_targets(out, path)):
            container[key] = replacement
    return out
