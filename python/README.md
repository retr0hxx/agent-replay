<!-- Language: **English** | [日本語](README.ja.md) | [Deutsch](README.de.md) -->

# agent-replay (Python)

Record & replay LLM API calls for deterministic agent tests.

`agent-replay` captures the HTTP traffic your agent makes to LLM providers
(Anthropic, OpenAI, …) into a human-readable JSONL "cassette", then plays it
back on subsequent runs so your tests are fast, offline, and deterministic —
while still flagging when a prompt has drifted away from what was recorded.

## Install

```bash
pip install agent-replay
```

Optional extras:

```bash
pip install "agent-replay[pytest]"   # pytest fixture & marker
```

## Quick start

```python
import agentreplay as ar

with ar.cassette("tests/cassettes/hello.jsonl", mode="auto") as c:
    client = c.httpx_client()   # a preconfigured httpx.Client
    r = client.post(
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}]},
    )
    print(r.json())
```

- First run: the cassette file doesn't exist yet → records the real response.
- Later runs: the file exists → serves the recorded response, no network.
- `mode` accepts `"record" | "replay" | "auto" | "passthrough"`, and can be
  overridden globally via `AGENTREPLAY_MODE`.

Async is the same shape:

```python
async with ar.cassette("tests/cassettes/hello.jsonl") as c:
    async with c.httpx_async_client() as client:
        r = await client.post(...)
```

## pytest

`agent-replay` ships a pytest plugin. Cassettes are auto-named from the test
node id and stored under `tests/cassettes/`.

```python
import pytest

@pytest.mark.agentreplay(mode="auto")
def test_agent(agentreplay):
    client = agentreplay.httpx_client()
    ...
```

## CLI

```bash
agentreplay inspect tests/cassettes/hello.jsonl   # header + summary
agentreplay show    tests/cassettes/hello.jsonl 0 # pretty-print seq 0
agentreplay verify  tests/cassettes/hello.jsonl   # re-check fingerprints
```

## Divergence

When the request your code sends no longer matches what was recorded (a
prompt changed, a tool schema was edited, …), `agent-replay` produces a
structured diff (`ar.Report`) instead of silently returning stale data. The
`divergence` policy (`"warn" | "error"`) controls whether it raises.

## License

MIT — see [LICENSE](LICENSE).

The TypeScript sibling of this package lives at
[`@retr0hxx/agent-replay`](https://www.npmjs.com/package/@retr0hxx/agent-replay).
