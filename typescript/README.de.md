<!-- Sprache: [English](README.md) | [日本語](README.ja.md) | **Deutsch** -->

# @retr0hxx/agent-replay

LLM-API-Aufrufe für deterministische Agent-Tests aufzeichnen und wiedergeben.

`agent-replay` zeichnet den HTTP-Verkehr, den dein Agent an LLM-Anbieter
(Anthropic, OpenAI, …) sendet, in einer menschenlesbaren JSONL-„Kassette"
auf und spielt ihn bei späteren Testläufen wieder ab. Deine Tests werden
dadurch schnell, offline lauffähig und deterministisch — und wenn sich ein
Prompt gegenüber der Aufzeichnung verändert hat, wird das ausdrücklich
gemeldet, statt stillschweigend veraltete Daten zurückzugeben.

## Installation

```bash
npm install --save-dev @retr0hxx/agent-replay
```

Benötigt Node.js `>= 20` (verwendet das eingebaute globale `fetch`).

## Schnellstart (vitest / jest / node:test)

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

- Erster Lauf: Die Kassettendatei existiert noch nicht → die echte Antwort
  wird aufgezeichnet.
- Spätere Läufe: Die Datei existiert → die aufgezeichnete Antwort wird
  ausgeliefert, ohne Netzwerkzugriff.
- `mode` akzeptiert `"record" | "replay" | "auto" | "passthrough"` und kann
  global über die Umgebungsvariable `AGENTREPLAY_MODE` überschrieben werden.

## Low-Level-API

Wenn du das globale `fetch` nicht patchen möchtest, kannst du es explizit
umhüllen:

```ts
import { Cassette, buildFetch } from "@retr0hxx/agent-replay";

const c = new Cassette("cassettes/hello.jsonl", { mode: "auto" });
c.open();
const fetch = buildFetch(c);   // anstelle des globalen fetch verwenden
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

## Divergenz

Wenn die Anfrage, die dein Code sendet, nicht mehr mit der Aufzeichnung
übereinstimmt (ein Prompt wurde geändert, ein Tool-Schema wurde angepasst,
…), erzeugt `agent-replay` ein strukturiertes Diff (`Report`), anstatt
stillschweigend veraltete Daten zurückzugeben. Die `divergence`-Policy
(`"warn" | "error"`) steuert, ob dabei eine Exception geworfen wird.

## Lizenz

MIT — siehe [LICENSE](LICENSE).

Das Python-Pendant dieses Pakets findest du unter
[`agent-replay` auf PyPI](https://pypi.org/project/agent-replay/).
