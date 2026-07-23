# brain-cognitive-architecture-jp

監査可能な適応型認知アーキテクチャの Claude Code Skill。**人間の脳の再現ではなく**、脳科学で比較的
支持されている *機能原理* を、決定的・再現可能・安全・監査可能なソフトウェア機構へ翻訳したもの。

- 概要と発火条件: [`SKILL.md`](SKILL.md)
- 憲法（不変原則）: [`constitution/`](constitution/)
- 設計リファレンス: [`references/`](references/)（比喩とアルゴリズムの境界・限界を含む）
- JSON Schema: [`schemas/`](schemas/)
- 実装（決定的 Python・標準ライブラリのみ）: [`scripts/brain_architecture/`](scripts/brain_architecture/)

## 位置づけ

本スキルは認知アーキテクチャ全体で、**関係学習・可塑性・忘却（共起グラフ/コネクトーム）は既存の
`skill-synapse-jp` を一モジュールとして再利用**する（`scripts/brain_architecture/synapse_bridge.py`・疎結合）。
安全 critical な抑制性エッジは本体が独立に保持する。

## インストール

スキルとして使う場合は `~/.claude/skills/brain-cognitive-architecture-jp/` へ配置する。
可変記憶（正本のイベントログ・派生 snapshot）は **スキル本体と分離** し、既定で `~/.claude/brain-memory/`
（`$BRAIN_MEMORY_DIR` で上書き可）に保存する。

```
cp -R brain-cognitive-architecture-jp ~/.claude/skills/
```

## 使い方（CLI）

```bash
# ラッパー経由（scripts を PATH に載せる）
python3 scripts/brain.py --dir /path/to/mem init
# あるいはパッケージとして
PYTHONPATH=scripts python3 -m brain_architecture --dir /path/to/mem init
```

主要コマンド（`--help` に全オプション）:

| コマンド | 役割 | 副作用 |
|---|---|---|
| `init` | 記憶ストア初期化 | 書込 |
| `observe` | 観測を不変イベントとして記録（感覚ゲート・機密除去） | 書込 |
| `attention` | 7 次元の注意プロファイル | なし |
| `working-memory` | 作業記憶の load/rehearse/decay/evict | 書込（load 等） |
| `retrieve` | 部分手掛かり検索・誤補完抑制・スコープ隔離 | なし |
| `predict` | 予測誤差の計算 | なし |
| `choose` | 方策選択（多基準・説明可能） | なし |
| `feedback` | 結果フィードバックを記録 | 書込 |
| `consolidate` | オフライン統合（既定 dry-run・候補のみ） | `--apply` 時のみ |
| `decay` | 忘却推奨の報告 | なし |
| `propose` | 自己改変候補の作成 | 書込 |
| `promote` | 昇格（executive 認可＋人間承認） | 書込（認可時） |
| `reject` | 提案却下 / 記憶廃止 | 書込 |
| `rollback` | backup から checksum 検証つき復元 | 書込 |
| `report` | 認知レポート | なし |
| `verify` | 整合性検査（無副作用） | なし |
| `replay` | event log から snapshot 再構築 | `--dry-run` 以外は書込 |
| `migrate` | スキーマ移行 | `--dry-run` 以外は書込 |

### 最小の実行例

```bash
export BRAIN_MEMORY_DIR=/tmp/brain-mem
python3 scripts/brain.py init
python3 scripts/brain.py observe --goal "deploy app" --situation "macOS sed differs" \
    --action "use gsed" --outcome verified_success --source-trust verified_local \
    --occurred-at 2026-07-01T10:00:00
python3 scripts/brain.py --json retrieve --cue '{"keywords":["sed","macos"]}'
python3 scripts/brain.py --json report
python3 scripts/brain.py --json verify        # 無副作用・replay 決定性を確認
```

## テスト

```bash
pytest        # unit / integration / regression / poisoning / privacy / chronology / property
```

## ロールバック

- 正本は append-only。誤った昇格は **retraction イベント**で打ち消す（`reject --memory ... --to-status deprecated`）。
- 派生ファイル（snapshot 等）は昇格前に自動 backup（`backups/*.sha256`）。復元は
  `rollback --backup <path> --to <path>`（checksum 不一致なら拒否）。`--dry-run` で無副作用に確認。
- snapshot はいつでも `replay` で event log から再生成できる（決定的）。

## 安全と限界

- `verify` / `dry-run` は無副作用。書込は安全書込（0600/fsync/os.replace・symlink/traversal 対策・lock・backup）。
- 未信頼・モデル生成源は行動規則（L4/L5）へ昇格不可。L4/L5 は人間承認必須。
- 既知の限界は [`references/limitations.md`](references/limitations.md) を参照。**「脳の再現」「意識」「感情」ではない。**
