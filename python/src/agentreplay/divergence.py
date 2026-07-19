"""Divergence records and Report container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Divergence:
    kind: str  # "request" | "flow_over" | "flow_unused"
    detail: str
    diff: list[dict[str, Any]] | None = None
    expected: dict[str, Any] | None = None
    actual: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "detail": self.detail}
        if self.diff is not None:
            d["diff"] = self.diff
        if self.expected is not None:
            d["expected"] = self.expected
        if self.actual is not None:
            d["actual"] = self.actual
        return d


@dataclass
class Report:
    mode: str
    cassette_path: str
    interactions_seen: int = 0
    interactions_played: int = 0
    interactions_recorded: int = 0
    divergences: list[Divergence] = field(default_factory=list)

    def add(self, d: Divergence) -> None:
        self.divergences.append(d)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "cassette_path": self.cassette_path,
            "interactions_seen": self.interactions_seen,
            "interactions_played": self.interactions_played,
            "interactions_recorded": self.interactions_recorded,
            "divergences": [d.to_dict() for d in self.divergences],
        }

    def summary(self) -> str:
        lines = [
            f"agent-replay report ({self.mode})",
            f"  cassette         : {self.cassette_path}",
            f"  interactions seen: {self.interactions_seen}",
            f"  played           : {self.interactions_played}",
            f"  recorded         : {self.interactions_recorded}",
            f"  divergences      : {len(self.divergences)}",
        ]
        for i, d in enumerate(self.divergences, 1):
            lines.append(f"  [{i}] {d.kind}: {d.detail}")
            if d.diff:
                for change in d.diff[:5]:
                    lines.append(
                        f"      - {change['path']} ({change['op']})"
                    )
                if len(d.diff) > 5:
                    lines.append(f"      ... {len(d.diff) - 5} more")
        return "\n".join(lines)
