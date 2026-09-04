# 神経科学 → ソフトウェア 対応表（比喩とアルゴリズムの境界）

本表の目的は、**どこまでが比喩で、どこからが実際のアルゴリズムか** を明示すること。
脳領域とソフトウェア機能を **1 対 1 対応させない**。列「生物学的知見」は仮説を含む要約であり、
列「実装の実体」がコードが実際に行う決定的処理である。行間の対応は *着想元* であって *等価* ではない。

| 着想元（神経科学） | 生物学的知見（仮説を含む・要約） | 計算論的抽象化 | 実装の実体（module.関数 / enum） | 比喩の限界 |
|---|---|---|---|---|
| 視床・感覚皮質・顕著性ネットワーク | 感覚入力の選別・ゲーティング | 信頼度判定・重複排除・機密除去・優先度仮設定 | `event_store.append_event`（`scan_payload`/`redact_payload`/content-addressed dedup） | ゲーティングの生理は再現しない。単なる決定的フィルタ |
| 前頭頭頂・顕著性ネットワーク | 目標関連情報の増強と無関係刺激の抑制 | 7 次元の注意プロファイル・目標関連性最重視 | `attention.score`（`ATTENTION_DIMENSIONS`, `_WEIGHTS`, `suppressed`） | 「注意」は重み付き和の近似。神経競合ではない |
| 前頭前野の作業記憶 | 容量制限・リハーサル維持・減衰脱落 | 動的容量＋活性指数減衰＋eviction | `working_memory.capacity/current_activation/rehearse/decay` | チャンクの意味的圧縮は goal_id グルーピングの近似 |
| 海馬 | エピソードの符号化・パターン分離・補完 | 文脈キーで別物を保ち、部分手掛かりで想起 | `episodic_memory.separation_key`（outcome除外・scope/partition含む）／`retrieval.retrieve` | 海馬を「長期倉庫」と扱わない。分離は決定的ハッシュ |
| 新皮質 | 複数経験からのスキーマ抽出・安定保持 | 意味記憶は promotion 経由でのみ生成・矛盾を同時保持 | `semantic_memory.apply_promotion`/`detect_conflicts` | 皮質の可塑性は模さない。昇格は人間ゲート |
| 線条体・皮質（手続） | 反復成功の自動化 | 適用範囲照合を経てのみ自動適用 | `procedural_memory.applicability`（`REQUIRED_PROCEDURE_FIELDS`） | 自動化＝安全条件つきの適用可否判定 |
| 基底核 | 候補行動の選択・探索/利用の調停 | 多基準の説明可能な効用・高リスクで探索抑制 | `policy_selection.select`（`POLICY_CRITERIA`, `contributions`） | 報酬値だけで決めない。勝者総取りは近似 |
| 中脳ドーパミン系（位相性活動） | **報酬そのものではなく報酬予測誤差に相関**するとの説 | 学習信号 = 観測 − 期待。想定外を強く更新 | `prediction.evaluate`（`prediction_error`, `NEG_SURPRISE_GAIN`） | 「ドーパミン」を報酬として扱わない。学習率調整の比喩に限定 |
| 扁桃体・顕著性 | 危険/損失刺激への優先的注意（恐怖専用ではない） | 顕著性と危険度を別軸で評価・承認ゲートへ | `safety.assess`（`HIGH_SALIENCE_OPERATIONS`） | 扁桃体を「恐怖装置」に還元しない。自動拒否しない |
| 抑制性回路（皮質/基底核/海馬） | 競合解消・誤反応の抑制 | 強化と対に抑制を実装 | `inhibition`（`INHIBITORY_RELATIONS`, `must_not_promote`, `resolve_competition`） | 抑制＝昇格/自動適用の遮断。神経抑制の生理は模さない |
| 恒常性可塑性 | 発火率の恒常性維持 | ハブの過強を派生側で正規化 | `learning.homeostatic_scale`（derived のみ・raw 不可侵） | raw を書き換えない点が生物と異なる設計選択 |
| 記憶固定化・睡眠中のリプレイ | オフライン統合・スキーマ化（定期バッチではない） | 候補生成のみ・本番自動変更なし | `consolidation.consolidate`（`dry_run`, `_hypothesize_semantics`） | 睡眠 = 定期バッチと同一視しない。SessionEnd で重い統合をしない |
| 前頭前野のメタ認知 | 既知感・確信度モニタ | 知識状態分類・較正誤差 | `metacognition.classify_memory`（`KNOWLEDGE_STATES`, `calibration_error`） | 「知っている感覚」は status/confidence の決定的分類の近似 |
| シナプス可塑性（LTP/LTD/STDP） | 共起・順序依存の重み変化 | 共起は弱い証拠。順序・base-rate 補正 | **skill-synapse-jp へ委譲**（`synapse_bridge`） | 共起回数だけを強度としない。関係グラフは別モジュール |

## 3 層の区別（本スキル全体の約束）

各モジュールの docstring は次の 3 層を分けて記述している:

1. **生物学的知見** — 何が観察/仮説されているか（断定を避け「〜と考えられている」で記す）。
2. **計算論的抽象化** — その原理を計算問題としてどう定式化するか。
3. **実装上の近似** — コードが実際に行う決定的処理（関数名・式）。読者はここだけを挙動の真実とみなしてよい。

比喩（1・2）とアルゴリズム（3）を取り違えないこと。限界の詳細は `limitations.md`。
