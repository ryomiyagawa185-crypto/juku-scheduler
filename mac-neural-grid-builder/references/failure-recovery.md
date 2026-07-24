# failure-recovery — 障害と復旧

## 想定する障害（§31）

Mac スリープ・ネットワーク切断・SSH 切断・Worker 停止・ディスク不足・メモリ不足・高温・ツール欠損・
成果物破損・部分転送・処理中の再起動・Control Node 停止。

## 失敗分類と再試行（§21・`retry.py`）

| クラス | 再試行 |
|---|---|
| transient / resource_exhaustion / node_offline / lost | ○（別ノード・指数バックオフ・上限つき） |
| invalid_input / permission_denied / dependency_missing / policy_denied / deterministic_failure | ×（再試行しない） |

同じ失敗を無限に繰り返さない。`should_retry(fc, attempt_no, max_retries)` で制御。

## Control Node 再起動（§31）

ジョブ状態は append-only events から `rebuild_state()` で再構築できる。`job inspect <id>` の
`rebuilt_state` が復元結果。列との不一致は `verify` が warning として検出。

## ロールバック（§16・`rollback.py`）

- `backup` で DB/config を checksum つき退避、`restore --backup ... [--dry-run]` で復元
  （checksum 不一致は拒否）。
- `job cancel <id>` = `rollback_job`: 未完了タスクを cancelled にし、work/ を掃除（監査・成果物の
  append-only 記録は保持）。

## 成果物の完全性

一時名 → checksum → 原子的改名。`collect` は manifest と実ファイルの checksum を突き合わせ、
不一致は例外。部分転送は正式名に昇格しない。

## 既知の制限

- リモート障害（SSH 切断・リモート Worker 停止）は Phase 2 の実機連携で扱う。MVP は localhost のため
  未検証。分散環境での厳密な直列化はホスト内ロックの範囲に限る。
- リアルタイム心拍・ノード自己申告は Phase 3。現状は inspect 時点のスナップショットで判断する。
