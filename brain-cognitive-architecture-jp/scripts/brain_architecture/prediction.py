# -*- coding: utf-8 -*-
"""prediction — 予測と予測誤差の学習（仕様 §H）。

【生物学的知見】脳は絶えず次の入力・結果を予測し、予測と実測の差（予測誤差）で
学習すると考えられている。中脳ドーパミン系の位相性活動は「報酬そのもの」ではなく
報酬予測誤差に相関するとする説が有力。
【計算論的抽象化】学習信号 = 観測 − 期待。想定内の成功は小さく更新し、想定外の
失敗は強く記録する。更新量は証拠信頼性・検証・スコープ一致・サンプル数・不確実性・
反証で調整する。
【実装上の近似】ここでの「ドーパミン」は報酬ではなく、学習率調整に関わる予測誤差の
計算論的比喩に限定する（reward という語は使わない）。
"""

from . import schemas

BASE_UPDATE = 0.3
NEG_SURPRISE_GAIN = 1.5   # 想定外の失敗は強く記録（正の驚きより重み付け）


def observed_value(outcome):
    """結果区分を [0,1] の観測値へ写像（外部検証済みを優先的に信頼）。"""
    return schemas.OUTCOME_QUALITY.get(outcome, 0.5)


def prediction_error(expected, outcome):
    """符号付き予測誤差 = 観測 − 期待（expected は成功見込み確率など 0..1）。"""
    return round(observed_value(outcome) - _clamp(expected), 4)


def evaluate(expected, outcome, context=None):
    """予測誤差評価を返す（説明可能な学習信号・§H/§13）。

    context: {evidence_reliability, scope_match, sample_size, uncertainty,
              contradictory_evidence, self_reported}
    """
    context = context or {}
    pe = prediction_error(expected, outcome)
    surprise = abs(pe)
    verified = outcome in schemas.VERIFIED_OUTCOMES
    self_reported = bool(context.get("self_reported"))

    rel = _clamp(context.get("evidence_reliability", 0.5))
    scope_match = 1.0 if context.get("scope_match", True) else 0.3
    n = max(1, int(context.get("sample_size", 1)))
    unc = _clamp(context.get("uncertainty", 0.4))
    contra = int(context.get("contradictory_evidence", 0))

    # 想定外の失敗（負の驚き）を強める非対称ゲイン。
    gain = NEG_SURPRISE_GAIN if pe < 0 else 1.0
    # 想定内の成功（surprise≈0）は過大強化しない。
    magnitude = BASE_UPDATE * surprise * gain
    magnitude *= rel * scope_match
    magnitude *= (1.0 - 0.5 * unc)               # 不確実なら更新幅を縮める
    magnitude *= (1.0 - 1.0 / (1.0 + n))         # サンプルが少ないほど控えめ
    if self_reported and not verified:
        magnitude *= 0.4                          # 自己申告のみは外部検証より弱く
    if contra:
        magnitude *= 1.0 / (1.0 + 0.5 * contra)   # 反証があれば更新を割り引く

    salience = _clamp(surprise * gain)            # 想定外ほど注意・記録の顕著性が高い
    notes = []
    if pe < -0.3:
        notes.append("想定外の失敗: 強く記録し、失敗条件を明示化する")
    elif abs(pe) < 0.1:
        notes.append("想定どおり: 過大強化しない（小さく更新）")
    if self_reported and not verified:
        notes.append("自己申告のみ: 外部検証を優先し更新を割り引く")

    return {
        "expected": round(_clamp(expected), 4),
        "observed": observed_value(outcome),
        "prediction_error": pe,
        "surprise": round(surprise, 4),
        "verified": verified,
        "update_weight": round(_clamp(magnitude), 4),
        "salience": round(salience, 4),
        "notes": notes,
    }


def _clamp(x, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return lo
