# 記憶システム（エピソード / 意味 / 手続）

## 記憶種別と状態

- 種別（`schemas.MEMORY_TYPES`）: `sensory / working / episodic / semantic / procedural / prospective /
  emotional_salience / inhibitory / meta_memory`。
- ライフサイクル状態（`STATUS`）: `observed → candidate → verified → active`（＋ `conflicted / deprecated /
  archived / rejected / purged`）。
- 昇格レベル（`LEVELS` L0..L5）は状態と別軸で保持し、`LEVEL_TO_STATUS` で粗く対応づける。
- 各記憶の必須項目（`MEMORY_SCHEMA`）: id・種類・範囲(scope)・状態・信頼度・出典(provenance)・作成日時、
  加えて証拠・成功/失敗回数・反証・有効期限・機密性・削除方針・derived。

## エピソード記憶（`episodic_memory`）

- **生物学的知見**: 海馬は個別の出来事を時刻・状況とともに符号化し、似た経験を別物として保つ（パターン分離）。
- **計算論的抽象化**: エピソードを **(scope, partition, goal, situation, action)** の分離キーで同定し、結果は
  success/failure として集計する。outcome をキーに含めないので、同一文脈の反復は同じエピソードへ集計され
  base-rate を数えられる。文言が少しでも違えば別キー = 別エピソードとなり混同しない。
- **実装上の近似**: `separation_key`（決定的 sha1）→ `episode_id`。`apply_observation` は evidence_ids・
  success/failure・created/last_used を **順序非依存・冪等** に更新する。
- 単一の成功事例を一般則へ **自動昇格させない**。意味記憶化は consolidate → promote 経由のみ。

## 意味記憶（`semantic_memory`）

- **生物学的知見**: 新皮質は複数エピソードから統計的規則性を抽出し、安定概念として長期保持する（と考えられる）。
- **計算論的抽象化**: 意味記憶 = 「主張(claim) + 適用範囲 + 信頼度 + 出典 + 有効期限」。矛盾する主張を
  同時に保持でき、時間変化する知識(review_after)と安定知識を区別する。
- **実装上の近似**: observation から自動生成されない。`apply_promotion`（承認済み変更 = promotion イベント）
  経由でのみ replay 時に構築される。`detect_conflicts` は同一主題で肯定/否定が併存する active 記憶を
  conflicted 候補として返す（自動改変はしない）。

## 手続記憶（`procedural_memory`）

- **生物学的知見**: 反復して成功する行動系列は自動化され、宣言的想起を要さず実行できるようになる（と考えられる）。
- **計算論的抽象化**: 手続 = 開始条件・前提・手順・期待結果・検証法・失敗時処理・ロールバック・適用禁止条件・
  必要承認（`REQUIRED_PROCEDURE_FIELDS`）。適用前に必ず適用範囲を照合する。
- **実装上の近似**: `applicability(procedure, context)` が適用禁止条件・前提・スコープ・危険度（`safety`）を
  照合し `{applicable, needs_approval, reasons}` を返す。`active`(L4) でない手続は自動適用しない。
  高顕著性操作を含む手続は `needs_approval=True`（危険だから拒否ではなく承認へ）。

## 派生と正本の関係

エピソード/意味/手続はすべて **snapshot（派生物）** の要素であり、正本の event log（observation /
promotion / retraction / feedback / inhibition イベント）から `snapshot.rebuild` で決定的に再構築される。
snapshot を直接編集する設計にはしていない。
