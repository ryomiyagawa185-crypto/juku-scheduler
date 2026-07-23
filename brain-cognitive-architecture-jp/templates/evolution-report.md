# 「進化」レポート テンプレート（限定的定義）

> **「進化」の定義**（`CORE_PRINCIPLES.md` P6）: 経験を不変イベントとして記録し、信頼できる証拠で
> 関連性や方策を更新し、誤りを抑制し、古い知識を減衰させ、検証(L0→L5)を通過した知識だけを長期記憶へ
> 昇格させること。**無制限の自己改変は進化ではない。**

---

- **期間**: ____ 〜 ____
- **scope / partition**: ________

## 1. 経験（不変イベント）
- 観測イベント数: ____（うち quarantined 将来時刻: ____）
- 機密検出で redact したイベント: ____

## 2. 生成した候補（仮説）
- semantic 候補: ____ / deprecation 候補: ____（`brain consolidate --apply`）

## 3. 昇格した知識（承認済み変更）
| memory_id | L 遷移 | 承認者 | 根拠 |
|---|---|---|---|
| | L_→L_ | | |

## 4. 減衰・忘却した知識
- 検索除外(`exclude_from_search`): ____ / 想起抑制(`suppress_recall`): ____ / 保護され減衰しなかった: ____

## 5. 抑制した誤り
- 誤補完抑制 / 外部命令の非昇格 / 重複 / 過学習遮断 / 競合方策の相互抑制: 各 ____

## 6. 矛盾・異常
- conflicts: ____ / 過学習・過強ハブ anomalies: ____

## 7. ロールバック
- 実施有無・backup パス・checksum 一致: ____

## 8. 評価指標（§19）
| 指標 | 値 | 備考 |
|---|---|---|
| retrieval precision / recall | | |
| false association rate | | |
| scope leakage rate | | 目標 0 |
| overgeneralization rate | | |
| memory contamination rate | | 目標 0 |
| calibration error (Brier) | | `metacognition.calibration_error` |
| prediction error（平均 |PE|） | | |
| rollback success rate | | |
| regression rate | | |
| privacy violation count | | 目標 0 |
| unsafe automatic action count | | 目標 0 |
| context reduction / task success / user correction | | |

## 9. 所見
> この期間の「進化」が定義に照らして健全か（証拠駆動・誤り抑制・検証済みのみ昇格）。逸脱があれば是正案。
