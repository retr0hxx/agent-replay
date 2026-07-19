"""Provider detection & provider-specific SSE reassembly."""

from __future__ import annotations

import json
from typing import Any

Provider = str  # "anthropic" | "openai" | "generic"

_ANTHROPIC_HOSTS = frozenset(["api.anthropic.com"])
_OPENAI_HOSTS = frozenset(["api.openai.com"])

# All hosts that are *automatically* treated as target (blocked from network in replay).
TARGET_HOSTS = _ANTHROPIC_HOSTS | _OPENAI_HOSTS


def detect(host: str, path: str) -> Provider:
    h = host.lower()
    if h in _ANTHROPIC_HOSTS and path.startswith("/v1/messages"):
        return "anthropic"
    if h in _OPENAI_HOSTS and (
        path.startswith("/v1/chat/completions") or path.startswith("/v1/responses")
    ):
        return "openai"
    return "generic"


# ---- SSE reassembly -----------------------------------------------------------

def parse_sse_events(raw: bytes) -> list[dict[str, Any]]:
    """Split an SSE payload into records.

    Returns a list of ``{"raw": "<full event block ending with blank line>"}``.
    We intentionally keep the raw block so replay can re-emit byte-identical
    payloads (spec §5.1: "生のまま記録").
    """
    text = raw.decode("utf-8", errors="replace")
    # Normalize CRLF → LF for splitting; we preserve LF-only in output.
    text = text.replace("\r\n", "\n")
    events: list[dict[str, Any]] = []
    buf: list[str] = []
    for line in text.split("\n"):
        if line == "":
            if buf:
                events.append({"raw": "\n".join(buf) + "\n\n"})
                buf = []
        else:
            buf.append(line)
    if buf:
        events.append({"raw": "\n".join(buf) + "\n\n"})
    return events


def _iter_data_lines(event_raw: str) -> list[str]:
    return [
        line[len("data: "):]
        if line.startswith("data: ")
        else line[len("data:"):]
        for line in event_raw.splitlines()
        if line.startswith("data:")
    ]


def _iter_event_names(event_raw: str) -> list[str]:
    return [
        line.split(":", 1)[1].strip()
        for line in event_raw.splitlines()
        if line.startswith("event:")
    ]


def reassemble(provider: Provider, events: list[dict[str, Any]]) -> Any | None:
    """Rebuild the final response body from streamed events. Returns None for generic."""
    if provider == "anthropic":
        return _reassemble_anthropic(events)
    if provider == "openai":
        return _reassemble_openai(events)
    return None


def _reassemble_anthropic(events: list[dict[str, Any]]) -> Any | None:
    """Anthropic Messages SSE → final Message object."""
    message: dict[str, Any] | None = None
    content_blocks: dict[int, dict[str, Any]] = {}
    for ev in events:
        raw = ev["raw"]
        names = _iter_event_names(raw)
        datas = _iter_data_lines(raw)
        for name, data in zip(names, datas):
            if not data:
                continue
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if name == "message_start":
                message = obj.get("message", {})
                message.setdefault("content", [])
            elif name == "content_block_start":
                idx = obj["index"]
                content_blocks[idx] = dict(obj["content_block"])
                if content_blocks[idx].get("type") == "text":
                    content_blocks[idx].setdefault("text", "")
                if content_blocks[idx].get("type") == "tool_use":
                    content_blocks[idx].setdefault("input", "")
            elif name == "content_block_delta":
                idx = obj["index"]
                delta = obj.get("delta", {})
                blk = content_blocks.get(idx, {})
                dtype = delta.get("type")
                if dtype == "text_delta":
                    blk["text"] = (blk.get("text") or "") + (delta.get("text") or "")
                elif dtype == "input_json_delta":
                    blk["input"] = (blk.get("input") or "") + (delta.get("partial_json") or "")
                content_blocks[idx] = blk
            elif name == "content_block_stop":
                idx = obj["index"]
                blk = content_blocks.get(idx)
                if blk and blk.get("type") == "tool_use" and isinstance(blk.get("input"), str):
                    try:
                        blk["input"] = json.loads(blk["input"]) if blk["input"] else {}
                    except json.JSONDecodeError:
                        pass
            elif name == "message_delta":
                if message is None:
                    continue
                delta = obj.get("delta", {})
                for k, v in delta.items():
                    message[k] = v
                if "usage" in obj:
                    message["usage"] = obj["usage"]
            elif name == "message_stop":
                pass
    if message is None:
        return None
    message["content"] = [content_blocks[i] for i in sorted(content_blocks)]
    return message


def _reassemble_openai(events: list[dict[str, Any]]) -> Any | None:
    """OpenAI chat.completion.chunk stream → single chat.completion object."""
    final: dict[str, Any] | None = None
    choices: dict[int, dict[str, Any]] = {}
    for ev in events:
        for data in _iter_data_lines(ev["raw"]):
            if data == "[DONE]" or not data:
                continue
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if final is None:
                final = {
                    "id": obj.get("id"),
                    "object": "chat.completion",
                    "created": obj.get("created"),
                    "model": obj.get("model"),
                    "choices": [],
                }
            for choice in obj.get("choices", []):
                idx = choice.get("index", 0)
                slot = choices.setdefault(
                    idx,
                    {"index": idx, "message": {"role": "assistant", "content": ""}, "finish_reason": None},
                )
                delta = choice.get("delta", {})
                if "role" in delta:
                    slot["message"]["role"] = delta["role"]
                if "content" in delta and delta["content"]:
                    slot["message"]["content"] = (slot["message"].get("content") or "") + delta["content"]
                if choice.get("finish_reason"):
                    slot["finish_reason"] = choice["finish_reason"]
            if "usage" in obj and obj["usage"] is not None:
                final["usage"] = obj["usage"]
    if final is None:
        return None
    final["choices"] = [choices[i] for i in sorted(choices)]
    return final
