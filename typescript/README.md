# @retr0hxx/agent-replay

Record & replay LLM API calls for deterministic agent tests.

`agent-replay` captures the HTTP traffic your agent makes to LLM providers
(Anthropic, OpenAI, …) into a human-readable JSONL "cassette", then plays it
back on subsequent runs so your tests are fast, offline, and deterministic —
while still flagging when a prompt has drifted away from what was recorded.

## Install

```bash
npm install --save-dev @retr0hxx/agent-replay
```

Requires Node.js `>= 20` (uses the built-in global `fetch`).

## Quick start (vitest / jest / node:test)

```ts
import { withCassette } from "@retr0hxx/agent-replay";

await withCassette("hello", { mode: "auto" }, async () => {
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    body: JSON.stringify({
      model: "claude-3",
      messages: [{ role: "user", content: "hi" }],
    }),
  });
  console.log(await r.json());
});
```

- First run: the cassette file doesn't exist yet → records the real response.
- Later runs: the file exists → serves the recorded response, no network.
- `mode` accepts `"record" | "replay" | "auto" | "passthrough"` and can be
  overridden globally via the `AGENTREPLAY_MODE` env var.

## Low-level API

If you don't want the global `fetch` patched, wrap explicitly:

```ts
import { Cassette, buildFetch } from "@retr0hxx/agent-replay";

const c = new Cassette("cassettes/hello.jsonl", { mode: "auto" });
c.open();
const fetch = buildFetch(c);   // use this instead of global fetch
try {
  await fetch("https://api.anthropic.com/v1/messages", { method: "POST", body: "..." });
} finally {
  c.close();
}
```

## CLI

```bash
npx agentreplay inspect cassettes/hello.jsonl
npx agentreplay show    cassettes/hello.jsonl 0
npx agentreplay verify  cassettes/hello.jsonl
```

## Divergence

When the request your code sends no longer matches what was recorded (a
prompt changed, a tool schema was edited, …), `agent-replay` produces a
structured diff (`Report`) instead of silently returning stale data. The
`divergence` policy (`"warn" | "error"`) controls whether it throws.

## License

MIT — see [LICENSE](LICENSE).

The Python sibling of this package lives at
[`agent-replay` on PyPI](https://pypi.org/project/agent-replay/).
