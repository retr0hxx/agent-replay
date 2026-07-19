"""httpx transport implementation."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterator

import httpx

from .divergence import Divergence
from .exceptions import (
    CassetteMissError,
    NonTargetHostError,
)
from .providers import TARGET_HOSTS, detect, parse_sse_events, reassemble
from .redaction import strip_auth_headers


def build_transport(cassette, *, async_mode: bool):
    """Return an httpx transport wired to ``cassette``."""
    upstream = httpx.AsyncHTTPTransport() if async_mode else httpx.HTTPTransport()
    if async_mode:
        return _AsyncTransport(cassette, upstream)
    return _SyncTransport(cassette, upstream)


# --------------------------------------------------------------------- helpers


def _parse_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        # Non-JSON bodies are stored as base64-tagged dicts.
        import base64
        return {"__non_json_b64__": base64.b64encode(raw).decode("ascii")}


def _serialize_body(body: Any) -> bytes:
    if body is None:
        return b""
    if isinstance(body, dict) and "__non_json_b64__" in body:
        import base64
        return base64.b64decode(body["__non_json_b64__"])
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _is_target(host: str, path: str, cassette) -> bool:
    if host.lower() in TARGET_HOSTS:
        return True
    provider = detect(host, path)
    return provider != "generic"


def _is_sse_content_type(headers: dict[str, str]) -> bool:
    ctype = ""
    for k, v in headers.items():
        if k.lower() == "content-type":
            ctype = v.lower()
            break
    return "text/event-stream" in ctype


def _headers_dict(h: Any) -> dict[str, str]:
    """Normalize an httpx.Headers / list-of-pairs / dict into a plain dict."""
    if hasattr(h, "multi_items"):
        # httpx.Headers
        return {k: v for k, v in h.items()}
    if isinstance(h, dict):
        return dict(h)
    return {k: v for k, v in list(h)}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# --------------------------------------------------------------------- sync transport


class _SyncTransport(httpx.BaseTransport):
    def __init__(self, cassette, upstream: httpx.HTTPTransport):
        self.c = cassette
        self.upstream = upstream

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        path = request.url.path
        method = request.method
        raw = request.read()
        body = _parse_body(raw)

        mode = self.c.effective_mode

        target = _is_target(host, path, self.c)
        allowed = host.lower() in self.c.allow_passthrough_hosts

        if mode == "passthrough":
            return self.upstream.handle_request(request)

        if not target:
            if allowed:
                return self.upstream.handle_request(request)
            raise NonTargetHostError(
                f"request to non-target host {host!r} blocked; add to allow_passthrough_hosts to permit"
            )

        if mode == "replay":
            interaction = self.c.lookup(method, host, path, body)
            if interaction is None:
                return self._on_miss(request, host, path, method, body)
            return self._replay_response(interaction)

        if mode == "record":
            return self._record_response(request, host, path, method, body)

        raise RuntimeError(f"unknown mode: {mode}")

    # ---------- on_miss ------------------------------------------------------

    def _on_miss(
        self,
        request: httpx.Request,
        host: str,
        path: str,
        method: str,
        body: Any,
    ) -> httpx.Response:
        policy = self.c.on_miss
        self.c.report.add(
            Divergence(kind="flow_over", detail=f"no cassette entry for {method} {host}{path}")
        )
        if policy == "error":
            raise CassetteMissError(
                f"no matching interaction for {method} {host}{path} "
                f"(on_miss='error'; use 'passthrough' or 'record_new' to change)"
            )
        if policy == "passthrough":
            return self.upstream.handle_request(request)
        if policy == "record_new":
            return self._record_response(request, host, path, method, body)
        raise RuntimeError(f"unknown on_miss policy: {policy}")

    # ---------- record -------------------------------------------------------

    def _record_response(
        self,
        request: httpx.Request,
        host: str,
        path: str,
        method: str,
        body: Any,
    ) -> httpx.Response:
        started_at = _iso_now()
        t0 = time.monotonic()
        upstream_resp = self.upstream.handle_request(request)
        headers = _headers_dict(upstream_resp.headers)

        req_headers_to_save = self._filter_headers(_headers_dict(request.headers))
        resp_headers_to_save = self._filter_headers(headers) if self.c.include_headers else None

        if _is_sse_content_type(headers):
            buf = bytearray()
            event_times: list[float] = []
            chunk_times: list[float] = []

            iterator = upstream_resp.stream

            def gen():
                start = time.monotonic()
                last = start
                for chunk in iterator:
                    now = time.monotonic()
                    chunk_times.append(now - last)
                    last = now
                    buf.extend(chunk)
                    yield chunk

            def on_close():
                events = parse_sse_events(bytes(buf))
                # Reconstruct delay_ms per event using accumulated chunk timings.
                # We don't have per-event granularity from the byte stream alone,
                # so we distribute chunk delays evenly across events for a coarse
                # timing profile. Fine-grained recorded timing is best-effort.
                total_ms = int((time.monotonic() - t0) * 1000) if event_times == [] else 0
                per = total_ms // max(len(events), 1) if events else 0
                stream_records = [
                    {"delay_ms": 0 if i == 0 else per, "data": ev["raw"]}
                    for i, ev in enumerate(events)
                ]
                provider = detect(host, path)
                final = reassemble(provider, events)
                self.c.record(
                    method=method,
                    host=host,
                    path=path,
                    request_body=body,
                    response_status=upstream_resp.status_code,
                    response_body=final,
                    response_stream=stream_records,
                    started_at=started_at,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    request_headers=req_headers_to_save,
                    response_headers=resp_headers_to_save,
                )

            stream = _RecordingByteStream(gen(), on_close, upstream_resp.stream)
            return httpx.Response(
                status_code=upstream_resp.status_code,
                headers=upstream_resp.headers,
                stream=stream,
                request=request,
            )

        # Non-SSE: read fully, record, and hand a fresh Response back to caller.
        body_bytes = upstream_resp.read()
        latency_ms = int((time.monotonic() - t0) * 1000)
        upstream_resp.close()
        response_body_parsed = _parse_body(body_bytes)
        self.c.record(
            method=method,
            host=host,
            path=path,
            request_body=body,
            response_status=upstream_resp.status_code,
            response_body=response_body_parsed,
            response_stream=None,
            started_at=started_at,
            latency_ms=latency_ms,
            request_headers=req_headers_to_save,
            response_headers=resp_headers_to_save,
        )
        return httpx.Response(
            status_code=upstream_resp.status_code,
            headers=upstream_resp.headers,
            content=body_bytes,
            request=request,
        )

    def _filter_headers(self, headers: dict[str, str]) -> dict[str, str] | None:
        stripped = strip_auth_headers(headers)
        if not self.c.include_headers:
            return None
        return {k: v for k, v in stripped.items() if k.lower() in self.c.include_headers}

    # ---------- replay -------------------------------------------------------

    def _replay_response(self, interaction) -> httpx.Response:
        request = httpx.Request(
            method=interaction.method,
            url=f"https://{interaction.host}{interaction.path}",
        )
        headers = interaction.response_headers or {}
        if interaction.response_stream:
            stream = _ReplayEventStream(
                interaction.response_stream,
                timing=self.c.stream_timing,
            )
            # Ensure content-type is set to SSE if missing.
            if not any(k.lower() == "content-type" for k in headers.keys()):
                headers = {**headers, "content-type": "text/event-stream"}
            return httpx.Response(
                status_code=interaction.response_status,
                headers=headers,
                stream=stream,
                request=request,
            )
        content = _serialize_body(interaction.response_body)
        if content and not any(k.lower() == "content-type" for k in headers.keys()):
            headers = {**headers, "content-type": "application/json"}
        return httpx.Response(
            status_code=interaction.response_status,
            headers=headers,
            content=content,
            request=request,
        )


# --------------------------------------------------------------------- byte streams


class _RecordingByteStream(httpx.SyncByteStream):
    def __init__(self, gen: Iterator[bytes], on_close, inner):
        self._gen = gen
        self._on_close = on_close
        self._inner = inner
        self._closed = False

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._gen:
            yield chunk

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if hasattr(self._inner, "close"):
                self._inner.close()
        finally:
            try:
                self._on_close()
            except Exception:
                pass


class _ReplayEventStream(httpx.SyncByteStream):
    def __init__(self, records: list[dict[str, Any]], *, timing: str):
        self._records = records
        self._timing = timing

    def __iter__(self) -> Iterator[bytes]:
        for rec in self._records:
            if self._timing == "recorded":
                delay = int(rec.get("delay_ms") or 0)
                if delay > 0:
                    time.sleep(delay / 1000)
            yield rec["data"].encode("utf-8")

    def close(self) -> None:
        pass


class _AsyncRecordingByteStream(httpx.AsyncByteStream):
    def __init__(self, agen: AsyncIterator[bytes], on_close, inner):
        self._agen = agen
        self._on_close = on_close
        self._inner = inner
        self._closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._agen:
            yield chunk

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if hasattr(self._inner, "aclose"):
                await self._inner.aclose()
        finally:
            try:
                self._on_close()
            except Exception:
                pass


class _AsyncReplayEventStream(httpx.AsyncByteStream):
    def __init__(self, records: list[dict[str, Any]], *, timing: str):
        self._records = records
        self._timing = timing

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for rec in self._records:
            if self._timing == "recorded":
                delay = int(rec.get("delay_ms") or 0)
                if delay > 0:
                    await asyncio.sleep(delay / 1000)
            yield rec["data"].encode("utf-8")

    async def aclose(self) -> None:
        pass


# --------------------------------------------------------------------- async transport


class _AsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, cassette, upstream: httpx.AsyncHTTPTransport):
        self.c = cassette
        self.upstream = upstream

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        path = request.url.path
        method = request.method
        raw = await request.aread()
        body = _parse_body(raw)

        mode = self.c.effective_mode
        target = _is_target(host, path, self.c)
        allowed = host.lower() in self.c.allow_passthrough_hosts

        if mode == "passthrough":
            return await self.upstream.handle_async_request(request)
        if not target:
            if allowed:
                return await self.upstream.handle_async_request(request)
            raise NonTargetHostError(
                f"request to non-target host {host!r} blocked; add to allow_passthrough_hosts to permit"
            )

        if mode == "replay":
            interaction = self.c.lookup(method, host, path, body)
            if interaction is None:
                return await self._on_miss(request, host, path, method, body)
            return self._replay_response(interaction)

        if mode == "record":
            return await self._record_response(request, host, path, method, body)

        raise RuntimeError(f"unknown mode: {mode}")

    async def _on_miss(self, request, host, path, method, body):
        policy = self.c.on_miss
        self.c.report.add(
            Divergence(kind="flow_over", detail=f"no cassette entry for {method} {host}{path}")
        )
        if policy == "error":
            raise CassetteMissError(
                f"no matching interaction for {method} {host}{path} (on_miss='error')"
            )
        if policy == "passthrough":
            return await self.upstream.handle_async_request(request)
        if policy == "record_new":
            return await self._record_response(request, host, path, method, body)
        raise RuntimeError(f"unknown on_miss: {policy}")

    async def _record_response(self, request, host, path, method, body):
        started_at = _iso_now()
        t0 = time.monotonic()
        upstream_resp = await self.upstream.handle_async_request(request)
        headers = _headers_dict(upstream_resp.headers)

        req_headers_to_save = self._filter_headers(_headers_dict(request.headers))
        resp_headers_to_save = self._filter_headers(headers) if self.c.include_headers else None

        if _is_sse_content_type(headers):
            buf = bytearray()

            async def agen():
                async for chunk in upstream_resp.aiter_bytes():
                    buf.extend(chunk)
                    yield chunk

            def on_close():
                events = parse_sse_events(bytes(buf))
                latency_ms = int((time.monotonic() - t0) * 1000)
                per = latency_ms // max(len(events), 1) if events else 0
                stream_records = [
                    {"delay_ms": 0 if i == 0 else per, "data": ev["raw"]}
                    for i, ev in enumerate(events)
                ]
                provider = detect(host, path)
                final = reassemble(provider, events)
                self.c.record(
                    method=method,
                    host=host,
                    path=path,
                    request_body=body,
                    response_status=upstream_resp.status_code,
                    response_body=final,
                    response_stream=stream_records,
                    started_at=started_at,
                    latency_ms=latency_ms,
                    request_headers=req_headers_to_save,
                    response_headers=resp_headers_to_save,
                )

            stream = _AsyncRecordingByteStream(agen(), on_close, upstream_resp.stream)
            return httpx.Response(
                status_code=upstream_resp.status_code,
                headers=upstream_resp.headers,
                stream=stream,
                request=request,
            )

        body_bytes = await upstream_resp.aread()
        latency_ms = int((time.monotonic() - t0) * 1000)
        await upstream_resp.aclose()
        response_body_parsed = _parse_body(body_bytes)
        self.c.record(
            method=method,
            host=host,
            path=path,
            request_body=body,
            response_status=upstream_resp.status_code,
            response_body=response_body_parsed,
            response_stream=None,
            started_at=started_at,
            latency_ms=latency_ms,
            request_headers=req_headers_to_save,
            response_headers=resp_headers_to_save,
        )
        return httpx.Response(
            status_code=upstream_resp.status_code,
            headers=upstream_resp.headers,
            content=body_bytes,
            request=request,
        )

    def _filter_headers(self, headers):
        stripped = strip_auth_headers(headers)
        if not self.c.include_headers:
            return None
        return {k: v for k, v in stripped.items() if k.lower() in self.c.include_headers}

    def _replay_response(self, interaction) -> httpx.Response:
        request = httpx.Request(
            method=interaction.method,
            url=f"https://{interaction.host}{interaction.path}",
        )
        headers = interaction.response_headers or {}
        if interaction.response_stream:
            stream = _AsyncReplayEventStream(
                interaction.response_stream, timing=self.c.stream_timing
            )
            if not any(k.lower() == "content-type" for k in headers.keys()):
                headers = {**headers, "content-type": "text/event-stream"}
            return httpx.Response(
                status_code=interaction.response_status,
                headers=headers,
                stream=stream,
                request=request,
            )
        content = _serialize_body(interaction.response_body)
        if content and not any(k.lower() == "content-type" for k in headers.keys()):
            headers = {**headers, "content-type": "application/json"}
        return httpx.Response(
            status_code=interaction.response_status,
            headers=headers,
            content=content,
            request=request,
        )
