<!-- Sprache: [English](README.md) | [日本語](README.ja.md) | **Deutsch** -->

# agent-replay

LLM-API-Aufrufe für deterministische Agent-Tests aufzeichnen und wiedergeben.

`agent-replay` zeichnet den HTTP-Verkehr, den dein Agent an LLM-Anbieter
(Anthropic, OpenAI, …) sendet, in einer menschenlesbaren JSONL-„Kassette"
auf und spielt ihn bei späteren Testläufen wieder ab. Deine Tests werden
schnell, offline lauffähig und deterministisch — und wenn sich ein Prompt
gegenüber der Aufzeichnung verändert hat, bekommst du ein strukturiertes
Diff statt einer stillschweigend veralteten Antwort.

Dieses Repository enthält **zwei parallele Implementierungen** mit einem
gemeinsamen Kassettenformat, sodass eine mit einer Sprache aufgezeichnete
Kassette in der anderen wiedergegeben werden kann.

## Pakete

| Runtime | Paket | Installation |
|---|---|---|
| Python (≥ 3.10) | [`agent-replay-py`](https://pypi.org/project/agent-replay-py/) | `pip install agent-replay-py` |
| Node.js (≥ 20)  | [`@retr0hxx/agent-replay`](https://www.npmjs.com/package/@retr0hxx/agent-replay) | `npm install --save-dev @retr0hxx/agent-replay` |

## Verzeichnisstruktur

```
python/       # Python-Paket — pytest-Plugin + httpx-Wrapper + CLI
typescript/   # TypeScript-Paket — fetch-Patch + withCassette-Helper + CLI
goldens/      # Sprachübergreifende JSONL-Fixtures, geteilt von beiden Testsuiten
```

Sprachspezifische Dokumentation und API-Beispiele findest du in den
jeweiligen Paketverzeichnissen:

- Python: [`python/README.de.md`](python/README.de.md) ([English](python/README.md) / [日本語](python/README.ja.md))
- TypeScript: [`typescript/README.de.md`](typescript/README.de.md) ([English](typescript/README.md) / [日本語](typescript/README.ja.md))

## Auf einen Blick

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

Beide akzeptieren `mode: "record" | "replay" | "auto" | "passthrough"` und
lassen sich global über die Umgebungsvariable `AGENTREPLAY_MODE`
überschreiben.

## Warum nicht einfach mocken?

Mocks ersetzen die Transportschicht durch Fälschungen; `agent-replay`
zeichnet den echten Transport einmal auf und spielt ihn danach Byte für Byte
wieder ab. Wenn sich der Prompt ändert, siehst du das Diff — statt still
und leise vom Produktionsverhalten wegzudriften.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
