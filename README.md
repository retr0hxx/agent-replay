<!-- Language: **English** | [日本語](README.ja.md) | [Deutsch](README.de.md) -->

# agent-replay

Record & replay LLM API calls for deterministic agent tests.

`agent-replay` captures the HTTP traffic your agent makes to LLM providers
(Anthropic, OpenAI, …) into a human-readable JSONL "cassette", then plays
it back on subsequent runs. Your tests become fast, offline, and
deterministic — and when a prompt drifts away from what was recorded, you
get a structured diff instead of a silent stale reply.

This repository ships two parallel implementations with a shared cassette
format, so a cassette recorded by one can be replayed by the other.

## Packages

| Runtime | Package | Install |
|---|---|---|
| Python (≥ 3.10) | [`agent-replay-py`](https://pypi.org/project/agent-replay-py/) | `pip install agent-replay-py` |
| Node.js (≥ 20)  | [`@retr0hxx/agent-replay`](https://www.npmjs.com/package/@retr0hxx/agent-replay) | `npm install --save-dev @retr0hxx/agent-replay` |

## Layout

```
python/       # Python package  — pytest plugin + httpx wrapper + CLI
typescript/   # TypeScript package — fetch patch + withCassette helper + CLI
goldens/      # Cross-language JSONL fixtures shared by both packages' test suites
```

Per-language docs and API examples live under each package directory:

- Python: [`python/README.md`](python/README.md) ([日本語](python/README.ja.md) / [Deutsch](python/README.de.md))
- TypeScript: [`typescript/README.md`](typescript/README.md) ([日本語](typescript/README.ja.md) / [Deutsch](typescript/README.de.md))

## At a glance

**Python**
```python
import agentreplay as ar

with ar.cassette("tests/cassettes/hello.jsonl", mode="auto") as c:
    client = c.httpx_client()
    r = client.post("https://api.anthropic.com/v1/messages", json={...})
```

**TypeScript**
```ts
import { withCassette } from "@retr0hxx/agent-replay";

await withCassette("hello", { mode: "auto" }, async () => {
  await fetch("https://api.anthropic.com/v1/messages", { method: "POST", body: "..." });
});
```

Both accept `mode: "record" | "replay" | "auto" | "passthrough"`, overridable
globally via the `AGENTREPLAY_MODE` environment variable.

## Why not just mock?

Mocking rewrites your test to fake the transport; `agent-replay` records the
real transport once, then plays it back byte-for-byte. When the prompt
changes, you see the diff instead of silently drifting away from production
behavior.

## License

MIT — see [LICENSE](LICENSE).
