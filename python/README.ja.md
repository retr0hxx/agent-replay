<!-- 言語: [English](README.md) | **日本語** | [Deutsch](README.de.md) -->

# agent-replay (Python)

決定論的なエージェントテストのための、LLM API 呼び出しの記録＆再生ライブラリ。

`agent-replay` はエージェントが LLM プロバイダ（Anthropic、OpenAI など）に対して
発行する HTTP 通信を、人間が読める JSONL 形式の「カセット」に記録し、次回以降の
実行ではそのカセットを再生します。テストは高速・オフライン・決定論的になり、
プロンプトが記録時と乖離した場合は静かに古い応答を返すのではなく差分として
明示的に報告します。

## インストール

```bash
pip install agent-replay-py
```

インストール名は `agent-replay-py`、import 名は `agentreplay` です
（PyPI に別プロジェクト `agentreplay` が存在するため、配布名だけ区別しています）。

オプション:

```bash
pip install "agent-replay-py[pytest]"   # pytest フィクスチャとマーカー
```

## クイックスタート

```python
import agentreplay as ar

with ar.cassette("tests/cassettes/hello.jsonl", mode="auto") as c:
    client = c.httpx_client()   # 事前設定済みの httpx.Client
    r = client.post(
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}]},
    )
    print(r.json())
```

- 初回実行: カセットファイルが存在しない → 実際のレスポンスを記録します。
- 2回目以降: ファイルが存在する → 記録済みレスポンスを返します（ネットワーク未使用）。
- `mode` は `"record" | "replay" | "auto" | "passthrough"` を受け付け、
  環境変数 `AGENTREPLAY_MODE` で全体を上書きできます。

非同期も同じ形です:

```python
async with ar.cassette("tests/cassettes/hello.jsonl") as c:
    async with c.httpx_async_client() as client:
        r = await client.post(...)
```

## pytest

`agent-replay` には pytest プラグインが同梱されています。カセットはテストの
ノード ID から自動命名され、`tests/cassettes/` 配下に保存されます。

```python
import pytest

@pytest.mark.agentreplay(mode="auto")
def test_agent(agentreplay):
    client = agentreplay.httpx_client()
    ...
```

## CLI

```bash
agentreplay inspect tests/cassettes/hello.jsonl   # ヘッダーと相互作用のサマリー
agentreplay show    tests/cassettes/hello.jsonl 0 # seq 0 を整形表示
agentreplay verify  tests/cassettes/hello.jsonl   # 構造と指紋を再検証
```

## 差分（Divergence）

コードが送信するリクエストが記録時と一致しなくなった場合（プロンプトの変更、
ツールスキーマの編集など）、`agent-replay` は古いデータを黙って返す代わりに
構造化された差分（`ar.Report`）を生成します。`divergence` ポリシー
（`"warn" | "error"`）で例外を投げるかどうかを制御できます。

## ライセンス

MIT — [LICENSE](LICENSE) を参照。

TypeScript 版は
[`@retr0hxx/agent-replay`](https://www.npmjs.com/package/@retr0hxx/agent-replay)
にあります。
