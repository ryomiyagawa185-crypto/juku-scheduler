"""承認の内容束縛（TOCTOU 対策）。

守りたい事故はこれ:
    ドラフトAを見て送信を承認 → 再生成でBになった → Bが送信される
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from origin_core import hashing
from policy import decide
from policy.approvals import ApprovalStore, BlanketApprovalRefused, _now


def _send_step(inputs):
    return {
        "step_id": "s1",
        "skill_id": "ops.line-notify",
        "skill_version": "1.0.0",
        "inputs": inputs,
        "expected_outputs": [],
        "gates_required": ["external-send"],
        "budget_usd": 0.01,
        "retry_policy": "none",
        "depends_on": [],
    }


def _send_entry(entry):
    return entry(
        id="ops.line-notify",
        risk="medium",
        data_class="internal",
        gates=["external-send"],
        budget={"per_call_usd": 0.05, "daily_usd": 0.50},
    )


def test_unapproved_send_waits(ctx, budget, approvals, rates, entry):
    from policy.context import PolicyContext

    c = PolicyContext.from_plan_step(_send_step({"to": "self", "text": "A"}), _send_entry(entry))
    d = decide(c, budget_store=budget, approval_store=approvals, rates=rates)
    assert d.status == "waiting_approval"
    assert d.gate == "external-send"


def test_approval_lets_the_exact_content_through(budget, approvals, rates, entry):
    from policy.context import PolicyContext

    inputs = {"to": "self", "text": "A"}
    c = PolicyContext.from_plan_step(_send_step(inputs), _send_entry(entry))
    approvals.grant("external-send", c.target_hash)

    d = decide(c, budget_store=budget, approval_store=approvals, rates=rates)
    assert d.status == "proceed"
    assert d.approval_ref


def test_changed_content_invalidates_the_approval(budget, approvals, rates, entry):
    """本文だけ差し替わったケース。ここが v0.1 の穴だった。"""
    from policy.context import PolicyContext

    approved = PolicyContext.from_plan_step(
        _send_step({"to": "self", "text": "A"}), _send_entry(entry)
    )
    approvals.grant("external-send", approved.target_hash)

    swapped = PolicyContext.from_plan_step(
        _send_step({"to": "self", "text": "B"}), _send_entry(entry)
    )
    d = decide(swapped, budget_store=budget, approval_store=approvals, rates=rates)
    assert d.status == "waiting_approval", "内容が変わったのに承認が生き残っている"


def test_expired_approval_is_rejected(approvals):
    record = approvals.grant("external-send", hashing.hash_value({"x": 1}), ttl_seconds=1)
    later = _now() + timedelta(seconds=5)
    assert approvals.find_valid("external-send", record["target_hash"], now=later) is None


def test_one_shot_approval_is_consumed(approvals):
    target = hashing.hash_value({"x": 1})
    record = approvals.grant("external-send", target)
    assert approvals.find_valid("external-send", target) is not None
    approvals.consume(record["approval_id"])
    assert approvals.find_valid("external-send", target) is None


@pytest.mark.parametrize("gate", ["destructive-ops", "legal-submission"])
def test_no_blanket_approval_for_the_dangerous_gates(approvals, gate):
    with pytest.raises(BlanketApprovalRefused):
        approvals.grant(gate, hashing.hash_value({"x": 1}), one_shot=False)
