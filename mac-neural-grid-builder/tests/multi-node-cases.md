# multi-node-cases — 複数ノードの検証観点（§33 integration / privacy）

対応する自動テスト: `mac-neural-grid/tests/test_integration.py` `test_privacy.py`。

## localhost での複数 Worker 模擬（実機不要）
- [x] 2〜3 の local ノードを登録・inspect（実プロセス隔離の subprocess Worker）。
- [x] 4 タスクを複数ノードへ分散（データ並列）。
- [x] 割当ごとの in-memory 負荷加算で偏りを緩和。

## privacy
- [x] 機密ジョブは外部 API へルーティングされない（決定的処理/ローカルへフォールバック）。
- [x] external-api executor はポリシー未許可で policy_denied。
- [x] events/監査に秘密値が残らない（redaction）。
- [ ] 顧客データが別スコープ/別ノードへ混入しない（instance 分離は運用 + partition ラベルで担保）。

## 実機（Phase 2・承認後）
- [ ] 2 台目へ canary 展開 → 検証 → 少数 → 全体（§32）。
- [ ] SSH transport で inspect-node.zsh を実行し能力台帳を収集。
- [ ] rsync/SFTP による成果物転送（一時名→checksum→原子的改名）。
- [ ] launchd 常駐 Worker の登録（plutil 検証・手動実行・明示承認後）。

## 実行方法
```
mac-neural-grid node add --host localhost --name worker-a --transport local --labels trusted
mac-neural-grid node add --host localhost --name worker-b --transport local --labels trusted
mac-neural-grid node inspect worker-a && mac-neural-grid node inspect worker-b
mac-neural-grid job run examples/sample-job.yaml
mac-neural-grid job status <JOB_ID>   # 複数ノードへの分散を確認
```
