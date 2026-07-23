# オフライン統合（固定化）と 忘却

## オフライン統合（`consolidation`）

- **生物学的知見**: 睡眠中に海馬のエピソードが再生され、新皮質へ転送・統合されてスキーマ化されるとする説がある。
  **睡眠は単なる定期バッチ処理ではない**。
- **計算論的抽象化**: 重複整理・関連エピソードのクラスタリング・仮説的意味記憶の生成・矛盾検出・信頼度再計算・
  古記憶の減衰・固定化候補生成・過学習検出・回帰確認。
- **実装上の近似**: `consolidate(paths, scope, as_of, dry_run)`。**本番知識を自動変更せず、候補（proposal）生成まで**。

### consolidate が行うこと

| 処理 | 実装 | 出力 |
|---|---|---|
| 関連エピソードのクラスタリング | `_episode_clusters`（正規化 goal + scope + partition） | クラスタ |
| 仮説的意味記憶の生成 | `_hypothesize_semantics`（`CORROBORATION_MIN=2` 以上・失敗過多でない） | semantic 候補(L1) |
| 古記憶の減衰候補 | `_decay_candidates`（低 retrievability・非保護のみ） | deprecation 候補 |
| 重複検出 | `inhibition.dedup_memories` | 重複ペア |
| 矛盾検出 | `semantic_memory.detect_conflicts` | conflicts |
| 過学習・過強ハブ検出 | `_overfitting_anomalies`（高段階×少サンプル、入射強度和>3） | anomalies（報告のみ） |

### 安全則

- **`dry_run=True`（既定）は一切ファイルを書かない**。`--apply` 時のみ proposals へ候補を書き込む（promotion は作らない）。
- **SessionEnd 等の短い終了処理で重い統合を実行しない**。明示コマンドまたは安全な定期実行として分離する。
- 本番昇格は `executive` の認可 ＋ 人間承認が必要（`LEARNING_POLICY.md` L6）。

## 忘却（`learning`）

- **生物学的知見**: 使われない記憶は想起されにくくなる（LTD・干渉）。固定化された記憶は減衰が遅い。
- **計算論的抽象化**: 忘却は削除だけではない。想起抑制 / 信頼度低下 / 検索除外 / 廃止 / アーカイブ / 完全削除を分ける。
- **実装上の近似**:
  - `retrievability(mem, as_of) = exp(−age/tau)`。`tau = 90`（`verified/active`）or `14`（それ以外）日。
  - `forgetting_action`: `retrievability < 0.05` → `exclude_from_search`、`< 0.2` → `suppress_recall`、それ以外 `none`。
  - **保護記憶（`is_protected`）は減衰で消さない**: L5・`system_policy`/`user_explicit` 源・`inhibitory` 型・
    失敗/反証を持つ記憶（重大失敗）。`retrievability` に下限 0.5 を課す。
- 忘却は `snapshot.rebuild` で `as_of` 依存の **derived** として毎回計算する。raw（観測数・証拠 id）は消さない。
