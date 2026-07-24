# PRIVACY_POLICY — プライバシー方針（憲法）

自動改変不可（§9）。感覚・入力ゲート（`event_store`）が保存前に強制する。

## PR1. 保存しないもの

APIキー・パスワード・秘密鍵・Cookie・セッショントークン・`.env` 内容・個人番号・決済情報・
不要な医療/法務案件情報・顧客文書全文・メール本文全文・生徒/保護者の詳細個人情報・原文プロンプト全文。

- 検出パターン: `event_store._SENSITIVE_PATTERNS`（private key / AWS / OpenAI / Anthropic / GitHub / Slack /
  bearer / password=… / env 代入 / クレジットカード / マイナンバー / email / cookie）。
- `scan_payload` が payload を再帰走査し、`redact_payload` が `[REDACTED:<cat>]` へ置換してから追記する。
  検出時は `contains_sensitive_data=true` と `sensitive_categories` を記録するが **原文は残さない**。

## PR2. 代わりに保存するもの

必要な場合は次のみ: `content_hash`（sha256・重複検知用）／匿名化ID／構造化要約（`payload` の許可フィールド）／
適用範囲（scope・partition）／証拠参照（`evidence_ids`）／保持期限（`retention_until`）。

- セッション識別子は生値でなく `session_id_hash`（sha256）で保存（`event_store.session_hash`）。
- 原文プロンプト・顧客名・ファイル名は保存しない。イベントは「何が/どの状況/何を目的/何を実行/結果/
  成功判定根拠/失敗条件/確認者/適用範囲」の構造化要約に限る。

## PR3. データ保持と削除方針

- 各記憶は `retention_until` と `deletion_policy` を持つ（既定 `decay_then_archive` / `review_then_archive`）。
- 忘却は削除だけでなく想起抑制・検索除外・アーカイブを含む（`LEARNING_POLICY.md` L5）。
- **完全削除（purge）** は tombstone を残しつつ内容を破棄する（`semantic_memory.apply_retraction`: `content=None`,
  `claim=None`）。event log は正本のため、purge も「retraction イベントの追記」で表現し、過去を改竄しない。

## PR4. スコープ・パーティション隔離（顧客間漏洩の防止）

- 顧客/組織/ユーザ instance は `partition` で隔離する。`retrieval.scope_allowed` は
  `partition` 不一致の記憶を返さない。`event_store.make_event_id` と `episodic_memory.separation_key` が
  `partition` を含むため、別顧客の同内容イベント/エピソードが衝突・統合しない。
- Mac 固有設定を他 Mac へ、一回限りの希望を恒久嗜好へ、勝手に一般化しない（`SCOPE_BREADTH`）。

## PR5. 外部送信は常に人間

保護者・顧客・会員・裁判所・第三者への送信は本スキルが自動で行わない。高顕著性操作 `external_send` は
承認ゲートへ回し、人間が最終送信する。
