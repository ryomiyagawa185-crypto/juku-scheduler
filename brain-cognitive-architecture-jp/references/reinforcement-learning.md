# 強化学習 と 昇格フロー

## 方策選択（`policy_selection`）

- **生物学的知見**: 基底核は複数候補から一つを選び、探索/利用のバランスや習慣的行動と目標指向行動の調停に関わる（と考えられる）。
- **計算論的抽象化**: 期待価値だけでなくリスク・不可逆性・コスト・不確実性・ユーザ選好・方針適合を同時比較する。
- **実装上の近似**: 説明可能な重み付き効用（`_WEIGHTS`）。負の寄与（`risk/cost/latency/uncertainty`）を明示。

### 評価軸（`POLICY_CRITERIA`）

`goal_alignment / expected_utility / success_probability / reversibility / evidence_quality / user_preference /
information_gain / policy_compliance`（正）と `risk / cost / latency / uncertainty`（負）。

- `risk` は `safety.assess.danger` を既定にする（明示指定と大きい方）。
- `select` は各候補の `contributions`（軸別寄与）と `explanation`（主要因・次点）を返す（**説明可能性**）。
- **探索/利用**: 高リスク環境（`max_danger ≥ 0.8` または `risk_domain ≥ 0.8`）では探索ボーナスを無効化（**高リスクでは探索を抑える**）。
- **高リスクは自動実行しない**: 選定候補が `danger ≥ 0.8` または `requires_approval` なら `auto_execute=False`（効用最大でも承認へ）。
- 習慣的方策 vs 目標指向: `active`(L4) の手続は習慣的に適用可能だが、高リスク・高不確実では常に多候補比較を経る。

## 昇格フロー L0→L5（`learning.promotion_gate` / `executive.authorize_promotion`）

新情報を即座に長期記憶へ入れない。段階的昇格のみ（`LEVEL_ORDER` の +1 のみ許可）。

| 段階 | 意味 | 昇格条件（コード） |
|---|---|---|
| L0 observation | 観測 | — |
| L0→L1 | candidate | `event_valid` ∧ `source_recorded` ∧ `sensitive_removed` |
| L1→L2 | corroborated | `independent_evidence_count ≥ 2` ∨ `user_confirmed` ∨ `decisive_test` |
| L2→L3 | verified | `independent_verification` ∧ `counterevidence_checked` ∧ `scope_fixed` ∧ `confidence_threshold_met` |
| L3→L4 | reusable procedure | `reproduced_conditions ≥ 2` ∧ `failure_conditions_known` ∧ `rollback_available` ∧ `regression_passed`；未信頼/モデル生成源は不可 |
| L4→L5 | constitutional rule | `human_approval` ∧ `security_reviewed` ∧ `diff_present` ∧ `versioned` ∧ `regression_passed` ∧ `rollback_available`；未信頼/モデル生成源は不可 |

- **単発の成功で昇格しない**: `inhibition.promotion_blocked` がサンプル数 < 2 を過学習の恐れとして遮断。
- **未信頼・モデル生成源は行動規則（L4/L5）へ昇格不可**（`schemas.TRUST_PROMOTABLE_TO_RULE`／`must_not_promote`）。
- **L4/L5 は人間の明示承認を必須**（`executive.authorize_promotion(human_approval=True)`）。
- 昇格は event log に `promotion` イベントとして記録され、replay で反映される（承認済み変更）。

## 報酬値だけで決めない

`expected_utility` は評価軸の一つにすぎず、`risk`・`reversibility`・`policy_compliance` 等と併せて総合する。
高リスク操作は期待効用が高くても自動実行せず承認ゲートへ回す。
