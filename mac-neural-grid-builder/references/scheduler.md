# scheduler — 能力ベースのノード選定

単純なラウンドロビンにしない。生の CPU 速度だけで選ばない。

## スコア（`scheduler.py`）

```
node_score = capability_match × availability × trust × locality × historical_reliability
             − resource_pressure − network_cost
```

- **capability_match**: 要件（architecture/memory_gb_min/capabilities/models/labels）を満たさなければ 0
  （＝除外）。満たす場合は必須ツール一致度で 0.7〜1.0。
- **availability**: `1 − resource_pressure`（CPU/メモリ/アクティブジョブから算出）。
- **trust**: untrusted=0 / low=0.4 / medium=0.7 / high=1.0。untrusted は割当対象外。
- **locality**: データ所在地の近さ（MVP は localhost=1.0）。
- **historical_reliability**: 過去 attempt の成功率（ラプラス平滑化・データ無しは 0.8）。
- **resource_pressure / network_cost**: 負荷・ネットワーク遅延の減点。

## 評価に含める項目（§11）

CPU 負荷・メモリ空き・ディスク空き・電源接続・バッテリー残量・温度・ネットワーク遅延・既存ジョブ数・
必要ツール・必要モデル・データ所在地・機密性・ジョブ優先度・推定処理時間・過去の成功率。

## 健全性ゲート（§18）

`health.assignable` が高温・低バッテリー（電源未接続）・電源必須ポリシー違反・CPU 逼迫・disabled・
untrusted を検出したら割り当てない。

## 分散（データ並列）

ジョブ内で割当ごとに in-memory の負荷を加算し、以降のタスクを他ノードへ分散させる（raw の DB 値は
変えない）。リアルタイム心拍ベースの分散は Phase 2。
