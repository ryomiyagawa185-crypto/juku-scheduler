# ローカル Claude Code への引き継ぎ

このファイルは、`origin-ai/` の続きをローカルの Claude Code に任せるための指示書。
**冒頭の「貼り付け用プロンプト」をそのまま Claude Code に渡せば作業が始まる。**

---

## 貼り付け用プロンプト

```
このリポジトリの origin-ai/ は、私個人のAI基盤の P0（骨格）と P1（安全床）まで実装済みです。
続きを担当してください。

まず読むもの（この順に）:
  1. docs/original-ai/handoff-to-local-claude-code.md  ← 作業手順と禁止事項
  2. origin-ai/README.md                                ← 構造と起動方法
  3. origin-ai/CLAUDE.md                                ← 推論層のルート契約
  4. docs/original-ai/review-notes.md                   ← なぜこの設計なのかの根拠

作業を始める前に必ず実行して、現状が緑であることを確認してください:
  cd origin-ai && pip install -e ".[dev]" && pytest -q

タスクは引き継ぎ書の「作業順序」に従ってください。1つ終わるごとに
pytest と scripts/build_registry.py --check を通し、コミットを分けてください。
引き継ぎ書の「壊してはいけない不変条件」に触れる変更をする場合は、
実装前に私に確認してください。
```

---

## 1. いま何ができているか

`origin-ai/` は動く状態で、テストは 48 件すべて緑。

- `plans/echo.plan.json` を実行すると、plan → policy → 実行層 → トレースの一周が通る
- 対話セッション（Hooks）とバッチ実行（middleware）が **同じ判定モジュール** を通る
- 判定が結論を出せない場合は必ずブロックする（fail-closed）
- 承認は内容ハッシュに束縛され、期限つき・原則 one-shot
- 台帳 `registry/skills.jsonl` は `SKILL.md` からの生成物で、手編集は CI で落ちる

確認済みの実挙動:

```
$ python -m orchestrator.runner plans/echo.plan.json
[s1] ブロック: pricing_placeholder          ← 単価未記入なので既定でブロック

$ ORIGIN_AI_ALLOW_PLACEHOLDER_PRICING=1 python -m orchestrator.runner plans/echo.plan.json
  s1  ok                                     ← 明示的オプトインでのみ通る

$ echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/x"}}' | python .claude/hooks/pre_tool_use.py
policy: 承認待ち: destructive-ops（対象ハッシュ sha256:4b3f51...）
exit=2                                       ← Hooks の exit 2 でツール実行がブロックされる
```

## 2. 壊してはいけない不変条件

これらは設計の核であり、便利さのために緩めない。緩めたくなったら実装前に相談すること。

1. **fail-closed** — ゲート・予算・分類の判定が結論を出せない（例外・ストア不能・単価未記入）なら
   必ず `BLOCK`。「判断できないので通す」は最悪の故障モードで、安全機構が沈黙して無効化されたことに
   誰も気づけない。
2. **判定は `policy/` にしかない** — フックやランナーに判定ロジックを書かない。書いた瞬間、
   そのルールは片方の経路でしか効かなくなる。
3. **承認は内容ハッシュに束縛** — 「このゲートを通ってよい」ではなく
   「この内容がこのゲートを通ってよい」。`destructive-ops` と `legal-submission` に
   まとめ承認を作らない。
4. **台帳は生成物** — `registry/skills.jsonl` を手で編集しない。真実源は `SKILL.md` のフロントマター。
5. **トレースに本文を書かない** — ハッシュと `artifacts/` へのポインタのみ。
   `trace.schema.json` の `additionalProperties: false` が防波堤。
6. **出力先は `data_class` が決める** — `pii` と `privileged` は `artifacts/open/` に書かない
   （`artifacts/open/` だけが外部同期の対象）。
7. **スキル間 import 禁止** — `skills.* → skills.*` は不可、`skills.* → origin_core` は可。
8. **外部作用のあるステップは自動リトライしない** — リトライ＝二重送信。

## 3. 作業順序

上から順に。1つ終わるごとに `pytest -q` と `python scripts/build_registry.py --check` を通し、
コミットを分けること。

### T1. 単価表を埋める（最優先・これをやるまで実行できない）

- `pricing/models.json` の `models` に、公式の料金ページから 1M トークンあたりの
  `input` / `cache_write` / `cache_read` / `output` を転記する
- `version` に転記元の改定日、`placeholder` を `false` に
- **完了条件:** `ORIGIN_AI_ALLOW_PLACEHOLDER_PRICING` なしで
  `python -m orchestrator.runner plans/echo.plan.json` が通る
- 注意: 単価は推測で書かない。公式ページを確認できない場合は placeholder のままにして、
  何が分からなかったかを報告すること（間違った単価は、単価が無いことより悪い）

### T2. トークンの実測を配線する

- いまは `origin_core/tokens.py` が推定値（CJK 1文字≒1トークンの当て推量）を返す
- `set_counter()` に本物のカウンタ（`count_tokens` API か同一トークナイザ）を注入する
- **完了条件:** `tokens.is_estimate()` が `False` になり、
  `tests/cost/` に入力トークンの黄金値回帰テストが追加されている
- 出力トークンは非決定的なので **上限のみ** 検査すること。等値比較のテストを書かない

### T3. 既存スキルを1つシム経由で載せて移行コストを実測する

- `adapters/legacy_skill.py` は、契約フィールドが欠けた `SKILL.md` を
  保守的な既定値（risk=high / data_class=pii / 外部送信は承認 / stage=experimental）で埋める
- 手持ちのスキルから **リスクの低いものを1つ** 選び、無改変で `skills/` に置いて
  `build_registry.py` が通るか試す
- **完了条件:** 1スキルが台帳に載り、`legacy_shim: true` が付き、
  「契約を書き足すのにどれくらいかかるか」の実測値が報告されている
- ここで得た数字が、残りの移行を一括でやるか段階的にやるかの判断材料になる

### T4. メタスキルを移植する（P2）

`skill-creator` / `skill-version-librarian` / `drift-audit` / `fact-check-guard` の4つ。

- `drift-audit` の対象は **`versions/` と作業ツリーの乖離** に限定すること。
  台帳整合の監査は不要（台帳が生成物になったので、ずれようがない）
- **完了条件:** 4スキルが台帳に載り、それぞれのユニットテストが緑

### T5. evals を作る（P4・最重要の欠落）

- `evals/datasets/<skill-id>/` に各20件、`evals/graders/`、`evals/thresholds.json`
- 二段構え:
  - **決定的チェック**（安価・CI 毎回）— 引用条番号の実在、判例名と裁判所・年月日の突合、
    入力に無い固有名詞・数値が出力に現れていないか
  - **ルーブリック採点**（LLM-judge・日次）— judge の信頼性は人手サンプルとの合意率で定期検証
- `stage` の昇格を合格率で門番する
- **完了条件:** 主要スキルの合格率が測定でき、閾値割れで自動降格する
- `data_class: privileged` のスキルは **実データを評価セットに使わない**（仮名化した合成事例で）

### T6. 高リスクスキルを載せる（P5・ここまでのゲートが緑になってから）

`gas-automation` / `line-notify` など外部作用のあるもの。**T1〜T5 が終わるまで着手しない。**
v0.1 の設計はこれを P2 でやる順序になっていて、ゲートのない基盤に外部送信スキルが載る
期間ができていた。それを避けるための順序変更なので、ここを前倒ししないこと。

## 4. やらないこと

- `registry/skills.jsonl` の手編集
- `policy/` の外に判定ロジックを書くこと
- 「今後すべて許可」の承認を `destructive-ops` / `legal-submission` に作ること
- 推論層のプロセスに Write / Bash / 外部送信ツールを渡すこと
- `test_chain_replay` 的な「LLM 出力のハッシュ等値」テストを書くこと
  （達成不能で恒常的に赤になり、やがて計装全体が信用されなくなる）
- スキル間で共有したいコードを `skills/` の中に置くこと（`origin_core/` に置く）
- 単価・料金・条文番号を推測で書くこと

## 5. 判断に迷ったら

- **設計の根拠** は `docs/original-ai/review-notes.md` に18件の指摘として全部書いてある。
  「なぜこうなっているのか」はまずそこを見る
- **不変条件に触れる変更**（§2 の8項目）は実装前に確認を取る
- **スキーマの変更** は影響範囲が広い（`schemas/` は全体の土台）。変更する場合は
  既存トレースが読めなくなるかどうかを先に確認する

## 6. 置き場所について

`origin-ai/` はいま `juku-scheduler` リポジトリの中にあるが、これは作業の都合。
独立したリポジトリに切り出すか `ronshocho` の中に移すかは未決定。
移す場合は以下だけ注意すれば、そのまま動く。

- `origin_core/__init__.py` の `ROOT` は `origin-ai/` 直下を指す想定
- `.github/workflows/skill-ci.yml` の `working-directory: origin-ai` を実際の位置に合わせる
- `.gitignore` の `state/` `traces/` `artifacts/{pii,privileged}/` を必ず引き継ぐ
