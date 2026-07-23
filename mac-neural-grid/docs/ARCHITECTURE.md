# アーキテクチャ（mac-neural-grid MVP）

## レイヤ分離（Rust 移行に備える）

CLI / プロトコル / スケジューラ / ストレージ / 実行エンジンを分離している。

| 層 | モジュール | 役割 |
|---|---|---|
| CLI | `cli.py` `__main__.py` | コマンド受付・出力・対話モード |
| 設定 | `config.py` | パス解決・既定値（コードと分離したポリシーは DB/`config/policies.yaml`） |
| 安全 | `security.py` | 原子的書込・path/symlink 防止・redaction・argv/allowlist・hash |
| 台帳 | `inventory.py` `discovery.py` `health.py` | ノード登録・能力調査・健全性ゲート |
| スケジューラ | `scheduler.py` | 能力ベース node_score（非ラウンドロビン） |
| ルーティング | `model_router.py` `policy_engine.py` | AI 実行方法選定・ポリシー/リスク判定 |
| 配送 | `dispatcher.py` `transport.py` | タスク配送・local/ssh transport |
| 実行 | `worker.py` `executor.py` | Worker Agent・executor allowlist |
| 成果物 | `artifact_store.py` | 一時名→checksum→原子的改名 |
| 復旧 | `retry.py` `rollback.py` | 失敗分類・再試行・backup/restore/rollback |
| 記録 | `database.py` `logging.py` `ids.py` | SQLite・append-only events・監査・冪等ID |

## 実行フロー

```
job run <spec>
  → jobspec.split_tasks         # Job を Task へ（per-file 等でデータ並列）
  → policy_engine.evaluate      # ポリシー適合・リスク分類（high_risk は承認ゲート）
  → _create_job (idempotent)    # job/tasks を DB へ（idempotency_key で二重実行防止）
  → dispatcher.dispatch_job
       per task, per attempt:
         scheduler.select_node  # capability×availability×trust×locality×reliability − pressure − net
         stage inputs → build envelope(payload_hash, expires_at)
         transport(local): subprocess `python -m mac_neural_grid.worker`  ← 実プロセス隔離
              worker: validate(schema, payload_hash, expiry) → executor → result.json/manifest.json
         retry.classify → 再試行可能なら別ノードへ
         artifact_store.collect # checksum 検証つき登録・中央集約
  → aggregation (control node)  # merge-summaries 等
  → job status: succeeded / partial / failed
```

## 正本と派生（§23）

- **正本**: `events`（append-only）。すべての遷移を記録。
- **派生**: `jobs.status` / `tasks.status` は高速参照用の列。`rebuild_state()` で events から再構築でき、
  Control 再起動後の復元と `verify` の一致検査に用いる。

## 分散推論の区別（§2）

データ並列 / タスク並列 / パイプライン並列 / モデル並列 / 複数モデル協調 / 投票・審議 を区別する。
**MVP はタスク並列とデータ並列のみ**を確実に実装。モデル並列・巨大モデル分散ロードは基盤安定後。

## 既知の制限

- リモート Mac は未実行（SSH transport は `allow_remote` 承認まで無効）。実機連携は Phase 2。
- 非 macOS では能力調査が degrade（本番は macOS 想定）。
- スケジューラの負荷分散はジョブ内の in-memory カウンタによる近似（リアルタイム心拍は Phase 2）。
- executor allowlist は多層防御の一層であり唯一の境界ではない。作業ディレクトリ制限・timeout・
  出力上限・ポリシーと併せて機能する。
