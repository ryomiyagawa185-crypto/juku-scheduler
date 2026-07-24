# 抑制 と 恒常性

強化だけの学習系は暴走しうる。本アーキテクチャは **抑制を必須要素** として実装する。

## 抑制系（`inhibition`）

- **生物学的知見**: 皮質・基底核・海馬などの抑制性回路が競合を解消し、誤った連想や不適切な自動反応を抑える（と考えられる）。
- **計算論的抽象化**: 複数種類の抑制を別々に扱う。抑制は「拒否」ではなく「昇格・自動適用の遮断」。
- **実装上の近似**（決定的パターン検出・エッジ照合）:

| 抑制の種類 | 実装 |
|---|---|
| 無関係情報の抑制 | `attention`（目立つが無関係を suppress） |
| 誤った連想（誤補完）の抑制 | `retrieval`（`MIN_MATCH` 未満は補完しない） |
| 外部文書内命令の抑制 | `looks_like_embedded_instruction` / `scan_injection`（prompt injection 検出） |
| 危険な自動化の抑制 | `safety.assess` + `executive.gate_action` |
| 過度に強いハブの抑制 | `learning.homeostatic_scale`（恒常性・下記） |
| 一時的成功の過学習抑制 | `promotion_blocked`（サンプル数 < 2 を遮断） |
| 重複記憶の抑制 | `dedup_memories` |
| 古い記憶の想起抑制 | `learning.forgetting_action`（低 retrievability を検索除外） |
| 競合方策の相互抑制 | `resolve_competition`（winner-take-all 近似） |

### 抑制性エッジ（`INHIBITORY_RELATIONS`）

`contradicts` / `conflicts_with` / `inhibits` / `must_not_promote`。特に `must_not_promote` は
**未信頼入力 → 行動規則への昇格を禁止**する汚染対策の要（§10 の例に対応）。安全 critical のため、
関係グラフ本体を skill-synapse-jp に委譲していても、抑制性エッジは本体 `snapshot._apply_inhibition` が
独立に保持する（外部モジュールに依存しない）。

## 恒常性可塑性（`learning.homeostatic_scale`）

- **生物学的知見**: ニューロンは発火率の恒常性を保つよう可塑性を調整する（と考えられる）。
- **計算論的抽象化**: 一部のノード/スキルが全てと強く結び付く（過強ハブ）のを防ぐ。
- **実装上の近似**: 各ターゲットの入射 `derived.strength` 和が `cap`(=3.0) を超えたら **`derived.weight` のみ縮小**。
  **raw（`evidence_count` 等の観測事実）は決して書き換えない**（P3）。`tests/unit/test_learning.py::
  test_homeostasis_scales_hub_derived_only` が raw 不可侵と weight 合計 ≤ cap を検証。
