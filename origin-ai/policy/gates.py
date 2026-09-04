"""ゲートの分類と、ツール呼び出し → ゲートの対応表。

ここは **育てる前提** の表。新しいツールや MCP を足したら、
その都度どのゲートに載るかを決めて追記すること。
未知のツールがどう扱われるかは classify_tool() の既定値で決まり、
既定は「外部作用の可能性があるものは人間承認」側に倒してある。
"""

from __future__ import annotations

import re

# 人間の承認を必要とするゲート
HUMAN_GATES = frozenset({"external-send", "legal-submission", "destructive-ops"})

# 「今後すべて許可」を作らせないゲート（毎回承認）
NO_BLANKET_APPROVAL = frozenset({"destructive-ops", "legal-submission"})

# 外部作用があるため自動リトライを禁じるゲート（二重送信防止）
EXTERNAL_EFFECT_GATES = frozenset({"external-send", "legal-submission"})

# メタスキルとしてパイプライン内で実行されるゲート。decide はブロックしない
AUTO_GATES = frozenset({"fact-check-guard"})

# 読み取り専用ツール（推論層に許可してよい）
READ_ONLY_TOOLS = frozenset(
    {"Read", "Grep", "Glob", "NotebookRead", "TodoRead", "WebSearch"}
)

WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})

# コマンド文字列に含まれていたら destructive-ops を発火させる
DESTRUCTIVE_PATTERNS = [
    r"\brm\s+-[a-zA-Z]*[rf]",
    r"\bgit\s+push\b.*--force",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[a-zA-Z]*f",
    r"\bdd\s+if=",
    r"\bmkfs\b",
    r"\btruncate\b",
    r"\bshred\b",
    r">\s*/dev/sd",
]

# 名前にこれらを含むツールは外部送信とみなす
EXTERNAL_SEND_HINTS = ("send", "post", "publish", "email", "mail", "notify", "tweet", "webhook")


def classify_tool(tool_name: str, tool_input: dict) -> tuple[str, ...]:
    """ツール呼び出しから発火すべきゲートを返す。

    既定は保守的側。判断がつかないツールは external-send 扱いにして
    人間に見せる（見せすぎは直せるが、見せ落としは事故になる）。
    """
    if tool_name in READ_ONLY_TOOLS:
        return ()

    lowered = tool_name.lower()

    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        if any(re.search(p, command) for p in DESTRUCTIVE_PATTERNS):
            return ("destructive-ops",)
        if re.search(r"\bcurl\b.*(-X\s*(POST|PUT|DELETE)|--data)", command):
            return ("external-send",)
        return ()

    if tool_name in WRITE_TOOLS:
        return ()  # ローカルの下書き作業は緩和側。出力先の妥当性は classification が見る

    if any(hint in lowered for hint in EXTERNAL_SEND_HINTS):
        return ("external-send",)

    if lowered.startswith("mcp__"):
        # 未知の MCP ツールは外部サービスに触る前提で扱う
        return ("external-send",)

    return ()


def requires_human(gates: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(g for g in gates if g in HUMAN_GATES)


def has_external_effect(gates: tuple[str, ...] | list[str]) -> bool:
    return any(g in EXTERNAL_EFFECT_GATES for g in gates)
