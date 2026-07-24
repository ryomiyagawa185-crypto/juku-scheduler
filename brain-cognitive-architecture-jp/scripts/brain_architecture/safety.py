# -*- coding: utf-8 -*-
"""safety — 扁桃体・顕著性評価に着想を得た安全層（仕様 §I）。

【生物学的知見】扁桃体・顕著性ネットワークは、危険や損失に関わる刺激へ優先的に
注意を割り当てると考えられている（恐怖専用装置ではない）。
【計算論的抽象化】高顕著性(high-salience)と高危険度(high-danger)を別軸で評価する。
高顕著性 ⇒ 自動拒否ではなく承認ゲートへ送る。過去の重大失敗を優先想起し、
過剰警戒(over-vigilance)は補正する。
【実装上の近似】操作タグの集合照合と、不可逆性/機密性の加点による説明可能なスコア。
本層は「拒否」ではなく「承認要求と注意喚起」を返す（判断は executive／人間）。
"""

from . import schemas

# 不可逆・拡散しやすい操作は危険度を上げる（顕著性とは別軸）。
_DANGER_WEIGHTS = {
    "delete": 0.9, "overwrite": 0.7, "external_send": 0.8,
    "credential_handling": 0.95, "permission_change": 0.85,
    "self_modification": 1.0, "multi_device_deploy": 0.9,
    "pii_processing": 0.7, "legal_decision": 0.8, "medical_decision": 0.9,
    "financial_decision": 0.85, "irreversible_config_change": 0.9,
}


def high_salience_hits(operations):
    """操作タグ集合のうち高顕著性(§I)に該当するものを返す。"""
    ops = set(operations or [])
    return sorted(ops & set(schemas.HIGH_SALIENCE_OPERATIONS))


def assess(context):
    """{salience, danger, hits, requires_approval, notes} を返す（説明可能な安全評価）。

    context: {operations:list, reversible:bool, sensitivity:str, evidence_quality:float}
    - salience: 注意を向けるべき度合い（該当操作数から）。
    - danger: 実際の危険度（不可逆性・機密性で加点）。
    - 高顕著性 ⇒ requires_approval=True（自動拒否ではない）。
    """
    ops = list(context.get("operations") or [])
    hits = high_salience_hits(ops)
    salience = min(1.0, 0.34 * len(hits)) if hits else _baseline_salience(context)
    danger = max([_DANGER_WEIGHTS.get(o, 0.0) for o in ops] + [0.0])
    if context.get("reversible") is False:
        danger = min(1.0, danger + 0.15)
    if context.get("sensitivity") == "high":
        danger = min(1.0, danger + 0.1)
        salience = min(1.0, salience + 0.1)
    # 過剰警戒補正: 証拠品質が高く可逆なら顕著性を少し下げる（§I 過剰警戒防止）。
    if context.get("reversible") is True and (context.get("evidence_quality") or 0) >= 0.8:
        salience = max(0.0, salience - 0.1)
    requires_approval = bool(hits) or danger >= 0.8
    notes = []
    if hits:
        notes.append("高顕著性操作: %s → 承認ゲートへ" % ", ".join(hits))
    if danger >= 0.8:
        notes.append("高危険度(%.2f): 不可逆/機密の可能性。ロールバック手段を確認。" % danger)
    return {"salience": round(salience, 3), "danger": round(danger, 3),
            "hits": hits, "requires_approval": requires_approval, "notes": notes}


def _baseline_salience(context):
    base = 0.1
    if context.get("sensitivity") == "high":
        base += 0.2
    return base


def recall_major_failures(memories, keywords=None, limit=5):
    """過去の重大失敗を優先的に想起する（§I）。verified_failure / counterevidence を持つ
    記憶を、失敗回数の多い順に返す。"""
    kws = set(k.lower() for k in (keywords or []))
    scored = []
    for m in memories:
        fails = m.get("failure_count", 0) + len(m.get("counterevidence_ids", []))
        if fails <= 0:
            continue
        text = " ".join(str(m.get(f, "")) for f in ("claim",)) + " " + \
            str((m.get("content") or {}))
        rel = 1.0 if not kws else (1.0 if any(k in text.lower() for k in kws) else 0.3)
        scored.append((fails * rel, m.get("memory_id"), m))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [m for _, _, m in scored[:limit]]
