# -*- coding: utf-8 -*-
"""学習: 単発昇格しない・自己評価だけで強化しない・外部検証で更新・想定外失敗を強く記録・
基準頻度・過強ハブ抑制・メタ可塑性。"""

from brain_architecture import learning


def _mem(trust="verified_local", s=0, f=0, counter=0, verified=False, level="L0"):
    return {"memory_id": "mem_x", "type": "semantic", "level": level,
            "status": "candidate", "provenance": {"source_trust": trust},
            "success_count": s, "failure_count": f,
            "counterevidence_ids": ["e%d" % i for i in range(counter)],
            "last_verified_at": "2026-07-01" if verified else None}


def test_no_single_success_promotion():
    mem = _mem(s=1)
    ok, reasons = learning.promotion_gate(mem, "L1",
                                          {"event_valid": True, "source_recorded": True,
                                           "sensitive_removed": True})
    assert ok  # L1 は形式のみ
    # L2 は複数独立証拠/確認/決定的テストが必要 → 単発では不可。
    ok2, r2 = learning.promotion_gate(_mem(level="L1", s=1), "L2",
                                      {"independent_evidence_count": 1})
    assert not ok2


def test_self_report_capped_confidence():
    self_only = _mem(trust="model_generated", s=5, f=0, verified=False)
    verified = _mem(trust="verified_authoritative", s=5, f=0, verified=True)
    assert learning.derive_confidence(self_only) <= 0.5
    assert learning.derive_confidence(verified) > learning.derive_confidence(self_only)


def test_external_verification_updates():
    prior = 0.5
    post = learning.bayesian_update(prior, evidence_reliability=0.9,
                                    observed_success=True, sample_size=5)
    assert post > prior


def test_counterevidence_lowers_confidence():
    without = learning.derive_confidence(_mem(trust="verified_local", s=4, verified=True))
    with_counter = learning.derive_confidence(
        _mem(trust="verified_local", s=4, counter=3, verified=True))
    assert with_counter < without


def test_base_rate_more_evidence_more_confident():
    low = learning.derive_confidence(_mem(trust="verified_local", s=1, verified=True))
    high = learning.derive_confidence(_mem(trust="verified_local", s=20, verified=True))
    assert high > low


def test_metaplasticity_lowers_lr_in_high_risk():
    assert learning.learning_rate(domain_risk=0.9) < learning.learning_rate(
        domain_risk=0.1)


def test_homeostasis_scales_hub_derived_only():
    edges = [{"source": "s%d" % i, "target": "hub", "relation": "coactivated_with",
              "raw": {"evidence_count": 10}, "derived": {"strength": 1.0}}
             for i in range(6)]
    learning.homeostatic_scale(edges, cap=3.0)
    total = sum(e["derived"]["weight"] for e in edges)
    assert total <= 3.01
    # raw は不可侵。
    assert all(e["raw"]["evidence_count"] == 10 for e in edges)


def test_untrusted_cannot_reach_rule_level():
    mem = _mem(trust="untrusted_external", level="L3", s=5, verified=True)
    ok, reasons = learning.promotion_gate(
        mem, "L4", {"reproduced_conditions": 3, "failure_conditions_known": True,
                    "rollback_available": True, "regression_passed": True})
    assert not ok
    assert any("昇格不可" in r for r in reasons)
