"""Generate a golden cassette by directly writing interactions via the Python API.

This script bypasses the network entirely — it constructs Interactions with the
Python Cassette so fingerprints are computed the same way the runtime would.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))

import agentreplay as ar  # noqa: E402


def main() -> None:
    out = ROOT / "goldens" / "cross_language_basic.jsonl"
    if out.exists():
        out.unlink()
    with ar.cassette(str(out), mode="record", presets=["uuids"]) as c:
        c.record(
            method="POST",
            host="api.anthropic.com",
            path="/v1/messages",
            request_body={
                "model": "claude-3",
                "messages": [{"role": "user", "content": "hi"}],
                "trace_id": "12345678-1234-4abc-8def-1234567890ab",
            },
            response_status=200,
            response_body={
                "id": "msg_g1",
                "role": "assistant",
                "content": [{"type": "text", "text": "hello"}],
            },
            response_stream=None,
        )
        c.record(
            method="POST",
            host="api.openai.com",
            path="/v1/chat/completions",
            request_body={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
            },
            response_status=200,
            response_body={
                "id": "chatcmpl_g1",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
            },
            response_stream=None,
        )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
