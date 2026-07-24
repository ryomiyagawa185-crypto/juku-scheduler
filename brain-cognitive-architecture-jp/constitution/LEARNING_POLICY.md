# LEARNING_POLICY — 学習方針（憲法）

学習の全アルゴリズムは決定的 Python（`learning.py`・`prediction.py`）にあり、モデルは読むだけ。
本方針は「何を根拠に、どれだけ、どの段階まで更新してよいか」を定める。

## L1. Hebbian は弱い証拠にすぎない

「同時に発火したものは結合する」を単純式にしない。共起は **関係候補を示す弱い証拠** として扱い、
強化には次を総合する: 共起・呼出し順序・時間差・入出力の受け渡し・成功結果・独立検証・ユーザー確認・
基準頻度・スコープ一致・反証・不確実性・サンプル数。

- 関係グラフ本体（共起・NPMI・位相・STDP 的順序・剪定）は **skill-synapse-jp** に委譲する（`synapse_bridge`）。
- 本体が独立に持つのは、安全 critical な抑制性エッジ（`inhibits`/`conflicts_with`/`contradicts`/`must_not_promote`）のみ。

## L2. 予測誤差学習（想定内成功を過大強化しない）

- `prediction.evaluate`: `prediction_error = observed − expected`。想定どおりの成功は `update_weight` を小さく、
  **想定外の失敗は `NEG_SURPRISE_GAIN`(=1.5) で強く記録**する。
- 更新量は `evidence_reliability`・`scope_match`・`sample_size`・`uncertainty`・`contradictory_evidence`・`self_reported` で調整。
- **外部検証(`VERIFIED_OUTCOMES`)を自己申告より優先**。自己申告のみは `update_weight` を割り引く。
- 「ドーパミン」の語を使う場合は **報酬そのものではなく予測誤差・学習率調整の計算論的比喩** に限定する。

## L3. ベイズ的更新（固定加点にしない）

- `learning.derive_confidence`: 信頼区分 `source_trust` を事前とする Beta 事後平均。
  `a0 = 1 + 2·trust_w`, `b0 = 1 + 2·(1−trust_w)`, `mean = (a0+s)/(a0+b0+s+f)`。反証で減衰。
- **未検証 × 未信頼源（`untrusted_external`/`model_generated`/`user_inferred`）は confidence を 0.5 で上限**。
- `learning.bayesian_update`: 事前信念に対し `lr = reliability · scope_match · (1−e^(−n/3))` で更新。

## L4. メタ可塑性・恒常性

- `learning.learning_rate`: **高リスク領域ほど学習率を下げる**（`domain_risk≥0.8` で ×0.3）。不安定・高失敗率でも下げる。
- `learning.homeostatic_scale`: 一部ノードが全てと強く結ぶのを防ぐ。**派生 `weight` のみ縮小し raw は不可侵**。

## L5. 忘却は削除だけではない

`learning.forgetting_action` / `retrievability`:
- 種別: 想起しにくくする / 信頼度を下げる / 検索対象から外す / 廃止(deprecate) / アーカイブ / 完全削除。
- 固定化された記憶（`verified`/`active`）は半減期が長い。**重要な失敗・安全規則・明示ユーザー方針・憲法(L5)は
  `is_protected` により単純な時間減衰で消さない**。

## L6. 昇格フロー L0→L5（`learning.promotion_gate`）

即座に長期記憶へ入れない。段階的昇格のみ許可（飛び級不可）。

| 遷移 | 条件（要約） |
|---|---|
| L0→L1 | イベント形式が妥当・出典記録・機密除去 |
| L1→L2 | 複数独立証拠 or 明示ユーザー確認 or 決定的テスト成功 |
| L2→L3 | 独立検証・反証確認・適用範囲確定・信頼度閾値通過 |
| L3→L4 | 複数条件下で再現・失敗条件既知・ロールバック可・回帰試験成功／**未信頼・モデル生成源は昇格不可** |
| L4→L5 | 人間の明示承認・セキュリティ審査・変更差分・バージョン管理・回帰試験・ロールバック作成／**未信頼・モデル生成源は昇格不可** |

- **単発の成功で昇格しない**（`inhibition.promotion_blocked` がサンプル数<2 を過学習の恐れとして遮断）。
- **自己評価だけで強化しない**（外部検証を優先）。
- **L5（憲法規則）は通常実行中に自動作成/変更しない**（`executive` ＋人間承認）。

## L7. 汚染に対する昇格制限（詳細は SAFETY/PRIVACY）

`untrusted_external` / `model_generated` は事実候補にはできるが **行動規則（L4/L5）へ昇格させない**
（`schemas.TRUST_PROMOTABLE_TO_RULE` と `inhibition.promotion_blocked`／`must_not_promote`）。
