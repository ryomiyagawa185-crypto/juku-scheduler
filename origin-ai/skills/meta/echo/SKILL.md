---
id: meta.echo
version: 0.1.0
tier: execution
risk: low
stage: experimental
data_class: internal
secrets: []
budget:
  per_call_usd: 0.01
  daily_usd: 0.10
gates: []
depends_on: []
triggers: ["echo", "疎通確認"]
retry_policy: auto:2
owner: user
---

# echo

## When
骨格の疎通確認だけに使う。実務では呼ばない。

## Goal
plan revision → policy → 実行層 → トレースの一周が通ることを確かめる。

## Inputs
- `message`（必須）: そのまま返す文字列
- `confirmed`（任意）: risk=high スキルの DRY_RUN 解除に使うフラグ（echo では未使用）

## Outputs
- stdout に `{"echo": <message>, "written": <path|null>}`
- `artifacts/open/echo/echo.txt`

## Permissions
- Read: なし
- Write: `artifacts/open/**`
- 外部呼び出し: なし

## Gates
なし（data_class=internal、外部作用なし）

## Constraints
- 予算: 1呼び出し 0.01 USD、日次 0.10 USD
- 他スキルへの直接 import 禁止（`origin_core` のみ可）

## Evidence
- `tests/test_p0_smoke.py`

## Handoff
- 上流: なし（手書きの plan から直接呼ぶ）
- 下流: なし
