"""SSE record & replay via a fake upstream that produces text/event-stream."""

from __future__ import annotations

import httpx

import agentreplay as ar
from agentreplay.transport import build_transport


ANTHROPIC_SSE = (
    b"event: message_start\n"
    b'data: {"type":"message_start","message":{"id":"msg_1","role":"assistant","model":"claude-3","content":[]}}\n'
    b"\n"
    b"event: content_block_start\n"
    b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n'
    b"\n"
    b"event: content_block_delta\n"
    b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello "}}\n'
    b"\n"
    b"event: content_block_delta\n"
    b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"world"}}\n'
    b"\n"
    b"event: content_block_stop\n"
    b'data: {"type":"content_block_stop","index":0}\n'
    b"\n"
    b"event: message_delta\n"
    b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"input_tokens":5,"output_tokens":2}}\n'
    b"\n"
    b"event: message_stop\n"
    b'data: {"type":"message_stop"}\n'
    b"\n"
)


def _fake_sse_transport(scripted_bytes):
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=scripted_bytes,
        )

    return httpx.MockTransport(handler)


def test_record_sse_and_reassemble(tmp_path):
    cassette_path = tmp_path / "sse.jsonl"
    with ar.cassette(str(cassette_path), mode="record") as c:
        client = httpx.Client(transport=build_transport(c, async_mode=False))
        client._transport.upstream = _fake_sse_transport(ANTHROPIC_SSE)  # type: ignore
        with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        ) as resp:
            body = b"".join(resp.iter_bytes())
        assert b"content_block_delta" in body
        client.close()

    # Now verify the cassette content
    import json

    lines = cassette_path.read_text().splitlines()
    inter = json.loads(lines[1])
    assert inter["provider"] == "anthropic"
    assert inter["response"]["stream"] is not None
    assert len(inter["response"]["stream"]) == 7  # 7 SSE event blocks
    final = inter["response"]["body"]
    assert final["id"] == "msg_1"
    assert final["content"][0]["text"] == "hello world"
    assert final["stop_reason"] == "end_turn"


def test_replay_sse_streams_bytes(tmp_path):
    cassette_path = tmp_path / "sse.jsonl"
    with ar.cassette(str(cassette_path), mode="record") as c:
        client = httpx.Client(transport=build_transport(c, async_mode=False))
        client._transport.upstream = _fake_sse_transport(ANTHROPIC_SSE)  # type: ignore
        with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        ) as resp:
            _ = b"".join(resp.iter_bytes())
        client.close()

    with ar.cassette(str(cassette_path), mode="replay") as c:
        client = c.httpx_client()
        with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        ) as resp:
            replayed = b"".join(resp.iter_bytes())
        client.close()

    assert b"content_block_delta" in replayed
    assert b"hello " in replayed
    assert b"world" in replayed
