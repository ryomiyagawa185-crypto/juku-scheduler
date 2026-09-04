# -*- coding: utf-8 -*-
"""semantic_memory — 大脳皮質型意味記憶（仕様 §E）。

【生物学的知見】新皮質は複数エピソードから統計的規則性を抽出し、安定した概念・
事実として長期に保持すると考えられている（記憶固定化の受け皿）。
【計算論的抽象化】意味記憶は「主張(claim) + 適用範囲 + 信頼度 + 出典 + 有効期限」。
矛盾する主張を同時に保持でき（conflicted）、時間変化する知識と安定知識を区別する。
【実装上の近似】意味記憶は observation から自動生成されない。consolidate が候補を
作り、executive の承認（promotion イベント）を経てのみ replay 時に構築される。
"""

from . import schemas


def apply_promotion(memories, event):
    """promotion イベントで意味/手続記憶を作成・更新する（承認済み変更・replay の一手）。

    payload = {memory: {...}, target_level, approver, evidence_ids, proposal_id}
    """
    payload = event.get("payload") or {}
    body = payload.get("memory") or {}
    mid = body.get("memory_id")
    if not mid:
        return None
    level = payload.get("target_level") or body.get("level") or "L2"
    status = schemas.LEVEL_TO_STATUS.get(level, "candidate")
    occurred = event.get("occurred_at", "")
    mem = memories.get(mid)
    if mem is None:
        mem = dict(body)
        mem.setdefault("type", "semantic")
        mem.setdefault("scope", event.get("scope", "project"))
        mem.setdefault("partition", event.get("partition"))
        mem.setdefault("content", None)
        mem.setdefault("success_count", 0)
        mem.setdefault("failure_count", 0)
        mem.setdefault("counterevidence_ids", [])
        mem.setdefault("created_at", occurred)
        mem.setdefault("provenance", {"source": event.get("source"),
                                      "source_trust": event.get("source_trust")})
        mem.setdefault("sensitivity", "high" if event.get("contains_sensitive_data")
                       else "none")
        mem.setdefault("deletion_policy", "review_then_archive")
        memories[mid] = mem
    # 承認による状態遷移（後勝ち＝occurred_at 順の replay で最終承認が反映される）。
    mem["level"] = level
    mem["status"] = status
    mem["claim"] = body.get("claim", mem.get("claim"))
    if body.get("content") is not None:
        mem["content"] = body.get("content")
    mem["valid_from"] = body.get("valid_from", mem.get("valid_from")) or occurred[:10]
    mem["review_after"] = body.get("review_after", mem.get("review_after"))
    mem["last_verified_at"] = occurred
    mem.setdefault("evidence_ids", [])
    for eid in payload.get("evidence_ids", []) + body.get("evidence_ids", []):
        if eid not in mem["evidence_ids"]:
            mem["evidence_ids"].append(eid)
    mem["evidence_ids"].sort()
    d = mem.setdefault("derived", {})
    d["approved_by"] = payload.get("approver")
    d["proposal_id"] = payload.get("proposal_id")
    d["promoted_at"] = occurred
    return mem


def apply_retraction(memories, event):
    """retraction イベントで記憶を deprecate/archive/reject/purge する（承認済み変更）。"""
    payload = event.get("payload") or {}
    mid = payload.get("memory_id")
    to_status = payload.get("to_status", "deprecated")
    mem = memories.get(mid)
    if mem is None or to_status not in schemas.STATUS:
        return None
    mem["status"] = to_status
    d = mem.setdefault("derived", {})
    d["retracted_reason"] = payload.get("reason")
    d["retracted_by"] = payload.get("approver")
    d["retracted_at"] = event.get("occurred_at")
    if to_status == "purged":
        # tombstone を残しつつ内容を破棄（完全削除・§7/§11）。
        mem["content"] = None
        mem["claim"] = None
    return mem


def detect_conflicts(memories):
    """同一 (scope, 正規化 claim topic) で contradictory な active 意味記憶を検出。

    ここでは「同じ主題キーで status/claim が両立しない」ものを conflicted 候補として
    返すのみ（自動改変はしない・consolidate/executive が扱う）。
    """
    conflicts = []
    by_topic = {}
    for m in memories.values():
        if m.get("type") != "semantic" or m.get("status") not in ("verified", "active"):
            continue
        topic = (m.get("scope"), _topic_key(m.get("claim")))
        by_topic.setdefault(topic, []).append(m)
    for topic, group in by_topic.items():
        claims = {(_topic_key(g.get("claim")), _polarity(g.get("claim"))) for g in group}
        polarities = {p for _, p in claims}
        if len(polarities) > 1:  # 肯定/否定が混在
            conflicts.append({"topic": topic[1], "scope": topic[0],
                              "memory_ids": sorted(g["memory_id"] for g in group)})
    return conflicts


def _topic_key(claim):
    if not claim:
        return ""
    toks = [t for t in "".join(c if c.isalnum() else " " for c in claim.lower()).split()
            if t not in ("not", "no", "never", "ない", "ではない", "でない")]
    return " ".join(sorted(set(toks)))[:120]


def _polarity(claim):
    if not claim:
        return "0"
    neg = any(n in claim for n in ("not ", "no ", "never", "ない", "ではない", "でない"))
    return "-" if neg else "+"
