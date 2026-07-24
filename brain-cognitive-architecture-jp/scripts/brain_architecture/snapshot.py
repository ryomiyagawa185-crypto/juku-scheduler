# -*- coding: utf-8 -*-
"""snapshot — event log から派生記憶状態を replay で再構築する（仕様 §15）。

正本＝append-only イベントログ。snapshot は決定的な純関数で再生成される派生物。
同じイベント集合と同じ as_of なら、挿入順・実行時刻に依らず必ず同一 snapshot に
なる（generated_at は含めない＝決定的）。忘却/信頼度は as_of 依存の derived として
毎回計算する（raw は改竄しない）。
"""

import hashlib

from . import schemas
from . import event_store
from . import episodic_memory
from . import semantic_memory
from . import learning
from . import validation
from . import __version__, __schema_version__


def _latest_date(events):
    dates = [str(e.get("occurred_at", ""))[:10] for e in events if e.get("occurred_at")]
    return max(dates) if dates else None


def _edge_id(scope, source, target, relation):
    key = "%s|%s|%s|%s" % (scope, source, target, relation)
    return "edge_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _apply_relations(edges, event):
    """observation payload に宣言された型付き関係を raw 証拠として集計する。"""
    payload = event.get("payload") or {}
    scope = event.get("scope", "project")
    for r in payload.get("relations", []) or []:
        if not isinstance(r, dict):
            continue
        s, t = r.get("source"), r.get("target")
        rel = r.get("relation") or r.get("type")
        if not (s and t) or rel not in schemas.RELATION_TYPES or s == t:
            continue
        eid = _edge_id(scope, s, t, rel)
        e = edges.get(eid)
        if e is None:
            e = {"edge_id": eid, "source": s, "target": t, "relation": rel,
                 "direction": schemas.RELATION_TYPES[rel]["direction"], "scope": scope,
                 "raw": {"evidence_count": 0}, "derived": {}, "status": "active",
                 "evidence_ids": []}
            edges[eid] = e
        if event["event_id"] not in e["evidence_ids"]:
            e["evidence_ids"].append(event["event_id"])
            e["evidence_ids"].sort()
            e["raw"]["evidence_count"] += 1


def _apply_inhibition(edges, event):
    """inhibition イベントを抑制性エッジとして刻む（安全critical・外部依存しない）。"""
    payload = event.get("payload") or {}
    s, t = payload.get("source"), payload.get("target")
    rel = payload.get("relation", "inhibits")
    scope = event.get("scope", "project")
    if not (s and t) or rel not in schemas.INHIBITORY_RELATIONS:
        return
    eid = _edge_id(scope, s, t, rel)
    e = edges.get(eid)
    if e is None:
        e = {"edge_id": eid, "source": s, "target": t, "relation": rel,
             "direction": schemas.RELATION_TYPES[rel]["direction"], "scope": scope,
             "raw": {"evidence_count": 0, "declared_strength": payload.get("strength", 1.0)},
             "derived": {}, "status": "active", "evidence_ids": [],
             "reason": payload.get("reason")}
        edges[eid] = e
    if event["event_id"] not in e["evidence_ids"]:
        e["evidence_ids"].append(event["event_id"])
        e["evidence_ids"].sort()
        e["raw"]["evidence_count"] += 1


def rebuild(paths, scope=None, as_of=None, include_future=False):
    """event log を replay して snapshot dict を返す（純関数・決定的）。"""
    events = event_store.all_events(paths, scope=scope, include_future=include_future)
    as_of = as_of or _latest_date(events) or validation.parse_dt(
        event_store.now_iso()).date().isoformat()

    memories = {}
    edges = {}
    for ev in events:
        kind = ev.get("kind")
        if kind == "observation":
            episodic_memory.apply_observation(memories, ev)
            _apply_relations(edges, ev)
        elif kind == "promotion":
            semantic_memory.apply_promotion(memories, ev)
        elif kind == "retraction":
            semantic_memory.apply_retraction(memories, ev)
        elif kind == "inhibition":
            _apply_inhibition(edges, ev)
        # note / feedback は監査・派生計算側で扱い、truth を変えない。

    # feedback イベントで既存記憶の success/failure を更新（予測誤差の観測）。
    for ev in events:
        if ev.get("kind") == "feedback":
            _apply_feedback(memories, ev)

    # 派生値（confidence / retrievability / forgetting）を as_of で毎回計算。
    for m in memories.values():
        m["confidence"] = learning.derive_confidence(m)
        d = m.setdefault("derived", {})
        d["retrievability"] = learning.retrievability(m, as_of)
        d["forgetting"] = learning.forgetting_action(m, as_of)
        d["protected"] = learning.is_protected(m)

    # 恒常性可塑性（派生 weight のみ縮小）と抑制性エッジの強度。
    for e in edges.values():
        d = e.setdefault("derived", {})
        cnt = (e.get("raw") or {}).get("evidence_count", 0)
        base = 1.0 - pow(2.718281828, -cnt / 3.0)
        if e["relation"] in schemas.INHIBITORY_RELATIONS:
            base = max(base, float((e.get("raw") or {}).get("declared_strength", 1.0)))
        d["strength"] = round(base, 4)
    learning.homeostatic_scale(list(edges.values()))

    # 矛盾検出（derived のみ。truth は変えない・§E/§L）。
    conflicts = semantic_memory.detect_conflicts(memories)
    conflict_ids = set()
    for c in conflicts:
        conflict_ids.update(c["memory_ids"])
    for mid in conflict_ids:
        memories[mid].setdefault("derived", {})["in_conflict"] = True

    snap = {
        "schema_version": __schema_version__,
        "engine_version": __version__,
        "scope": scope or "all",
        "generated_at": None,   # 決定性のため実時刻は含めない
        "as_of": as_of,
        "event_count": len(events),
        "source_event_hash": event_store.ordered_event_hash(events),
        "memories": [memories[k] for k in sorted(memories)],
        "edges": [edges[k] for k in sorted(edges)],
        "working_memory": [],   # 作業記憶はセッション一時。snapshot には永続しない。
        "stats": {
            "n_memories": len(memories),
            "n_edges": len(edges),
            "n_conflicts": len(conflicts),
            "conflicts": conflicts,
            "by_type": _count_by(memories, "type"),
            "by_status": _count_by(memories, "status"),
            "by_level": _count_by(memories, "level"),
        },
    }
    return snap


def _apply_feedback(memories, event):
    payload = event.get("payload") or {}
    mid = payload.get("memory_id")
    mem = memories.get(mid)
    if mem is None:
        return
    outcome = payload.get("outcome", "unknown")
    q = schemas.OUTCOME_QUALITY.get(outcome, 0.5)
    if event["event_id"] in mem.get("evidence_ids", []):
        return
    mem.setdefault("evidence_ids", []).append(event["event_id"])
    mem["evidence_ids"].sort()
    if q >= 0.75:
        mem["success_count"] = mem.get("success_count", 0) + 1
        if outcome in schemas.VERIFIED_OUTCOMES:
            mem["last_verified_at"] = event.get("occurred_at")
    elif q < 0.5:
        mem["failure_count"] = mem.get("failure_count", 0) + 1
        if outcome in ("verified_failure", "user_rejected"):
            mem.setdefault("counterevidence_ids", []).append(event["event_id"])
            mem["counterevidence_ids"].sort()


def _count_by(memories, field):
    out = {}
    for m in memories.values():
        k = m.get(field)
        out[k] = out.get(k, 0) + 1
    return out
