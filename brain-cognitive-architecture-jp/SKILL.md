---
name: brain-cognitive-architecture-jp
description: 複数の認知機能（感覚ゲート・注意・作業記憶・エピソード/意味/手続記憶・パターン分離/補完・予測誤差・強化/抑制・記憶固定/忘却・メタ認知）を、互いに分離された監査可能・再現可能・安全なソフトウェア機構として統合した適応型認知アーキテクチャ。正本を append-only イベントログとし、信頼できる証拠で関連性や方策を更新し、誤りを抑制し、古い知識を減衰させ、検証(L0→L5)を通過した知識だけを長期記憶へ昇格させる。observe/attention/working-memory/retrieve/predict/choose/feedback/consolidate/promote/verify/replay を明示的に依頼されたときに使用する（イベント記録という副作用を持つため自動発火は無効＝人が実行タイミングを制御する）。「人間の脳の再現」「意識」「感情を持つ」ではない。【委譲】関係学習・可塑性・忘却（共起グラフ/コネクトーム）は skill-synapse-jp へ；その読取専用検査は skill-synapse-inspect-jp へ；スキル生態系全体の進化・シナジー・融合は aeon-forge へ；採択後の SKILL.md 鍛造は skill-forge へ。本スキルはそれらの上位に立つ認知アーキテクチャ全体で、関係学習モジュールとして skill-synapse-jp を再利用する。
when_to_use: "@brain、認知アーキテクチャ、記憶を観測して/observe、注意配分、作業記憶、エピソード記憶、意味記憶、手続記憶、部分手掛かりで想起/retrieve、予測誤差、方策選択、記憶固定/consolidate、昇格/promote、忘却/decay、replay、認知レポート、記憶の検証/verify"
argument-hint: "[init|observe|attention|working-memory|retrieve|predict|choose|feedback|consolidate|decay|propose|promote|reject|rollback|report|verify|replay|migrate] [options]"
disable-model-invocation: true
user-invocable: true
compatibility: "Claude Code（ローカルFS書込可）。Python 3（標準ライブラリのみ・fcntl 依存＝POSIX）。macOS/Linux。jsonschema 不要。"
metadata:
  version: "1.0.0"
  engine_version: "1.0.0"
  schema_version: "1.0.0"
  author: 宮川涼
---

# brain-cognitive-architecture-jp — 監査可能な適応型認知アーキテクチャ

## 1. Mission

本スキルは **「人間の脳の再現」ではない**。脳科学で比較的支持されている *機能原理* を、**分離・監査・再現・ロールバック可能なソフトウェア機構**へ翻訳したもの。目的は、次の認知機能を互いに独立した層として実装し、統合された**安全な適応型認知アーキテクチャ**を成立させること：感覚ゲート／注意／作業記憶／エピソード・意味・手続記憶／パターン分離・補完／予測・予測誤差／強化・習慣化・目標指向／感情的顕著性／不確実性評価／メタ認知／認知的柔軟性／意思決定／オフライン統合／恒常性／異常検知／説明可能性。

「脳のように進化する」とは、次の意味に**限定**する：**経験を不変イベントとして記録し、信頼できる証拠で関連性や方策を更新し、誤りを抑制し、古い知識を減衰させ、検証を通過した知識だけを長期記憶へ昇格させること**。無制限の自己改変は進化ではない。

## 2. Scientific limitations（科学的立場）

- 脳領域とソフトウェア機能を **1対1対応させない**。「右脳/左脳」等の単純化を使わない。
- 「ニューロン」「シナプス」「ドーパミン」「扁桃体」を装飾に使わない。共起回数だけをシナプス強度とみなさない。記憶を単一保存領域として扱わない。感情を正負スコアに、ドーパミンを報酬に、扁桃体を恐怖装置に、海馬を長期倉庫に還元しない。睡眠を定期バッチと同一視しない。自己評価だけを学習の証拠にしない。
- 概念を使うときは必ず **(1) 生物学的知見 / (2) 計算論的抽象化 / (3) ソフトウェア実装上の近似** を区別する（各モジュール docstring と `references/` に明記）。
- **禁止表現**：「人間の脳を再現した」「意識を実装した」「感情を持つ」。本スキルは*意識・人格の再現ではなく、複数の認知機能を分離・統合した適応型認知アーキテクチャ*である。
- 全体像・比喩とアルゴリズムの境界・限界は **`references/neuroscience-to-software-map.md` と `references/limitations.md`** を参照。

## 3. Activation conditions

副作用（イベント記録・台帳更新）を持つため **自動発火は無効**（`disable-model-invocation: true`）。ユーザーが `@brain` や上記コマンドを明示したときにのみ起動する。読取専用の検査（`verify`/`report`/`retrieve`/`attention`/`predict`/`choose`/`decay`）はいつでも安全に実行できる。

## 4. Cognitive processing loop（標準実行ループ・§21）

`1 Sense → 2 Validate → 3 Filter → 4 Attend → 5 Load WM → 6 Retrieve(episodic/semantic) → 7 Predict → 8 Generate candidates → 9 Inhibit unsafe/irrelevant → 10 Select policy → 11 Execute or request approval → 12 Observe outcome → 13 Compute prediction error → 14 Store episode → 15 Learning candidate → 16 Consolidate(controlled) → 17 Report decision & uncertainty`

対応 CLI（詳細は `references/` と `--help`）：

```
brain observe   --event event.json        # A 感覚ゲート: 不変イベントとして記録（原文/秘密は保存しない）
brain attention --stimulus @s.json --goal @g.json   # B 注意（7次元・目標関連性を最重視）
brain working-memory --action load --ref mem_.. --goal-id ..  # C 作業記憶（容量制限・減衰）
brain retrieve  --cue '{"keywords":[..]}' # D/E 部分手掛かり検索・誤補完抑制・スコープ隔離
brain predict   --expected 0.8 --outcome verified_failure     # H 予測誤差（想定外の失敗を強く記録）
brain choose    --candidates @c.json      # G 方策選択（多基準・説明可能・高危険は自動実行しない）
brain feedback  --memory mem_.. --outcome verified_success    # 結果観測→予測誤差
brain consolidate --dry-run               # M オフライン統合（候補のみ・本番を自動変更しない）
brain promote   --memory mem_.. --level L4 --human-approval --evidence @e.json  # J 昇格ゲート
brain report / verify / replay --dry-run  # 説明可能性・整合性・決定的再生成
```

## 5. Memory hierarchy（記憶階層・§4/§15）

- **正本 = append-only イベントログ**（`~/.claude/brain-memory/events/`）。二度と書き換えない。
- **snapshot / relation graph = 派生物**。`replay` で決定的に再構築（挿入順・実時刻に非依存）。
- 記憶種別：`sensory / working / episodic / semantic / procedural / prospective / emotional_salience / inhibitory / meta_memory`。
- 各記憶は id・種類・範囲・信頼区分・信頼度・出典・証拠・作成/確認/使用日時・成功/失敗回数・反証・有効期限・状態・機密性・削除方針を持つ。状態：`observed→candidate→verified→active`（＋`conflicted/deprecated/archived/rejected/purged`）。
- **スコープ**（`session..global`）と**パーティション**（顧客/組織の instance）で隔離。狭いスコープを優先し、顧客情報を別顧客へ伝播させない。

## 6. Learning and promotion rules（§7/§8）

- **Hebbian は弱い証拠**。共起・順序・時間差・受け渡し・成功結果・独立検証・ユーザー確認・基準頻度・スコープ一致・反証・不確実性・サンプル数を総合する（関係グラフ本体は skill-synapse-jp に委譲）。
- **予測誤差学習**：想定内の成功は小さく、想定外の失敗は強く更新。**ベイズ的更新**：固定加点でなく事前信念×証拠。**メタ可塑性**：高リスク領域は学習率を下げる。**恒常性**：派生 weight のみ縮小（raw 不可侵）。**忘却**：削除だけでなく想起抑制/検索除外/信頼度低下/廃止/アーカイブを分ける。重大失敗・安全規則・明示ユーザー方針は時間減衰で消さない。
- **昇格フロー L0→L5**：`L0 observation → L1 candidate → L2 corroborated → L3 verified → L4 reusable procedure → L5 constitutional rule`。各段に厳格な条件（`references/reinforcement-learning.md`・`constitution/LEARNING_POLICY.md`）。**単発成功では昇格しない。自己評価だけでは強化しない。**

## 7. Inhibition and safety（§I/§K）

- **抑制は必須要素**：無関係情報・誤連想・外部文書内命令・危険自動化・過強ハブ・一時的成功の過学習・重複記憶・古記憶・競合方策を、それぞれ別の抑制で扱う。
- **顕著性と危険度は別軸**。高顕著性操作（削除/上書き/外部送信/認証/権限/自己改変/多端末展開/個人情報/法務/医療/金銭/不可逆設定）は**自動拒否ではなく承認ゲート**へ送る。過去の重大失敗を優先想起し、過剰警戒は補正する。
- **前頭前野型実行制御**（`executive`）だけが本番昇格・長期記憶更新・手続変更・改変提案・危険操作の承認要求を許可できる。**この層自身も安全規則を書き換えられない。**

## 8. Self-modification restrictions（§9）

通常タスク実行中に **自動変更しない**：`SKILL.md`／憲法／安全規則／承認要件／権限／hooks／MCP設定／学習率上限／昇格条件／外部送信規則／削除規則／秘密処理規則。自己改変は候補としてのみ生成し、`改変理由→根拠→diff→期待効果→副作用→反例→回帰試験→セキュリティ試験→sandbox→人間承認→canary→本番昇格→ロールバック確認` を経る。L5 規則は通常実行中に自動作成/変更しない。

## 9. Verification（§16/§22）

- `verify` は **読取専用（無副作用）**：イベント検証・snapshot 整合・**replay 決定性**・将来時刻検出・backup checksum を確認する。
- すべての書込は安全書込（ランダム一時ファイル→0600→fsync→os.replace→親dir fsync・symlink/traversal 対策・lock・backup+checksum・rollback）。`dry-run` は一切書き換えない。
- テスト：`pytest`（unit/integration/regression/poisoning/privacy/chronology/property）。

## 10. References

- `references/neuroscience-to-software-map.md` — 比喩とアルゴリズムの境界（対応表）
- `references/memory-systems.md`／`attention-and-working-memory.md`／`predictive-processing.md`／`reinforcement-learning.md`／`inhibition-and-homeostasis.md`／`metacognition.md`／`consolidation-and-forgetting.md`
- `references/limitations.md` — 既知の限界と誤用の注意
- `constitution/CORE_PRINCIPLES.md`／`LEARNING_POLICY.md`／`SAFETY_POLICY.md`／`PRIVACY_POLICY.md`
- `schemas/*.json` — event/memory/edge/goal/policy/proposal の JSON Schema
- 実装：`scripts/brain_architecture/`（決定的 Python。数値・状態遷移はこのコードだけが書く）

> 可変記憶（`~/.claude/brain-memory/`）はスキル本体と分離する。`$BRAIN_MEMORY_DIR` で上書き可能。
