"""P1 の完了基準の中核。

判定が結論を出せないとき、通してはならない。
ここが緑でない限り、外部作用のあるスキルを新基盤に載せない。
"""

from __future__ import annotations

import pytest

from origin_core import pricing
from policy import decide
from policy.budget import BudgetStore
from policy.decide import ALLOW_PLACEHOLDER_ENV


def test_budget_store_failure_blocks(ctx, approvals, rates, monkeypatch):
    """予算ストアが読めないときにブロックする（fail-open してはならない）。"""

    class BrokenStore(BudgetStore):
        def has_headroom(self, *a, **kw):
            raise OSError("disk gone")

    d = decide(ctx(), budget_store=BrokenStore(), approval_store=approvals, rates=rates)
    assert d.status == "blocked"
    assert d.reason == "policy_error:OSError"


def test_approval_store_failure_blocks(ctx, budget, rates):
    """承認ストアが壊れているときにブロックする。"""

    class BrokenApprovals:
        def find_valid(self, *a, **kw):
            raise RuntimeError("db locked")

    d = decide(
        ctx(step_overrides={"gates_required": ["external-send"]}),
        budget_store=budget,
        approval_store=BrokenApprovals(),
        rates=rates,
    )
    assert d.status == "blocked"
    assert d.reason == "policy_error:RuntimeError"


def test_placeholder_pricing_blocks(ctx, budget, approvals, monkeypatch):
    """単価が未記入なら費用が記録できないのでブロックする。

    ここを通すと見積りが 0 になり、日次予算が永久に超過しない
    （＝予算ガードが存在しないのと同じ）。
    """
    monkeypatch.delenv(ALLOW_PLACEHOLDER_ENV, raising=False)
    assert pricing.is_placeholder(), "出荷時の pricing/models.json は placeholder のはず"

    d = decide(ctx(), budget_store=budget, approval_store=approvals)  # rates を渡さない
    assert d.status == "blocked"
    assert d.reason == "pricing_placeholder"


def test_placeholder_pricing_opt_in_is_explicit(ctx, budget, approvals, monkeypatch):
    """明示的なオプトインがあるときだけ通す（黙って通る fail-open とは違う）。"""
    monkeypatch.setenv(ALLOW_PLACEHOLDER_ENV, "1")
    d = decide(ctx(), budget_store=budget, approval_store=approvals)
    assert d.status == "proceed"


def test_deprecated_skill_blocks(ctx, budget, approvals, rates):
    d = decide(
        ctx(entry_overrides={"stage": "deprecated"}),
        budget_store=budget,
        approval_store=approvals,
        rates=rates,
    )
    assert d.status == "blocked"
    assert d.reason == "skill_deprecated"


def test_missing_cost_estimate_blocks(ctx, budget, approvals, rates):
    """プランのステップは必ず見積りを持つ。持たないものは通さない。"""
    d = decide(
        ctx(step_overrides={"budget_usd": None}),
        budget_store=budget,
        approval_store=approvals,
        rates=rates,
    )
    assert d.status == "blocked"
    assert d.reason == "cost_estimate_missing"


@pytest.mark.parametrize("policy_value", ["auto:1", "auto:3"])
def test_retry_forbidden_for_external_effect(ctx, budget, approvals, rates, policy_value):
    """外部送信の自動リトライは二重送信。設計で禁じる。"""
    d = decide(
        ctx(step_overrides={"gates_required": ["external-send"], "retry_policy": policy_value}),
        budget_store=budget,
        approval_store=approvals,
        rates=rates,
    )
    assert d.status == "blocked"
    assert d.reason == "retry_forbidden_for_external_effect"
