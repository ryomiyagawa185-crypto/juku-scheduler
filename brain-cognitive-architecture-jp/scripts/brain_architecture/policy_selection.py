# -*- coding: utf-8 -*-
"""policy_selection — 基底核型方策選択層（仕様 §G/§12）。

【生物学的知見】基底核は複数の候補行動から一つを選び、探索と利用のバランスや
習慣的行動と目標指向行動の調停に関わると考えられている。
【計算論的抽象化】期待価値だけでなくリスク・不可逆性・コスト・不確実性・
ユーザ選好・方針適合を同時に比較する。高リスク領域では探索を抑える。
【実装上の近似】説明可能な重み付き効用。負の寄与（risk/cost/latency/uncertainty）を
明示し、各候補の寄与内訳を返す。高危険は効用最大でも自動実行しない（承認へ回す）。
"""

from . import schemas
from . import safety

# 効用の重み（正: 高いほど良い / 負: 高いほど悪い）。合議で調整可能。
_WEIGHTS = {
    "goal_alignment": 0.24, "expected_utility": 0.16, "success_probability": 0.16,
    "reversibility": 0.10, "evidence_quality": 0.10, "user_preference": 0.08,
    "information_gain": 0.06, "policy_compliance": 0.10,
    "risk": -0.22, "cost": -0.08, "latency": -0.05, "uncertainty": -0.10,
}
HIGH_RISK = 0.8


def _clamp(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def evaluate_candidate(candidate, context=None):
    """1候補の効用を説明可能な内訳つきで評価する。"""
    context = context or {}
    crit = dict(candidate.get("criteria") or {})
    sa = safety.assess({"operations": candidate.get("operations"),
                        "reversible": candidate.get("reversible"),
                        "sensitivity": candidate.get("sensitivity"),
                        "evidence_quality": crit.get("evidence_quality")})
    # risk は安全層の danger を既定にする（明示指定があれば大きい方を採用）。
    crit["risk"] = max(_clamp(crit.get("risk", 0.0)), sa["danger"])
    if "reversibility" not in crit and candidate.get("reversible") is not None:
        crit["reversibility"] = 1.0 if candidate["reversible"] else 0.0

    contributions = {}
    for k, w in _WEIGHTS.items():
        v = _clamp(crit.get(k, 0.5 if w > 0 else 0.0))
        contributions[k] = round(w * v, 4)
    utility = round(sum(contributions.values()), 4)

    return {
        "candidate_id": candidate.get("candidate_id"),
        "description": candidate.get("description"),
        "utility": utility,
        "contributions": contributions,
        "safety": sa,
        "requires_approval": sa["requires_approval"] or
        bool(candidate.get("requires_approval")),
        "danger": sa["danger"],
    }


def select(candidates, context=None, explore=True):
    """候補群から方策を選択し、ランキングと選定理由を返す（§12/§13）。

    - 高危険(danger>=0.8)候補は効用最大でも auto_execute=False（承認要求）。
    - 探索ボーナスは高リスク環境では無効化する（§G 高リスクでは探索を抑える）。
    """
    context = context or {}
    if not candidates:
        return {"selected": None, "ranking": [], "auto_execute": False,
                "explanation": "候補が無い"}
    evals = [evaluate_candidate(c, context) for c in candidates]
    max_danger = max(e["danger"] for e in evals)
    high_risk_env = max_danger >= HIGH_RISK or context.get("risk_domain", 0) >= HIGH_RISK

    for e in evals:
        bonus = 0.0
        if explore and not high_risk_env:
            # 探索: 情報利得の大きい候補を少しだけ後押し（利用一辺倒を避ける）。
            ig = e["contributions"].get("information_gain", 0.0) / max(
                _WEIGHTS["information_gain"], 1e-9)
            bonus = 0.05 * _clamp(ig)
        e["explore_bonus"] = round(bonus, 4)
        e["score"] = round(e["utility"] + bonus, 4)

    ranking = sorted(evals, key=lambda e: (e["score"], str(e["candidate_id"])),
                     reverse=True)
    winner = ranking[0]
    auto_execute = not winner["requires_approval"] and winner["danger"] < HIGH_RISK
    explanation = _explain(winner, ranking, high_risk_env)
    return {
        "selected": winner["candidate_id"],
        "auto_execute": auto_execute,
        "requires_approval": not auto_execute,
        "high_risk_env": high_risk_env,
        "ranking": ranking,
        "explanation": explanation,
    }


def _explain(winner, ranking, high_risk_env):
    top = sorted(winner["contributions"].items(), key=lambda kv: abs(kv[1]),
                 reverse=True)[:3]
    drivers = ", ".join("%s(%+.3f)" % (k, v) for k, v in top)
    msg = "選定=%s / 効用=%.3f / 主要因: %s" % (
        winner["candidate_id"], winner["score"], drivers)
    if not winner["danger"] < HIGH_RISK or winner["requires_approval"]:
        msg += " / 高危険または承認必須のため自動実行せず承認要求"
    if high_risk_env:
        msg += " / 高リスク環境のため探索を抑制"
    if len(ranking) > 1:
        msg += " / 次点=%s(%.3f)" % (ranking[1]["candidate_id"], ranking[1]["score"])
    return msg
