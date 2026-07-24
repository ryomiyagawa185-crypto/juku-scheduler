# deployment — 常駐・launchd・canary

## Worker 常駐（§28）

ユーザー単位の LaunchAgent（`~/Library/LaunchAgents/`）を優先。テンプレートは
`mac-neural-grid/launchd/com.miyagawa.mac-neural-grid.worker.plist`。

守ること: 絶対パス・明示的な環境変数（PYTHONPATH/MNG_HOME）・標準出力/標準エラー・再起動方針
（Crashed のみ再起動・ThrottleInterval で無期限スパム防止）・重複起動防止（Label）・
ログローテーション（newsyslog/手動）・`plutil -lint` 検証・無効化手順・削除手順。

```
plutil -lint com.miyagawa.mac-neural-grid.worker.plist   # 構文検証
# 手動実行で動作確認してから:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.miyagawa.mac-neural-grid.worker.plist
# 無効化:
launchctl bootout gui/$(id -u)/com.miyagawa.mac-neural-grid.worker
```

**登録前に手動実行で検証**。launchd 登録は**明示承認後**に行う（§28/§36）。

## canary 展開（§32）

```
1台で canary → 検証 → 少数台 → 検証 → 全体
```

新しい Worker・設定・スクリプトを複数ノードへ展開するときは、最初に1台だけで実行し検証する。
10 台へ一度に変更しない。`bootstrap-node.zsh` は登録前チェック（読取専用）を助ける。

## MVP のスコープ

本 MVP は launchd 登録・Worker 配布・リモート実行を**自動化しない**。localhost の subprocess Worker で
基盤を安定させてから、承認を得て段階展開する。
