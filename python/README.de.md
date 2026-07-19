<!-- Sprache: [English](README.md) | [日本語](README.ja.md) | **Deutsch** -->

# agent-replay (Python)

LLM-API-Aufrufe für deterministische Agent-Tests aufzeichnen und wiedergeben.

`agent-replay` zeichnet den HTTP-Verkehr, den dein Agent an LLM-Anbieter
(Anthropic, OpenAI, …) sendet, in einer menschenlesbaren JSONL-„Kassette"
auf und spielt ihn bei späteren Testläufen wieder ab. Deine Tests werden
dadurch schnell, offline lauffähig und deterministisch — und wenn sich ein
Prompt gegenüber der Aufzeichnung verändert hat, wird das ausdrücklich
gemeldet, statt stillschweigend veraltete Daten zurückzugeben.

## Installation

```bash
pip install agent-replay
```

Optionale Extras:

```bash
pip install "agent-replay[pytest]"   # pytest-Fixture und -Marker
```

## Schnellstart

```python
import agentreplay as ar

with ar.cassette("tests/cassettes/hello.jsonl", mode="auto") as c:
    client = c.httpx_client()   # ein vorkonfigurierter httpx.Client
    r = client.post(
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}]},
    )
    print(r.json())
```

- Erster Lauf: Die Kassettendatei existiert noch nicht → die echte Antwort
  wird aufgezeichnet.
- Spätere Läufe: Die Datei existiert → die aufgezeichnete Antwort wird
  ausgeliefert, ohne Netzwerkzugriff.
- `mode` akzeptiert `"record" | "replay" | "auto" | "passthrough"` und kann
  global über die Umgebungsvariable `AGENTREPLAY_MODE` überschrieben werden.

Asynchron funktioniert es genauso:

```python
async with ar.cassette("tests/cassettes/hello.jsonl") as c:
    async with c.httpx_async_client() as client:
        r = await client.post(...)
```

## pytest

`agent-replay` bringt ein pytest-Plugin mit. Kassetten werden automatisch
nach der Test-Node-ID benannt und unter `tests/cassettes/` abgelegt.

```python
import pytest

@pytest.mark.agentreplay(mode="auto")
def test_agent(agentreplay):
    client = agentreplay.httpx_client()
    ...
```

## CLI

```bash
agentreplay inspect tests/cassettes/hello.jsonl   # Header + Zusammenfassung
agentreplay show    tests/cassettes/hello.jsonl 0 # seq 0 hübsch ausgeben
agentreplay verify  tests/cassettes/hello.jsonl   # Struktur & Fingerprints prüfen
```

## Divergenz

Wenn die Anfrage, die dein Code sendet, nicht mehr mit der Aufzeichnung
übereinstimmt (ein Prompt wurde geändert, ein Tool-Schema wurde angepasst,
…), erzeugt `agent-replay` ein strukturiertes Diff (`ar.Report`), anstatt
stillschweigend veraltete Daten zurückzugeben. Die `divergence`-Policy
(`"warn" | "error"`) steuert, ob dabei eine Exception geworfen wird.

## Lizenz

MIT — siehe [LICENSE](LICENSE).

Das TypeScript-Pendant dieses Pakets findest du unter
[`@retr0hxx/agent-replay`](https://www.npmjs.com/package/@retr0hxx/agent-replay).
