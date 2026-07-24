# architecture-cases — 構成・機能の検証観点（§33 unit/integration）

対応する自動テスト: `mac-neural-grid/tests/test_unit.py` `test_integration.py` `test_schemas.py`。

## Unit
- [x] ノード選択: 能力要件（arch/memory/tools/labels）未充足は除外。信頼・低負荷を優先。untrusted は選ばない。
- [x] ポリシー判定: executor→risk（read_only/reversible/high_risk）。rm/external-api は high_risk。
- [x] ジョブ分割: per-file で入力数=タスク数。`job:` サブキー形の平坦化。
- [x] ID 生成: node_id は IP を「そのまま ID」にしない。idempotency_key は入力順に非依存。
- [x] checksum: sha256 一致。
- [x] path 検証: `safe_join` が traversal を拒否。
- [x] schema 同期: schemas/*.json と schemas.py が一致。

## Integration（localhost Worker）
- [x] 1 Worker ジョブ: run→2/2 成功、artifacts が checksum つきで存在。
- [x] 2 Worker 分散: 4 タスクが複数ノードへ分散。
- [x] verify: 実行後も無副作用で ok。
- [x] cancel: 未完了→cancelled。
- [x] Control 再起動: events から状態再構築（succeeded 一致）。
- [x] 冪等: 同一ジョブ再作成で reused。
- [x] 同梱 YAML 例のロード（PyYAML があれば）。

## 受け入れ（§37）
`doctor / node list / node inspect localhost / job plan / job run / job status / logs / verify` が
localhost で動作すること。複数 Worker を模擬した統合試験が通ること。→ `validate-skill.zsh` で確認可。
