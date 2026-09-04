# Grok CLI 連携ガイド（juku-scheduler）

本リポジトリを **Grok CLI** から扱うための設定・使い方をまとめる。
記載内容は `@xai-official/grok` **v0.2.118**（2026-07-31 公開）を実際に実行して確認したもの。
未確認の項目には「未確認」と明記してある。

---

## 0. どの「Grok CLI」か

npm 上に紛らわしい 2 つが存在する。本ガイドは **前者（公式）** を対象とする。

| | パッケージ | 提供元 | 認証の環境変数 |
|---|---|---|---|
| 公式 | `@xai-official/grok` | xAI (`xai-security`) | `XAI_API_KEY` |
| 有志版 | `@vibe-kit/grok-cli` | コミュニティ | `GROK_API_KEY` |

有志版は 2025-11 の v0.0.34 で更新が止まっており、設定ファイルも `~/.grok/user-settings.json` と
別系統。取り違えると設定が一切効かないので、まず次で確認する。

```bash
grok --version
# → grok 0.2.118 (1e1687c1cf)   … 公式版
```

---

## 1. 導入

```bash
# 公式インストーラ
curl -fsSL https://x.ai/cli/install.sh | bash

# または npm
npm i -g @xai-official/grok
```

**対応プラットフォーム**（公式 README 記載）

| OS | アーキテクチャ |
|---|---|
| macOS | Apple Silicon (arm64) のみ |
| Linux | x86_64 / arm64 |
| Windows | x86_64 |

macOS の Intel 機は対応表に無い。

更新は `grok update`（npm 導入なら `npm i -g @xai-official/grok@latest`）。

---

## 2. 認証

3 通り。優先度の高い順ではなく、いずれか 1 つで成立する。

```bash
# A. ブラウザが使える端末
grok login

# B. ブラウザが無い端末・SSH 越し
grok login --device-code

# C. CI / ヘッドレス環境
export XAI_API_KEY="xai-..."      # キーは https://console.x.ai で発行
```

未認証で実行すると次のエラーで止まる（実測）。

```
Not signed in. To authenticate without a browser, run:
  grok login --device-code
```

資格情報は `~/.grok/auth.json` に保存される。**このファイルは絶対にコミットしない**
（本リポジトリの `.gitignore` で除外済み）。

---

## 3. モデル

```bash
grok models
# Default model: grok-4.5
# Available models:
#   * grok-4.5 (default)
```

未認証状態では `grok-4.5` のみが見える。認証後に選択肢が増えるかは未確認。
セッション単位の切替は `-m` / `--model`、思考量の調整は `--reasoning-effort`（別名 `--effort`）。

---

## 4. このリポジトリでの使い方

### 対話セッション

```bash
cd juku-scheduler
grok                                  # TUI を起動
grok "sw.js のキャッシュ版数を上げて"    # 初期プロンプト付きで起動
grok -c                               # 直近セッションを再開
grok -r                               # セッションを選んで再開
```

### ヘッドレス（1 ターンで終了）

```bash
grok -p "index.html の振替期限まわりのロジックを要約して"

# JSON で受け取る
grok -p "変更点を列挙して" --output-format json

# スキーマを固定して構造化出力
grok -p "TODO を抽出" --json-schema '{"type":"object","properties":{"todos":{"type":"array","items":{"type":"string"}}}}'
```

`--output-format` は `plain` / `json` / `streaming-json` / `streaming-messages-json` の 4 種。
`streaming-messages-json` は Anthropic Messages API のワイヤ形式の NDJSON なので、
既存の Claude 向けパイプラインにそのまま流し込める。

### 作業を隔離する

`index.html` は単一巨大ファイルで衝突しやすい。並行作業させるなら git worktree を使う。

```bash
grok --worktree=feat/furikae "振替期限の判定を直して"
```

### 権限

```bash
grok --permission-mode acceptEdits          # 編集は自動承認、コマンドは確認
grok --allow 'Bash(git status:*)' --deny 'Bash(rm -rf:*)'
grok --always-approve                       # 全自動。信頼できる作業だけに使う
```

`--permission-mode` に指定できる値：`default` / `acceptEdits` / `auto` / `dontAsk` /
`bypassPermissions` / `plan`。

> **未確認**: 権限ルールをファイルで永続化する経路は特定できていない。
> `.claude/settings.json`・`.grok/settings.json`・`~/.grok/config.toml` の
> `[permissions]` をそれぞれ試したが、いずれも `grok inspect` の
> `Permissions → Source: (none)` のままだった。当面はフラグ指定で運用する。

---

## 5. Claude の資産をそのまま使える

これが実務上いちばん大きい。`grok inspect` で確認した実測結果：

### 5-1. プロジェクト指示

Grok CLI はリポジトリ直下の **`CLAUDE.md` と `AGENTS.md` の両方**を
Project Instructions として読み込む。

```
Project Instructions (2)
└ /path/to/repo/CLAUDE.md (project, ~4 tokens)
└ /path/to/repo/AGENTS.md (project, ~4 tokens)
```

一方、`GROK.md` / `.grok/GROK.md` / `.grok/AGENTS.md` は **読まれない**（実測で確認）。
本リポジトリでは `AGENTS.md` を規約の正本としている。

### 5-2. スキル

`~/.claude/skills/` 配下のスキルをそのまま認識する。実機では 199 件が
`user [claude]` として列挙された。Grok 専用に置く場合は `.grok/skills/`。

### 5-3. その他の共有ディレクトリ

バイナリ内の参照から、以下が Grok / Claude 両系統で探索される。

| 用途 | Grok | Claude |
|---|---|---|
| スキル | `.grok/skills/` | `.claude/skills/` |
| サブエージェント | `.grok/agents/` | `.claude/agents/` |
| スラッシュコマンド | `.grok/commands/` | `.claude/commands/` |
| ルール | `.grok/rules/` | `.claude/rules/` |
| プラグイン | `.grok/plugins/` | `.claude/plugins/` |
| 設定 | `~/.grok/config.toml` | `.claude/settings.json` |

現状の設定がどう解決されているかは、常に次で確認できる。

```bash
grok inspect
```

---

## 6. 設定ファイル

ユーザー設定は `~/.grok/config.toml`（TOML）。バイナリ内に確認できたセクションは
`[ui]` `[models]` `[skills]` `[agent]` `[terminal]` `[cli]` `[mcp_servers]`
`[hooks.PreToolUse]` `[sandbox]` など。

```toml
[ui]
screen_mode = "minimal"   # 既定を scrollback ネイティブ描画にする

[cli]
use_leader = true         # 複数クライアントで 1 バックエンドを共有
```

`~/.grok/` 配下のその他のファイル：`auth.json`（資格情報）、`sessions/`、
`memory/MEMORY.md`（`--experimental-memory` 用）、`mcp_credentials.json`、
`sandbox.toml`、`leader.sock`。

主な環境変数：`XAI_API_KEY`、`GROK_HOME`、`GROK_SANDBOX`、`GROK_LOG_FILE`、
`GROK_MODELS_BASE_URL`、`GROK_EXTRA_CA_BUNDLE`。

---

## 7. MCP サーバー

```bash
grok mcp list
grok mcp add <name> ...
grok mcp doctor      # 接続診断
grok mcp enable / disable / remove
```

`~/.grok/config.toml` の `[mcp_servers.<name>]` としても定義できる。

---

## 8. 主なサブコマンド

| コマンド | 用途 |
|---|---|
| `grok inspect` | このディレクトリで解決される設定を表示（トラブル時はまずこれ） |
| `grok doctor` | 端末・クリップボード・色・入力の対応状況を診断 |
| `grok models` | 利用可能なモデル一覧 |
| `grok sessions` | セッションの一覧・検索・復元 |
| `grok export` | セッションを Markdown で書き出し |
| `grok worktree` | git worktree の管理 |
| `grok memory` | セッション横断メモリの管理 |
| `grok plugin` | プラグイン / マーケットプレイスの管理 |
| `grok update` | 更新確認・特定バージョンの導入 |
| `grok wrap <cmd>` | 任意コマンドを OSC 52 クリップボード対応で実行 |

---

## 9. 同梱スクリプト

`scripts/grok-review.sh` は、認証状態を確認したうえで
ヘッドレスモードでこのリポジトリに質問・レビューを投げるラッパー。

```bash
./scripts/grok-review.sh                       # 既定のレビュー観点で実行
./scripts/grok-review.sh "sw.js の版数は上がっている？"
./scripts/grok-review.sh --json "TODO を列挙して"
```

---

## 10. 注意

- `~/.grok/auth.json`、`.env`、`.grok/mcp_credentials.json` は機微情報。コミットしない
- 生徒名・保護者連絡先を含むデータをプロンプトに貼らない（外部 API に送信される）
- `--always-approve` / `--permission-mode bypassPermissions` は確認を全て飛ばす。
  本リポジトリは実運用中のアプリなので、常用しない
