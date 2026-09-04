# -*- coding: utf-8 -*-
"""procedural_memory — 手続記憶（仕様 §F）。

【生物学的知見】反復して成功する行動系列は、線条体・皮質を含む回路で自動化され、
宣言的な想起を要さず実行できるようになると考えられている。
【計算論的抽象化】手続 = 開始条件・前提・手順・期待結果・検証法・失敗時処理・
ロールバック・適用禁止条件・必要承認 を持つ構造。適用前に必ず適用範囲を照合する。
【実装上の近似】手続は promotion(L4) を経てのみ active になる。自動適用の前に
applicability() が禁止条件・前提・スコープ・危険度を照合し、危険手続は承認ゲートへ。
"""

# 手続記憶が必ず備えるべきフィールド（§F）。欠けると L4 昇格を拒否する。
REQUIRED_PROCEDURE_FIELDS = [
    "start_conditions", "preconditions", "steps", "expected_result",
    "verification", "on_failure", "rollback", "forbidden_conditions",
    "required_approval",
]


def missing_fields(procedure):
    """手続記憶に欠けている必須フィールドを返す（空なら完備・L4 昇格の門）。"""
    content = procedure.get("content") or procedure
    return [f for f in REQUIRED_PROCEDURE_FIELDS if not content.get(f)]


def applicability(procedure, context):
    """適用可否を判定し {applicable, reasons, needs_approval} を返す（自動適用前の照合）。

    context: {scope, facts:set/list, operations:list, risk:float}
    - 適用禁止条件(forbidden_conditions)に該当 → applicable=False
    - 前提(preconditions)を満たさない → applicable=False
    - スコープ不一致 → applicable=False
    - required_approval or 高危険操作 → needs_approval=True（危険だから拒否ではなく承認へ）
    """
    content = procedure.get("content") or procedure
    facts = set(context.get("facts") or [])
    ops = set(context.get("operations") or [])
    reasons = []
    applicable = True

    for fc in content.get("forbidden_conditions", []) or []:
        if fc in facts or fc in ops:
            applicable = False
            reasons.append("適用禁止条件に該当: %s" % fc)

    for pc in content.get("preconditions", []) or []:
        if pc not in facts:
            applicable = False
            reasons.append("前提を満たさない: %s" % pc)

    scope_req = content.get("applicable_scope") or procedure.get("scope")
    if scope_req and context.get("scope") and scope_req != context.get("scope"):
        applicable = False
        reasons.append("スコープ不一致: 手続=%s / 文脈=%s" % (scope_req, context.get("scope")))

    needs_approval = bool(content.get("required_approval"))
    from .safety import high_salience_hits
    if high_salience_hits(context.get("operations")):
        needs_approval = True
        reasons.append("高顕著性操作を含むため承認が必要")

    if procedure.get("status") not in ("active",):
        applicable = False
        reasons.append("手続が active でない（未昇格 L4 のみ自動適用可）")

    return {"applicable": applicable, "needs_approval": needs_approval,
            "reasons": reasons}
