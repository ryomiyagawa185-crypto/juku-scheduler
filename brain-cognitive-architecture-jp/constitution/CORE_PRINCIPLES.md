# CORE_PRINCIPLES — 中核原則（憲法）

本ファイルは brain-cognitive-architecture-jp の不変原則を定める。通常タスク実行中に
自動変更してはならない（§9・自己改変禁止対象）。各原則には、コード上のどこで担保されるかを併記する。

## P1. 正本は append-only イベントログ

- **event log = 事実 / snapshot = 派生状態 / proposal = 仮説 / promotion = 承認済み変更**、を厳密に分離する。
- イベントは二度と書き換えない。過去の事実の追加は「時間の巻き戻し」ではなく、ログに事実を足して `replay` で反映する。
- 担保: `event_store.append_event`（追記のみ）／`snapshot.rebuild`（純関数の再構築）／`snapshot.py` は snapshot を直接編集しない。

## P2. 数値・状態遷移は決定的 Python だけが書く

- NPMI・信頼度・注意スコア・予測誤差・昇格判定などをモデル（LLM）が暗算しない。必ずエンジンを呼んで結果を読む。
- 再現性が台帳の命。同じイベント列と同じ `as_of` なら、挿入順・実時刻に依らず snapshot は必ず一致する。
- 担保: `snapshot.rebuild` は `generated_at` を含めず決定的。`event_store._sort_key` は content-addressed な `event_id` で tie-break。`cmd_verify` が 2 回の rebuild 一致を検査。

## P3. raw（観測事実）と derived（再計算値）を分離する

- 恒常性正規化・忘却・信頼度は **derived だけ** を変える。観測数や証拠 id（raw）を後から改竄しない。
- 担保: `learning.homeostatic_scale`（`derived.weight` のみ縮小、`raw.evidence_count` 不可侵）／`edge["raw"]` と `edge["derived"]` の分離。

## P4. 自律実行しない・自動発火無効

- 「日次統合」等は外部 cron／明示コマンドが叩いた時だけ成立する。観測が無ければ捏造せず「欠損」と記す。
- 担保: `SKILL.md` の `disable-model-invocation: true`。イベント記録という副作用を持つコマンドは人がタイミングを制御する。

## P5. 狭いスコープを優先し、パーティションを隔離する

- 一時的指示を恒久ルールにしない。プロジェクト固有知識を global へ自動昇格しない。顧客情報を別顧客へ伝播しない。Mac 固有設定を他 Mac へ一般化しない。
- 担保: `retrieval.scope_allowed`（`SCOPE_BREADTH` により「等しいか広い」記憶のみ下位へ generalize）＋パーティション一致必須。`event_store.make_event_id` と `episodic_memory.separation_key` が `partition` を含む。

## P6. 「進化」の限定的定義

- 進化とは、**経験を不変イベントとして記録し、信頼できる証拠で関連性や方策を更新し、誤りを抑制し、古い知識を減衰させ、検証(L0→L5)を通過した知識だけを長期記憶へ昇格させること** に限定する。
- スキルが無制限に自己改変することを進化と呼ばない。
- 担保: `learning.promotion_gate`（段階的昇格・各段条件）／`executive.authorize_promotion`（L4/L5 は人間承認必須）／`consolidation.consolidate`（候補生成のみ・本番自動変更なし）。

## P7. 科学的誠実さ

- 脳領域とソフトウェア機能を 1 対 1 対応させない。神経科学の語を装飾に使わない。
- 神経科学概念を用いるときは **(1) 生物学的知見 (2) 計算論的抽象化 (3) 実装上の近似** を区別する（各モジュール docstring・`references/`）。
- 「人間の脳を再現した」「意識を実装した」「感情を持つ」とは言わない。本スキルは *複数の認知機能を分離・統合した安全で監査可能な適応型認知アーキテクチャ* である。

## P8. 安全は最優先で、この憲法自身も自動改変不可

- `executive` 層だけが昇格・長期記憶更新・改変提案を許可できるが、**その層自身も安全規則・この憲法を書き換えられない**。
- 担保: `executive.PROTECTED_TARGETS` / `executive.guard_self_modification`。詳細は `SAFETY_POLICY.md`。
