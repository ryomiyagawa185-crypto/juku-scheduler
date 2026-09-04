"""policy — 予算・ゲート・承認・データ分類の判定を行う単一モジュール。

対話セッション（.claude/hooks/）とバッチ実行（orchestrator/middleware.py）の
両方がここを呼ぶ。判定をここ以外に書かないこと。書いた瞬間に
「どちらかの経路でだけ効くルール」が生まれ、ガバナンスに穴が開く。
"""

from .context import PolicyContext
from .decide import BLOCKED, PROCEED, WAITING_APPROVAL, Decision, decide

__all__ = [
    "PolicyContext",
    "Decision",
    "decide",
    "PROCEED",
    "BLOCKED",
    "WAITING_APPROVAL",
]
