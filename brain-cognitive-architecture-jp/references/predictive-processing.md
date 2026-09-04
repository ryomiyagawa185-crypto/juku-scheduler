# 予測処理 と 予測誤差

## 立場（3 層の区別）

- **生物学的知見**: 脳は絶えず次の入力・結果を予測し、予測と実測の差（予測誤差）で学習するとされる。
  中脳ドーパミン系の位相性活動は **「報酬そのもの」ではなく報酬予測誤差** に相関するという説が有力。
- **計算論的抽象化**: 学習信号 = 観測 − 期待。想定内の成功は小さく、想定外の失敗は強く記録する。
- **実装上の近似**: `prediction.evaluate` の決定的計算。「ドーパミン」の語は **報酬ではなく予測誤差・学習率調整の
  計算論的比喩** に限定し、コードにも `reward` という概念は置かない。

## 予測誤差の計算（`prediction`）

```
prediction_error = observed_value(outcome) − expected        # 符号付き
surprise         = |prediction_error|
```

- `observed_value` は結果区分を `OUTCOME_QUALITY`（0..1）で写像。外部検証済み(`VERIFIED_OUTCOMES`)を優先的に信頼。
- `expected` は成功見込み確率など 0..1。

## 更新量の調整（想定内成功を過大強化しない）

`update_weight = BASE_UPDATE(0.3) × surprise × gain × rel × scope_match × (1−0.5·unc) × (1−1/(1+n)) × …`

- `gain = NEG_SURPRISE_GAIN(1.5)` if `prediction_error < 0` else `1.0` — **想定外の失敗を強める非対称ゲイン**。
- `surprise ≈ 0`（想定どおり）の成功は `update_weight` が小さくなる（過大強化しない）。
- `rel = evidence_reliability`、`scope_match`（不一致で ×0.3）、`unc = uncertainty`（高いほど更新幅を縮小）、
  `n = sample_size`（少ないほど控えめ）。
- `self_reported and not verified` は ×0.4（**自己申告のみは外部検証より弱く**）。
- `contradictory_evidence` があれば ×`1/(1+0.5·k)`。

## 顕著性への接続

`salience = surprise × gain`（想定外ほど注意・記録の顕著性が高い）。この値は `notes` とともに返され、
「想定外の失敗は強く記録し失敗条件を明示化する」「想定どおりは小さく更新」などの説明可能な指示になる。

## 例

| expected | outcome | prediction_error | 相対的 update | 解釈 |
|---|---|---|---|---|
| 0.95 | verified_success | ≈ +0.05 | 小 | 想定内。過大強化しない |
| 0.90 | verified_failure | ≈ −0.90 | 大（×1.5） | 想定外の失敗。強く記録 |
| 0.50 | unverified_completion（自己申告） | 0 | 割引（×0.4） | 外部検証がないので弱く |
