"""Cassette core: config, file I/O, matching, and the public ``cassette`` context manager."""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .canonical import canonical_json
from .diff import json_diff
from .divergence import Divergence, Report
from .exceptions import (
    CassetteFormatError,
    CassetteMissError,
    DivergenceError,
)
from .fingerprint import fingerprint as compute_fp
from .normalization import normalize
from .providers import Provider, detect
from .redaction import apply_redaction

FORMAT_VERSION = 1
LIBRARY_NAME = "agent-replay"
LIBRARY_VERSION = "0.1.0"


# ---- data model ---------------------------------------------------------------


@dataclass
class Interaction:
    id: str
    seq: int
    provider: Provider
    method: str
    host: str
    path: str
    request_body: Any
    fp_exact: str
    fp_norm: str
    response_status: int
    response_body: Any
    response_stream: list[dict[str, Any]] | None
    response_headers: dict[str, str] | None = None
    request_headers: dict[str, str] | None = None
    started_at: str | None = None
    latency_ms: int | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kind": "interaction",
            "id": self.id,
            "seq": self.seq,
            "provider": self.provider,
            "method": self.method,
            "host": self.host,
            "path": self.path,
            "request": {
                "body": self.request_body,
                "fp_exact": self.fp_exact,
                "fp_norm": self.fp_norm,
            },
            "response": {
                "status": self.response_status,
                "body": self.response_body,
                "stream": self.response_stream,
            },
        }
        if self.request_headers is not None:
            d["request"]["headers"] = self.request_headers
        if self.response_headers is not None:
            d["response"]["headers"] = self.response_headers
        if self.started_at is not None or self.latency_ms is not None:
            d["timing"] = {"started_at": self.started_at, "latency_ms": self.latency_ms}
        return d

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "Interaction":
        req = obj.get("request", {})
        res = obj.get("response", {})
        timing = obj.get("timing") or {}
        return cls(
            id=obj["id"],
            seq=obj["seq"],
            provider=obj.get("provider", "generic"),
            method=obj["method"],
            host=obj["host"],
            path=obj["path"],
            request_body=req.get("body"),
            fp_exact=req["fp_exact"],
            fp_norm=req["fp_norm"],
            response_status=res.get("status", 200),
            response_body=res.get("body"),
            response_stream=res.get("stream"),
            response_headers=res.get("headers"),
            request_headers=req.get("headers"),
            started_at=timing.get("started_at"),
            latency_ms=timing.get("latency_ms"),
        )


@dataclass
class CassetteHeader:
    format_version: int = FORMAT_VERSION
    library: str = LIBRARY_NAME
    library_version: str = LIBRARY_VERSION
    created_at: str = ""
    normalization: dict[str, Any] = field(default_factory=lambda: {"ignore_paths": [], "presets": []})
    redaction_rules: list[dict[str, Any]] = field(default_factory=list)
    labels: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": "header",
            "format_version": self.format_version,
            "library": self.library,
            "library_version": self.library_version,
            "created_at": self.created_at,
            "normalization": self.normalization,
            "redaction_rules": self.redaction_rules,
            "labels": self.labels,
        }

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "CassetteHeader":
        if obj.get("kind") != "header":
            raise CassetteFormatError("first line is not a header")
        return cls(
            format_version=obj.get("format_version", FORMAT_VERSION),
            library=obj.get("library", LIBRARY_NAME),
            library_version=obj.get("library_version", LIBRARY_VERSION),
            created_at=obj.get("created_at", ""),
            normalization=obj.get("normalization") or {"ignore_paths": [], "presets": []},
            redaction_rules=obj.get("redaction_rules") or [],
            labels=obj.get("labels") or {},
        )


# ---- Cassette runtime --------------------------------------------------------


ModeName = str  # "record" | "replay" | "auto" | "passthrough"


class Cassette:
    """Runtime state for one open cassette."""

    def __init__(
        self,
        path: str,
        *,
        mode: ModeName = "auto",
        on_miss: str = "error",
        divergence: str = "warn",
        require_all_played: bool = False,
        ignore_paths: list[str] | None = None,
        presets: list[str] | None = None,
        redact: list[dict[str, Any]] | None = None,
        allow_passthrough_hosts: list[str] | None = None,
        stream_timing: str = "none",
        include_headers: list[str] | None = None,
        labels: dict[str, Any] | None = None,
    ):
        self.path = str(path)
        env_mode = os.environ.get("AGENTREPLAY_MODE")
        self.mode: ModeName = env_mode or mode
        self.on_miss = on_miss
        self.divergence_policy = divergence
        self.require_all_played = require_all_played
        self.stream_timing = stream_timing
        self.allow_passthrough_hosts = set(h.lower() for h in (allow_passthrough_hosts or []))
        self.include_headers = frozenset(h.lower() for h in (include_headers or []))
        self.labels = labels or {}

        self._runtime_ignore_paths = list(ignore_paths or [])
        self._runtime_presets = list(presets or [])
        self._runtime_redact = list(redact or [])

        # Populated in __enter__ once we know record vs replay.
        self.effective_mode: ModeName = self.mode
        self.header: CassetteHeader | None = None
        self._interactions: list[Interaction] = []
        self._consumed: list[bool] = []
        self._seq_counter = 0
        self._record_file = None
        self._lock = threading.Lock()

        self.report = Report(mode=self.mode, cassette_path=self.path)

    # ------------------------------------------------------------------ open/close

    def __enter__(self) -> "Cassette":
        self._resolve_mode()
        if self.effective_mode == "replay":
            self._load()
        elif self.effective_mode == "record":
            self._open_record()
        elif self.effective_mode == "passthrough":
            pass
        else:
            raise ValueError(f"unknown mode: {self.effective_mode}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._record_file is not None:
            self._record_file.close()
            self._record_file = None

        if self.effective_mode == "replay":
            unused = [i for i, c in enumerate(self._consumed) if not c]
            for i in unused:
                inter = self._interactions[i]
                self.report.add(
                    Divergence(
                        kind="flow_unused",
                        detail=f"interaction {inter.id} (seq={inter.seq}) was recorded but never replayed",
                    )
                )
            if unused and self.require_all_played:
                raise DivergenceError(
                    f"{len(unused)} unused interactions and require_all_played=True"
                )

    def _resolve_mode(self) -> None:
        m = self.mode
        if m == "auto":
            if Path(self.path).exists():
                m = "replay"
            else:
                m = "record"
                print(f"[agent-replay] recording new cassette: {self.path}", flush=True)
        elif m not in ("record", "replay", "passthrough"):
            raise ValueError(f"unknown mode: {m}")
        self.effective_mode = m
        self.report.mode = m

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
        except FileNotFoundError:
            raise CassetteFormatError(f"cassette not found: {self.path}")
        if not lines:
            raise CassetteFormatError(f"empty cassette: {self.path}")
        try:
            header_obj = json.loads(lines[0])
        except json.JSONDecodeError as e:
            raise CassetteFormatError(f"bad header JSON: {e}")
        self.header = CassetteHeader.from_json(header_obj)
        interactions: list[Interaction] = []
        for i, ln in enumerate(lines[1:], start=1):
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError as e:
                raise CassetteFormatError(f"bad interaction JSON on line {i+1}: {e}")
            if obj.get("kind") != "interaction":
                raise CassetteFormatError(f"line {i+1} is not an interaction")
            interactions.append(Interaction.from_json(obj))
        self._interactions = interactions
        self._consumed = [False] * len(interactions)
        self._seq_counter = max((it.seq for it in interactions), default=0)

        # Runtime rules override cassette rules where given; otherwise use header's.
        if not self._runtime_ignore_paths:
            self._runtime_ignore_paths = list(self.header.normalization.get("ignore_paths") or [])
        if not self._runtime_presets:
            self._runtime_presets = list(self.header.normalization.get("presets") or [])
        if not self._runtime_redact:
            self._runtime_redact = list(self.header.redaction_rules or [])

    def _open_record(self) -> None:
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.header = CassetteHeader(
            created_at=_utc_now_iso(),
            normalization={
                "ignore_paths": list(self._runtime_ignore_paths),
                "presets": list(self._runtime_presets),
            },
            redaction_rules=list(self._runtime_redact),
            labels=self.labels,
        )
        self._record_file = open(self.path, "w", encoding="utf-8")
        self._record_file.write(canonical_json(self.header.to_json()) + "\n")
        self._record_file.flush()

    # ------------------------------------------------------------------ helpers

    def apply_redaction(self, body: Any) -> Any:
        return apply_redaction(body, self._runtime_redact)

    def compute_fingerprints(
        self, method: str, host: str, path: str, redacted_body: Any
    ) -> tuple[str, str]:
        fp_exact = compute_fp(method, host, path, redacted_body)
        fp_norm = compute_fp(
            method,
            host,
            path,
            redacted_body,
            ignore_paths=self._runtime_ignore_paths,
            presets=self._runtime_presets,
        )
        return fp_exact, fp_norm

    # ------------------------------------------------------------------ replay lookup

    def lookup(
        self, method: str, host: str, path: str, body: Any
    ) -> Interaction | None:
        """Find a matching un-consumed interaction; return None to signal on_miss."""
        redacted = self.apply_redaction(body)
        fp_exact, fp_norm = self.compute_fingerprints(method, host, path, redacted)
        self.report.interactions_seen += 1

        candidates = [
            i
            for i, it in enumerate(self._interactions)
            if not self._consumed[i]
            and it.host == host.lower()
            and it.path == path
        ]
        if not candidates:
            return None

        # 1) fp_exact
        for i in candidates:
            if self._interactions[i].fp_exact == fp_exact:
                return self._consume(i)

        # 2) fp_norm
        for i in candidates:
            if self._interactions[i].fp_norm == fp_norm:
                return self._consume(i)

        # 3) order fallback
        i = min(candidates, key=lambda k: self._interactions[k].seq)
        chosen = self._interactions[i]
        diff = json_diff(chosen.request_body, redacted)
        self.report.add(
            Divergence(
                kind="request",
                detail=f"fingerprint mismatch on {method} {host}{path}; fell back to seq={chosen.seq}",
                diff=diff,
            )
        )
        if self.divergence_policy == "error":
            raise DivergenceError(
                f"request divergence on {method} {host}{path} (seq={chosen.seq})"
            )
        elif self.divergence_policy == "warn":
            print(
                f"[agent-replay] WARN: request divergence on {method} {host}{path} (seq={chosen.seq})",
                flush=True,
            )
        return self._consume(i)

    def _consume(self, i: int) -> Interaction:
        with self._lock:
            self._consumed[i] = True
            self.report.interactions_played += 1
        return self._interactions[i]

    # ------------------------------------------------------------------ record write

    def record(
        self,
        method: str,
        host: str,
        path: str,
        request_body: Any,
        response_status: int,
        response_body: Any,
        response_stream: list[dict[str, Any]] | None,
        started_at: str | None = None,
        latency_ms: int | None = None,
        request_headers: dict[str, str] | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> Interaction:
        redacted = self.apply_redaction(request_body)
        fp_exact, fp_norm = self.compute_fingerprints(method, host, path, redacted)
        provider = detect(host, path)
        self._seq_counter += 1
        seq = self._seq_counter
        interaction = Interaction(
            id=f"int_{seq:04d}",
            seq=seq,
            provider=provider,
            method=method.upper(),
            host=host.lower(),
            path=path,
            request_body=redacted,
            fp_exact=fp_exact,
            fp_norm=fp_norm,
            response_status=response_status,
            response_body=response_body,
            response_stream=response_stream,
            request_headers=request_headers,
            response_headers=response_headers,
            started_at=started_at,
            latency_ms=latency_ms,
        )
        with self._lock:
            if self._record_file is not None:
                self._record_file.write(canonical_json(interaction.to_json()) + "\n")
                self._record_file.flush()
            self._interactions.append(interaction)
            self._consumed.append(True)
            self.report.interactions_recorded += 1
            self.report.interactions_seen += 1
            self.report.interactions_played += 1
        return interaction

    # ------------------------------------------------------------------ transport

    def httpx_client(self, **client_kwargs: Any):
        """Return an httpx.Client wired to this cassette."""
        import httpx
        from .transport import build_transport

        transport = build_transport(self, async_mode=False)
        return httpx.Client(transport=transport, **client_kwargs)

    def httpx_async_client(self, **client_kwargs: Any):
        """Return an httpx.AsyncClient wired to this cassette."""
        import httpx
        from .transport import build_transport

        transport = build_transport(self, async_mode=True)
        return httpx.AsyncClient(transport=transport, **client_kwargs)


# ---- public factory ----------------------------------------------------------


@contextmanager
def cassette(path: str, **kwargs: Any) -> Iterator[Cassette]:
    """Open a cassette as a context manager. See :class:`Cassette` for options."""
    c = Cassette(path, **kwargs)
    try:
        c.__enter__()
        yield c
    finally:
        c.__exit__(None, None, None)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
