# job-protocol — ジョブ/タスク/envelope プロトコル

## Job と Task の分離（§10）

```
Job ─┬─ Task 1
     ├─ Task 2
     └─ Aggregation Task
```

ジョブ YAML 例（§10。`job:` サブキー形は loader が平坦化）:

```yaml
job:
  name: pdf-summary
  policy: confidential-local-only
tasks:
  - type: document-summary
    input_glob: ./documents/*.pdf
    split: per-file            # データ並列
    executor: local-llm
    requirements: {architecture: arm64, memory_gb_min: 16, capabilities: [pdftotext, local-llm]}
aggregation: {type: merge-summaries, node: control}
```

分割戦略（`jobspec.split_tasks`）: `per-file`（1ファイル1タスク）/ `per-item` / `none`。

## 配送 envelope（§9）

`transport → node` の各メッセージに含める:
`protocol_version / job_id / task_id / attempt_id / node_id / command_type / payload_hash /
created_at / expires_at / permissions / resource_limits / result_destination / payload`。

- Worker は schema・`payload_hash`・`expires_at`（replay 対策）・protocol を検証してから実行。
- 期限切れは `quarantined`、改竄は `invalid_input` で拒否。

## 状態（§21）

`pending → assigned → running → succeeded/failed/retrying/cancel_requested/cancelled/timed_out/
lost/quarantined`。ジョブは `pending/planned/running/partial/succeeded/failed/cancelled`。

## 冪等（§22）

`idempotency_key = f(name, input_hash, policy_name)`。既存ジョブがあれば再利用し二重実行しない。
