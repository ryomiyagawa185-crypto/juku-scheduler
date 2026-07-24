# -*- coding: utf-8 -*-
"""mac_neural_grid — 複数 Mac を「計算ノード」として安全に統括する分散 AI ジョブ実行 CLI。

重要な立場（誇張の禁止）:
  本システムは複数 Mac の RAM/GPU を一つに融合しない。各 Mac を独立した *ノード* として扱う
  分散ジョブ実行基盤である。中央 Control Node が、能力ベースでジョブを分割・配置し、SSH（将来）
  もしくは localhost（MVP）で配送し、成果物を回収・監査・復旧する。

MVP (Phase 1) の範囲:
  - 手動ノード登録（SSH host-key 確認あり）
  - 能力調査（node inspect・クロスプラットフォーム、macOS 重視で graceful degradation）
  - タスク並列 / データ並列（per-file 分割）
  - localhost での複数 Worker 模擬統合試験（local transport・実プロセス隔離）
  - SQLite（append-only events からジョブ状態を再構築）
  - checksum つき成果物回収 / retry 分類 / cancel / audit log / verify

将来（Phase 2/3）は Worker 常駐(launchd)・自然言語ジョブ生成の高度化・AI モデルルーター拡張・
複数 AI 協調・自動負荷分散。設計は CLI/protocol/scheduler/storage/executor を分離し、Rust 移行に備える。
"""

__version__ = "0.1.0"
PROTOCOL_VERSION = "mng/1"
