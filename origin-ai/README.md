# origin-ai

宮川涼個人のAI基盤。P0（骨格）と P1（安全床）まで実装済み。

設計の根拠は `../docs/original-ai/project-structure.md`（v0.2）、
v0.1 からの変更理由は `../docs/original-ai/review-notes.md` にある。

## 起動

```bash
cd origin-ai
pip install -e ".[dev]"

python scripts/build_registry.py        # SKILL.md → registry/skills.jsonl
pytest -q                               # 48 tests

# P0 の疎通確認。既定ではブロックされる（下記）
ORIGIN_AI_ALLOW_PLACEHOLDER_PRICING=1 python -m orchestrator.runner plans/echo.plan.json
```

## 最初に必ずやること — 単価表の記入

`pricing/models.json` は **placeholder のまま出荷している**。この状態では
`policy.decide()` がすべてのプラン実行を `pricing_placeholder` でブロックする。

意図的な fail-closed。単価が 0 のまま動かすと費用の見積りが常に 0 になり、
日次予算が永久に超過せず、**予算ガードが存在しないのと同じ状態**になる。
公式の料金ページから 1M トークンあたりの単価を転記し、`placeholder` を `false` にすること。

環境変数 `ORIGIN_AI_ALLOW_PLACEHOLDER_PRICING=1` は疎通確認用の明示的な逃げ道で、
この状態で書かれたトレースは `pricing_version` が `"PLACEHOLDER"` になるため、
後から「費用が記録できていない実行」として判別できる。

## 構造

```
CLAUDE.md            共通原則（推論層のルート契約）
policy/              判定の唯一の実装。ここ以外に判定ロジックを書かない
  decide.py            fail-closed。例外・未確定はすべて BLOCK
  approvals.py         承認は内容ハッシュに束縛（TOCTOU 対策）
  budget.py            SQLite でアトミックに加算（競合で取りこぼさない）
  classification.py    data_class → 出力先の強制
  gates.py             ツール → ゲートの対応表（育てる前提）
origin_core/         純粋ライブラリ。スキルから import してよい唯一のもの
adapters/
  claude_code/         ランタイム固有の接着剤はここだけ
  legacy_skill.py      既存スキルを無改変で載せるシム
orchestrator/
  middleware.py        バッチ経路のアダプタ（hook_adapter と対）
  runner.py            plan revision の実行
registry/skills.jsonl  ★ 生成物。手で編集しない
schemas/               契約の土台（フロントマター・plan・trace・approval）
```

## 判定の入口は2つ、実装は1つ

```
.claude/hooks/pre_tool_use.py  ─┐
                                ├─→ policy/decide.py
orchestrator/middleware.py    ─┘
```

Claude Code の Hooks はツール呼び出し単位で stdin から JSON を受け取る機構なので、
`PlanStep` は渡ってこない。判定をフック側に書くと対話セッションでしか効かなくなり、
バッチ実行に穴が開く。`tests/governance/test_policy_parity.py` がその穴の見張り。

## 壊してはいけない不変条件

CI（`.github/workflows/skill-ci.yml`）が全部を検査している。

| 不変条件 | 見張っているテスト |
|---|---|
| 判定不能なら必ずブロック | `tests/governance/test_fail_closed.py` |
| 承認は内容ハッシュに束縛・期限つき・one-shot | `tests/governance/test_approval_binding.py` |
| 対話経路とバッチ経路が同じ判定 | `tests/governance/test_policy_parity.py` |
| 出力先は data_class が決める | `tests/governance/test_data_class.py` |
| トレースに本文を書かない | `tests/trace/test_trace_schema.py` |
| 台帳は SKILL.md の生成物 | `scripts/build_registry.py --check` |
| スキル間 import 禁止（origin_core は可） | `scripts/check_skill_independence.py` |

## 未実装（意図的）

| 範囲 | 状態 |
|---|---|
| 推論層の呼び出し・再計画（plan_log 追記） | 未実装。P2 |
| トークンの実測 | `origin_core.tokens.set_counter()` に注入するまで推定値 |
| evals（出力品質） | ディレクトリごと未作成。P4 |
| メタスキル（skill-creator ほか）の移植 | 未着手。P2 |
| 保持期間の自動削除 | 方針だけ（`policy/classification.py`）。実装は未 |
| 分散実行 | 未着手。P7 |
