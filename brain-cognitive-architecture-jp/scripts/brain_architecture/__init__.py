# -*- coding: utf-8 -*-
"""brain_architecture — 監査可能な適応型認知アーキテクチャの計算コア。

このパッケージは「人間の脳の再現」ではない。脳科学で比較的支持されている
機能原理（感覚ゲート・注意・作業記憶・エピソード/意味/手続記憶・パターン
分離/補完・予測誤差・強化/抑制・固定化/忘却・メタ認知）を、**決定的で
再現可能・監査可能なソフトウェア機構**へ翻訳したものである。

分離の鉄則:
  - event log = 事実（append-only・不変）
  - snapshot  = 派生状態（event log から replay で再構築可能）
  - proposal  = 仮説（自動では本番に入らない）
  - promotion = 承認済み変更（人間ゲートを通過したものだけ）

数値・状態遷移はこの決定的 Python だけが書く。モデル（LLM）は読むだけ。
比喩とアルゴリズムの境界は references/neuroscience-to-software-map.md を参照。
"""

__version__ = "1.0.0"
__engine_version__ = "1.0.0"
__schema_version__ = "1.0.0"
