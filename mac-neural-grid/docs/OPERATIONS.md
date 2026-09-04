# 運用ガイド（mac-neural-grid）

## 実機 Mac 連携の前に（承認が必要な操作）

本 MVP は次を**自動実行しない**。運用で有効化する際は、1台ずつ承認・canary してから広げる（§32）。

1. **SSH 鍵と host 鍵**: 鍵は手動で用意。初回接続で host 鍵を確認し `known_hosts` に固定。
   `StrictHostKeyChecking=no` を使わない（`accept-new` は初回のみ受理）。
2. **ノード登録**: `node add --host <mac.local> --user <op> --transport ssh` 後、host 鍵確認まで
   `trust=untrusted`。確認後に `node trust <id> --level medium|high`。
3. **リモート inspect**: `scripts/inspect-node.zsh` を SSH で実行して能力 JSON を取得（Phase 2）。
4. **Worker 常駐**: `launchd/*.plist` を実パスへ編集 → `plutil -lint` → 手動実行で検証 →
   明示承認後に `launchctl bootstrap`（§28）。
5. **外部 AI API**: ポリシーで `external_ai_api: true` を明示し、承認を得た場合のみ。機密は不可。

## canary 展開（§32）

```
1台で実行 → 検証 → 少数台 → 検証 → 全体
```
10 台へ一度に変更しない。新 Worker/設定/スクリプトは最初の1台で必ず検証する。

## 日常運用

```bash
mac-neural-grid dashboard          # 概況
mac-neural-grid node list          # ノード一覧
mac-neural-grid capabilities       # 能力台帳
mac-neural-grid job list           # ジョブ一覧
mac-neural-grid logs --job <id>    # 監査/イベント
mac-neural-grid verify             # 整合性（無副作用）
mac-neural-grid backup --label daily
```

## リソース・電源への配慮（§18/§19）

- 高温・バッテリー低下・電源未接続のノードには新規割当をしない（`health.assignable`）。
- 長時間処理は macOS で `caffeinate -i` にスコープして実行し、ジョブ終了で自動解放（無期限に起こさない）。

## 障害対応（§31）

- Control 再起動: `job inspect <id>` の `rebuilt_state` で events から状態を復元できる。
- 失敗タスク: `job retry <id>`（再試行可能な失敗のみ別ノードで再実行）。
- ジョブ中止: `job cancel <id>`（未完了を cancelled・作業ディレクトリ掃除・監査は保持）。
- 破損復旧: `restore --backup <path> --to <target>`（checksum 不一致は拒否・`--dry-run` 可）。

## トラブルシュート

| 症状 | 確認 |
|---|---|
| `有効なノードが無い` | `node list` / `node add` / `node disable` 状態 |
| タスクが `lost` | 能力要件（arch/memory/tools）を満たすノードがあるか、health ゲート |
| `requires_approval` | high_risk ジョブ。内容を確認し `job dispatch <id> --yes` |
| `violations` | ポリシー違反（機密での外部送信等）。ポリシーかタスクを見直す |
