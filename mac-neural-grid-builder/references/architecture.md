# architecture — 全体構成

```
Control Node (cli.py)
  → Scheduler (scheduler.py・能力ベース)
  → Dispatcher (dispatcher.py)
  → Worker Agents (worker.py・実プロセス隔離)
  → Executors (executor.py・allowlist)
  → Artifacts/Results (artifact_store.py)
  ↑ Policy(policy_engine) / Model Router(model_router) / Health(health) / Retry(retry) /
    Audit+SQLite append-only events(database) / Ids(ids) / Security(security)
```

## レイヤ分離（Rust 移行に備える・§5）

CLI / プロトコル / スケジューラ / ストレージ / 実行エンジンを独立させる。プロトコル（envelope）と
スケジューラは純粋なデータ変換に寄せ、副作用（FS/SSH/DB）は transport/artifact_store/database に閉じる。

## Control と Worker の責務

- Control: CLI 受付・自然言語の構造化(nlplan)・ノード/ジョブ台帳・スケジューリング・ポリシー判定・
  状態表示・ログ集約・成果物管理。
- Worker: 能力報告・許可ジョブのみ受信・作業ディレクトリ作成・実行・ログ/成果物返送・
  タイムアウト/中断対応・一時データの安全な扱い。

## 実行フロー

`split_tasks → policy evaluate(risk gate) → create_job(idempotent) → per task: select_node →
stage → envelope(payload_hash,expires) → worker(subprocess) → result → retry.classify → collect →
aggregation → job status(succeeded/partial/failed)`。

## transport（local / ssh / sim）

- `local`: subprocess で argv 実行（localhost・複数 Worker を実プロセス隔離）。
- `ssh`（Phase 2・実装済み）: rsync で package 配備＋入力ステージング → `ssh … python3 -m
  mac_neural_grid.worker` でリモート Worker 起動 → rsync で成果物フェッチ → checksum 検証。
  `StrictHostKeyChecking=no` を拒否。`--allow-remote` の明示承認が無ければ実行しない（§36）。
  OpenSSH は destination 以降を command とするため `--` を付けず、remote 再分割対策として引数に空白を
  含めない（`python3 -c "…"` の形は使わず module 実行にする）。SSH/rsync の argv と配送制御フローは
  ユニット/シミュレーションテスト済み。**実機ネットワーク越しは未検証（canary 必須）**。
- `LocalRemoteSimTransport`: 同一ホストで「リモート配送」を模擬し、ステージング→リモート実行→フェッチ→
  checksum の全経路をネットワーク無しで検証するテスト用 transport。
