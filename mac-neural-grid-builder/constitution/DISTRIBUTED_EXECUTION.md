# DISTRIBUTED_EXECUTION — 分散実行憲法

## D1. 各 Mac は独立ノード（§2）

複数 Mac を一台の巨大コンピュータへ仮想結合しない。RAM/GPU は自動融合しない。システムは
**独立ノードへのジョブ分割・配置・回収・復旧** を行う分散ジョブ実行基盤である。誇張表現を用いない。

## D2. 並列の種別を区別する（§2）

データ並列 / タスク並列 / パイプライン並列 / モデル並列 / 複数モデル協調 / 投票・審議 を区別する。
**信頼性の高いタスク並列とデータ並列を優先**する。モデル並列・巨大モデル分散ロードは基盤安定後。

## D3. 能力ベース配置（§11）

要件（arch/memory/tools/models/labels）を満たさないノードを除外し、
`capability_match × availability × trust × locality × historical_reliability
 − resource_pressure − network_cost` で選ぶ。単純ラウンドロビン・生 CPU 速度だけで選ばない。
高温・低バッテリー・電源未接続・逼迫・スリープ直前のノードには割り当てない（§18/§19）。

## D4. 正本は append-only events（§23）

ジョブ/タスクの現在状態は events から再構築可能にする。snapshot 的な列は高速参照の派生物。
Control 再起動後も events から復元できること（§31）。

## D5. 冪等（§22）

すべてに一意 ID。idempotency_key/input_hash/policy_hash により同一ジョブの再送で二重実行しない。

## D6. 実行隔離（§16）

各タスクは専用作業ディレクトリ（input/work/output/logs/manifest.json/result.json）で実行。
ユーザーの元ファイルを直接変更しない（作業コピー/コピーオンライト）。

## D7. 失敗は分類して有限に再試行（§21）

再試行可能な失敗（transient/resource_exhaustion/node_offline/lost）だけを別ノードで再実行。
非再試行（invalid_input/permission_denied/dependency_missing/policy_denied/deterministic_failure）は
再試行しない。指数バックオフ・上限つき。同じ失敗を無限に繰り返さない。

## D8. リソース制御・caffeinate（§18/§19）

ジョブ単位で timeout/max_retries/優先度/同時実行数/最大メモリ/出力上限/ログ上限/ネットワーク可否/
外部 API 可否/電源必須/最低バッテリーを設定できる。長時間処理は `caffeinate` を **特定ジョブに
スコープ**し、終了後に残らないことを保証する。無期限に Mac を起こし続けない。

## D9. MVP 優先（§34）

最初から全機能を作らない。Phase 1（手動登録・タスク/データ並列・localhost 統合）を安定させてから
Phase 2（常駐・NL 生成・ルーター・機密ポリシー・dashboard）、Phase 3（協調・自動分散・TUI）。
