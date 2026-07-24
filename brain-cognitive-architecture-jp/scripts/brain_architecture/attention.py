# -*- coding: utf-8 -*-
"""attention — 注意制御層（仕様 §B）。

【生物学的知見】前頭頭頂の注意ネットワークと顕著性ネットワークが、目標関連情報を
増強し無関係な刺激を抑制すると考えられている。
【計算論的抽象化】注意を単一値にせず 7 次元へ分解する。強い刺激だからではなく、
現在の目標との関連性を主軸に配分し、目立つが無関係な入力を抑制する。
【実装上の近似】各次元は決定的なスコア関数。総合注意は目標関連性を最重視した
重み付き和で、goal_relevance が低い高顕著性入力には抑制係数をかける。
"""

import re

from . import schemas
from . import safety

# 総合注意の重み（goal_relevance を最重視・§B）。
_WEIGHTS = {
    "goal_relevance": 0.34, "expected_information_gain": 0.16, "risk": 0.14,
    "uncertainty": 0.12, "urgency": 0.10, "novelty": 0.08, "emotional_salience": 0.06,
}
ADMIT_THRESHOLD = 0.35

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(text):
    if not text:
        return set()
    text = str(text).lower()
    toks = set(_WORD_RE.findall(text))
    # CJK など空白区切りでない言語向けに文字バイグラムも足す。
    cjk = [c for c in text if ord(c) > 0x3000]
    toks.update(cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1))
    return toks


def _overlap(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / float(len(a | b)) if inter else 0.0


def _clamp(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def score(stimulus, goal=None, context=None):
    """刺激1件の注意プロファイルを返す（7次元＋総合＋admit/suppressed）。

    stimulus: {content|text, operations, urgency, uncertainty, novelty?}
    goal: {keywords, description}
    context: {seen_tokens:set, failure_keywords:list}
    """
    context = context or {}
    goal = goal or {}
    text = stimulus.get("content") or stimulus.get("text") or ""
    if isinstance(text, dict):
        text = " ".join(str(v) for v in text.values())
    stim_tok = _tokens(text)
    goal_tok = _tokens(goal.get("description")) | set(
        t.lower() for t in (goal.get("keywords") or []))

    goal_relevance = _overlap(stim_tok, goal_tok)

    # 新奇性: 既知トークンとの重なりが小さいほど高い（familiarity の逆）。
    seen = context.get("seen_tokens")
    if stimulus.get("novelty") is not None:
        novelty = _clamp(stimulus["novelty"])
    elif seen:
        novelty = 1.0 - _overlap(stim_tok, set(seen))
    else:
        novelty = 0.5

    urgency = _clamp(stimulus.get("urgency", 0.3))
    sa = safety.assess({"operations": stimulus.get("operations"),
                        "reversible": stimulus.get("reversible"),
                        "sensitivity": stimulus.get("sensitivity"),
                        "evidence_quality": stimulus.get("evidence_quality")})
    risk = sa["danger"]
    uncertainty = _clamp(stimulus.get("uncertainty", 0.5))

    fk = _tokens(" ".join(context.get("failure_keywords") or []))
    emotional_salience = max(sa["salience"],
                             0.6 if (fk and stim_tok & fk) else 0.0)

    # 期待情報利得: 目標に関連しつつ不確実性を減らせそうな新奇情報ほど高い。
    expected_information_gain = round(goal_relevance * (0.5 + 0.5 * novelty) *
                                     (0.5 + 0.5 * uncertainty), 4)

    dims = {
        "goal_relevance": round(goal_relevance, 4),
        "novelty": round(novelty, 4),
        "urgency": round(urgency, 4),
        "risk": round(risk, 4),
        "uncertainty": round(uncertainty, 4),
        "emotional_salience": round(emotional_salience, 4),
        "expected_information_gain": expected_information_gain,
    }
    total = sum(_WEIGHTS[k] * dims[k] for k in _WEIGHTS)

    # 抑制: 目立つ(novelty/urgency/salience 高)が目標無関係なら注意を絞る（§B/§K）。
    suppressed = False
    if goal_relevance < 0.2 and max(novelty, urgency, emotional_salience) > 0.6 \
            and risk < 0.8:
        total *= 0.4
        suppressed = True

    return {
        "dimensions": dims,
        "attention_score": round(_clamp(total), 4),
        "admit": total >= ADMIT_THRESHOLD or risk >= 0.8,
        "suppressed": suppressed,
        "safety": sa,
    }


def rank(stimuli, goal=None, context=None, capacity=5):
    """複数刺激を注意でランク付けし、上位 capacity 件を admit する（注意資源の上限・§B）。"""
    scored = []
    for i, s in enumerate(stimuli):
        r = score(s, goal, context)
        scored.append({"index": i, "stimulus": s, **r})
    # 高危険は関連性が低くても落とさない（安全のため注意を残す）。
    scored.sort(key=lambda r: (r["safety"]["danger"] >= 0.8, r["attention_score"]),
                reverse=True)
    for j, r in enumerate(scored):
        r["admitted"] = (j < capacity) and (r["admit"])
    return scored
