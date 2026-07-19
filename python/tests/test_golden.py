"""Verify the shared golden cassette is playable from Python."""

from __future__ import annotations

from pathlib import Path

import agentreplay as ar

GOLDEN = Path(__file__).resolve().parents[2] / "goldens" / "cross_language_basic.jsonl"


def test_golden_is_verifiable_and_replays():
    assert GOLDEN.exists(), f"golden not found: {GOLDEN}"
    with ar.cassette(str(GOLDEN), mode="replay") as c:
        client = c.httpx_client()
        r = client.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": "claude-3",
                "messages": [{"role": "user", "content": "hi"}],
                "trace_id": "abcdef12-3456-4abc-8def-abcdef123456",
            },
        )
        assert r.json()["id"] == "msg_g1"
        client.close()
