# 注意 と 作業記憶

## 注意制御（`attention`）

- **生物学的知見**: 前頭頭頂の注意ネットワークと顕著性ネットワークが、目標関連情報を増強し無関係な刺激を抑制する（と考えられる）。
- **計算論的抽象化**: 注意を単一値にせず 7 次元へ分解する（`ATTENTION_DIMENSIONS`）: `goal_relevance / novelty /
  urgency / risk / uncertainty / emotional_salience / expected_information_gain`。
- **実装上の近似**: 各次元は決定的スコア。総合注意は `_WEIGHTS`（`goal_relevance` を最重視: 0.34）による重み付き和。

### 目標関連性を主軸にする（強い刺激だからではなく）

- `goal_relevance` は刺激トークンと目標トークンの Jaccard 重なり（`_overlap`）。CJK は文字バイグラムでも近似。
- **抑制**: `goal_relevance < 0.2` かつ `max(novelty, urgency, emotional_salience) > 0.6` かつ `risk < 0.8` の
  「目立つが無関係」入力は総合注意を ×0.4 し `suppressed=True`（admit されない）。
- **危険は落とさない**: `risk ≥ 0.8` の入力は関連性が低くても `admit=True`（安全のため注意を残す）。
- 期待情報利得: `goal_relevance × (0.5+0.5·novelty) × (0.5+0.5·uncertainty)`。

### 注意資源の上限（過剰切替の防止）

- `attention.rank(stimuli, goal, context, capacity)` は候補を注意でランク付けし、上位 `capacity` 件のみ
  `admitted=True` にする。高危険は関連性が低くても順位を落とさない tie-break を持つ。

## 作業記憶（`working_memory`）

- **生物学的知見**: 作業記憶は容量が限られ、リハーサルで維持され、維持されない項目は減衰・脱落する（と考えられる）。
- **計算論的抽象化**: 少量の項目のみ保持し、容量は固定でなく認知負荷・項目複雑さで変わる。活性は時間で減衰し、
  リハーサルで回復。目標と無関係になった項目は削除する。
- **実装上の近似**:
  - `capacity(cognitive_load, avg_complexity)`: `7 − 3·load − 2·complexity` を `[MIN_SLOTS=3, MAX_SLOTS=9]` にクランプ（**固定値にしない**）。
  - `current_activation`: `activation0 · exp(−age/TAU_SECONDS)`（`TAU_SECONDS=600`）。`ACTIVATION_FLOOR=0.15` 未満は脱落。
  - `load`: 容量超過時に最小活性の項目を eviction。同一 content_ref はリハーサル扱い。
  - `rehearse`: 活性と期限を回復（維持）。`decay`: 期限切れ・低活性を脱落。
  - `evict_irrelevant(current_goal_id)`: 現在の目標と無関係な項目を削除。
  - `chunk`: 既定は `goal_id` でチャンク化。
- **全記憶を作業記憶に載せない**。WM はセッション一時状態で、snapshot には永続しない（`snapshot.rebuild` の
  `working_memory: []`）。CLI では `<scope>/working_memory.json` に分離保存する。
