<!-- 言語: [English](README.md) | **日本語** | [Deutsch](README.de.md) -->

# agent-replay

決定論的なエージェントテストのための、LLM API 呼び出しの記録＆再生ライブラリ。

`agent-replay` はエージェントが LLM プロバイダ（Anthropic、OpenAI など）に対して
発行する HTTP 通信を、人間が読める JSONL 形式の「カセット」に記録し、次回以降の
実行ではそのカセットを再生します。テストは高速・オフライン・決定論的になり、
プロンプトが記録時と乖離した場合は静かに古い応答を返すのではなく構造化された
差分として明示的に報告します。

このリポジトリには **Python 版と TypeScript 版** の 2 実装が入っており、
カセット形式は共通化されているので、片方で記録したカセットをもう片方で
再生することもできます。

## パッケージ

| ランタイム | パッケージ | インストール |
|---|---|---|
| Python (≥ 3.10) | [`agent-replay-py`](https://pypi.org/project/agent-replay-py/) | `pip install agent-replay-py` |
| Node.js (≥ 20)  | [`@retr0hxx/agent-replay`](https://www.npmjs.com/package/@retr0hxx/agent-replay) | `npm install --save-dev @retr0hxx/agent-replay` |

## ディレクトリ構成

```
python/       # Python パッケージ — pytest プラグイン + httpx ラッパー + CLI
typescript/   # TypeScript パッケージ — fetch パッチ + withCassette ヘルパー + CLI
goldens/      # 両実装のテストで共有する言語横断 JSONL フィクスチャ
```

言語別の詳細ドキュメントと API 例は各パッケージ配下にあります:

- Python: [`python/README.ja.md`](python/README.ja.md) ([English](python/README.md) / [Deutsch](python/README.de.md))
- TypeScript: [`typescript/README.ja.md`](typescript/README.ja.md) ([English](typescript/README.md) / [Deutsch](typescript/README.de.md))

## 一目でわかる使い方

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

どちらも `mode: "record" | "replay" | "auto" | "passthrough"` を受け付け、
環境変数 `AGENTREPLAY_MODE` で全体を上書きできます。

## なぜモックではなく記録＆再生なのか

モックはトランスポート層を書き換えて「偽の応答」を返しますが、
`agent-replay` は本物のトランスポートを一度だけ記録し、次回以降は
バイト単位でそのまま再生します。プロンプトが変わったときには
本番挙動から静かにズレていくのではなく、差分として明示的に検知できます。

## ライセンス

MIT — [LICENSE](LICENSE) を参照。
