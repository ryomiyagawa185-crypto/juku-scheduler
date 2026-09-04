"""判定の唯一の実装。対話経路もバッチ経路もここを通る。

**fail-closed が最重要の性質。** 予算ストアが読めない、単価が未記入、
ゲートの実装が例外を投げた——どの場合も PROCEED を返してはいけない。
安全機構が沈黙して無効化されるのが最悪の故障モードで、
壊れていることに気づけないまま外部送信が通る。

判定順序（先に落ちたものが理由になる）:
  1. 単価表が placeholder（費用が記録できない）
  2. deprecated なスキル
  3. 費用見積りが無い
  4. 1呼び出し上限
  5. 日次上限
  6. データ分類に反する出力先
  7. 外部作用があるのに自動リトライが有効（二重送信）
  8. 人間承認ゲートの未承認／内容不一致
  9. risk=high の初回は DRY_RUN に倒す
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from origin_core import pricing

from . import classification, gates as gates_mod
from .approvals import ApprovalStore
from .budget import BudgetStore
from .context import PolicyContext

ALLOW_PLACEHOLDER_ENV = "ORIGIN_AI_ALLOW_PLACEHOLDER_PRICING"

PROCEED = "proceed"
BLOCKED = "blocked"
WAITING_APPROVAL = "waiting_approval"


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str | None = None
    gate: str | None = None
    approval_ref: str | None = None
    target_hash: str | None = None
    mutate: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.status != PROCEED

    @property
    def dry_run(self) -> bool:
        return bool(self.mutate.get("dry_run"))

    def message(self) -> str:
        if self.status == PROCEED:
            return "dry_run に倒して実行します" if self.dry_run else "実行を許可"
        if self.status == WAITING_APPROVAL:
            return f"承認待ち: {self.gate}（対象ハッシュ {self.target_hash}）"
        return f"ブロック: {self.reason}"

    @classmethod
    def proceed(cls, **mutate: Any) -> "Decision":
        return cls(PROCEED, mutate=mutate)

    @classmethod
    def block(cls, reason: str) -> "Decision":
        return cls(BLOCKED, reason=reason)

    @classmethod
    def wait(cls, gate: str, target_hash: str) -> "Decision":
        return cls(WAITING_APPROVAL, reason="approval_required", gate=gate, target_hash=target_hash)


def _placeholder_pricing_allowed() -> bool:
    """P0 のデモ用の明示的な逃げ道。既定では閉じている。

    環境変数での明示的なオプトインなので、黙って通る fail-open とは違う。
    この状態で書かれたトレースは pricing_version が "PLACEHOLDER" になり、
    後から「これは費用が記録できていない実行だ」と判別できる。
    """
    return os.environ.get(ALLOW_PLACEHOLDER_ENV) == "1"


def decide(
    ctx: PolicyContext,
    *,
    budget_store: BudgetStore | None = None,
    approval_store: ApprovalStore | None = None,
    now: datetime | None = None,
    rates: dict | None = None,
) -> Decision:
    try:
        return _decide(ctx, budget_store, approval_store, now, rates)
    except Exception as e:  # noqa: BLE001 - fail-closed は広く捕まえるのが正しい
        return Decision.block(f"policy_error:{type(e).__name__}")


def _decide(
    ctx: PolicyContext,
    budget_store: BudgetStore | None,
    approval_store: ApprovalStore | None,
    now: datetime | None,
    rates: dict | None,
) -> Decision:
    # 1. 単価が未記入なら費用を記録できない
    if ctx.source == "plan_step" and rates is None:
        if pricing.is_placeholder() and not _placeholder_pricing_allowed():
            return Decision.block("pricing_placeholder")

    # 2. 廃止されたスキル
    if ctx.stage == "deprecated":
        return Decision.block("skill_deprecated")

    # 3-5. 費用
    if ctx.estimated_cost_usd is not None:
        if ctx.estimated_cost_usd > ctx.per_call_budget_usd + 1e-12:
            return Decision.block("per_call_budget_exceeded")
        store = budget_store or BudgetStore()
        if not store.has_headroom(ctx.skill_id, ctx.estimated_cost_usd, ctx.daily_budget_usd):
            return Decision.block("daily_budget_exceeded")
    elif ctx.source == "plan_step":
        # プランのステップは必ず見積りを持つこと（planner の責務）
        return Decision.block("cost_estimate_missing")

    # 6. 出力先がデータ分類に反していないか
    if ctx.output_paths:
        violations = classification.check_outputs(ctx.data_class, ctx.output_paths)
        if violations:
            return Decision.block(f"data_class_violation:{violations[0]}")

    # 7. 外部作用があるのに自動リトライが有効
    if gates_mod.has_external_effect(ctx.gates_required) and ctx.retry_policy != "none":
        return Decision.block("retry_forbidden_for_external_effect")

    # 8. 人間承認ゲート
    human_gates = gates_mod.requires_human(ctx.gates_required)
    if human_gates:
        approvals = approval_store or ApprovalStore()
        for gate in human_gates:
            approval = approvals.find_valid(gate, ctx.target_hash, now=now)
            if approval is None:
                return Decision.wait(gate, ctx.target_hash)
        # すべてのゲートで有効な承認が見つかった。参照を返して runner が消費する
        last = approvals.find_valid(human_gates[-1], ctx.target_hash, now=now)
        approval_ref = last["approval_id"] if last else None
        if ctx.risk == "high" and not ctx.confirmed:
            return Decision(PROCEED, approval_ref=approval_ref, mutate={"dry_run": True})
        return Decision(PROCEED, approval_ref=approval_ref)

    # 9. risk=high の初回は DRY_RUN 固定
    if ctx.risk == "high" and not ctx.confirmed:
        return Decision.proceed(dry_run=True)

    return Decision.proceed()
