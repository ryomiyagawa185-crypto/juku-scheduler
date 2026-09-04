# miyagawa-ai 設計レビュー用ドキュメント

**配置先:** `ronshocho/miyagawa-ai/docs/DESIGN-FOR-REVIEW.md`
**版:** v1.0（レビュー用）
**作成日:** 2026-08-04
**正本:** `miyagawa_ai_advice_bundle`（稼働中の方針・20ファイル）
**目的:** ロードマップ Step 1「総合監査」の入力として、設計を1枚に集約し、
未検証項目と未解決の設計事項を明示する

---

## このドキュメントの使い方

### 状態語彙

各コンポーネントの `status` は次から選ぶ。**既定は `UNVERIFIED`。**

| 値 | 意味 |
|---|---|
| `OPERATED` | 実運用で使っている |
| `TESTED` | テストがあり通っている |
| `IMPLEMENTED` | 実装はあるがテストが無い |
| `PARTIAL` | 一部だけ実装 |
| `PLANNED_ONLY` | 構想のみ |
| `NOT_FOUND` | 探したが見つからない |
| `UNVERIFIED` | **未確認（本書の初期値）** |
| `DEPRECATED` | 廃止予定 |
| `ORPHANED` | 呼び出し元が無い |

> **重要:** 本書の status 欄は全て `UNVERIFIED` から始まる。
> 本書の作成者はコードを確認していないため、実装状況を記載できない。
> 監査の Phase 1（現状採取）で埋めること。
> 中核原則「実装済み・テスト済み・実運用済み・構想のみを混同しない」の適用対象は本書自身でもある。

### レビューの進め方

1. §2 の表の status を埋める（Phase 1）
2. §4 の不変条件それぞれについて、破れる経路が無いか検証する（Phase 3）
3. §9 の未解決事項に答えを出す（Phase 4）
4. §10 の Baseline を固定し、§11 の様式で判定する（Phase 5）

---

## 0. レビュー範囲

### 範囲

- Control Plane / Worker / Recall / Memory / Document RAG / Artifact / Shadow・Canary
- Trace・費用・評価
- Security / Privacy / Supply Chain / Backup・DR

### 非範囲（今回は判定しない）

- Vector DB / Embedding
- Temporal / Kubernetes
- 自動 Memory 登録
- `code.generate` と自動 Patch 適用
- R4 の自動化

---

## 1. 設計原則（正本）

```text
実装済み・テスト済み・実運用済み・構想のみを混同しない
一度に直す Issue は原則1件
修正前に失敗する再現テストを作る
Recall / Memory / Document RAG / Artifact / Trace の正本を分離する
no_match と ambiguous ではモデルを呼ばない
外部 fallback、Memory DB 書込み、R4 操作は明示的に制御する
モデル名ではなく digest、Prompt は hash、設定は version で固定する
本番回答と Shadow 回答を混ぜない
AI へ任意モデル・任意 Prompt・任意 Tool・任意 Shell を選ばせない
回答・Claim・Citation・Memory ID を型付き Schema で検証する
バックアップの存在ではなく、復元成功を確認する
```

### 開発サイクル

```text
作る → 使う → 測る → Issue化 → 1件だけ直す
→ 回帰テストへ追加 → 限定運用 → 閉じる
```

---

## 2. コンポーネント状態表

> **status 欄は Phase 1 で埋める。空欄・推測での記入は不可。**

### 2.1 Control Plane / Worker

| # | コンポーネント | 期待される姿 | status | 根拠（ファイル:行 / テスト名） |
|---|---|---|---|---|
| CP-1 | FastAPI 受付口 | 唯一の受付口である | `UNVERIFIED` | |
| CP-2 | Pydantic Schema | `AskRequest` / `AskResponse` / `RecallResult` が固定 | `UNVERIFIED` | |
| CP-3 | Provider Adapter | モデル呼び出しは必ず経由する | `UNVERIFIED` | |
| CP-4 | Trace 記録 | original_text 全文を保存しない | `UNVERIFIED` | |
| W-1 | Ollama bind | `127.0.0.1:11434` のみ。LAN 非公開 | `UNVERIFIED` | |
| W-2 | Tailscale Serve | Worker Agent だけ公開。Funnel 不使用 | `UNVERIFIED` | |
| W-3 | Bearer Token | Control → Worker の認証 | `UNVERIFIED` | |
| W-4 | capability 決定 | モデル・template は **Worker 側**が決める | `UNVERIFIED` | |
| W-5 | 起動時検証 | 指定モデル未存在なら**起動失敗** | `UNVERIFIED` | |

### 2.2 Recall / Memory

| # | コンポーネント | 期待される姿 | status | 根拠 |
|---|---|---|---|---|
| R-1 | 正規化 | NFKC → casefold → 空白正規化 → compact 版 | `UNVERIFIED` | |
| R-2 | 照合 | 完全一致 → 部分一致 → 文字 bi-gram → tri-gram | `UNVERIFIED` | |
| R-3 | scope filter | **ranking 前**に適用 | `UNVERIFIED` | |
| R-4 | 判定 | `top1 < minimum_score → no_match` / `top1-top2 < minimum_margin → ambiguous` | `UNVERIFIED` | |
| R-5 | no_match 挙動 | 一般知識で補完しない。**モデルを呼ばない** | `UNVERIFIED` | |
| R-6 | ambiguous 挙動 | 一件へ勝手に確定しない。**モデルを呼ばない** | `UNVERIFIED` | |
| R-7 | Trace | selected Memory ID を残す | `UNVERIFIED` | |
| M-1 | 登録ゲート | 必須13項目（下記）を満たさないと登録不可 | `UNVERIFIED` | |
| M-2 | assertion_status | `verified` のみ自動注入可 | `UNVERIFIED` | |
| M-3 | model_inference | 通常 Recall へ入れない | `UNVERIFIED` | |
| M-4 | 隔離 | source_ref なし / subject 不明 / scope 不明は quarantined | `UNVERIFIED` | |

Memory 必須項目:

```text
memory_id / scope / kind / subject_id / original_text / source_ref
assertion_status / valid_from / valid_to / sensitivity
created_by / created_at / original_text_hash
```

assertion_status の値域:

```text
verified / user_asserted / model_summary / model_inference
legacy_unverified / quarantined / expired / superseded
```

### 2.3 Document RAG

| # | コンポーネント | 期待される姿 | status | 根拠 |
|---|---|---|---|---|
| D-1 | 正本分離 | 原本 Artifact が正本。parsed JSON と Chunk は派生 | `UNVERIFIED` | |
| D-2 | DB 分離 | Memory DB と Document RAG DB が別 | `UNVERIFIED` | |
| D-3 | Version | immutable。古い版は削除せず `active=0` | `UNVERIFIED` | |
| D-4 | 検索対象 | current version のみ | `UNVERIFIED` | |
| D-5 | 日本語検索 | FTS5 trigram。3文字未満は substring fallback | `UNVERIFIED` | |
| D-6 | 再順位付け | bigram / trigram / heading / substring / reciprocal rank | `UNVERIFIED` | |
| D-7 | Citation | 9項目（citation_id 〜 heading_path）を保持 | `UNVERIFIED` | |
| D-8 | 禁止事項 | 外部 Embedding API / 自動 OCR / 自動 Memory 登録 / 全事業横断検索 が無いこと | `UNVERIFIED` | |

### 2.4 Artifact Plane

| # | コンポーネント | 期待される姿 | status | 根拠 |
|---|---|---|---|---|
| A-1 | Artifact ID | SHA-256。filename を保存パスに使わない | `UNVERIFIED` | |
| A-2 | CAS | Content-Addressed Storage | `UNVERIFIED` | |
| A-3 | Token 分離 | Read Token と Write Token が別 | `UNVERIFIED` | |
| A-4 | 取得制限 | Worker は任意 URL を取得しない | `UNVERIFIED` | |
| A-5 | 再検証 | ダウンロード後に size / hash を再検証 | `UNVERIFIED` | |
| A-6 | Trace | Artifact 本文を通常 Trace へ保存しない | `UNVERIFIED` | |
| A-7 | code.review 隔離 | network none / rootfs read-only / cap-drop ALL / no-new-privileges / pids・memory・cpu 制限 / Docker socket 禁止 / `shell=True` 禁止 / Secret なし | `UNVERIFIED` | |
| A-8 | document.parse | Docling local only / OCR 既定無効 / `external_calls = 0` | `UNVERIFIED` | |
| A-9 | 分離 | `code.review`（読取専用）と `code.generate`（未実施）が分離 | `UNVERIFIED` | |

### 2.5 分散実行・Shadow / Canary

| # | コンポーネント | 期待される姿 | status | 根拠 |
|---|---|---|---|---|
| F-1 | Worker Journal | `running / completed / failed / interrupted` | `UNVERIFIED` | |
| F-2 | Heartbeat | 5秒間隔・20秒で stale | `UNVERIFIED` | |
| F-3 | Drain | `active / draining / disabled`。state file 破損時は disabled | `UNVERIFIED` | |
| F-4 | Job Lease | 多重実行の防止 | `UNVERIFIED` | |
| F-5 | 再送分類 | 「通信失敗 ≠ 実行失敗」を実装（§4 INV-6） | `UNVERIFIED` | |
| F-6 | ID 体系 | `job_id` / `attempt_id` / `idempotency_key` の3層 | `UNVERIFIED` | |
| S-1 | Shadow 分離 | Shadow 結果を利用者へ返さない | `UNVERIFIED` | |
| S-2 | 決定論的割当 | `SHA-256(job_id + policy_version + purpose)` → bucket 0-99 | `UNVERIFIED` | |
| S-3 | 昇格 | 5% → 20% → 50% → 100% | `UNVERIFIED` | |
| S-4 | ロールバック | 絶対条件違反1件で Canary 0% | `UNVERIFIED` | |
| S-5 | GroundedAnswer 検証 | 未許可 Memory ID / 根拠なし Claim / claims と used_memory_ids の不一致を**通常コードで**検出 | `UNVERIFIED` | |

### 2.6 Security / Privacy / Operations

| # | コンポーネント | 期待される姿 | status | 根拠 |
|---|---|---|---|---|
| SEC-1 | Trust Boundary | `interactive / eval / evolve / commit` の4境界 | `UNVERIFIED` | |
| SEC-2 | Commit Gateway | R4 外部作用は**ここだけ**が実行 | `UNVERIFIED` | |
| SEC-3 | Tool 権限表 | Read/Write/Delete/External/Approval/Secret/Risk/Owner を全 Tool に登録 | `UNVERIFIED` | |
| SEC-4 | Injection 前提 | メール/PDF/DOCX/Web/Git/MCP/Tool結果/**Memory**/OCR/**Model出力** を未信頼扱い | `UNVERIFIED` | |
| SEC-5 | Secret 保管 | macOS Keychain | `UNVERIFIED` | |
| SEC-6 | Secret 走査 | Git履歴/.env/Shell履歴/Trace/Artifact/Fixture/Screenshot/Docker/LaunchAgent | `UNVERIFIED` | |
| SEC-7 | 供給網固定 | `latest` 禁止 / Docker digest 固定 / Model digest 固定 / UNKNOWN license は保留 | `UNVERIFIED` | |
| OPS-1 | Trace 項目 | §6 の全項目 | `UNVERIFIED` | |
| OPS-2 | Backup 対象 | Memory DB / RAG DB / Task DB / Journal / Artifact / Prompt / Config / Eval / Audit / Git | `UNVERIFIED` | |
| OPS-3 | **復元検証** | バックアップの存在ではなく**復元成功**を確認済み | `UNVERIFIED` | |
| OPS-4 | RPO / RTO | 数値が定義され、実測で満たしている | `UNVERIFIED` | |

---

## 3. アーキテクチャ

### 3.1 処理の流れ

```text
質問
 → Control Plane（FastAPI・唯一の受付口）
 → Recall（正規化 → scope filter → 照合 → 判定）
 → no_match / ambiguous ならここで終了（モデルを呼ばない）
 → Provider Adapter
 → Worker（Ollama / capability から Worker 側がモデルと template を決定）
 → Structured Output（GroundedAnswer / CitedAnswer）
 → 通常コードによる構造検証
 → Trace
 → Evaluation
 → Backup
```

### 3.2 正本の分離

```text
Memory DB          … 人・事業に関する記憶の正本
Document RAG DB    … 文書由来。Memory DB とは別 DB
Artifact Store     … 原本の正本（SHA-256 で content-addressed）
Trace              … 実行記録。本文と秘密値は入れない
```

派生物（parsed JSON / Chunk / FTS5 Index）は再構築可能なものとして扱い、正本と混同しない。

### 3.3 Trust Boundary

```text
interactive ─┐
eval        ─┼─→ 読み取り・評価のみ
evolve      ─┘
commit      ───→ Commit Gateway のみが R4 外部作用を実行
```

---

## 4. 不変条件

**違反が見つかったら止める。レビューではそれぞれについて「破れる経路が無いこと」を示す。**

| # | 不変条件 | 検証方法 |
|---|---|---|
| INV-1 | `no_match` / `ambiguous` でモデルを呼ばない | Golden Path 3・Trace の model call 数 |
| INV-2 | 別 scope の記憶を Candidate へ入れない | Golden Path 4 |
| INV-3 | `verified` 以外の Memory を自動注入しない | 登録ゲートのテスト |
| INV-4 | local 障害時に外部 fallback しない | Golden Path 5 |
| INV-5 | Shadow 結果を利用者へ返さない | S-1 の経路検査 |
| INV-6 | **通信失敗 ≠ 実行失敗** — 下表の分類に従う | 障害注入テスト |
| INV-7 | Trace に本文全文・秘密値を保存しない | Trace の schema 検査 ＋ 秘密走査 |
| INV-8 | AI に任意モデル・任意 Prompt・任意 Tool・任意 Shell を選ばせない | Control → Worker の payload 検査 |
| INV-9 | 回答・Claim・Citation・Memory ID を型付き Schema で検証する | S-5 |
| INV-10 | **判定器自身が結論を出せない場合は拒否する** | §9 Q2（未解決） |

### INV-6 の再送分類

| 事象 | 再送 |
|---|---|
| Connect Error | 可 |
| Connect Timeout | 可 |
| 処理前 429 | 可 |
| Drain 中 423 | 可 |
| **Read Timeout** | **不可** |
| 状態照会不能 | 不可 |
| SIDE_EFFECT を持つ Job | 不可 |
| 実行開始が不明な 5xx | 不可 |

「不可」の場合は自動再送せず、**Worker Journal への状態照会が成功してから**判断する
（`running` なら待つ / `interrupted` なら人間へ）。

---

## 5. 評価と絶対条件

### 5.1 20問 実利用受入試験

分類:

```text
A：そのまま使える
B：軽微修正
C：大幅修正
D：誤情報・別人・根拠なし
N：no_match が妥当
```

**絶対条件（1件でも違反したら不合格。平均点で埋めない）:**

```text
D                 = 0
wrong_subject     = 0
cross_scope       = 0
unsupported_fact  = 0
external_fallback = 0
memory_db_write   = 0
```

品質条件:

```text
A または B >= 15/20
no_match 問題 2/2
v1 rollback 成功
```

### 5.2 FailureReason

```text
ENTITY_NOT_RESOLVED / ENTITY_WRONG / SCOPE_WRONG
RETRIEVAL_MISS / RETRIEVAL_WRONG / STALE_MEMORY
CONTEXT_OMISSION / GENERATION_OMISSION / UNSUPPORTED_CLAIM
UX_PROBLEM / PERFORMANCE
```

優先順位: `priority_score = safety_weight + impact × frequency`

```text
ENTITY_WRONG      safety_weight 100
SCOPE_WRONG       100
UNSUPPORTED_CLAIM  80
STALE_MEMORY       40
```

### 5.3 Issue ライフサイクル

```text
OPEN → TRIAGED → IN_PROGRESS → FIXED → VERIFIED → REGRESSION_ADDED → CLOSED
```

---

## 6. Trace 記録項目

```text
trace_id / task_id / job_id / attempt_id
scope / retriever_version
model requested / resolved / digest
prompt_hash / memory_snapshot_hash
selected Memory IDs / selected Citation IDs
Tool / approval
latency / usage / failure reason
```

**保存しないもの:** 本文全文・秘密値・original_text 全文・Artifact 本文

---

## 7. Baseline 固定項目

比較の基準として、監査完了時に次を固定して記録する。

```text
HEAD SHA
dependency lock hash
config hash
Prompt hash
model name / digest
retriever version
Memory snapshot hash
evaluation suite hash
test result hash
```

---

## 8. Golden Path

| # | 経路 | 期待 |
|---|---|---|
| GP-1 | 既知記憶 | 正しい Memory が選ばれ、Citation が付く |
| GP-2 | 曖昧人物 | `ambiguous` を返し、**モデルを呼ばない** |
| GP-3 | no_match | `no_match` を返し、一般知識で補完しない |
| GP-4 | scope 越境防止 | 別 scope の記憶が Candidate に入らない |
| GP-5 | local 障害 | 外部 fallback せずに失敗する |
| GP-6 | **承認の迂回不能性**（§9 Q7 で追加） | アクセシビリティ権限を持つプロセスから、Commit Gateway の承認を通さずに R4 外部作用へ到達できない |

---

## 9. 未解決の設計事項（レビューで答えを出す）

> 以下は稼働方針の文書群に**記載が見つからなかった**もの。実装済みであれば
> 該当箇所を示して閉じる。未実装であれば対応方針を決める。

### Q1. 承認は「何に対する」承認か（最優先）

Tool 権限表に `Approval` 欄があり、R4 は Commit Gateway が実行する。
しかし承認が**内容に束縛されているか**が不明。

**塞ぐべき穴:**

```text
ドラフト A を見て送信を承認
 → 再生成で内容が B に変わる
 → 承認済みフラグだけが残って B が送信される
```

**推奨:** 承認レコードに `target_hash`（承認時点の入力＋本文の正規化ハッシュ）を持たせ、
実行直前に再計算して不一致なら失効させる。既定は one-shot・期限つき。
破壊的操作と法的提出物には「今後すべて許可」を作らない。

**相性:** Artifact が既に SHA-256 で content-addressed なので、その ID をそのまま
`target_hash` に使える。新しい仕組みを足す必要は小さい。

- [ ] 実装済み → 該当箇所: ______
- [ ] 未実装 → 対応: ______

### Q2. 判定器自身が壊れたときどうなるか（INV-10）

「指定モデル未存在なら起動失敗」は fail-closed。一方、**権限チェック・承認照会・
容量照会を行う側**が例外を出した／ストアが読めない場合の既定が不明。

**塞ぐべき穴:** 例外を握りつぶして通す実装だと、安全機構が沈黙して無効化されたことに
誰も気づけない。

**推奨:** 判定が結論を出せない場合は必ず拒否する（fail-closed）ことを明文化し、
「ストアを壊した状態で高リスク操作が通らないこと」を回帰テストにする。

- [ ] 実装済み → 該当箇所: ______
- [ ] 未実装 → 対応: ______

### Q3. Read Timeout 後の Journal 照会は自動化されているか

INV-6 の分類は正しい。その上で、「不可」に分類された後の**実際の手順**
（Journal 照会 → `running` なら待つ / `interrupted` なら人間へ）が
コードとして存在するか、運用手順に留まっているか。

- [ ] 実装済み → 該当箇所: ______
- [ ] 未実装 → 対応: ______

### Q4. sensitivity と外部同期境界の対応

`sensitivity` は Artifact と Memory にあり、scope filter もある。
不明なのは「**どの sensitivity がどこに置かれ、どれが外部同期されるか**」。

事件記録や生徒データが Dropbox 等に同期される経路があると、
分類フィールドがあっても実効性が無い。

- [ ] 分離済み → 同期対象: ______ / 非同期対象: ______
- [ ] 未整理 → 対応: ______

### Q5. Claude Code セッションからの直接アクセス

「FastAPI が唯一の受付口」という保証は、**Claude Code が同じ Mac から
Memory DB / Artifact Store / Trace を直接読み書きできる場合に破れる**。

> **2026-08-05 追記: 実質的に答えが出ている。** Q7 のとおり、Claude を含む複数のアプリに
> アクセシビリティ権限（コンピュータの制御）が付与されている。この権限を持つプロセスは
> ターミナルへキー入力を送れるため、FastAPI を経由せずファイルへ到達できる。
> したがって「FastAPI が唯一の受付口」は **アプリ層の設計上の性質であって、
> OS 層で強制されているものではない**。Q7 とあわせて扱うこと。

- [ ] 直接アクセス不可 → 根拠: ______
- [x] 可能 → 対応（FastAPI 経由に限定 / Hooks で同じポリシーを通す）: ______

### Q7. OS レイヤの権限付与が Trust Boundary を迂回する

**観測（2026-08-05・システム設定のスクリーンショットより）**

| 権限 | 許可されているアプリ |
|---|---|
| アクセシビリティ<br>（コンピュータの制御） | BetterSnapTool / Canva / ChatGPT / claude / Claude / Codex Computer Use / Dropbox / Genspark Claw / Google Chrome / LINE / Microsoft Excel / Microsoft Word / Notepad / Safari / Sider / zoom.us / スクリプトエディタ（AEServer は無効） |
| 画面収録とシステムオーディオ録音 | ChatGPT / claude / Claude / Google Chrome / LINE / Sider / TapRecord / zoom.us（ターミナルは無効） |

**なぜ設計上の問題か**

設計では R4 外部作用を Commit Gateway だけが実行することになっている（SEC-2）。
しかしこれはアプリ層の取り決めであり、OS 層では次が成立する。

1. **アクセシビリティ権限は、他アプリへのキー入力・クリックの合成を許す。**
   ターミナルの画面収録が無効でも、アクセシビリティを持つプロセスは
   **ターミナルへ入力を送れる**ので、そこからファイルにも DB にも到達できる。
   実質的に「ユーザー権限でのコード実行」と同等と見なすのが安全側。
2. **アプリ層の承認 UI は合成イベントから保護されない。** macOS の TCC 同意ダイアログは
   合成クリックに対して保護されているが、**自作の承認画面（Commit Gateway の承認ボタン、
   Chainlit の承認 UI）は保護対象外**。承認を自動でクリックされ得る。
3. **画面収録は、設計上の秘匿区分をまたぐ経路になる。** Trace に本文を書かず、
   sensitivity で保存先を分けても、**画面に表示された事件記録や生徒情報は
   画面収録権限を持つアプリから読める**。11 章の Network 対策（Ollama を LAN 非公開等）は
   この経路を塞がない。
4. **権限を持つアプリの多くが、未信頼データを読む agent である。**
   ChatGPT / Claude / Codex Computer Use / Genspark Claw / Sider は、Web・PDF・メールを
   読んで動く。§SEC-4 で「Web / PDF / Model 出力は未信頼」と定めている当の入力が、
   コンピュータ制御権限を持つプロセスに入っていく。
   Prompt Injection が成立した場合の到達範囲が、そのままこの権限の範囲になる。

**確認項目**

| # | 項目 | 判定 |
|---|---|---|
| Q7-1 | `claude`（小文字・汎用アイコン）と `Claude`（Anthropic アイコン）の2エントリそれぞれについて、bundle ID と署名を特定する | |
| Q7-2 | アクセシビリティが**業務上必要な**アプリを列挙する（例: BetterSnapTool・Codex Computer Use・Sider） | |
| Q7-3 | 不要と判断したものを解除する（候補: Dropbox / Microsoft Excel / Microsoft Word / Canva / Notepad / LINE / zoom.us） | |
| Q7-4 | 画面収録が必要なアプリを列挙する（候補: zoom.us・TapRecord のみ） | |
| Q7-5 | 事件記録・生徒データを画面に出す作業中に、画面収録権限を持つ agent を動かさない運用にできるか | |
| Q7-6 | Commit Gateway の承認 UI が、合成イベントで押され得る形になっていないか（物理キー入力の確認・確認語の入力など、合成しにくい確認手段の採用可否） | |
| Q7-7 | 権限の棚卸しを月次 Architecture Review の定常項目にする | |

**評価への反映**

Golden Path に1本追加することを推奨する。

```text
GP-6：承認の迂回不能性
  アクセシビリティ権限を持つプロセスから、
  Commit Gateway の承認を通さずに R4 外部作用へ到達できないこと
```

- [ ] 対応済み → 内容: ______
- [ ] 未対応 → 是正計画: ______

### Q6. 入力トークンの回帰と、外部 API 経路のキャッシュ階層

`tokens_measured` と文字数代理値の分離は正しい。追加で不明なのは2点。

1. **入力トークンの黄金値回帰** — Prompt が知らぬ間に肥大していないかの検査。
   モデルを呼ばずに数えるだけなので安く決定的
2. **キャッシュ階層** — 外部 API を使う経路があるなら、通常入力 / キャッシュ書込 /
   キャッシュ読出を分けて記録しないと、コストが実態と乖離し最適化の効果も測れない

- [ ] 実装済み → 該当箇所: ______
- [ ] 未実装 → 対応: ______

---

## 10. 監査フェーズと判定様式

### フェーズ

```text
Phase 0：変更凍結
Phase 1：現状採取（§2 の status を埋める）
Phase 2：構造・実装監査
Phase 3：実行・安全性検証（§4 の不変条件）
Phase 4：設計と実装の照合（§9 の未解決事項）
Phase 5：是正計画と Baseline 確定（§7）
```

### トラック

```text
Track A：Product・業務適合性
Track B：Code・Architecture
Track C：Data・AI Quality
Track D：Security・Privacy・Legal
Track E：Operations・Resilience
```

### 判定

```text
BASELINE_ACCEPTED
BASELINE_ACCEPTED_WITH_CONDITIONS
BASELINE_REJECTED
```

軸別に判定し、**総合判定は最も低い軸に合わせる。**

| 軸 | 判定 | 条件 / 根拠 |
|---|---|---|
| Product | | |
| Quality | | |
| Security | | |
| Privacy | | |
| Operations | | |
| Maintainability | | |
| **総合** | | 最も低い軸に一致すること |

---

## 付録. 本書の限界

- 本書は稼働方針の文書群を正本に再構成したもので、**コードは確認していない**
- したがって §2 の status は全て `UNVERIFIED` であり、実装状況の主張ではない
- §9 の「記載が見つからなかった」は「実装に無い」ではない。既にあれば該当箇所を示して閉じる
- 本書自体も §1 の原則「実装済み・構想のみを混同しない」の適用対象である
