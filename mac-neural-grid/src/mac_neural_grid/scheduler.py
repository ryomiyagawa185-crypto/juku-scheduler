# -*- coding: utf-8 -*-
"""scheduler — 能力ベースのノード選定（仕様 §11）。単純ラウンドロビンにしない。

node_score = capability_match × availability × trust × locality × historical_reliability
             − resource_pressure − network_cost
生の CPU 速度だけで選ばない。要件（arch/memory/tools/models）を満たさないノードは除外する。
"""

from . import health

_TRUST_SCORE = {"untrusted": 0.0, "low": 0.4, "medium": 0.7, "high": 1.0}


def capability_match(node, requirements):
    """要件充足度を返す（0..1）。必須要件を満たさなければ 0（＝除外）。"""
    req = requirements or {}
    cap = node.get("capabilities") or {}
    tools = cap.get("tools") or {}
    arch_req = req.get("architecture")
    if arch_req and cap.get("architecture") not in (arch_req, None):
        if cap.get("architecture") is not None:
            return 0.0
    mem_min = req.get("memory_gb_min")
    if mem_min is not None and cap.get("memory_gb") is not None and \
            cap["memory_gb"] < mem_min:
        return 0.0
    needed = req.get("capabilities") or []
    have = sum(1 for c in needed if tools.get(c))
    if needed and have < len(needed):
        return 0.0
    models_req = req.get("models") or []
    node_models = set(cap.get("models") or [])
    if models_req and not set(models_req) <= node_models:
        return 0.0
    labels_req = set(req.get("labels") or [])
    if labels_req and not labels_req <= set(node.get("labels") or []):
        return 0.0
    # 充足度: 必須は満たしている前提で、余裕（メモリ・ツール一致）を加点。
    score = 0.7
    if needed:
        score += 0.3 * (have / len(needed))
    else:
        score += 0.3
    return min(1.0, score)


def historical_reliability(db, node_id):
    """過去の attempt から成功率を推定（データが無ければ 0.8 の弱事前）。"""
    if db is None:
        return 0.8
    rows = db.conn.execute(
        "SELECT status,COUNT(*) c FROM attempts WHERE node_id=? GROUP BY status",
        (node_id,)).fetchall()
    total = sum(r["c"] for r in rows)
    if total == 0:
        return 0.8
    succ = sum(r["c"] for r in rows if r["status"] == "succeeded")
    # ラプラス平滑化。
    return round((succ + 4) / (total + 5), 4)


def score_node(node, requirements, policy=None, db=None, locality=1.0,
               network_cost=0.0):
    cm = capability_match(node, requirements)
    ok, reasons = health.assignable(node, policy)
    if cm <= 0.0 or not ok:
        return {"node_id": node["node_id"], "score": 0.0, "eligible": False,
                "reasons": (["能力要件を満たさない"] if cm <= 0 else []) + reasons,
                "capability_match": cm}
    availability = 1.0 - health.resource_pressure(node.get("capabilities"))
    trust = _TRUST_SCORE.get(node.get("trust"), 0.0)
    reliability = historical_reliability(db, node["node_id"])
    pressure = health.resource_pressure(node.get("capabilities"))
    score = cm * availability * trust * locality * reliability - pressure - network_cost
    return {"node_id": node["node_id"], "score": round(score, 4), "eligible": True,
            "capability_match": cm, "availability": round(availability, 4),
            "trust": trust, "historical_reliability": reliability,
            "resource_pressure": round(pressure, 4), "reasons": []}


def rank_nodes(nodes, requirements, policy=None, db=None, exclude=None):
    exclude = exclude or set()
    scored = [score_node(n, requirements, policy, db)
              for n in nodes if n["node_id"] not in exclude]
    eligible = [s for s in scored if s["eligible"]]
    eligible.sort(key=lambda s: (s["score"], s["node_id"]), reverse=True)
    return eligible, scored


def select_node(nodes, requirements, policy=None, db=None, exclude=None):
    """最良の割当先を1件返す（無ければ None）。説明可能な内訳つき。"""
    eligible, _all = rank_nodes(nodes, requirements, policy, db, exclude)
    return eligible[0] if eligible else None
