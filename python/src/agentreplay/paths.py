"""Minimal JSONPath-like traversal used by redaction & normalization.

Supported syntax
----------------
- Dotted keys:            ``a.b.c``
- Numeric index:          ``a[0]``
- Wildcard index:         ``a[*]``  (all elements)
- Leading ``$`` allowed but optional
- ``**`` (recursive descent) is intentionally NOT supported in v0.1.

The traversal engine yields ``(container, key_or_index)`` pairs so callers can
mutate in place (delete, replace) without threading paths back through.
"""

from __future__ import annotations

import re
from typing import Any, Iterator, Tuple

_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[([0-9]+|\*)\]")


def _tokenize(path: str) -> list[tuple[str, str]]:
    """Return list of (kind, value) tokens.

    kind in {"key", "index", "wildcard"}.
    """
    if path.startswith("$"):
        path = path[1:]
        if path.startswith("."):
            path = path[1:]
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(path):
        if path[pos] == ".":
            pos += 1
            continue
        m = _TOKEN_RE.match(path, pos)
        if not m:
            raise ValueError(f"invalid path token near {path[pos:pos+10]!r} in {path!r}")
        if m.group(1) is not None:
            tokens.append(("key", m.group(1)))
        else:
            g = m.group(2)
            if g == "*":
                tokens.append(("wildcard", "*"))
            else:
                tokens.append(("index", g))
        pos = m.end()
    return tokens


def iter_targets(obj: Any, path: str) -> Iterator[Tuple[Any, Any]]:
    """Yield ``(container, key)`` pairs for every location matching ``path``.

    ``container[key]`` is the matched value; deleting via ``del container[key]``
    or reassigning via ``container[key] = ...`` is safe.
    """
    tokens = _tokenize(path)
    yield from _walk(obj, tokens, 0)


def _walk(node: Any, tokens: list[tuple[str, str]], i: int) -> Iterator[Tuple[Any, Any]]:
    if i >= len(tokens):
        return
    kind, val = tokens[i]
    is_last = i == len(tokens) - 1

    if kind == "key":
        if not isinstance(node, dict) or val not in node:
            return
        if is_last:
            yield node, val
        else:
            yield from _walk(node[val], tokens, i + 1)
    elif kind == "index":
        if not isinstance(node, list):
            return
        idx = int(val)
        if idx >= len(node):
            return
        if is_last:
            yield node, idx
        else:
            yield from _walk(node[idx], tokens, i + 1)
    else:  # wildcard
        if isinstance(node, list):
            for idx in range(len(node)):
                if is_last:
                    yield node, idx
                else:
                    yield from _walk(node[idx], tokens, i + 1)
        elif isinstance(node, dict):
            for k in list(node.keys()):
                if is_last:
                    yield node, k
                else:
                    yield from _walk(node[k], tokens, i + 1)
