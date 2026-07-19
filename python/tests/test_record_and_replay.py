"""End-to-end: record via a fake upstream, then replay, then verify."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import agentreplay as ar
from agentreplay.transport import build_transport


class FakeUpstream(httpx.MockTransport):
    """httpx.MockTransport that returns canned JSON responses per request."""

    def __init__(self, script):
        self._script = list(script)

        def handler(request: httpx.Request) -> httpx.Response:
            payload = self._script.pop(0)
            return httpx.Response(
                payload.get("status", 200),
                json=payload["body"],
            )

        super().__init__(handler)


def _install_fake_upstream(cassette, script):
    """Replace the transport's upstream with a scripted MockTransport."""
    fake = FakeUpstream(script)
    # Both the actual transport and its .upstream field are used; we swap the field.
    cassette._patched_client = httpx.Client(transport=build_transport(cassette, async_mode=False))
    cassette._patched_client._transport.upstream = fake  # type: ignore[attr-defined]
    return cassette._patched_client


def test_record_then_replay_roundtrip(tmp_path):
    cassette_path = tmp_path / "session.jsonl"

    # ---- record
    with ar.cassette(str(cassette_path), mode="record") as c:
        client = _install_fake_upstream(
            c,
            [
                {"body": {"id": "msg_1", "content": [{"type": "text", "text": "hi"}]}},
                {"body": {"id": "msg_2", "content": [{"type": "text", "text": "bye"}]}},
            ],
        )
        r1 = client.post(
            "https://api.anthropic.com/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "yo"}]},
        )
        r2 = client.post(
            "https://api.anthropic.com/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "ok"}]},
        )
        assert r1.json()["id"] == "msg_1"
        assert r2.json()["id"] == "msg_2"
        client.close()

    assert cassette_path.exists()
    lines = cassette_path.read_text().splitlines()
    assert json.loads(lines[0])["kind"] == "header"
    assert len(lines) == 3

    # ---- replay
    with ar.cassette(str(cassette_path), mode="replay") as c:
        client = c.httpx_client()
        r1 = client.post(
            "https://api.anthropic.com/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "yo"}]},
        )
        r2 = client.post(
            "https://api.anthropic.com/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "ok"}]},
        )
        assert r1.json()["id"] == "msg_1"
        assert r2.json()["id"] == "msg_2"
        client.close()

    # No divergences expected.
    with ar.cassette(str(cassette_path), mode="replay") as c:
        client = c.httpx_client()
        client.post(
            "https://api.anthropic.com/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "yo"}]},
        )
        client.close()


def test_replay_on_miss_error(tmp_path):
    cassette_path = tmp_path / "s.jsonl"
    with ar.cassette(str(cassette_path), mode="record") as c:
        client = _install_fake_upstream(c, [{"body": {"ok": True}}])
        client.post(
            "https://api.anthropic.com/v1/messages", json={"model": "m", "messages": []}
        )
        client.close()

    with ar.cassette(str(cassette_path), mode="replay") as c:
        client = c.httpx_client()
        # first call matches
        client.post("https://api.anthropic.com/v1/messages", json={"model": "m", "messages": []})
        # second call has no match → on_miss='error' (default)
        with pytest.raises(ar.CassetteMissError):
            client.post("https://api.anthropic.com/v1/messages", json={"model": "m", "messages": [{"role": "u", "content": "extra"}]})
        client.close()


def test_replay_blocks_non_target_host(tmp_path):
    cassette_path = tmp_path / "s.jsonl"
    with ar.cassette(str(cassette_path), mode="record") as c:
        client = _install_fake_upstream(c, [{"body": {"ok": True}}])
        client.post("https://api.anthropic.com/v1/messages", json={"model": "m", "messages": []})
        client.close()

    with ar.cassette(str(cassette_path), mode="replay") as c:
        client = c.httpx_client()
        with pytest.raises(ar.NonTargetHostError):
            client.get("https://example.com/anything")
        client.close()


def test_normalization_recovers_from_timestamp_drift(tmp_path):
    """fp_exact mismatch, but fp_norm matches after preset applied."""
    cassette_path = tmp_path / "s.jsonl"
    with ar.cassette(
        str(cassette_path),
        mode="record",
        presets=["timestamps"],
    ) as c:
        client = _install_fake_upstream(c, [{"body": {"ok": True}}])
        client.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}],
                "system_time": "2026-01-01T00:00:00Z",
            },
        )
        client.close()

    with ar.cassette(str(cassette_path), mode="replay") as c:
        client = c.httpx_client()
        r = client.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}],
                "system_time": "2026-07-19T00:00:00Z",  # different timestamp
            },
        )
        assert r.json() == {"ok": True}
        client.close()
        assert c.report.interactions_played == 1
        assert not any(d.kind == "request" for d in c.report.divergences)


def test_request_divergence_falls_back_and_reports(tmp_path):
    cassette_path = tmp_path / "s.jsonl"
    with ar.cassette(str(cassette_path), mode="record") as c:
        client = _install_fake_upstream(c, [{"body": {"who": "A"}}])
        client.post(
            "https://api.anthropic.com/v1/messages",
            json={"model": "m", "messages": [{"role": "user", "content": "one"}]},
        )
        client.close()

    with ar.cassette(str(cassette_path), mode="replay", divergence="warn") as c:
        client = c.httpx_client()
        r = client.post(
            "https://api.anthropic.com/v1/messages",
            json={"model": "m", "messages": [{"role": "user", "content": "two"}]},
        )
        assert r.json() == {"who": "A"}
        client.close()
        assert any(d.kind == "request" for d in c.report.divergences)
