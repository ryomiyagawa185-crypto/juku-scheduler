# -*- coding: utf-8 -*-
"""executive — 前頭前野型実行制御層（仕様 §J/§9）。

【生物学的知見】前頭前野は長期目標の維持、衝動の抑制、規則衝突の解消、複数選択肢の
比較などに関わると考えられている。
【計算論的抽象化】この層だけが「本番昇格・長期記憶更新・手続変更・スキル改変提案・
危険操作の承認要求」を許可できる。ただしこの層自身も安全規則を書き換えられない。
【実装上の近似】昇格ゲート(learning)＋抑制(inhibition)＋安全評価(safety)を統合し、
高段階(L4/L5)や保護対象への変更には人間承認を強制する。決定は監査ログに残す。
"""

from . import learning
from . import inhibition
from . import safety
from . import schemas

# 通常タスク実行中に自動変更してはならない対象（§9）。executive でも自動改変不可。
PROTECTED_TARGETS = [
    "SKILL.md", "constitution", "safety_policy", "approval_requirements",
    "permissions", "hooks", "mcp_config", "learning_rate_caps",
    "promotion_conditions", "external_send_rules", "deletion_rules",
    "secret_handling_rules",
]


def is_protected_target(target):
    t = (target or "").lower()
    return any(p.lower() in t for p in PROTECTED_TARGETS)


def authorize_promotion(mem, target_level, evidence, snapshot=None, approver=None,
                        human_approval=False):
    """記憶の昇格を認可するか判定する（§8/§9/§10 の全ゲートを統合）。

    戻り値: {authorized, requires_human, reasons, gate}
    """
    reasons = []
    ev = dict(evidence or {})
    # L4/L5（行動規則・憲法）は人間承認を必須にする。
    high_level = target_level in ("L4", "L5")
    if high_level:
        ev["human_approval"] = bool(human_approval)

    gate_ok, gate_reasons = learning.promotion_gate(mem, target_level, ev)
    reasons.extend(gate_reasons)

    # 抑制系: 未信頼源・must_not_promote・過学習の恐れは規則昇格を遮断（§10/§K）。
    if high_level and snapshot is not None:
        blocked, block_reasons = inhibition.promotion_blocked(mem, snapshot)
        if blocked:
            reasons.extend(block_reasons)

    requires_human = high_level
    authorized = (len(reasons) == 0) and (not high_level or human_approval)
    if high_level and not human_approval:
        reasons.append("L4/L5 は人間の明示承認が必要（未承認）")

    return {"authorized": authorized, "requires_human": requires_human,
            "reasons": reasons, "target_level": target_level,
            "approver": approver if authorized else None}


def guard_self_modification(proposal):
    """自己改変提案が「候補どまり」の要件を満たすか検査する（§9）。

    - 保護対象（SKILL.md/憲法/安全規則等）への変更は、通常経路では自動適用不可。
    - §9 チェックリスト（回帰/セキュリティ/sandbox/人間承認/canary/rollback）が
      すべて揃うまで applied にできない。
    戻り値: {may_apply, requires_human, reasons}
    """
    reasons = []
    ptype = proposal.get("type")
    target = (proposal.get("diff") or {}).get("target") if isinstance(
        proposal.get("diff"), dict) else None
    if ptype == "skill_change" or is_protected_target(target):
        reasons.append("保護対象への変更: 通常実行中の自動適用は禁止（人間ゲート必須）")
    checklist = proposal.get("checklist") or {}
    required = ["regression_test", "security_test", "sandbox_run",
               "human_approval", "canary", "rollback_prepared"]
    missing = [k for k in required if not checklist.get(k)]
    if missing:
        reasons.append("チェックリスト未達: %s" % ", ".join(missing))
    may_apply = (len(reasons) == 0)
    return {"may_apply": may_apply, "requires_human": True, "reasons": reasons}


def gate_action(candidate, context=None):
    """危険操作の実行可否をゲートする（衝動的自動実行の抑制・§J）。"""
    sa = safety.assess({"operations": candidate.get("operations"),
                        "reversible": candidate.get("reversible"),
                        "sensitivity": candidate.get("sensitivity")})
    allow_auto = not sa["requires_approval"] and sa["danger"] < safety_high()
    return {"allow_auto_execute": allow_auto, "requires_approval":
            not allow_auto, "safety": sa}


def safety_high():
    return 0.8
