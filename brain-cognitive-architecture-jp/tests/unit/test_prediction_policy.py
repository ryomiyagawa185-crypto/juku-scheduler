# -*- coding: utf-8 -*-
"""予測誤差の非対称性と、方策選択の高リスク非自動実行。"""

from brain_architecture import prediction, policy_selection


def test_unexpected_failure_recorded_strongly():
    surprise_fail = prediction.evaluate(0.9, "verified_failure",
                                        {"evidence_reliability": 0.9})
    expected_succ = prediction.evaluate(0.95, "verified_success",
                                        {"evidence_reliability": 0.9})
    assert surprise_fail["salience"] > expected_succ["salience"]
    assert surprise_fail["update_weight"] > expected_succ["update_weight"]
    assert surprise_fail["prediction_error"] < 0


def test_expected_success_not_overreinforced():
    r = prediction.evaluate(0.95, "verified_success")
    assert r["update_weight"] < 0.1


def test_self_reported_discounted():
    verified = prediction.evaluate(0.5, "verified_success",
                                   {"evidence_reliability": 0.9})
    self_rep = prediction.evaluate(0.5, "unverified_completion",
                                   {"evidence_reliability": 0.9, "self_reported": True})
    assert self_rep["update_weight"] < verified["update_weight"]


def test_high_uncertainty_shrinks_update():
    low = prediction.evaluate(0.5, "verified_failure",
                              {"evidence_reliability": 0.9, "uncertainty": 0.0})
    high = prediction.evaluate(0.5, "verified_failure",
                               {"evidence_reliability": 0.9, "uncertainty": 1.0})
    assert high["update_weight"] < low["update_weight"]


def test_high_risk_not_auto_executed():
    cands = [
        {"candidate_id": "safe", "operations": [], "reversible": True,
         "criteria": {"goal_alignment": 0.7, "success_probability": 0.7}},
        {"candidate_id": "risky", "operations": ["delete", "external_send"],
         "reversible": False,
         "criteria": {"goal_alignment": 1.0, "success_probability": 1.0}},
    ]
    res = policy_selection.select(cands, {})
    # たとえ risky の効用が高くても自動実行は許さない。
    if res["selected"] == "risky":
        assert res["auto_execute"] is False
    # 安全側が選ばれるか、選ばれても承認要求になる。
    assert res["selected"] in ("safe", "risky")


def test_explanation_present():
    cands = [{"candidate_id": "a", "criteria": {"goal_alignment": 0.6}}]
    res = policy_selection.select(cands, {})
    assert "explanation" in res and res["ranking"][0]["contributions"]
