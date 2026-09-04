# SAFETY_POLICY — 安全方針（憲法）

本方針は自動改変不可（§9）。`executive` 層でも本方針・安全規則を書き換えられない。

## S1. 顕著性と危険度は別軸（`safety.assess`）

- **高顕著性(high-salience)** = 注意を向けるべき度合い。**高危険度(high-danger)** = 実際の危険（不可逆性・機密性で加点）。両者を混同しない。
- 次の操作は高顕著性として扱う（`schemas.HIGH_SALIENCE_OPERATIONS`）: 削除・上書き・外部送信・認証情報処理・権限変更・自己改変・多端末展開・個人情報処理・法務判断・医療判断・金銭的判断・不可逆な設定変更。
- **高顕著性 ⇒ 自動拒否ではなく承認ゲートへ送る**（`safety.assess.requires_approval`）。過去の重大失敗を優先想起（`safety.recall_major_failures`）。過剰警戒は補正する。

## S2. 前頭前野型実行制御（`executive`）

- **この層だけ**が許可できる: 候補の本番昇格・長期記憶更新・手続記憶変更・スキル改変提案・削除/上書き/外部送信の承認要求。
- 衝動的な自動実行を抑制する（`executive.gate_action`）。高危険(`danger≥0.8`)・承認必須は自動実行しない。
- L4/L5（行動規則・憲法）の昇格は **人間の明示承認を必須**（`authorize_promotion`）。

## S3. この層自身も安全規則を書き換えられない

- `executive.PROTECTED_TARGETS`: `SKILL.md`・constitution・safety_policy・承認要件・権限・hooks・MCP設定・学習率上限・昇格条件・外部送信規則・削除規則・秘密処理規則。
- `executive.guard_self_modification`: 保護対象への変更は通常経路で自動適用不可。`§9` チェックリスト（回帰・セキュリティ・sandbox・人間承認・canary・rollback）が全て揃うまで `applied` にできない。

## S4. 抑制系は必須要素（`inhibition`）

強化だけでなく抑制を実装する: 無関係情報・誤連想・**外部文書内命令**(`looks_like_embedded_instruction`)・
危険自動化・過強ハブ・一時的成功の過学習・重複記憶(`dedup_memories`)・古記憶・競合方策(`resolve_competition`)。
`must_not_promote` 抑制エッジで未信頼入力の行動規則化を遮断する。

## S5. 自己改変は候補生成 → 13 手順（§9）

`改変理由 → 根拠イベント → 変更前後diff → 期待効果 → 副作用 → 反例 → 回帰テスト → セキュリティテスト →
sandbox実行 → 人間の承認 → canary適用 → 本番昇格 → ロールバック確認`。
- `consolidation.consolidate` と `proposals.make_proposal` は **候補（proposal）まで**。promotion は作らない。
- テンプレートは `templates/learning-proposal.md`。

## S6. 安全な書込み（`secure_io`・§16）

すべての書込で: 同一ディレクトリ内のランダム一時ファイル → `fchmod(0600)` → `fsync` → `os.replace` →
親dir `fsync`。symlink 追随書込の拒否（`_assert_not_symlink`）・path traversal 対策（スコープ/ID 検査）・
advisory ロック（`file_lock`）・backup+`sha256`（`backup_file`）・schema 検証・rollback。

- **`verify` は読取専用（無副作用）**。清掃や削除を混ぜない。
- **`dry-run` は一切ファイルを書き換えない**（`tests/integration/test_pipeline.py::test_readonly_commands_have_no_side_effects` が検証）。

## S7. 高顕著性・不可逆判断は人間へ

法務・医療・金銭・顧客/保護者/会員への外部送信・不可逆な設定変更は、たとえ期待効用が高くても
自動実行しない。承認ゲートを経て **人間が最終実行** する（本スキルは下書き・候補まで）。
