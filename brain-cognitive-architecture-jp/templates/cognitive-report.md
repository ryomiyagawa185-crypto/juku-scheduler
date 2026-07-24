# 認知レポート テンプレート（説明可能性・§13）

重要判断ごとに、検証可能な決定記録を残すための様式。内部の完全な推論過程は保存せず、
**追跡可能な要素** を記録する。`brain report` / `brain verify` の出力を該当欄に貼る。

---

- **日時 / scope / partition**: ________
- **目標（goal）**: ________

## 1. 使った入力
> どの観測イベント（`evt_...`）・刺激を用いたか。source_trust を明記。

## 2. 想起した記憶 / 抑制した記憶
> `brain retrieve` の `results`（想起）と `suppressed`（誤補完・低想起で抑制）。

## 3. 注意プロファイル
> `brain attention` の 7 次元と `admit/suppressed`。

## 4. 比較した方策
> `brain choose` の `ranking` と各候補の `contributions`（軸別寄与）・`explanation`。

## 5. 予測 → 実結果 → 予測誤差
> `brain predict` の `expected` / `observed` / `prediction_error` / `update_weight` / `salience`。

## 6. 学習候補 / 昇格しなかったもの
> `brain consolidate --dry-run` の候補。昇格を見送った理由（`promotion_gate` の reasons）。

## 7. 判断根拠（なぜその判断をしたか）
> 主要因を 1–3 点。高危険なら承認要求に回した旨。

## 8. 知識状態と不確実性（メタ認知）
> `brain report` の epistemic 分布。knowledge_state（known_verified / … / unknown / not_retrieved / outdated）と
> confidence。追加調査の要否（`should_investigate`）。

## 9. 整合性
> `brain verify`: `ok` / `deterministic` / `n_problems`。
