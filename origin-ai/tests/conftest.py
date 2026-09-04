"""共通フィクスチャ。

テストは必ず一時ディレクトリのストアを使う。既定のストアを掴むと
実際の予算カウンタと承認レコードを汚染し、テストの結果が
「昨日いくら使ったか」に依存し始める。
"""

from __future__ import annotations

import pytest

from policy.approvals import ApprovalStore
from policy.budget import BudgetStore
from policy.context import PolicyContext

# テスト用の単価（1M トークンあたり USD）。実際の料金表とは無関係の固定値。
TEST_RATES = {"input": 3.0, "cache_write": 3.75, "cache_read": 0.3, "output": 15.0}


@pytest.fixture
def state_path(tmp_path):
    return tmp_path / "origin.db"


@pytest.fixture
def budget(state_path):
    store = BudgetStore(state_path)
    yield store
    store.close()


@pytest.fixture
def approvals(state_path):
    store = ApprovalStore(state_path)
    yield store
    store.close()


@pytest.fixture
def rates():
    return dict(TEST_RATES)


@pytest.fixture
def entry():
    """台帳エントリの雛形。テストごとに上書きして使う。"""

    def _make(**overrides):
        base = {
            "id": "legal.sample",
            "version": "1.0.0",
            "tier": "reasoning",
            "risk": "medium",
            "stage": "stable",
            "data_class": "privileged",
            "secrets": [],
            "gates": [],
            "depends_on": [],
            "budget": {"per_call_usd": 0.30, "daily_usd": 1.00},
            "retry_policy": "none",
            "path": "skills/legal/sample",
        }
        base.update(overrides)
        return base

    return _make


@pytest.fixture
def step():
    def _make(**overrides):
        base = {
            "step_id": "s1",
            "skill_id": "legal.sample",
            "skill_version": "1.0.0",
            "inputs": {"case_id": "sample"},
            "expected_outputs": [],
            "gates_required": [],
            "budget_usd": 0.10,
            "retry_policy": "none",
            "depends_on": [],
        }
        base.update(overrides)
        return base

    return _make


@pytest.fixture
def ctx(entry, step):
    def _make(step_overrides=None, entry_overrides=None) -> PolicyContext:
        return PolicyContext.from_plan_step(
            step(**(step_overrides or {})), entry(**(entry_overrides or {}))
        )

    return _make
