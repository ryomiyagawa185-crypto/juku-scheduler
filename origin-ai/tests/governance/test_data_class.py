"""データ分類に反する出力先を拒否する。

扱うのが訴訟記録と未成年の生徒データである以上、
「どこに書いてよいか」をスキルの自由にしてはいけない。
"""

from __future__ import annotations

import pytest

from policy import classification, decide


@pytest.mark.parametrize(
    "data_class,path,allowed",
    [
        ("privileged", "artifacts/privileged/essence/answer.md", True),
        ("privileged", "artifacts/open/essence/answer.md", False),
        ("pii", "artifacts/pii/students/2026.json", True),
        ("pii", "artifacts/open/students/2026.json", False),
        ("internal", "artifacts/open/report.md", True),
        ("internal", "artifacts/privileged/report.md", False),
        ("privileged", "artifacts/privileged/../open/leak.md", False),
        ("privileged", "/etc/passwd", False),
        ("privileged", "artifacts/privileged-but-not-really/x.md", False),
    ],
)
def test_output_path_allowed(data_class, path, allowed):
    assert classification.output_path_allowed(data_class, path) is allowed


def test_decide_blocks_wrong_output_root(ctx, budget, approvals, rates):
    d = decide(
        ctx(step_overrides={"expected_outputs": ["artifacts/open/leak.md"]}),
        budget_store=budget,
        approval_store=approvals,
        rates=rates,
    )
    assert d.status == "blocked"
    assert d.reason.startswith("data_class_violation")


def test_decide_allows_correct_output_root(ctx, budget, approvals, rates):
    d = decide(
        ctx(step_overrides={"expected_outputs": ["artifacts/privileged/case/answer.md"]}),
        budget_store=budget,
        approval_store=approvals,
        rates=rates,
    )
    assert d.status == "proceed"


def test_only_open_is_synced():
    """同期されるのは artifacts/open/ だけ。"""
    assert classification.is_synced("artifacts/open/report.md")
    assert not classification.is_synced("artifacts/pii/students.json")
    assert not classification.is_synced("artifacts/privileged/case.md")


def test_privileged_is_never_auto_deleted():
    assert classification.RETENTION_DAYS["privileged"] is None
    assert classification.RETENTION_DAYS["pii"] == 90
