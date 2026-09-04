# -*- coding: utf-8 -*-
"""model_router — タスクごとに最適な AI 実行方法を選ぶ（仕様 §12）。

候補: Claude Code / Claude API / OpenAI API / ローカルLLM / ルールベース / 決定的スクリプト /
複数モデル審議。ルーティング条件: 機密性・入力容量・必要精度・速度・コスト・ネットワーク可否・
ローカルモデル能力・タスク種別・再現性・外部送信許可。

原則:
  - 機密文書は明示許可が無い限り外部 AI API を使わない。
  - 数値処理・ファイル変換・checksum 等は AI に任せず決定的ツールを優先する。
"""

# タスク種別 → 決定的に処理すべき（AI 不要）ものの集合（§12）。
_DETERMINISTIC_TYPES = {"checksum", "convert", "hash", "rename", "count", "extract"}


def route(task, policy, node_capabilities=None):
    """タスクの実行方法を決め {method, executor, reason, external} を返す。"""
    policy = policy or {}
    ttype = (task.get("type") or "").lower()
    executor = task.get("executor")
    caps = node_capabilities or {}
    tools = caps.get("tools") or {}

    # 1) 決定的で済むものは AI を使わない。
    if executor in ("checksum", "shell", "python", "ffmpeg", "custom-script") or \
            any(k in ttype for k in _DETERMINISTIC_TYPES):
        return {"method": "deterministic", "executor": executor or "shell",
                "external": False, "reason": "決定的ツールで十分（AI 不要・§12）"}

    confidential = (policy.get("external_ai_api") is False) or \
        (policy.get("external_network") is False)

    # 2) 機密: 外部 API 禁止。ローカル推論があればそれ、無ければ決定的抽出へ。
    if confidential:
        if tools.get("ollama"):
            return {"method": "local-llm", "executor": "local-llm", "external": False,
                    "reason": "機密ポリシー: ローカル推論のみ使用（外部送信なし・§12）"}
        return {"method": "deterministic", "executor": "document-summary",
                "external": False,
                "reason": "機密かつローカル推論なし: 決定的抽出要約で処理（外部送信なし）"}

    # 3) 外部許可あり: ローカルを優先しつつ、精度要求が高ければ外部 API を候補に。
    if policy.get("prefer_local_models") and tools.get("ollama"):
        return {"method": "local-llm", "executor": "local-llm", "external": False,
                "reason": "prefer_local_models: ローカル推論を優先"}
    if tools.get("claude_code"):
        return {"method": "claude-code", "executor": "claude-code", "external": True,
                "reason": "Claude Code CLI が利用可能（外部送信あり・要ポリシー許可）"}
    return {"method": "deterministic", "executor": executor or "document-summary",
            "external": False, "reason": "既定: 決定的処理へフォールバック"}


def coordination_note(strategy):
    """複数 AI 協調の注意（§13）。一致=正しいとしない。独立性のない多数決を強い証拠にしない。"""
    return {
        "strategy": strategy,
        "caveat": "複数モデルが一致しても正しいとは限らない。独立性のないモデル間の多数決を"
                  "強い証拠として扱わない（§13）。",
    }
