"""バッチ実行側のアダプタ。hook_adapter と対になる。

この2つが同じ判定を返すことを tests/governance/test_policy_parity.py が検査する。
"""

from __future__ import annotations

from origin_core import registry

from policy import Decision, PolicyContext, decide


def evaluate(step: dict, *, body: str | None = None, **kwargs) -> Decision:
    try:
        entry = registry.get(step["skill_id"])
    except registry.SkillNotFound:
        entry = None  # 台帳に無いスキルは保守的な既定値で扱われる
    ctx = PolicyContext.from_plan_step(step, entry, body=body)
    return decide(ctx, **kwargs)


def before_step(step: dict, **kwargs) -> Decision:
    return evaluate(step, **kwargs)
