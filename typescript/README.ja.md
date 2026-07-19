<!-- 言語: [English](README.md) | **日本語** | [Deutsch](README.de.md) -->

# @retr0hxx/agent-replay

決定論的なエージェントテストのための、LLM API 呼び出しの記録＆再生ライブラリ。

`agent-replay` はエージェントが LLM プロバイダ（Anthropic、OpenAI など）に対して
発行する HTTP 通信を、人間が読める JSONL 形式の「カセット」に記録し、次回以降の
実行ではそのカセットを再生します。テストは高速・オフライン・決定論的になり、
プロンプトが記録時と乖離した場合は静かに古い応答を返すのではなく差分として
明示的に報告します。

## インストール

```bash
npm install --save-dev @retr0hxx/agent-replay
```

Node.js `>= 20` が必要です（組み込みのグローバル `fetch` を使用します）。

## クイックスタート（vitest / jest / node:test）

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

- 初回実行: カセットファイルが存在しない → 実際のレスポンスを記録します。
- 2回目以降: ファイルが存在する → 記録済みレスポンスを返します（ネットワーク未使用）。
- `mode` は `"record" | "replay" | "auto" | "passthrough"` を受け付け、
  環境変数 `AGENTREPLAY_MODE` で全体を上書きできます。

## 低レベル API

グローバル `fetch` を差し替えたくない場合は、明示的にラップできます:

```ts
import { Cassette, buildFetch } from "@retr0hxx/agent-replay";

const c = new Cassette("cassettes/hello.jsonl", { mode: "auto" });
c.open();
const fetch = buildFetch(c);   // グローバル fetch の代わりに使う
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

## 差分（Divergence）

コードが送信するリクエストが記録時と一致しなくなった場合（プロンプトの変更、
ツールスキーマの編集など）、`agent-replay` は古いデータを黙って返す代わりに
構造化された差分（`Report`）を生成します。`divergence` ポリシー
（`"warn" | "error"`）で例外を投げるかどうかを制御できます。

## ライセンス

MIT — [LICENSE](LICENSE) を参照。

Python 版は
[PyPI の `agent-replay-py`](https://pypi.org/project/agent-replay-py/)
にあります。
