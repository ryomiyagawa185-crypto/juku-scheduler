# security-cases — セキュリティ検証観点（§33 security）

対応する自動テスト: `mac-neural-grid/tests/test_security.py`。

- [x] 不正/未確認ホスト鍵: `StrictHostKeyChecking=no` を拒否（SecurityError）。
- [x] リモート実行の承認: `allow_remote=False` の SSH transport は run で拒否。
- [x] symlink 攻撃: symlink への原子的書込を拒否。
- [x] path traversal: 作業ディレクトリ外の結合を拒否。
- [x] 未許可コマンド: allowlist 外の実行体を `validate_argv` が拒否。
- [x] shell injection: メタ文字を含むノード出力を `looks_like_shell_injection` が検出。
- [x] 巨大出力: `max_output_bytes` で truncate。
- [x] 壊れた JSON: envelope 破損は exit 2 で拒否。
- [x] 偽装 Worker/改竄: `payload_hash` 不一致は invalid_input で拒否。
- [x] replay/期限切れ: `expires_at` 超過は quarantined。
- [x] 外部送信禁止: 機密ポリシー下の external-api は violation で実行前に停止。
- [x] high_risk 承認: rm を含む shell（ポリシー非違反）は requires_approval で停止。

## 手動確認（実機・承認後）
- [ ] 初回接続で host 鍵を目視確認し known_hosts に固定（`bootstrap-node.zsh`）。
- [ ] 秘密値が CLI 引数・ログ・JSON に残らない（`verify` + Keychain 運用）。
- [ ] ノード間で秘密値を複製しない。
