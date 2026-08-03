"""対話経路とバッチ経路が同じ判定を返すこと。

v0.1 の Hooks 擬似コードは PlanStep を引数に取っていたが、
Claude Code の Hooks はツール呼び出し単位で stdin から JSON を受け取る機構。
そのまま実装すると、片方の経路でしかポリシーが効かない
「穴のあるガバナンス」になる。このテストがその穴の見張り。

比較するのは status と gate。mutate（DRY_RUN）は risk 由来なので
経路ではなく台帳の risk が揃っているときだけ一致する。
"""

from __future__ import annotations

import pytest

from adapters.claude_code.hook_adapter import evaluate as hook_evaluate
from orchestrator.middleware import evaluate as batch_evaluate

SEND_INPUTS = {"channel": "self", "text": "テスト送信"}
DESTRUCTIVE_INPUTS = {"command": "rm -rf ./tmp/work"}
READ_INPUTS = {"file_path": "skills/meta/echo/SKILL.md"}


def _entry(**overrides):
    base = {
        "id": "ops.sample",
        "version": "1.0.0",
        "tier": "execution",
        "risk": "high",
        "stage": "stable",
        "data_class": "internal",
        "secrets": [],
        "gates": [],
        "depends_on": [],
        "budget": {"per_call_usd": 0.50, "daily_usd": 5.00},
        "retry_policy": "none",
    }
    base.update(overrides)
    return base


def _plan_step(inputs, gates):
    return {
        "step_id": "s1",
        "skill_id": "ops.sample",
        "skill_version": "1.0.0",
        "inputs": inputs,
        "expected_outputs": [],
        "gates_required": gates,
        "budget_usd": 0.01,
        "retry_policy": "none",
        "depends_on": [],
    }


def _tool_payload(tool_name, inputs):
    return {"tool_name": tool_name, "tool_input": inputs}


@pytest.mark.parametrize(
    "tool_name,inputs,gates",
    [
        ("mcp__line__send_message", SEND_INPUTS, ["external-send"]),
        ("Bash", DESTRUCTIVE_INPUTS, ["destructive-ops"]),
        ("Read", READ_INPUTS, []),
    ],
)
def test_both_entrypoints_agree(monkeypatch, budget, approvals, rates, tool_name, inputs, gates):
    monkeypatch.setattr("origin_core.registry.get", lambda *a, **kw: _entry(gates=gates))

    kwargs = dict(budget_store=budget, approval_store=approvals, rates=rates)
    from_hook = hook_evaluate(_tool_payload(tool_name, inputs), **kwargs)
    from_batch = batch_evaluate(_plan_step(inputs, gates), **kwargs)

    assert from_hook.status == from_batch.status, (
        f"{tool_name}: 対話経路 {from_hook.status} / バッチ経路 {from_batch.status}"
    )
    assert from_hook.gate == from_batch.gate


def test_the_same_approval_satisfies_both_entrypoints(monkeypatch, budget, approvals, rates):
    """承認は内容ハッシュに束縛されるので、経路が違っても同じ承認で通る。"""
    monkeypatch.setattr(
        "origin_core.registry.get", lambda *a, **kw: _entry(gates=["external-send"])
    )
    kwargs = dict(budget_store=budget, approval_store=approvals, rates=rates)

    pending = hook_evaluate(_tool_payload("mcp__line__send_message", SEND_INPUTS), **kwargs)
    assert pending.status == "waiting_approval"

    approvals.grant("external-send", pending.target_hash)

    assert hook_evaluate(_tool_payload("mcp__line__send_message", SEND_INPUTS), **kwargs).status == "proceed"
    assert batch_evaluate(_plan_step(SEND_INPUTS, ["external-send"]), **kwargs).status == "proceed"


def test_unknown_mcp_tool_is_treated_as_external_send(monkeypatch, budget, approvals, rates):
    """未知の MCP ツールは外部サービスに触る前提で扱う（見せ落としより見せすぎ）。"""
    monkeypatch.setattr("origin_core.registry.get", lambda *a, **kw: _entry())
    d = hook_evaluate(
        _tool_payload("mcp__unknown__do_something", {"x": 1}),
        budget_store=budget,
        approval_store=approvals,
        rates=rates,
    )
    assert d.status == "waiting_approval"
    assert d.gate == "external-send"
