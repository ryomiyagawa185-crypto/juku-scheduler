# mac-neural-grid

複数の Mac を **計算ノード** として安全に統括する、分散 AI ジョブ実行 CLI（MVP / Phase 1）。

> **これは何ではないか（誇張の否定）**: 複数 Mac の RAM/GPU を一つに融合する仕組みではない。
> 「複数 Mac を一つの巨大な GPU に結合した」とは主張しない。各 Mac を *独立ノード* として扱い、
> 能力ベースでジョブを分割・配置・監査・復旧する分散ジョブ実行基盤である。

## 現状（実装済み）

- 手動ノード登録（SSH host-key 確認を前提・`StrictHostKeyChecking=no` を禁止）
- 能力調査 `node inspect`（クロスプラットフォーム。macOS 重視で他 OS は graceful degradation）
- タスク並列 / データ並列（per-file 分割）
- **localhost の複数 Worker を実プロセス隔離で実行**（`local` transport）
- **SSH リモート配送（Phase 2）**: 入力ステージング → リモート Worker 起動 → 成果物フェッチ →
  checksum 検証。`--allow-remote` の明示承認が必須（§36）。SSH/rsync の argv 構築と配送制御フローは
  ユニット/シミュレーションテストで検証済み。**実機ネットワーク越しの実接続は未検証**（実機で canary が必要）。
- SQLite（append-only events からジョブ状態を再構築）
- checksum つき成果物回収・失敗分類と再試行・cancel・冪等（idempotency key）
- ポリシー（機密は外部 AI API 不使用）・AI ルーター（決定的処理を優先）・監査ログ・`verify`

実機の複数 Mac で動かす手順 → [`docs/REMOTE-MACS.md`](docs/REMOTE-MACS.md)。

## まだ自動実行しない（明示承認・§36）

SSH 鍵生成 / known_hosts 変更 / launchd 常駐登録 / Homebrew 導入 / 外部 AI API 呼出し / sudo /
ファイアウォール変更 / 複数 Mac への設定一括変更。リモート実行そのものは `--allow-remote` を付けた
時のみ有効（既定は無効）。新規展開は 1 台ずつ canary で（§32）。

## インストール

CLI 本体は `~/Projects/mac-neural-grid/` へ配置する想定。可変状態は
`~/Library/Application Support/mac-neural-grid/`（`$MNG_HOME` で上書き可）。

```bash
# 開発実行（インストール不要）
PYTHONPATH=src python3 -m mac_neural_grid --help
# もしくは editable install（PyYAML を含む）
pip install -e .
mac-neural-grid --help
```

## クイックスタート（§37 の受け入れコマンド）

```bash
export MNG_HOME=/tmp/mng
PYTHONPATH=src python3 -m mac_neural_grid init
PYTHONPATH=src python3 -m mac_neural_grid doctor
PYTHONPATH=src python3 -m mac_neural_grid node list
PYTHONPATH=src python3 -m mac_neural_grid node inspect localhost
PYTHONPATH=src python3 -m mac_neural_grid job plan examples/sample-job.yaml
PYTHONPATH=src python3 -m mac_neural_grid job run examples/sample-job.yaml
PYTHONPATH=src python3 -m mac_neural_grid job status <JOB_ID>
PYTHONPATH=src python3 -m mac_neural_grid logs --job <JOB_ID>
PYTHONPATH=src python3 -m mac_neural_grid verify
```

複数ノードを localhost で模擬:

```bash
mac-neural-grid node add --host localhost --name worker-a --transport local --labels trusted
mac-neural-grid node add --host localhost --name worker-b --transport local --labels trusted
mac-neural-grid node inspect worker-a && mac-neural-grid node inspect worker-b
mac-neural-grid job run examples/sample-job.yaml   # タスクが複数ノードへ分散
```

自然言語（構造化計画のみ・実行はしない）:

```bash
mac-neural-grid job plan --prompt "このフォルダのテキストを機密扱いで要約して" --inputs "./docs/*.txt"
mac-neural-grid shell        # 対話モード
```

## アーキテクチャ

```
Control Node (CLI) → Scheduler(能力ベース) → Dispatcher → Worker Agents(隔離実行) → Executors → Artifacts
                                   ↑ Policy / Model Router / Health / Retry / Audit / SQLite(events)
```

詳細は [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)、運用は [`docs/OPERATIONS.md`](docs/OPERATIONS.md)。
設計・保守を助ける Claude Code Skill は `mac-neural-grid-builder`。

## セキュリティ

argv 配列実行（`shell=True`/eval なし）・executor/command allowlist・作業ディレクトリ制限・
path traversal / symlink 防止・原子的書込(0600/0700)・payload_hash 検証・期限(replay)対策・
秘密値 redaction・監査ログ・タイムアウト・出力上限・checksum・rollback。詳細は
`mac-neural-grid-builder/constitution/SECURITY.md`。

## テスト

```bash
pytest    # unit / integration / security / failure / privacy（PyYAML 無しでも動作。YAML例は skip）
```

## ロールバック

- `mac-neural-grid backup` で DB/config を checksum つき退避、`restore --backup ... [--dry-run]` で復元。
- `job cancel <id>` は未完了タスクを cancelled にし作業ディレクトリを掃除（監査は残す）。
- ジョブ状態は events から再構築可能（Control 再起動後も復元）。

## 既知の制限

`docs/ARCHITECTURE.md` と `mac-neural-grid-builder/references/failure-recovery.md` を参照。
本 MVP はリモート Mac 連携を**実行していない**（設計のみ）。SSH transport は明示承認まで無効。
