# observability — 監査・ログ・状態

## SQLite テーブル（§23・`database.py`）

`nodes / capabilities / jobs / tasks / attempts / artifacts / events / policies / audit_log`。

- **events は append-only**。すべての遷移（job_created/task_assigned/task_started/task_succeeded/
  task_failed/… /artifact_stored）を記録。
- ジョブ/タスクの現在状態は列にも持つが、`rebuild_state()` で events から再構築でき、Control 再起動後の
  復元と `verify` の一致検査に用いる。

## 監査ログ（§24）

`audit_log` に actor/action/data を記録（redact 済み）。node_add/inspect/trust/dispatch_job/
dispatch_task/rollback_job 等。

## CLI での観測

```
mac-neural-grid dashboard          # 概況（ノード数・ジョブ状態分布）
mac-neural-grid job status <id>    # タスク別の状態・ノード・試行回数
mac-neural-grid job inspect <id>   # spec・rebuilt_state・artifacts
mac-neural-grid logs --job <id>    # events（redact 済み）
mac-neural-grid artifacts --job <id>
mac-neural-grid verify             # schema/状態一致/秘密値/checksum を無副作用で検査
```

## 秘密値の非保存

`logging.emit/write_log` と `database.append_event/audit` は書込前に `redact_obj` を通す。
`verify` は監査/イベントに秘密値パターンが残っていないことを確認する。
