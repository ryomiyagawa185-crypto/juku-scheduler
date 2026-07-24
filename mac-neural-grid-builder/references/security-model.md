# security-model — 脅威モデルと防御

## 脅威と対策

| 脅威 | 対策（実装） |
|---|---|
| 不正/変化した host 鍵 | `StrictHostKeyChecking=accept-new`（no 禁止）・untrusted 既定・`node trust` |
| shell injection | argv 配列実行・executor/command allowlist・`looks_like_shell_injection` 検査 |
| path traversal | `safe_join` / `assert_within`（作業ディレクトリ外を拒否） |
| symlink 攻撃 | `assert_not_symlink`（symlink への書込拒否） |
| 未許可コマンド | `validate_argv`（allowlist・basename 検査） |
| 巨大出力 | `max_output_bytes` で truncate |
| 壊れた JSON | envelope/結果の schema 検証・行スキップ |
| 偽装 Worker/改竄 | `payload_hash` 検証（不一致は invalid_input） |
| replay/期限切れ | `expires_at` 検証（quarantine） |
| 外部送信 | ポリシー（機密は外部 API 禁止）・model_router・approval ゲート |
| 秘密値漏洩 | `redact`（ログ/events/監査）・CLI 引数へ埋め込まない・Keychain 推奨 |
| 競合書込 | `file_lock`（flock）・原子的書込 |
| 中断復旧 | 一時ファイル方式・events からの状態再構築 |

## 最小権限とスコープ

ノードごとに信頼レベル。ジョブは permissions/resource_limits を envelope に持つ。ノード間で
秘密値を複製しない。ノード出力は未信頼入力として検証する。

## リスク分類と承認（§15）

read_only / reversible / high_risk。high_risk は対象/件数/容量/外部送信先/使用モデル/必要権限/
不可逆性/バックアップ/ロールバック/予定コマンドを提示し、明示承認を得るまで実行しない。

## 監査（§24）

誰が/いつ/どのノード/なぜ/何を/どのモデル/外部送信/どのファイル/結果/失敗/再試行/承認/キャンセル/
成果物 checksum を記録。秘密値・機密原文・API キーは残さない。`verify` が redaction 漏れを検査。
