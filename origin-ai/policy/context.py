"""PolicyContext — 対話経路とバッチ経路を1つの形に揃える。

これがあるおかげで decide() は「どこから来た呼び出しか」を知らずに済み、
2つの入口が同じルールで判定されることをテストで担保できる
（tests/governance/test_policy_parity.py）。

v0.1 の Hooks 擬似コードは PlanStep を引数に取っていたが、
Claude Code の Hooks はツール呼び出し単位で stdin から JSON を受け取る機構で、
PlanStep は渡ってこない。そのまま実装すると対話経路とバッチ経路の
どちらか一方でしかポリシーが効かなくなる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from origin_core import hashing

from . import gates as gates_mod

# 台帳に無いスキル／未知のツールに使う保守的な既定値
UNKNOWN_DEFAULTS = {
    "risk": "high",
    "stage": "experimental",
    "data_class": "pii",
    "per_call_budget_usd": 0.05,
    "daily_budget_usd": 0.50,
}


@dataclass(frozen=True)
class PolicyContext:
    source: str  # "plan_step" | "tool_call"
    skill_id: str
    skill_version: str
    tier: str
    risk: str
    stage: str
    data_class: str
    gates_required: tuple[str, ...]
    per_call_budget_usd: float
    daily_budget_usd: float
    target_hash: str
    estimated_cost_usd: float | None = None  # None = 費用の発生しない呼び出し
    inputs: dict[str, Any] = field(default_factory=dict)
    output_paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    retry_policy: str = "none"
    confirmed: bool = False
    known_skill: bool = True

    @classmethod
    def from_plan_step(cls, step: dict, entry: dict | None, *, body: str | None = None) -> "PolicyContext":
        e = entry or {}
        budget = e.get("budget", {})
        declared = tuple(e.get("gates", []))
        step_gates = tuple(step.get("gates_required", []))
        return cls(
            source="plan_step",
            skill_id=step["skill_id"],
            skill_version=step.get("skill_version", e.get("version", "0.0.0")),
            tier=e.get("tier", "reasoning+execution"),
            risk=e.get("risk", UNKNOWN_DEFAULTS["risk"]),
            stage=e.get("stage", UNKNOWN_DEFAULTS["stage"]),
            data_class=e.get("data_class", UNKNOWN_DEFAULTS["data_class"]),
            gates_required=tuple(dict.fromkeys(declared + step_gates)),
            per_call_budget_usd=float(
                budget.get("per_call_usd", UNKNOWN_DEFAULTS["per_call_budget_usd"])
            ),
            daily_budget_usd=float(
                budget.get("daily_usd", UNKNOWN_DEFAULTS["daily_budget_usd"])
            ),
            target_hash=hashing.target_hash(step.get("inputs", {}), body),
            estimated_cost_usd=step.get("budget_usd"),
            inputs=dict(step.get("inputs", {})),
            output_paths=tuple(step.get("expected_outputs", [])),
            secrets=tuple(e.get("secrets", [])),
            retry_policy=step.get("retry_policy", e.get("retry_policy", "none")),
            confirmed=bool(step.get("inputs", {}).get("confirmed", False)),
            known_skill=entry is not None,
        )

    @classmethod
    def from_tool_call(cls, payload: dict, entry: dict | None = None) -> "PolicyContext":
        """Claude Code の PreToolUse ペイロードから作る。

        payload 例: {"tool_name": "Bash", "tool_input": {"command": "..."}}
        """
        tool_name = payload.get("tool_name", "")
        tool_input = payload.get("tool_input", {}) or {}
        e = entry or {}
        budget = e.get("budget", {})
        gate_tuple = gates_mod.classify_tool(tool_name, tool_input)
        return cls(
            source="tool_call",
            skill_id=e.get("id", f"tool.{tool_name.lower() or 'unknown'}"),
            skill_version=e.get("version", "0.0.0"),
            tier="execution",
            risk=e.get("risk", "high" if gate_tuple else "low"),
            stage=e.get("stage", "stable"),
            data_class=e.get("data_class", UNKNOWN_DEFAULTS["data_class"]),
            gates_required=tuple(dict.fromkeys(tuple(e.get("gates", [])) + gate_tuple)),
            per_call_budget_usd=float(
                budget.get("per_call_usd", UNKNOWN_DEFAULTS["per_call_budget_usd"])
            ),
            daily_budget_usd=float(
                budget.get("daily_usd", UNKNOWN_DEFAULTS["daily_budget_usd"])
            ),
            target_hash=hashing.target_hash(tool_input, None),
            estimated_cost_usd=None,  # ツール呼び出し自体には課金が発生しない
            inputs=dict(tool_input),
            output_paths=(),  # 出力先の検査は plan 経路で行う
            secrets=tuple(e.get("secrets", [])),
            retry_policy="none",
            confirmed=bool(tool_input.get("confirmed", False)),
            known_skill=entry is not None,
        )
