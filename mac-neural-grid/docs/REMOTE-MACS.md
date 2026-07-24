# 実機の複数 Mac で動かす（Phase 2・SSH リモート実行）

このページの手順で、**別の実機 Mac へ実際にジョブを流せます**。安全のため、リモート実行は
`--allow-remote` を付けたときだけ有効です（既定は無効）。まず 1 台で canary してから増やしてください。

> 正直な注意: SSH/rsync のコマンド構築と配送制御フローは自動テスト済みですが、**ネットワーク越しの
> 実接続はあなたの環境が初検証**です。1 台ずつ、小さなジョブから始めてください。

以下の `USER` と `WORKER` は各自の値に置き換えます（Tailscale なら `WORKER` は相手 Mac の
Tailscale IP か MagicDNS 名。例: `100.92.153.116` / `mac-mini-01`）。**コメント行（`#`）は貼らないこと。**

## 0. ワーカー側 Mac の準備（相手の Mac で 1 回）

- 「システム設定 > 一般 > 共有 > リモートログイン」を **オン**（SSH を許可）。
- `python3` が使えること（`brew install python` もしくは Xcode Command Line Tools）。
- `rsync` は macOS 標準で入っています。

## 1. 鍵と host 鍵（Control Mac で）

```
ssh-keygen -t ed25519
ssh-copy-id USER@WORKER
ssh -o StrictHostKeyChecking=accept-new USER@WORKER "sw_vers -productVersion; uname -m"
```
最後の行で相手の macOS 版と arch が表示され、`known_hosts` に host 鍵が固定されれば準備完了です。

## 2. ノード登録・信頼・配備・調査（Control Mac で）

```
mac-neural-grid node add --host WORKER --user USER --transport ssh --name worker-01 --labels trusted
```
`node_id`（例 `node-worker-01-xxxxxxxx`）が表示されます。以降これを `NID` とします。

```
mac-neural-grid node trust NID --level high
mac-neural-grid worker install --node NID --allow-remote
mac-neural-grid node inspect NID --allow-remote
mac-neural-grid node ping NID --allow-remote
```
- `worker install` … 相手 Mac の `$HOME/.mac-neural-grid/pkg/` へ Worker 一式を rsync（pip 不要）。
- `node inspect --allow-remote` … 相手 Mac 上で能力を収集（arch/RAM/ツール等が台帳に入る）。
- `node ping --allow-remote` … `ok: true` なら疎通 OK。

## 3. まず 1 台で canary 実行（Control Mac で）

```
cd ~/mng-test
mac-neural-grid job run job.json --allow-remote
mac-neural-grid job list
mac-neural-grid --json job status ジョブID
```
`summary.results` の各 `node_id` に worker-01 が出て、`succeeded` になれば **実機リモート実行が成功**です。
成果物は Control 側に checksum 検証つきで回収されます（`mac-neural-grid artifacts --job ジョブID`）。

## 4. 台数を増やす（canary 通過後）

2 台目以降も同じ手順（`node add` → `node trust` → `worker install --allow-remote` →
`node inspect --allow-remote`）。登録できたら：
```
mac-neural-grid job run job.json --allow-remote
```
タスクが能力ベースで複数の実機 Mac に分散します（`job status` の `node_id` で確認）。

## 内部で実際に走るコマンド（監査用）

`mac-neural-grid` が相手 Mac に対して発行するのは次の形だけです（`StrictHostKeyChecking=no` は使いません）：
```
ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes USER@WORKER mkdir -p $HOME/.mac-neural-grid/pkg
rsync -a --delete -e 'ssh -o StrictHostKeyChecking=accept-new ...' <local>/src/mac_neural_grid/ USER@WORKER:$HOME/.mac-neural-grid/pkg/mac_neural_grid/
rsync -a --delete -e 'ssh ...' <input> USER@WORKER:$HOME/.mac-neural-grid/jobs/JOB/TASK/input/<name>
ssh ... USER@WORKER /usr/bin/env PYTHONPATH=$HOME/.mac-neural-grid/pkg python3 -m mac_neural_grid.worker --envelope $HOME/.mac-neural-grid/jobs/JOB/TASK/envelope.json
rsync -a -e 'ssh ...' USER@WORKER:$HOME/.mac-neural-grid/jobs/JOB/TASK/output/ <local>/output/
```
`sudo`・鍵生成・known_hosts 変更・launchd 登録・外部 API・ファイアウォール変更は **一切しません**。

## うまくいかないとき

| 症状 | 対処 |
|---|---|
| `command not found: mac-neural-grid` | venv を有効化、または前回作った alias を利用 |
| `リモート実行/転送は明示承認が必要` | コマンドに `--allow-remote` を付ける |
| タスクが `lost` | `node trust NID --level high`／`node inspect --allow-remote` 済みか、要件を満たすノードがあるか |
| `node ping` が false | リモートログイン ON か、`ssh USER@WORKER` が単体で通るか、Tailscale 接続 |
| `worker install` 失敗 | 相手 Mac に `python3`/`rsync` があるか、`$HOME` 書込可か |

## 常駐 Worker（launchd・任意）

`launchd/com.miyagawa.mac-neural-grid.worker.plist` を実パスに編集し、`plutil -lint` → 手動実行で検証 →
**明示承認のうえ** `launchctl bootstrap` してください（`docs/OPERATIONS.md` 参照）。自動登録はしません。
