# 学習・自己改変 提案テンプレート

`brain propose` で生成される候補（`proposals.make_proposal`）を人が記述・審査するための様式。
このテンプレートは §9 の自己改変 13 手順と `checklist` キーに対応する。**候補は自動では本番に入らない。**

---

- **proposal_id**: `prop_________`
- **type**: `semantic | procedure | edge | deprecation | skill_change`
- **target_level**: `L1 | L2 | L3 | L4 | L5`（該当時）
- **scope / partition**: `________`

## 1. 改変理由（rationale）
> なぜこの変更が必要か。どの目標・課題に資するか。

## 2. 根拠イベント（evidence_ids）
> `evt_...` を列挙。独立した証拠か、単一セッションの反復でないかを明記。

## 3. 変更前後 diff
```diff
- （変更前）
+ （変更後）
```

## 4. 期待効果（expected_effect）
## 5. 副作用（side_effects）
> 過度な一般化・スコープ漏洩・退行の可能性。適用範囲の限定。

## 6. 反例（counterexamples）
> 失敗条件・当てはまらない状況。

## チェックリスト（すべて満たすまで `applied` にできない）

| 手順 | 状態 | 備考 |
|---|---|---|
| 7. 回帰テスト（regression_test） | ☐ | |
| 8. セキュリティテスト（security_test） | ☐ | |
| 9. sandbox 実行（sandbox_run） | ☐ | |
| 10. 人間の承認（human_approval） | ☐ | 承認者: |
| 11. canary 適用（canary） | ☐ | |
| 12. ロールバック作成（rollback_prepared） | ☐ | backup パス: |
| 13. ロールバック確認 | ☐ | `brain rollback --backup ... --to ... --dry-run` |

> **保護対象**（SKILL.md/憲法/安全規則/権限/hooks/MCP/学習率上限/昇格条件/外部送信/削除/秘密処理）への
> 変更は、通常実行中の自動適用が禁止（`executive.guard_self_modification`）。必ず人間ゲートを通す。
