# failure-cases — 障害・復旧の検証観点（§33 failure）

対応する自動テスト: `mac-neural-grid/tests/test_failure.py`。

- [x] 依存欠損: ffmpeg 未導入ノードは dependency_missing でクリーンに失敗（非再試行）。
- [x] タイムアウト: 時間超過は timed_out → transient（再試行可能）。
- [x] 不正入力: 存在しない入力は invalid_input（非再試行）。
- [x] 成果物破損: checksum 不一致の transfer は例外。
- [x] manifest 不一致: collect が manifest と実ファイルの checksum 差を検出して例外。
- [x] 一部ノード失敗: 成功+失敗混在 → job は partial/failed。
- [x] バックオフ: 単調増加・上限 60s。

## 手動/Phase 2 観点
- [ ] Worker 切断・ネットワーク切断（実機 SSH）。
- [ ] ディスク不足（空き容量チェックで transfer 拒否）。
- [ ] 重複配送: idempotency_key で二重実行なし（unit で検証済み）。
- [ ] 同時キャンセル: cancel_requested → cancelled の競合。
- [ ] Control Node 停止からの復元: events による rebuild_state（integration で検証済み）。
