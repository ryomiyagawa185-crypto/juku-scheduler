# オリジナルAI プロジェクト構造設計書

**バージョン:** v0.2（レビュー反映版）
**前版:** v0.1（設計案）
**改訂根拠:** `docs/original-ai/review-notes.md`（S1–S6 / M1–M6 / G1–G5 / R）
**対象:** ユーザー個人のオリジナルAI基盤（コードネーム: `miyagawa-ai` 後継 / `origin-ai`）
**参照実装:** Claude Code（`.claude/` + `SKILL.md` + Hooks + Subagents）、既存の `skill-version-librarian-rm`、`context-economy-cc`、`ship-gate-cc`、`ai-council-jp`

---

## 設計原則（v0.2）

0. **単一の真実源** — 同じ事実を2箇所に書かない。派生情報はすべて生成物とし、CI で「生成し直して差分ゼロ」を強制する。*（v0.1 からの追加。台帳と `SKILL.md` の二重管理を廃止するため）*
1. **スキル（ツール）の独立性** — 各スキルは自己完結した契約（`SKILL.md`）と実装（`commands/`, `scripts/`）を持つ。禁止するのは**スキル間の相互依存**であり、純粋ライブラリ（`origin_core/`）の利用は許可する。*（v0.1 の「`common/` 全面禁止」を修正）*
2. **推論層と実行層の分離は「権限」で担保する** — 推論層のプロセスには書き込み系・ネットワーク系のツールを渡さない。計画は凍結せず、追記可能なログとして再計画を正常系で扱う。*（v0.1 の「plan.json 凍結」を修正）*
3. **レビュー優先ゲート** — 高リスク・外部作用のある操作は承認ゲートを通す。承認は**内容ハッシュに束縛**し、期限つき・原則 one-shot とする。*（TOCTOU 対策を追加）*
4. **コスト・トレース・品質の三点計装** — 費用と遅延だけでなく、**出力品質（evals）**も回帰検証の対象にする。*（v0.1 に欠落していた evals を追加）*
5. **フェイルセーフは常に閉じる方向** — ゲート・予算の評価が結論を出せない場合は必ずブロックする。安全機構が沈黙して無効化される故障モードを設計で排除する。*（追加）*

---

## 0. 全体アーキテクチャ（概念図）

```
┌─────────────────────────────────────────────────────────────────┐
│                      USER INTERFACE LAYER                        │
│              （CLI / Web / LINE通知 / MCPクライアント）             │
└───────────────────────────┬─────────────────────────────────────┘
                            │ intent
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│         REASONING LAYER  （推論層 / 判断のみ・書込権限なし）        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  CLAUDE.md（共通原則・ガードレール・出力契約）              │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │  skill selection : モデルが description を読んで選ぶ        │  │
│  │  └─ router.py は「候補の除外・検証」のみ（選定はしない）     │  │
│  │  planner  → plan_log.jsonl に revision を追記               │  │
│  └──────────────────────────────────────────────────────────┘  │
│  許可ツール: Read / Grep / Glob のみ（Write・Bash・送信は不可）   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ plan revision（追記ログ）
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                        POLICY  （policy/）                       │
│   予算 / ゲート / DRY_RUN / データ分類 の判定を行う単一モジュール   │
│   ├── 入口A: .claude/hooks/*.py      （対話セッション用アダプタ）  │
│   └── 入口B: orchestrator/middleware  （バッチ実行用アダプタ）    │
│   ※ 両入口が同一判定を返すことを test_policy_parity で保証        │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│         EXECUTION LAYER  （実行層 / 決定的な手続き）                │
│  │  Skill Runner（scripts/*.py, commands/*.md）                  │
│  │  ├─ skills/legal/*       ├─ skills/edu/*                      │
│  │  ├─ skills/ops/*         ├─ skills/meta/*                     │
│  │  └─ skills/user-mirror/*                                      │
│  │  共通基盤: origin_core/（スキーマ検証・トレース・予算・ハッシュ）│
│  │  冪等性: idempotency_key / 一時ファイル + atomic rename        │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│    STORAGE / OBSERVABILITY / EVALUATION                          │
│  ├─ artifacts/{open,pii,privileged}/  （分類別・同期範囲を分離）   │
│  ├─ traces/   （本文は書かない：ハッシュ＋ポインタのみ）           │
│  ├─ costs/    （キャッシュ階層別・単価表バージョンつき）           │
│  ├─ evals/    （出力品質の回帰・stage 昇格の門番）                │
│  └─ versions/ （skill-version-librarian の不変スナップショット）  │
└─────────────────────────────────────────────────────────────────┘
```

**v0.1 からの構造変更（要点）**

| 変更 | 理由 |
|---|---|
| `policy/` を新設し Hooks と実行層の両方から呼ぶ | 対話経路とバッチ経路でルールが食い違う穴を塞ぐ（M5） |
| ルーターを「選定」から「除外・検証」に反転 | モデル本来の選択能力を下回らないため（S2） |
| `origin_core/` を追加 | 純粋関数のためにLLM往復を強いる設計を回避（M1） |
| `evals/` を追加 | 形式検査しかなく中身の誤りが素通りする穴を塞ぐ（G1） |
| `artifacts/` をデータ分類別に分離 | 事件記録・生徒データが同期先に平文で載るのを防ぐ（S6） |

---

## 1. ディレクトリ構造（トップレベル）

```
origin-ai/
├── CLAUDE.md                    # ★ 共通原則・ガードレール（最上位契約）
├── README.md
├── pyproject.toml
│
├── .claude/                     # Claude Code 固有設定（一次ランタイム）
│   ├── settings.json            #   権限（推論層の許可ツールをここで絞る）
│   ├── agents/                  #   Subagent 定義（Claude Code の実際の置き場）
│   ├── hooks/                   #   policy/ を呼ぶだけの薄いアダプタ
│   │   ├── pre_tool_use.py
│   │   ├── post_tool_use.py
│   │   └── session_end.py
│   └── commands/                #   スラッシュコマンド
│
├── policy/                      # ★ 判定ロジックの単一実装（M5）
│   ├── budget.py                #   予算残高照会・アトミック加算
│   ├── gates.py                 #   ゲート発火判定
│   ├── approvals.py             #   承認レコードの発行・検証（S4）
│   ├── classification.py        #   data_class に基づく出力先・保持期間の決定
│   └── decide.py                #   統合エントリ（fail-closed）
│
├── origin_core/                 # ★ 純粋ライブラリ（副作用なし・依存OK）（M1）
│   ├── schema.py                #   JSON Schema 検証
│   ├── tracing.py               #   トレース書き出し（シークレットマスキング込み）
│   ├── tokens.py                #   トークン計数（count_tokens / トークナイザ）
│   ├── pricing.py               #   単価表参照・コスト算出
│   └── hashing.py               #   入力・出力の正規化ハッシュ
│
├── registry/                    # 台帳（★ 生成物。手で編集しない）（S1）
│   ├── skills.jsonl             #   build_registry.py の出力
│   ├── skills.schema.json
│   └── dependencies.dot
│
├── orchestrator/
│   ├── SKILL.md
│   ├── router.py                #   候補の除外・検証のみ（選定はモデル）（S2）
│   ├── planner.py               #   plan revision の生成
│   ├── middleware.py            #   policy/ を呼ぶバッチ側アダプタ
│   └── chain.py
│
├── skills/                      # 独立スキル群（1スキル1ディレクトリ）
│   ├── legal/ ├── edu/ ├── ops/ ├── meta/ └── user-mirror/
│
├── adapters/                    # ★ ランタイム固有／移行の隔離層（G4, G5）
│   ├── claude_code/             #   Claude Code 依存コードをここだけに閉じる
│   └── legacy_skill.py          #   拡張フィールドのない既存 SKILL.md のシム
│
├── evals/                       # ★ 出力品質の評価（G1）
│   ├── datasets/<skill-id>/     #   入力＋期待要素／禁止要素
│   ├── graders/                 #   決定的チェッカ + LLM-judge ルーブリック
│   └── thresholds.json          #   stage 昇格に必要な合格率
│
├── tests/
│   ├── unit/ ├── integration/ ├── cost/ ├── trace/
│   └── governance/              #   ゲート発火・fail-closed・policy parity
│
├── pricing/models.json          # 単価表（改定日・バージョンつき）（M2）
├── traces/YYYY-MM-DD/*.jsonl    # 本文を書かない
├── costs/YYYY-MM-DD.json
├── versions/skills/<id>/<semver>/
├── artifacts/
│   ├── open/                    #   同期可
│   ├── pii/                     #   同期対象外・90日保持
│   └── privileged/              #   同期対象外・削除禁止（事件記録）
│
└── docs/
    ├── architecture.md ├── contracts.md ├── data-policy.md └── runbooks/
```

---

## 2. CLAUDE.md 構成（共通原則の最上位契約）

v0.1 の §1–§10 を維持し、以下の2節を追加、§2 と §5 を差し替える。

```markdown
## 2. 二層分離の原則  【v0.2 で差し替え】
- 分離の担保は「計画の凍結」ではなく「権限の分離」で行う
- 推論層のプロセスに Write / Edit / Bash / 外部送信ツールを渡さない
  （.claude/settings.json の permissions と実行層プロセスの制限の二重で担保）
- 再計画は例外ではなく正常系。plan_log.jsonl に revision として追記する
- 予算はプラン単位ではなくセッション単位の残高で管理する

## 5. スキル選択ルール  【v0.2 で差し替え】
- 選定はモデルが description を読んで行う（progressive disclosure）
- router.py は候補の「除外」と「検証」のみを行い、選定はしない
  除外条件: stage=deprecated / 日次予算枯渇 / 権限不足 / depends_on 未充足
- 台帳にないスキルを勝手に作らない
- 受験モードか実務モードかを推測で確定しない（明示問い返し）

## 11. データ分類  【v0.2 で新設】
- 全スキルは data_class を宣言する: public / internal / pii / privileged
- pii: 塾生徒の氏名・成績・連絡先、保護者情報
- privileged: 事件記録、相手方情報、依頼者との通信
- トレースに本文を書かない（ハッシュ + artifacts へのポインタのみ）
- pii / privileged の成果物は artifacts/{pii,privileged}/ に出力し、外部同期の対象外
- 保持: internal 30日 / pii 90日で削除 / privileged は削除せず別管理

## 12. 秘密情報  【v0.2 で新設】
- APIキー・トークンは環境変数または OS キーチェーンのみ
- SKILL.md の secrets: に宣言したものだけを実行層が注入する
- トレース・ログ書き出し時に宣言済みシークレット値を必ずマスクする
- エラーメッセージ経由の漏洩を防ぐため、例外整形も同じマスカを通す
```

### 2.2 CLAUDE.md のカスケード

v0.1 のまま維持（ルート最優先、サブディレクトリは追加規則のみ、ルートを緩めない）。

---

## 3. スキル登録台帳（Registry）

### 3.1 台帳は生成物である（S1 — v0.1 からの最大の変更）

**唯一の真実源は各スキルの `SKILL.md` フロントマター。** `registry/skills.jsonl` はそこから機械生成する。

```bash
python scripts/build_registry.py            # SKILL.md 群 → skills.jsonl を生成
python scripts/build_registry.py --check    # 生成し直して差分があれば exit 1（CI）
```

これにより v0.1 が抱えていた「台帳と SKILL.md がずれる → drift-audit で検出する」という自作自演の構造が消える。`drift-audit` は本来の役割（`versions/` のスナップショットと作業ツリーの乖離検出）に専念する。

生成される行の例：

```jsonl
{"id":"legal.civil-law-jp","version":"1.4.2","stage":"stable","path":"skills/legal/civil-law-jp","tier":"reasoning","triggers":["民法","94条2項","要件事実"],"inputs_schema":"schemas/civil-law-jp.in.json","outputs_schema":"schemas/civil-law-jp.out.json","gates":["fact-check-guard"],"budget":{"per_call_usd":0.30,"daily_usd":5.00},"depends_on":["meta.fact-check-guard>=1.0.0"],"data_class":"privileged","secrets":[],"risk":"medium","eval_pass_rate":0.94,"last_evaluated":"2026-07-29"}
{"id":"ops.gas-automation","version":"2.1.0","stage":"beta","path":"skills/ops/gas-automation","tier":"execution","triggers":["GAS","スプレッドシート","自動化"],"gates":["external-send","destructive-ops"],"budget":{"per_call_usd":0.05,"daily_usd":1.00},"safety_contract":{"dry_run_default":true,"idempotent":true,"config_externalized":true},"data_class":"internal","secrets":["GAS_DEPLOY_TOKEN"],"risk":"high","eval_pass_rate":0.88,"last_evaluated":"2026-07-29"}
```

### 3.2 必須フィールド（v0.2 で追加したもの）

v0.1 の `id` `version` `stage` `tier` `triggers` `inputs_schema` `outputs_schema` `gates` `budget` `depends_on` `risk` に加えて：

| フィールド | 内容 | 追加理由 |
|---|---|---|
| `data_class` | `public` / `internal` / `pii` / `privileged` | S6 |
| `secrets` | 注入を許可するシークレット名の配列 | G2 |
| `eval_pass_rate` / `last_evaluated` | 直近の eval 合格率と実施日 | G1（stage 昇格の根拠） |

`depends_on` はバージョン範囲つきで書く（`meta.fact-check-guard>=1.0.0`）。範囲を意味あるものにするため、SemVer の刻み方を §5.3 で定義する。

---

## 4. スキルオーケストレーター

### 4.1 責務

ユーザー意図を受け取り、**モデルが選んだスキル**を検証し、実行順序を plan revision として `plan_log.jsonl` に追記する。自らはツールを叩かない。

### 4.2 `router.py` の責務反転（S2）

v0.1: 台帳の `triggers` をキーワード＋埋め込みでマッチして候補を選ぶ
v0.2: **選定はモデル。router は選ばれた候補に対して以下だけを行う。**

1. `stage: deprecated` を除外し、後継スキルを提示する
2. 日次予算が枯渇しているスキルを除外する
3. `depends_on` のバージョン範囲を満たすか検査する
4. `data_class` が現在のセッション文脈で許容されるか検査する
5. `risk: high` が選ばれた場合、選定理由の明示を要求する

埋め込み検索の導入は、スキル数が概ね50を超えて description の常時投入がコンテキストを圧迫し始めてからでよい。progressive disclosure（description のみ常駐、本文は必要時に読み込み）なら数百スキルまで持つ。

### 4.3 plan revision（S3 — v0.1 の `plan.json` 凍結を置き換え）

計画は単一の確定ファイルではなく、`plan_log.jsonl` への**追記**とする。再計画は例外ではなく正常系のイベント。

```json
{
  "plan_id": "uuid",
  "revision": 2,
  "parent_revision": 1,
  "revision_reason": "s1 の出力で新たな争点が判明したため s2 以降を差し替え",
  "created_at": "2026-08-03T22:00:00+09:00",
  "session_id": "uuid",
  "user_intent": "エッセン社の事業譲渡について答弁書ドラフトを作成",
  "steps": [
    {
      "step_id": "s1",
      "skill_id": "legal.dispute-resolution-jp",
      "skill_version": "1.2.0",
      "inputs": {"case_id": "essence-transfer", "doc_type": "answer_brief"},
      "expected_outputs": ["artifacts/privileged/essence/answer_brief_draft.md"],
      "gates_required": ["legal-submission"],
      "data_class": "privileged",
      "idempotency_key": "sha256:...",
      "budget_usd": 0.20,
      "retry_policy": "none",
      "depends_on": []
    },
    {
      "step_id": "s2",
      "skill_id": "meta.fact-check-guard",
      "skill_version": "1.0.3",
      "inputs": {"target": "artifacts/privileged/essence/answer_brief_draft.md"},
      "idempotency_key": "sha256:...",
      "depends_on": ["s1"],
      "budget_usd": 0.05,
      "retry_policy": "auto:2"
    }
  ],
  "session_budget_remaining_usd": 3.42,
  "gates_summary": ["legal-submission"],
  "review_required": true
}
```

**制約（v0.2）**
- 凍結対象は plan 全体ではなく**承認済みステップ**。承認後に `idempotency_key` が変わったステップは承認が失効する（§6.3）。
- 予算はセッション残高（`session_budget_remaining_usd`）で管理する。再計画が正常系である以上、プラン単位の上限は機能しない。
- `review_required: true` のステップは実行層を起動せず人間承認を待つ。

### 4.4 冪等性・部分失敗（G3 — v0.1 に規定なし）

- 全ステップに `idempotency_key = sha256(plan_id + step_id + inputs_hash)` を付与。実行層は完了済みキーのステップをスキップする。
- ファイル出力は一時ファイルへ書いてから **atomic rename**。半端な成果物を残さない。
- `retry_policy`: 外部作用のあるステップ（`gates` に `external-send` / `legal-submission` を含む）は **`none` 固定**。自動リトライによる二重送信を設計で禁じる。純粋な読み取り・生成のみのステップは `auto:N` を許可する。

---

## 5. スキルの独立性契約（`SKILL.md`）

```markdown
---
id: legal.civil-law-jp
version: 1.4.2
tier: reasoning
risk: medium
stage: stable
data_class: privileged        # v0.2 追加
secrets: []                   # v0.2 追加
budget: {per_call_usd: 0.30, daily_usd: 5.00}
gates: [fact-check-guard]
depends_on: [meta.fact-check-guard>=1.0.0]
---

# civil-law-jp

## When / Goal / Inputs / Outputs / Permissions / Gates / Constraints / Evidence / Handoff
（v0.1 の構成を維持）

## Evals                       # v0.2 追加
- データセット: evals/datasets/legal.civil-law-jp/
- 決定的チェック: 引用条番号の実在検証、判例名と裁判所・年月日の突合
- ルーブリック採点: evals/graders/legal_rubric.yaml
- stable 維持に必要な合格率: 0.90
```

### 5.1 独立性の定義（M1 — v0.1 から修正）

| | v0.1 | v0.2 |
|---|---|---|
| スキル間 import | 禁止 | 禁止（変更なし） |
| 共通ユーティリティ | 禁止（メタスキル化） | **`origin_core/` として許可** |
| 判断を含む共通処理 | メタスキル化 | メタスキル化（変更なし） |

`origin_core/` に置いてよいのは**副作用も判断も持たない純粋な処理**のみ（スキーマ検証・ハッシュ・トークン計数・単価計算・トレース書き出し）。LLM の判断が入るもの（`fact-check-guard` 等）は従来どおりメタスキルとして台帳経由で呼ぶ。

lint（`scripts/check_skill_independence.py`）が禁じるのは `skills.* → skills.*` の import だけ。`skills.* → origin_core` は許可する。

### 5.2 Permissions

推論層スキル（`tier: reasoning`）は Read / Grep / Glob のみ。Write と外部送信は `tier: execution` のスキルが実行層プロセスで行う。この制限は `.claude/settings.json` と実行層プロセスの capability の**両方**で設定する（片方だけだと経路によって抜ける）。

### 5.3 SemVer の刻み方（M6 — v0.1 に規定なし）

| 区分 | 該当する変更 |
|---|---|
| **major** | inputs / outputs スキーマの破壊的変更、gates の削除、権限の拡大、data_class の緩和 |
| **minor** | 入力の任意項目追加、gates の追加、能力の追加、data_class の厳格化 |
| **patch** | プロンプト文言・内部実装の変更で、契約と eval 合格ラインが不変のもの |

`stage` の昇格（experimental → beta → stable）は **eval 合格率が `evals/thresholds.json` の閾値を満たすこと**を条件とする（§8）。人間の感触だけで stable にしない。

---

## 6. Policy と Hooks

### 6.1 判定ロジックの単一化（M5）

v0.1 は Hooks の擬似コードが `PlanStep` を引数に取っていたが、Claude Code の Hooks は**ツール呼び出し単位**で発火し stdin の JSON を受け取る機構であり、`PlanStep` は渡ってこない。このまま実装すると、対話セッションとバッチ実行のどちらか一方でしかポリシーが効かない。

v0.2 では判定を `policy/decide.py` に一本化し、2つの薄いアダプタから呼ぶ。

```python
# policy/decide.py — 唯一の判定実装
def decide(ctx: PolicyContext) -> Decision:
    """ctx はツール呼び出しからも PlanStep からも構築できる共通形。
    例外・タイムアウトで結論が出せない場合は必ず BLOCK を返す（fail-closed）。"""
    try:
        if not budget.has_headroom(ctx.skill_id, ctx.estimated_cost_usd):
            return Decision.block("budget_exceeded")

        for gate in ctx.gates_required:
            approval = approvals.find_valid(gate, ctx.target_hash)
            if approval is None:
                return Decision.wait_for_approval(gate, ctx.target_hash)

        if ctx.risk == "high" and not ctx.inputs.get("confirmed"):
            return Decision.proceed(mutate={"dry_run": True})

        if not classification.output_path_allowed(ctx.data_class, ctx.output_paths):
            return Decision.block("data_class_violation")

        return Decision.proceed()
    except Exception as e:
        return Decision.block(f"policy_error:{type(e).__name__}")   # fail-closed（S5）
```

```python
# .claude/hooks/pre_tool_use.py — 対話セッション用アダプタ
payload = json.load(sys.stdin)             # tool_name, tool_input などを受け取る
d = decide(PolicyContext.from_tool_call(payload))
if d.blocked:
    print(d.reason, file=sys.stderr)
    sys.exit(2)                            # PreToolUse は exit 2 でツール実行をブロック
sys.exit(0)
```

```python
# orchestrator/middleware.py — バッチ実行用アダプタ
def before_step(step: PlanStep) -> HookResult:
    return HookResult.from_decision(decide(PolicyContext.from_plan_step(step)))
```

`tests/governance/test_policy_parity.py` が、同一の意味を持つ入力に対して両アダプタが同じ判定を返すことを検査する。

### 6.2 予算カウンタの原子性（S5）

日次予算の消費は複数プロセスから同時に更新され得る。JSON ファイルの read-modify-write は競合で必ず取りこぼすため、**SQLite のトランザクション**（またはファイルロック）で加算する。ストアが読めない・書けない場合は `BLOCK`。

### 6.3 承認レコード（S4 — v0.1 に規定なし）

v0.1 の `HookResult.WAIT_FOR_APPROVAL(gate)` は、承認がどこに保存され何に対する承認なのかが未定義だった。承認後に入力が差し替わると、承認済みフラグだけが残って別物が実行される（TOCTOU）。

```json
{
  "approval_id": "uuid",
  "scope": "step",
  "target_hash": "sha256:...",
  "gate": "external-send",
  "approver": "user",
  "granted_at": "2026-08-03T22:10:00+09:00",
  "expires_at": "2026-08-03T23:10:00+09:00",
  "one_shot": true
}
```

- `target_hash` は承認時点の inputs（＋外部送信なら本文）の正規化ハッシュ。**実行直前に再計算して不一致なら承認を無効化し、再承認を要求する。**
- 既定は `one_shot: true` / 有効期限1時間。
- 「今後すべて許可」は gate 単位＋期限つきでのみ設定可。**`destructive-ops` と `legal-submission` は対象外**（毎回承認）。

### 6.4 post / session_end

- `post_tool_use.py` — 実測トークン（キャッシュ階層別）・レイテンシ・出力ハッシュを `traces/` に追記、`costs/` を更新、出力スキーマ検証。不一致なら後続ステップを止める。
- `session_end.py` — 日次コストレポート生成、ドリフト監査の軽量実行、差分検出時に LINE 通知。

---

## 7. テスト（費用・トレース・ガバナンス）

### 7.1 テスト階層

| 層 | 場所 | 目的 |
|---|---|---|
| Unit | `tests/unit/<domain>/` | スキル単体の入出力契約 |
| Cost | `tests/cost/` | 入力トークン回帰・予算超過検出 |
| Trace | `tests/trace/` | ログスキーマ・制御フロー再現性 |
| Integration | `tests/integration/` | スキルチェーンの E2E |
| Governance | `tests/governance/` | ゲート発火・fail-closed・policy parity・承認失効 |
| **Eval** | `evals/`（§8） | **出力品質**（v0.2 で新設） |

### 7.2 費用テスト（M3 — v0.1 の方式を修正）

v0.1 の `test_token_regression` はモック LLM の下で `tokens_in` を黄金値と比較していたが、モックはトークンを数えないため空テストになる。入力側と出力側を分ける。

```python
def test_input_token_regression(golden_costs):
    """入力トークンは実際に数える。モデル呼び出しは発生しないので安価かつ決定的。"""
    for case in golden_costs.load("legal.civil-law-jp"):
        prompt = build_prompt(case.inputs)             # 実際のプロンプト構築
        n = origin_core.tokens.count(prompt, model=case.model_id)
        assert n <= case.golden_input_tokens * 1.10, \
            f"Token bloat: {n} vs {case.golden_input_tokens}"

def test_output_tokens_bounded(recorded_responses):
    """出力は非決定的。等値ではなく上限のみを検査する。"""
    for case in recorded_responses.load("legal.civil-law-jp"):
        assert case.output_tokens <= case.max_tokens

def test_daily_budget_blocks_after_cap(budget_store):
    """日次予算を超えたら次の呼び出しがブロックされる（v0.1 から維持）"""
    budget_store.set("legal.civil-law-jp", daily_usd=1.00)
    for _ in range(3):
        assert decide(ctx(cost=0.30)).status == "proceed"
    assert decide(ctx(cost=0.30)).status == "blocked"

def test_budget_store_failure_is_fail_closed(broken_budget_store):
    """ストアが壊れているとき、通してはならない（S5）"""
    assert decide(ctx(cost=0.30)).status == "blocked"
```

`tests/cost/golden_costs.jsonl` には**測定日・モデルID・単価表バージョン**を持たせ、モデル更新時に一括更新できるようにする。

```jsonl
{"skill":"legal.civil-law-jp","case":"basic_94_2","model_id":"...","input_tokens":1200,"cache_read_input_tokens":900,"output_tokens":800,"pricing_version":"2026-07-01","measured_at":"2026-07-29"}
```

### 7.3 トレーステスト（M4 — v0.1 の replay を修正）

v0.1 の `test_chain_replay` は `outputs_hash` の等値を要求していたが、LLM 出力のバイト等値は temperature 0 でも保証されない。恒常的に赤になるテストは無視されるようになり、計装への信頼が壊れる。検査対象を分割する。

```python
def test_trace_conforms_to_schema():
    schema = load_schema("schemas/trace.schema.json")
    for line in read_all_jsonl("traces/**/*.jsonl"):
        jsonschema.validate(line, schema)

def test_executor_only_steps_are_byte_reproducible():
    """LLM を含まない手続きステップは、ハッシュ等値で再現性を検査してよい"""
    trace = load_trace("traces/2026-08-01/plan-abc123.jsonl")
    for step in trace.steps_where(tier="execution"):
        assert replay(step).outputs_hash == step.outputs_hash

def test_reasoning_steps_replay_control_flow():
    """推論を含むステップは記録済みレスポンス（カセット）を差し込み、
    ステップ列・ゲート発火・予算消費という制御フローの再現を検査する。
    生成テキストは意味的不変条件（スキーマ準拠・必須節の存在）で検査する。"""
    trace = load_trace("traces/2026-08-01/plan-abc123.jsonl")
    r = replay(trace, cassette="tests/trace/cassettes/plan-abc123.yaml")
    assert r.step_sequence == trace.step_sequence
    assert r.gates_triggered == trace.gates_triggered
    assert all(validates(o, schema_of(o.skill_id)) for o in r.outputs)
```

### 7.4 トレーススキーマ v2（M2 — v0.1 から必須項目を拡張）

v0.1 は `tokens_in` / `tokens_out` / `cost_usd` の3つに潰していたため、プロンプトキャッシュを使った瞬間にコスト計算が実態から乖離し、**キャッシュ最適化の効果が測定できない**（計装の主目的が達成できない）。

```json
{
  "type": "object",
  "required": [
    "trace_id","plan_id","plan_revision","step_id","skill_id","skill_version",
    "model_id","prompt_hash","pricing_version",
    "input_tokens","cache_creation_input_tokens","cache_read_input_tokens","output_tokens",
    "cost_usd","latency_ms","started_at","ended_at",
    "status","gates_triggered","approval_ref","data_class",
    "inputs_hash","outputs_hash","artifact_refs","retry_count","error_class"
  ],
  "properties": {
    "trace_id": {"type":"string","format":"uuid"},
    "status": {"enum":["ok","blocked","error","waiting_approval","skipped_idempotent"]},
    "data_class": {"enum":["public","internal","pii","privileged"]},
    "gates_triggered": {"type":"array","items":{"type":"string"}},
    "artifact_refs": {"type":"array","items":{"type":"string"},
                      "description":"成果物へのパス。本文そのものは書かない"}
  },
  "additionalProperties": false
}
```

`cost_usd` は `pricing/models.json` を参照して算出し、`pricing_version` を残す。単価改定後も過去トレースを遡って再計算できる。

### 7.5 CI

```yaml
name: skill-ci
on: [push, pull_request]
jobs:
  test:
    steps:
      - run: python scripts/build_registry.py --check     # 台帳が生成物と一致（S1）
      - run: pytest tests/unit
      - run: pytest tests/cost                            # 入力トークンのみ厳格に
      - run: pytest tests/trace
      - run: pytest tests/governance                      # fail-closed / parity / 承認失効
      - run: python scripts/check_skill_independence.py   # skills→skills の import 禁止
      - run: python scripts/scan_secrets_and_pii.py       # traces/ artifacts/ の誤コミット検出
      - run: python evals/run.py --deterministic-only     # 決定的チェックのみ（安価）
  nightly-eval:
    schedule: [{cron: "0 18 * * *"}]
    steps:
      - run: python evals/run.py --full                   # LLM-judge を含む全量
```

---

## 8. 評価（evals）— v0.2 で新設（G1）

**v0.1 の最大の欠落。** 費用・トレース・スキーマの回帰テストは揃っていたが、**出力の中身の正しさ**を見るものが一つもなかった。この基盤で最も損害が大きい故障は予算超過でもトレース欠損でもなく、**自信満々に間違った条文を引いた書面**と**取り違えた生徒データに基づく面談資料**であり、v0.1 のどのテストもそれを検出しない。

### 8.1 二段構えの採点

1. **決定的チェック（安価・CI 毎回）**
   - 引用条番号が実在するか（法令データとの突合）
   - 判例名・裁判所・年月日の組み合わせが一致するか
   - 入力に存在しない固有名詞・数値が出力に現れていないか（幻覚の代理指標）
   - 必須節の有無、出力スキーマ準拠
2. **ルーブリック採点（LLM-judge・日次）**
   - スキルごとの評価軸（例: 要件事実の網羅性、反論の想定、結論の明確さ）
   - judge の信頼性は**人手サンプルとの合意率**で定期検証し、合意率が落ちたら judge のプロンプトを改訂する（judge 自体も版管理対象）

### 8.2 stage 昇格の門番

```json
// evals/thresholds.json
{
  "experimental_to_beta": {"deterministic_pass": 0.80, "rubric_mean": 3.5},
  "beta_to_stable":       {"deterministic_pass": 0.95, "rubric_mean": 4.0},
  "stable_maintenance":   {"deterministic_pass": 0.90, "rubric_mean": 3.8}
}
```

- 閾値を割ったスキルは自動で `stage` を降格し、台帳の再生成でルーターの除外対象になる（§4.2）。
- `data_class: privileged` のスキルは評価セットに**実データを使わない**。匿名化・仮名化した合成事例で評価する。

---

## 9. バージョン管理・監査・データ保持

- `skill-version-librarian` を `skills/meta/` に配置し、`versions/skills/<id>/<semver>/` に不変スナップショットを保存（v0.1 から維持）。
- `SKILL.md` 変更は根拠記載つきコミットを伴う（v0.1 から維持）。
- `drift-audit` の対象は **`versions/` と作業ツリーの乖離**に限定する。台帳整合の監査は §3.1 の生成物化により不要になった（S1）。
- **保持期間（S6・v0.2 新設）**

| 分類 | 保存先 | 外部同期 | 保持 |
|---|---|---|---|
| `public` / `internal` | `artifacts/open/` | 可 | 30日（traces）／成果物は任意 |
| `pii` | `artifacts/pii/` | **不可** | 90日で自動削除 |
| `privileged` | `artifacts/privileged/` | **不可** | 自動削除しない・別途手動管理 |

---

## 10. 既存スキルからの移行（G4 — v0.2 で新設）

v0.1 は「新契約に書き換えてから移植する」前提だったが、既存スキルは相当数あり、一斉書き換えは現実的でない。**シムを先に作る。**

`adapters/legacy_skill.py` が、拡張フィールドを持たない既存 `SKILL.md` を読み込み、欠損フィールドに**保守的な既定値**を補って動かす。

| 欠損フィールド | 補う既定値 | 方針 |
|---|---|---|
| `risk` | `high` | 不明なら最も厳しく |
| `stage` | `experimental` | 昇格は eval 通過後 |
| `gates` | `[external-send, destructive-ops]` | 外部作用は必ず承認 |
| `data_class` | `pii` | 同期対象外に置く |
| `budget` | `per_call_usd: 0.05` | 小さく始める |

これで既存スキルは**無改変で新基盤に載り**、価値の高いものから順に契約を書き足していける。ビッグバン移植を避けることが完走の条件。

---

## 11. 設計上の非目標（v0.2 で修正）

- **完全自律の自己改変** — スキルの自動生成・自動デプロイは行わない（v0.1 から維持）
- ~~**共通ユーティリティ層を作らない**~~ → **修正:** `origin_core/`（純粋ライブラリ）は作る。禁止するのは**スキル間の相互依存**のみ（M1）
- **推論層からの直接副作用** — LLM に直接 Write・外部送信ツールを渡さない（v0.1 から維持・強化）
- ~~**モデル固有機能への依存をしない**~~ → **修正（G5）:** 一次ランタイムは **Claude Code に決める**。移植性の約束は「`skills/` 配下（SKILL.md + scripts + prompts）を素の Markdown と Python に保つ」に限定し、ランタイム固有の接着剤は `adapters/claude_code/` に隔離する。「移植性のために設計が歪むのに実際には移植できない」という両取りを避ける。

---

## 12. 実装ロードマップ（R — v0.1 から順序を変更）

**v0.1 の問題:** 高リスクスキル（`gas-automation`, risk: high）の移植が P2、ゲート実装が P4 で、**ゲートのない状態で外部作用スキルが新基盤に載る期間**があった。安全床を先に敷く順序に組み替える。

| フェーズ | 内容 | 完了基準 |
|---|---|---|
| **P0: 骨格** | ルート `CLAUDE.md`・`origin_core/`・`policy/` スタブ・`build_registry.py`・シム | 手書き plan で echo スキルが動き、台帳が生成できる |
| **P1: 安全床** | `policy/`（予算・ゲート・承認・分類）＋ Hooks/middleware の2アダプタ＋トレース v2 | **ゲートを通らずに外部作用が起きないことがテストで確認できる**。fail-closed と policy parity が緑 |
| **P2: メタスキル移植** | `skill-creator`, `skill-version-librarian`, `drift-audit`, `fact-check-guard` | 4スキルが台帳生成に載り、ユニットテスト通過 |
| **P3: 低リスク実務スキル** | `civil-law-jp`, `juku-scheduling` 等（`tier: reasoning` 中心） | スキル間 import 検査に合格、シム経由で既存スキルも稼働 |
| **P4: eval 基盤** | `evals/` データセット・決定的チェッカ・judge・昇格閾値 | 主要スキルの合格率が測定でき、stage 昇格が自動判定される |
| **P5: 高リスク実務スキル** | `gas-automation`, `line-notify` 等（外部作用あり） | DRY_RUN 既定・承認の内容ハッシュ束縛・二重送信防止が緑 |
| **P6: User Mirror** | `voice-adapter` を承認済みプロファイル限定で稼働 | 法律/医療文脈での自動抑制テストが緑 |
| **P7: 分散実行** | `mac-cluster-orchestrator` を Executor バックエンドに接続 | step が分散され、トレースが集約される |

---

## 13. 参考実装との対応表

| 参照 | origin-ai 対応 |
|---|---|
| Claude Code `.claude/` | `.claude/`（固有部分は `adapters/claude_code/` に隔離） |
| Claude Code `SKILL.md` | `skills/*/SKILL.md`（**唯一の真実源**・拡張フィールド追加） |
| Claude Code Hooks | `.claude/hooks/*`（判定は `policy/` に委譲する薄いアダプタ） |
| Claude Code Subagents | `.claude/agents/` + `orchestrator/chain.py` |
| `skill-version-librarian-rm` | `skills/meta/skill-version-librarian/` |
| `context-economy-cc` | `CLAUDE.md` §8 と入力トークン回帰テスト（§7.2） |
| `ship-gate-cc` | `policy/gates.py` + `policy/approvals.py` |
| `ai-council-jp` | `orchestrator/chain.py` の合議モード |
| `miyagawa-ai` Domain Pack | `skills/<domain>/` |
| Mac Grid | Executor バックエンド（P7） |

---

## 次アクション（優先順）

1. **`schemas/trace.schema.json` と `SKILL.md` フロントマターの JSON Schema を先に確定させる**（§3.2・§7.4）。台帳が生成物である以上、フロントマターのスキーマが全体の土台になる。
2. **`scripts/build_registry.py` と `--check` を実装**し、CI に入れる（S1 の解消はここで完了する）。
3. **`policy/decide.py` を fail-closed で実装し、`tests/governance/` を先に書く**。P1 の完了基準（ゲートを通らずに外部作用が起きない）はこのテストで定義される。
4. **`adapters/legacy_skill.py` のシムを実装**し、既存スキルを1つ無改変で動かして移行コストを実測する（G4 の見積もりを確定させる）。
5. 主要3スキルの eval データセットを各20件作る（§8）。合格率が測れて初めて stage の運用が始まる。
