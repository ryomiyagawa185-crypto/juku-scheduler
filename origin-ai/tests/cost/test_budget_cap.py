"""予算。

v0.1 のトークン回帰テストはモック LLM の下で tokens_in を黄金値と
比較していたが、モックはトークンを数えないので空テストになる。
入力側は実測（count_tokens / トークナイザ）、出力側は上限のみ、と分ける。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from origin_core import pricing, tokens
from policy import decide
from policy.budget import BudgetStore


def test_daily_budget_blocks_after_cap(ctx, budget, approvals, rates):
    c = ctx(step_overrides={"budget_usd": 0.30}, entry_overrides={
        "budget": {"per_call_usd": 0.30, "daily_usd": 1.00}
    })
    kwargs = dict(budget_store=budget, approval_store=approvals, rates=rates)

    for _ in range(3):
        assert decide(c, **kwargs).status == "proceed"
        budget.spend(c.skill_id, 0.30)

    d = decide(c, **kwargs)
    assert d.status == "blocked"
    assert d.reason == "daily_budget_exceeded"


def test_per_call_cap(ctx, budget, approvals, rates):
    d = decide(
        ctx(step_overrides={"budget_usd": 0.40}, entry_overrides={
            "budget": {"per_call_usd": 0.30, "daily_usd": 5.00}
        }),
        budget_store=budget,
        approval_store=approvals,
        rates=rates,
    )
    assert d.status == "blocked"
    assert d.reason == "per_call_budget_exceeded"


def test_concurrent_spend_is_not_lost(state_path):
    """JSON の read-modify-write なら取りこぼす更新を、取りこぼさないこと。

    取りこぼすと「まだ使っていない」ことになり、予算ガードが fail-open する。
    """
    def worker(_):
        store = BudgetStore(state_path)
        try:
            store.spend("legal.sample", 0.01)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(40)))

    store = BudgetStore(state_path)
    try:
        assert abs(store.spent_today("legal.sample") - 0.40) < 1e-9
    finally:
        store.close()


def test_cache_tiers_are_priced_separately(rates):
    """キャッシュ読み出しは通常入力より安い。1つの tokens_in に潰すと測れない。"""
    plain = pricing.Usage(input_tokens=10_000)
    cached = pricing.Usage(input_tokens=1_000, cache_read_input_tokens=9_000)

    plain_cost = pricing.cost_usd(plain, "test", rates=rates)
    cached_cost = pricing.cost_usd(cached, "test", rates=rates)

    assert cached_cost < plain_cost
    assert abs(cached.cache_hit_ratio - 0.9) < 1e-9


def test_token_count_is_flagged_as_estimate_until_a_counter_is_injected():
    """推定値で予算を判断しないための旗。"""
    tokens.reset_counter()
    assert tokens.is_estimate()
    assert tokens.count("民法94条2項の類推適用") > 0

    tokens.set_counter(lambda text, model: 42)
    try:
        assert not tokens.is_estimate()
        assert tokens.count("なんでも") == 42
    finally:
        tokens.reset_counter()
