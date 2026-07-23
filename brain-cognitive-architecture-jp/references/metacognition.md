# メタ認知

## 立場（3 層の区別）

- **生物学的知見**: 前頭前野などが「自分が知っているか」の感覚（確信度・既知感）をモニタし、想起の成否や
  不確実性を評価する（と考えられる）。
- **計算論的抽象化**: 知っている/知らない・推論/事実・予測/実測を区別し、自己評価の信頼性を低く扱い、
  必要なら追加調査を選ぶ。
- **実装上の近似**: `metacognition` の決定的分類と較正計算。「知っている感覚」は status/confidence/出典/有効期限
  からの分類の近似であって、内観の再現ではない。

## 7 つの知識状態（`KNOWLEDGE_STATES`）

`known_verified / known_unverified / inferred / conflicted / unknown / not_retrieved / outdated`。

### 「見つからない」と「存在しない」を区別する

`retrieval.retrieve` が返す `knowledge_state`:
- 当該スコープに記憶が **存在しない** → `unknown`。
- 記憶はあるが手掛かりに **合致しない**（閾値未満で誤補完を抑制）→ `not_retrieved`。

この区別は本アーキテクチャの中核的な誠実さであり、`tests/unit/test_memory.py::test_false_completion_suppressed`
と `tests/unit/test_inhibition_metacog.py::test_unknown_vs_not_retrieved` が検証する。

### 記憶単位の分類（`classify_memory`）

- `deprecated/archived/rejected/purged` → `outdated`。
- `derived.in_conflict` → `conflicted`（矛盾の同時保持を明示）。
- `review_after < as_of` → `outdated`（時間変化する知識）。
- 未検証 × `model_generated`/`user_inferred` → `inferred`（**推論と事実を区別**）。
- 検証済み × `confidence ≥ 0.7` → `known_verified`。それ以外 → `known_unverified`。

## 自己評価の信頼性を低く扱う・追加調査の判断

- `should_investigate(knowledge_state, confidence, risk)`: `unknown/not_retrieved/conflicted/outdated`、
  または高リスク(≥0.6)×低確信(<0.7) なら `True`。
- 自己申告は較正の証拠として弱く扱う（`epistemic_report` の注記、`prediction` の `self_reported` 割引）。

## 較正誤差（`calibration_error`）

`records: [{confidence, correct}]` に対し **Brier スコア**（`mean((confidence − outcome)^2)`）と
`reliability_gap = |mean(confidence) − accuracy|` を返す。§19 の評価指標 `calibration_error` に対応する。
確信度が実際の正答率とどれだけずれているかを監査できる。
