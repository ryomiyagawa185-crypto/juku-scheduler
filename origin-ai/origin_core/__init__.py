"""origin_core — 純粋ライブラリ（副作用なし・判断なし）。

スキルからの import を許可する唯一のパッケージ。
ここに置いてよいのは「副作用も判断も持たない処理」だけ:
スキーマ検証・ハッシュ・トークン計数・単価計算・トレース書き出し。

LLM の判断が入るもの（fact-check-guard 等）はここではなくメタスキルにし、
台帳経由で呼ぶこと。スキル間の直接 import は
scripts/check_skill_independence.py が拒否する。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

__all__ = ["ROOT", "hashing", "schema", "tokens", "pricing", "tracing"]
