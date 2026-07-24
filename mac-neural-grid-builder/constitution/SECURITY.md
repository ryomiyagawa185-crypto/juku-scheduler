# SECURITY — セキュリティ憲法（mac-neural-grid）

自動改変不可。設計・実装・保守のすべてで遵守する。

## S1. 接続と認証（§8/§29）

- SSH 鍵認証。**`StrictHostKeyChecking=no` を既定にしない**（`accept-new` は初回のみ受理し以後固定）。
- host 鍵不一致を無視しない。未確認のリモートは `trust=untrusted` で登録し、確認後に `node trust`。
- 最小権限。ノードごとに信頼レベル（untrusted/low/medium/high）。IP を node_id に固定しない。

## S2. コマンド実行（§17）

- **argv 配列のみ**。`shell=True` の無制限利用・`eval`・未引用変数・外部入力の直接実行・`curl | bash`・
  SSH 先での無検証 `sudo`・秘密値の CLI 引数埋め込みを禁止。
- executor allowlist・command allowlist・引数検証・作業ディレクトリ制限・timeout・resource limit・
  出力サイズ上限。これらは多層防御であり、単一の allowlist を唯一の境界にしない。
- **ノードから受け取った出力も未信頼入力**として検証する（injection・巨大出力・壊れた JSON）。

## S3. ジョブ完全性（§9/§22/§29）

- envelope に `protocol_version / payload_hash / created_at / expires_at / permissions /
  resource_limits` を含め、Worker が schema・payload_hash・期限（replay 対策）を検証。
- 一意 ID と idempotency_key で二重実行を防ぐ。期限切れジョブは quarantine。

## S4. ファイルシステム（§16/§20）

- 原子的書込（一時名 → fchmod 0600 → fsync → os.replace → 親 dir fsync）・0700 ディレクトリ。
- path traversal / symlink 攻撃を防止（`safe_join` / `assert_within` / symlink 書込拒否）。
- 成果物は 一時名 → checksum 確認 → 原子的改名。空き容量・サイズ・上書きを確認。

## S5. リスクゲート（§15）

- read_only / reversible / high_risk を分類。high_risk（削除・上書き・移動・権限変更・sudo・
  launchd・外部送信・AI API 送信・複数 Mac 一括変更・ソフト導入・設定変更・認証情報処理）は
  対象/件数/容量/外部送信先/使用モデル/必要権限/不可逆性/バックアップ/ロールバック/予定コマンドを
  提示し、**明示的な承認**を得てから実行。承認なしに自動実行しない。

## S6. 監査とキャンセル（§24/§21）

- 誰が/いつ/どのノードが/なぜ選ばれ/何を実行し/どのモデルで/外部送信有無/どのファイル/結果/失敗/
  再試行/承認/キャンセル/成果物 checksum を記録。**秘密値・機密文書原文・API キーはログに残さない**。
- cancel・timeout・rollback を常に用意。Control 再起動後に状態復元。

## S7. デプロイ安全（§28/§32）

- Worker 常駐はユーザー単位 LaunchAgent。登録は plutil 検証 → 手動実行 → **明示承認**後。
- 新規展開は 1台 canary → 検証 → 少数 → 全体。10 台へ一度に変更しない。
