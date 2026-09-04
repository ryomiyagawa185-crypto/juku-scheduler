---
name: mac-neural-grid-builder
description: 複数の Mac を「計算ノード」として安全に統括する分散 AI ジョブ実行 CLI「mac-neural-grid」を設計・構築・テスト・保守するためのビルダースキル。単なる SSH ラッパーではなく、ノード発見/登録・能力台帳・ジョブ分割・能力ベース配置・SSH(将来)/localhost 配送・実行隔離・成果物 checksum 回収・失敗分類と再試行・監査・ロールバック・AI モデルルーティング（機密は外部 API 不使用）・冪等・SQLite(append-only events) を備える。MVP は手動ノード登録型のタスク並列/データ並列で、自動発見・常駐 Worker・複数 AI 審議・モデル分割は基盤安定後に足す。「複数台 Mac を連携する AI CLI を作って」「Mac をクラスタにして分散処理」「mac-neural-grid を構築/改修/テスト」等で使用する。【重要】複数 Mac の RAM/GPU を一つに融合するとは主張しない（各 Mac は独立ノード）。他 Mac への SSH・鍵操作・Worker 配布・launchd 登録・Homebrew 導入・外部 API 呼出し・sudo・リモート実行は明示承認まで自動実行しない。【委譲】単一 Mac の GUI/純正アプリ操作は mac-orchestrator、複数 Mac の汎用 SSH 統合運用は mac-cluster-orchestrator、macOS 自動化レシピは mac-renkei、Codex への実装外注は codex-conductor-jp へ。本スキルは分散 AI ジョブ CLI という独立プロダクトの設計・実装・検収を担う。
when_to_use: "mac-neural-grid、複数Macを連携するAI CLI、Macクラスタで分散処理、ノードにジョブ配布、能力ベースでMac選定、分散ジョブ実行基盤を構築/改修/テスト、Worker常駐設計、@neural-grid、@mng-builder"
argument-hint: "[design|build|test|inspect|deploy-plan|review] 対象や要件"
user-invocable: true
compatibility: "Claude Code。設計対象 CLI は Python 3.11（標準ライブラリ + PyYAML）。実行対象は macOS/zsh/Apple Silicon 中心。ビルダー自体はクロスプラットフォームで localhost 検証可能。"
metadata:
  version: "1.0.0"
  builds: "mac-neural-grid (>=0.1.0)"
  author: 宮川涼
---

# mac-neural-grid-builder — 分散 AI ジョブ CLI の設計・構築・保守

## 1. Mission

複数の Mac を **独立した計算ノード** として安全に統括する分散 AI ジョブ実行 CLI
`mac-neural-grid` を、設計 → 実装 → テスト → 保守する。**単なる SSH ラッパーではない**:
ノード能力台帳・ジョブ分割・能力ベース配置・実行隔離・成果物 checksum 回収・失敗復旧・監査・
AI モデルルーティング・冪等・append-only イベントを備えた基盤を作る。

**誇張の禁止**: 「複数 Mac を一つの巨大な GPU に結合した」等、実現していないことを主張しない。
複数 Mac の RAM/GPU は自動融合しない。分散推論は データ並列 / タスク並列 / パイプライン並列 /
モデル並列 / 複数モデル協調 / 投票・審議 を区別し、**MVP はタスク並列とデータ並列を優先**する。

## 2. 成果物の配置

- CLI 本体: `~/Projects/mac-neural-grid/`（本リポジトリでは `mac-neural-grid/`）。
- 本スキル: `~/.claude/skills/mac-neural-grid-builder/`。
- 可変状態は本体と分離: `~/Library/Application Support/mac-neural-grid/`（`$MNG_HOME`）。

## 3. 起動条件と自動実行の境界（§36）

このスキルは設計・実装・検収を助ける。**今回自動実行してよいのは**: ローカルの読取専用調査・
プロジェクト作成・新規コード・localhost テスト Worker・テスト用 SQLite・副作用のない単体テスト・
localhost 統合テスト・ドキュメント/Skill 作成。

**明示承認なしに実行しない**: 他 Mac への SSH・SSH 鍵生成/変更・known_hosts 変更・Worker 配布・
launchd 登録・Homebrew 導入・外部 AI API 呼出し・外部送信・sudo・ファイアウォール変更・
リモートコマンド/転送・複数 Mac への設定変更。

## 4. 基本アーキテクチャ

```
Control Node (CLI) → Scheduler(能力ベース) → Dispatcher → Worker Agents(実行隔離) → Executors → Artifacts/Results
                             ↑ Policy / Model Router / Health / Retry / Audit / SQLite(append-only events)
```

- **Control Node**: CLI 受付・自然言語の構造化・ノード/ジョブ台帳・スケジューリング・ポリシー判定・
  状態表示・ログ集約・成果物管理。
- **Worker Node**: 能力報告・許可ジョブのみ受信・作業ディレクトリ作成・実行・ログ/成果物返送・
  タイムアウト/中断対応・一時データの安全削除。
- **Executor**: 実行方法を抽象化（shell/python/claude-code/local-llm/external-api/ffmpeg/ocr/
  document/custom）。決定的処理（checksum・変換）は AI に任せない。

詳細は `references/`（architecture / node-discovery / scheduler / job-protocol / ai-routing /
artifact-transfer / security-model / observability / deployment / failure-recovery）。

## 5. スケジューラ（非ラウンドロビン・§11）

```
node_score = capability_match × availability × trust × locality × historical_reliability
             − resource_pressure − network_cost
```
生の CPU 速度だけで選ばない。要件（arch/memory/tools/models/labels）未充足は除外。高温・
バッテリー低下・電源未接続・逼迫ノードには割り当てない（health ゲート）。

## 6. ジョブモデル・冪等（§10/§22）

Job ⊃ Task（＋ Aggregation）。per-file/per-item でデータ並列に分割。すべてに一意 ID
（job_id/task_id/attempt_id/idempotency_key/input_hash/policy_hash）を付け、同一ジョブの再送で
二重実行しない。正本は append-only events で、状態はそこから再構築可能。

## 7. AI モデルルーター（§12）

機密性・容量・精度・速度・コスト・ネットワーク可否・ローカル能力・種別・再現性・外部送信許可で
実行方法を選ぶ。**機密文書は明示許可が無い限り外部 AI API を使わない**。数値処理・変換・checksum は
決定的ツールを優先。複数モデル協調では「一致＝正しい」としない・独立性のない多数決を強い証拠にしない。

## 8. 安全モデル（§15/§17/§29/§30）

- リスク分類 read_only / reversible / high_risk。high_risk（削除・上書き・外部送信・権限・sudo・
  launchd・複数 Mac 一括変更・認証情報）は対象/件数/容量/不可逆性/ロールバック/予定コマンドを提示し
  **明示承認**を得る。
- argv 配列実行（`shell=True`/eval/未引用変数/`curl|bash`/無検証 sudo を禁止）・executor/command
  allowlist・作業ディレクトリ制限・timeout・出力上限。
- SSH 鍵・host 鍵確認・最小権限・ノード信頼レベル・payload_hash・schema 検証・path traversal/symlink
  防止・原子的書込(0600/0700)・秘密値の非表示・外部送信制御・監査ログ・cancel・timeout・rollback。
- **ノードからの出力も未信頼入力として検証**する。
- 秘密値（API キー/パスワード/鍵/Cookie/トークン/.env/個人情報/法務/生徒/顧客/医療）を CLI 引数・
  ログ・JSON に平文保存しない。必要なら Keychain。ノード間で秘密値を複製しない。

## 9. 実行隔離・成果物（§16/§20）

各タスクは専用ディレクトリ `.../jobs/JOB/TASK/{input,work,output,logs,manifest.json,result.json}` で
実行。元ファイルを直接変更しない（作業コピー）。成果物は **一時名 → checksum 確認 → 原子的改名**。

## 10. 失敗処理・復旧（§21/§31）

状態 pending→…→succeeded/failed/retrying/cancelled/timed_out/lost/quarantined。失敗を分類
（transient/resource_exhaustion/node_offline/invalid_input/permission_denied/dependency_missing/
policy_denied/deterministic_failure/unknown）し、**再試行可能なものだけ**別ノードで再実行。同じ失敗を
無限に繰り返さない。Control 再起動後に events から状態復元。

## 11. デプロイ（canary・§28/§32）

Worker 常駐はユーザー単位 LaunchAgent（絶対パス・明示環境変数・plutil 検証・無効化手順）。
新 Worker/設定/スクリプトは **1台で canary → 検証 → 少数 → 検証 → 全体**。10 台へ一度に変更しない。

## 12. 実装手順（§35）と MVP（§34）

1 ローカル読取調査 → 2 CLI 名衝突確認 → 3 対象 Mac/ネットワーク整理 → 4 脅威モデル → 5 MVP 設計 →
6 JSON Schema → 7 Control 実装 → 8 localhost Worker → 9 SQLite → 10 配送 → 11 回収 → 12 失敗処理 →
13 セキュリティ検査 → 14 1台統合テスト → 15 2台目 canary → 16 複数台テスト → 17 文書 → 18 Skill →
19 回帰 → 20 ロールバック検証。**Phase 1** = Python CLI・SQLite・手動登録・SSH 接続・capability 調査・
read-only ジョブ・1ファイル並列・ログ・checksum・retry・cancel・localhost 統合。Phase 2 = 常駐/launchd・
NL ジョブ生成・モデルルーター・機密ポリシー・dashboard。Phase 3 = 複数 AI 協調・自動負荷分散・
自己申告・成果物キャッシュ・分散イベント・TUI。

## 13. 検証（§33/§37）

`pytest`（unit/integration/security/failure/privacy）。受け入れ: `doctor / node list /
node inspect localhost / job plan / job run / job status / logs / verify` が localhost で動作し、
複数 Worker を模擬した統合試験が通ること。テスト観点は `tests/*.md`。

## 14. スキル連携（設計上の要点）

```
brain-cognitive-architecture-jp（何をどう考えるか：目標・注意・記憶・方針決定）
        ↓
mac-neural-grid（どの Mac でどう実行するか：選定・分割・配送・統合）
        ↓
skill-synapse-jp（実績から構成改善候補を探す：どのスキル/ノードが有効だったか観測）
```

## 15. References / Constitution / Schemas / Scripts

- `constitution/SECURITY.md` `DISTRIBUTED_EXECUTION.md` `PRIVACY.md`
- `references/*.md`（10 本）／`schemas/*.json`（6 種）
- `scripts/inspect-node.zsh`（能力調査・読取専用）・`bootstrap-node.zsh`（登録前チェック）・
  `validate-environment.zsh`・`validate-skill.zsh`
- `tests/*.md`（architecture / security / failure / multi-node の観点表）
