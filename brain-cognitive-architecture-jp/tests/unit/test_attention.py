# -*- coding: utf-8 -*-
"""注意: 目立つが無関係を抑制・緊急だが低信頼・高関連低新奇・過剰切替防止。"""

from brain_architecture import attention as attn


GOAL = {"keywords": ["deploy", "sed", "macos", "nginx"]}


def test_salient_but_irrelevant_suppressed():
    r = attn.score({"content": "URGENT sale click now win prize",
                    "urgency": 0.95, "novelty": 0.95}, GOAL)
    assert r["suppressed"] is True
    assert r["admit"] is False


def test_goal_relevant_admitted():
    r = attn.score({"content": "deploy sed macos nginx issue", "urgency": 0.3}, GOAL)
    assert r["dimensions"]["goal_relevance"] > 0.3
    assert r["admit"] is True
    assert r["suppressed"] is False


def test_urgent_low_trust_does_not_dominate():
    # 緊急だが目標無関係 → 目標関連の穏当な入力より総合注意が高くならない。
    urgent_irrelevant = attn.score({"content": "emergency lottery", "urgency": 1.0},
                                   GOAL)
    relevant_calm = attn.score({"content": "sed macos deploy", "urgency": 0.2}, GOAL)
    assert relevant_calm["attention_score"] > urgent_irrelevant["attention_score"]


def test_high_relevance_low_novelty_still_admitted():
    r = attn.score({"content": "sed macos deploy nginx", "novelty": 0.05,
                    "urgency": 0.2}, GOAL)
    assert r["admit"] is True


def test_high_risk_not_dropped_even_if_irrelevant():
    r = attn.score({"content": "unrelated", "operations": ["delete", "external_send"],
                    "reversible": False}, GOAL)
    assert r["admit"] is True  # 危険は関連性が低くても注意を残す


def test_capacity_limits_switching():
    stimuli = [{"content": "sed macos %d deploy" % i, "urgency": 0.5}
               for i in range(10)]
    ranked = attn.rank(stimuli, GOAL, capacity=3)
    admitted = [r for r in ranked if r["admitted"]]
    assert len(admitted) <= 3  # 同時に扱う課題数を制限（過剰切替防止）
