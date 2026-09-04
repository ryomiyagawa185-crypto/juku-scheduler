# node-discovery — ノード発見・登録・能力台帳

## 安全な手動登録優先（§8）

自動発見（mDNS 等）は既定で無効。まず `node add` で手動登録する。

```
mac-neural-grid node add --host macstudio.local --user operator --name macstudio-01 --transport ssh
```

登録時に確認: SSH host 鍵・ユーザー・ノード実体・macOS 版・CPU アーキ・実行可能ツール・
作業ディレクトリ・ディスク容量・権限範囲・接続経路・信頼レベル。host 鍵未確認のリモートは
`trust=untrusted` で登録し、確認後に `node trust <id> --level medium|high`。

## 能力台帳（§7）

`node inspect` が各 Mac の能力を収集する（読取専用）。収集項目: node_id/hostname/display_name/
macOS 版/architecture/CPU/コア数/RAM/空きディスク/GPU・Neural Engine/バッテリー/電源/温度/
ネットワーク遅延/利用可能ツール・モデル/Homebrew/Python/Claude Code/ollama/現在負荷/
アクティブジョブ/labels/信頼スコープ/最終心拍。**IP を node_id に固定しない**。

- localhost: `discovery.inspect_local`（Python 標準ライブラリ・クロスプラットフォーム）。
- リモート Mac: `scripts/inspect-node.zsh` を SSH で実行し JSON を取得（Phase 2・明示承認後）。
- 取得できない項目は null（環境を固定仮定しない・graceful degradation）。

## 能力例

```json
{"node_id":"node-macstudio-01-ab12cd34","architecture":"arm64","memory_gb":64,
 "labels":["high-memory","always-on","local-llm"],
 "tools":{"claude_code":true,"ollama":true,"ffmpeg":true},
 "current_load":{"cpu_percent":18,"active_jobs":1}}
```
