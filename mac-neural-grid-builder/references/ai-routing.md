# ai-routing — AI モデルルーティング

## 候補と条件（§12）

候補: Claude Code / Claude API / OpenAI API / ローカル LLM / ルールベース / **AI を使わない決定的
スクリプト** / 複数モデル審議。ルーティング条件: 機密性・入力容量・必要精度・速度・コスト・
ネットワーク可否・ローカルモデル能力・タスク種別・再現性・外部送信許可。

## 原則（`model_router.route`）

1. **決定的で済むものは AI を使わない**。checksum・ファイル変換・数値処理・rename は決定的ツール優先。
2. **機密は外部 API 不使用**。`external_ai_api: false` / `external_network: false` のポリシー下では、
   ローカル推論（ollama 等）があればそれ、無ければ **決定的抽出要約** へフォールバック（外部送信ゼロ）。
3. 外部許可があり `prefer_local_models` ならローカル優先。精度要求が高い時のみ外部 API を候補に。

## 複数 AI 協調（§13）

parallel generation / independent review / critic / judge / majority vote / weighted vote / debate /
specialist routing / consensus。ただし:

- **複数モデルが一致しただけで正しいと判断しない**。
- **独立性のないモデル同士の多数決を、強い証拠として扱わない**（`model_router.coordination_note`）。

MVP は協調を実装せず、決定的処理と（能力があれば）ローカル推論に限定する。
