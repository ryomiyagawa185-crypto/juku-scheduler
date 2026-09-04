# origin-ai v0.2 と 稼働中 miyagawa-ai の突き合わせ

**突き合わせ対象:** `miyagawa_ai_advice_bundle`（20ファイル / ローカル Mac で稼働中の方針）
**対象:** `docs/original-ai/project-structure.md`（v0.2）と `origin-ai/` の実装
**日付:** 2026-08-04

> 注意: バンドルは**助言のまとめ**であってコードではない。以下で「記載がない」と書いた項目は
> 「実装に無い」ではなく「この文書群に書かれていない」の意味。実装済みかどうかは
> ローカルで確認すること。

---

## 結論

**`origin-ai` を別システムとして作り進めるのはやめたほうがいい。**

理由は3つ。

1. **miyagawa-ai の方が安全設計が進んでいる。** 下の A に挙げた9項目は、v0.2 に無いか、
   v0.2 より強い。特に Recall/Memory・評価の絶対条件・Claim/Citation の構造検証・
   「通信失敗 ≠ 実行失敗」の再送分類は、v0.2 の対応物より明確に優れている。
2. **二重化は宮川さん自身の原則に反する。** 「実装済み・テスト済み・実運用済み・構想のみを
   混同しない」の反対をやることになる。Trace と評価セットが2系統に割れると、
   どちらの数字も比較できなくなる。
3. **v0.2 の価値ある部分は少数で、移植できる。** 下の B の4項目だけを miyagawa-ai に
   持ち込めば足りる。プラットフォームごと持ち込む必要はない。

`origin-ai/` のコードは**廃棄でなく参照実装**として残す価値がある（B の4項目は
テスト付きで動く形になっているため、移植元として使える）。

---

## A. バンドルの方が進んでいる点（v0.2 を捨てるべき箇所）

| # | 項目 | miyagawa-ai | origin-ai v0.2 | 判定 |
|---|---|---|---|---|
| A1 | **Recall / Memory** | scope filter を ranking 前に適用、`assertion_status`（verified / model_inference / quarantined）、`verified` のみ自動注入、登録ゲート13項目 | **概念ごと無い** | v0.2 の全面的な欠落 |
| A2 | **no_match / ambiguous でモデルを呼ばない** | 絶対条件として明文化 | 無い | 安全性でもコストでも v0.2 の予算ガードより効く |
| A3 | **評価の絶対条件** | `D=0` `wrong_subject=0` `cross_scope=0` `unsupported_fact=0` `external_fallback=0` `memory_db_write=0` ＋ FailureReason 11分類 ＋ Issue ライフサイクル | 合格率の閾値のみ（`evals/thresholds.json`） | **バンドルが正しい。** 平均合格率だけだと「別人の情報を返した1件」が高得点に埋もれる |
| A4 | **Claim / Citation の構造検証** | GroundedAnswer / CitedAnswer を**通常コードで**検証（未許可 Memory ID・根拠なし Claim・claims と used_memory_ids の不一致） | `fact-check-guard`（LLM が LLM を検査するメタスキル） | **バンドルが正しい。** 構造検証は決定的で安く、判定がぶれない |
| A5 | **「通信失敗 ≠ 実行失敗」** | 再送可（Connect Error / 処理前429 / Drain中423）と再送禁止（Read Timeout / 状態照会不能 / SIDE_EFFECT / 実行開始不明の5xx）を分類 | 「外部作用ゲートを持つステップは `retry_policy: none`」だけ | **v0.2 は不足。** ゲートを持たないステップの Read Timeout で二重実行し得る |
| A6 | **Shadow / Canary** | `SHA-256(job_id + policy_version + purpose)` で決定論的に bucket 割当、5→20→50→100%、絶対条件違反1件で 0% へ戻す | stage 昇格のみ。トラフィック分割の機構が無い | v0.2 の欠落 |
| A7 | **供給網の固定** | model **digest**（名前でなく）、prompt hash、config version、`latest` 禁止、Docker image digest 固定、UNKNOWN license は採用保留 | trace に `prompt_hash` があるだけ。供給網の方針は無い | v0.2 の欠落 |
| A8 | **実行サンドボックス** | code.review = network none / rootfs read-only / cap-drop ALL / no-new-privileges / pids・memory・cpu 制限 / Docker socket 禁止 / `shell=True` 禁止 | **無い**（`subprocess.run` でスキルを起動するだけ） | v0.2 の欠落。外部由来のコードを読む用途では致命的 |
| A9 | **Backup / DR** | 「バックアップの存在ではなく**復元成功**を確認する」＋ RPO / RTO ＋ 対象10種 | 無い | v0.2 の欠落 |

補足で2つ。

- **Prompt Injection** — バンドルは Memory と Model 出力まで未信頼データに含めている。v0.2 は
  injection に一切触れていない。これも A の系列。
- **Trust Boundary** — `interactive / eval / evolve / commit` の4境界と、R4 外部作用は
  Commit Gateway だけが実行する構造は、v0.2 のゲート一覧より整理されている。

---

## B. v0.2 から移植する価値があるもの（優先順）

これだけを miyagawa-ai に持ち込めばよい。それぞれ `origin-ai/` に動くコードとテストがある。

### B1. 承認を内容ハッシュに束縛する（最優先）

- **バンドルの現状:** Tool 権限表に `Approval` 欄があり、R4 は Commit Gateway が実行する。
  ただし「承認が**何に対する**承認か」の束縛は記載がない。
- **塞ぐ穴:** 承認した後に内容が変われば、承認済みフラグだけが残って別物が実行される。
  「ドラフトAを見て送信を承認 → 再生成でBになった → Bが送信される」。
- **移植元:** `origin-ai/policy/approvals.py` ＋ `tests/governance/test_approval_binding.py`
- **要点:** 承認レコードに `target_hash`（承認時点の inputs＋本文の正規化ハッシュ）を持たせ、
  実行直前に再計算して不一致なら失効。既定 one-shot・期限1時間。
  `destructive-ops` / `legal-submission` 相当にはまとめ承認を作らせない。
- **相性:** Artifact が既に SHA-256 で content-addressed なので、材料は揃っている。
  Artifact ID をそのまま `target_hash` に使える。

### B2. 判定器自身が壊れたときの挙動を決めて、テストで固定する

- **バンドルの現状:** 絶対条件は明確で、「指定モデル未存在なら起動失敗」は fail-closed。
  ただし**判定を行う側**（権限チェック・承認照会・予算照会）が例外を出した／ストアが
  読めない場合の既定が記載されていない。
- **塞ぐ穴:** 実装によっては「例外 → 握りつぶし → 通す」になる。安全機構が沈黙して
  無効化されたことに誰も気づけないのが最悪の故障モード。
- **移植元:** `origin-ai/policy/decide.py`（全体を try/except で包んで BLOCK に変換）＋
  `tests/governance/test_fail_closed.py`（ストアを壊した状態で通らないことを回帰テスト）

### B3. A5 の再送分類を idempotency と接続する

これは移植ではなく**バンドル側の強化**。バンドルの再送分類は正しいので、v0.2 の
`retry_policy` の考え方は捨てて、代わりに次を追加する。

- `SIDE_EFFECT` を持つ Job は、再送可否の判定以前に **attempt が1回だけ成立する**ことを
  `idempotency_key` で保証する（バンドルに既にある概念）
- Read Timeout 後は自動再送せず、**Worker Journal への状態照会が成功してから**判断する
  （`running` なら待つ、`interrupted` なら人間へ）

### B4. データ分類と同期境界を明示的に結ぶ

- **バンドルの現状:** `sensitivity` が Artifact と Memory にあり、scope filter もある。
  分類自体はある。
- **足りていない可能性:** 「どの分類がどこに置かれ、**どれが外部同期されるか**」の対応。
  事件記録が Dropbox 等に同期される経路があると、分類フィールドがあっても意味がない。
- **移植元:** `origin-ai/policy/classification.py`（分類 → 出力先の強制、同期対象の限定）
- **確認だけで済むかもしれない項目。** 既に分離されているなら移植不要。

---

## C. 私の助言のうち撤回するもの

v0.2 で書いたが、miyagawa-ai の文脈では**間違っている／不要**なもの。

| 撤回する助言 | 理由 |
|---|---|
| **予算を USD で管理する**（v0.2 §4.3・§6.2・`policy/budget.py`） | miyagawa-ai は local Ollama が第一で、支配的なコストは USD ではなく **latency・slot・容量**。USD の日次上限は外部 API を使う経路にしか効かない。予算の代わりに Capability Policy の `deadline_seconds` と slot 管理を使うのが正しい |
| **単価未記入ならブロック**（`pricing_placeholder`） | 上と同じ理由で、local 実行には単価が存在しない。外部 API を使う経路にだけ残す |
| **台帳を生成物にする**（S1） | miyagawa-ai はスキル台帳ではなく Capability / Worker 構成。台帳という対象自体が無い。ただし原則「同じ事実を2箇所に書かない」は `config hash` / `prompt hash` / `model digest` の固定として既に実現されている |
| **plan revision を追記ログにする**（S3） | FastAPI を唯一の受付口にし、Capability Policy から Worker 側がモデルと template を決める構造の方が強い。plan_log は不要 |
| **対話経路とバッチ経路の parity**（M5） | 入口が FastAPI 1つなら、そもそも2経路にならない。**ただし条件付き** — Claude Code のセッションから同じ Memory DB / Artifact を直接触れる経路があるなら、そこは FastAPI の保証の外側なので、parity の問題は形を変えて残る（下の D2） |
| **`fact-check-guard` をメタスキルにする** | A4 のとおり、構造検証を通常コードでやる方が安く決定的。LLM に LLM を検査させない |

---

## D. どちらにも見当たらないもの

### D1. 入力トークンの回帰と、外部 API 経路のキャッシュ階層

バンドルには `tokens_measured` と文字数代理値の分離があり、これは正しい。その上で:

- **入力トークンの黄金値回帰**（プロンプトが知らぬ間に肥大していないか）の記載がない。
  モデルを呼ばずにトークンを数えるだけなので安く、決定的に測れる
- 外部 API を使う経路があるなら、**キャッシュ階層**（通常入力 / キャッシュ書込 / キャッシュ読出）を
  分けて記録しないと、コストが実態と乖離し、キャッシュ最適化の効果も測れない

### D2. Claude Code セッションからの直接アクセス

FastAPI が唯一の受付口という保証は、**Claude Code が同じマシンで Memory DB や
Artifact Store を直接読み書きできる場合に破れる**。実際、私はいまこのセッションで
ローカルの状態を知らずに設計を書いていた。

- Claude Code のセッションが触れる範囲を、FastAPI 経由に限定するか、
  Hooks で同じポリシーを通すかを決める必要がある
- ここは `origin-ai/adapters/claude_code/hook_adapter.py` の考え方が使える
  （判定は1箇所に置き、Hooks は薄いアダプタにする）

---

## E. 推奨アクション

1. **`origin-ai` を新規プラットフォームとして進めない。** `docs/original-ai/` は
   miyagawa-ai への移植元・参照として残す
2. **B1（承認の内容束縛）を miyagawa-ai に入れる。** 単独で完結し、いま無いなら
   実損に直結する穴。`origin-ai/policy/approvals.py` をそのまま持っていける
3. **B2（fail-closed の明文化と回帰テスト）を入れる。** 監査の Track D / E で
   「判定器が壊れたときどうなるか」を1問として立てる
4. **B3（Read Timeout 後の Journal 照会）をバンドルの Step 5 に組み込む**
5. **B4 と D2 は確認から。** 既に満たしていれば作業ゼロ
6. **バンドルの Step 1（総合監査）→ Step 2（Recall 中核）の順序は変えない。**
   これは正しい順序で、私の v0.2 のロードマップより優先度判断が適切
