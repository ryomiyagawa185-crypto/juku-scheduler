# -*- coding: utf-8 -*-
"""episodic_memory — 海馬型エピソード記憶（仕様 §D）。

【生物学的知見】海馬は個別の出来事を時刻・状況とともに符号化し、パターン分離
（似た経験を別物として保つ）とパターン補完（部分手掛かりからの想起）を担うと
考えられている。
【計算論的抽象化】エピソードを (状況, 目的, 行動) の分離キーで同定し、結果は
success/failure として集計する。似て非なるエピソードは別 id になり混同しない。
【実装上の近似】分離キーは内容の決定的ハッシュ。挿入順に依存せず replay で一致する。
単一の成功事例を一般則へ自動昇格させない（意味記憶化は consolidate→promote 経由）。
"""

import hashlib
import json

from . import schemas

# エピソード内容として保持するキー（原文でなく構造化要約・§11）。
EPISODE_FIELDS = ["what", "situation", "goal", "action", "success_basis",
                  "failure_conditions", "applicable_scope", "confirmed_by"]


def _norm(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return " ".join(v.lower().split())
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def separation_key(payload, scope, partition=None):
    """パターン分離キー: (scope, partition, goal, situation, action) の決定的ハッシュ。

    結果(outcome)は含めない → 同一文脈の反復は同じエピソードへ集計され、
    success/failure の基準頻度を数えられる（§7 base-rate）。文言が少しでも
    異なれば別キー = 別エピソードとなり、似た経験を混同しない（§D）。partition を
    含めるので、別顧客の同内容エピソードが統合されない（§5 漏洩防止）。
    """
    parts = [scope, partition or "", _norm(payload.get("goal")),
             _norm(payload.get("situation")), _norm(payload.get("action"))]
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


def episode_id(key):
    return "mem_ep_" + key[:16]


def _extract_content(payload):
    return {k: payload[k] for k in EPISODE_FIELDS if k in payload}


def apply_observation(memories, event):
    """observation イベントをエピソード記憶へ集計する（replay の一手）。

    memories: {memory_id: memory} の可変 dict。将来時刻(quarantined)は呼出側で除外。
    """
    payload = event.get("payload") or {}
    scope = event.get("scope", schemas.SCOPES[2])
    key = separation_key(payload, scope, event.get("partition"))
    mid = episode_id(key)
    occurred = event.get("occurred_at", "")
    outcome = payload.get("outcome", "unknown")
    trust = event.get("source_trust", "untrusted_external")
    mem = memories.get(mid)
    if mem is None:
        mem = {
            "memory_id": mid, "type": "episodic", "level": "L0",
            "status": "observed", "scope": scope, "partition": event.get("partition"),
            "claim": None, "content": _extract_content(payload),
            "confidence": 0.0, "sensitivity": _sensitivity(event),
            "provenance": {"source": event.get("source"), "source_trust": trust},
            "evidence_ids": [], "counterevidence_ids": [],
            "success_count": 0, "failure_count": 0,
            "created_at": occurred, "last_verified_at": None,
            "last_used_at": occurred, "valid_from": occurred[:10] or None,
            "review_after": None, "retention_until": payload.get("retention_until"),
            "deletion_policy": "decay_then_archive",
            "derived": {"observation_count": 0, "trust_weights": []},
        }
        memories[mid] = mem
    # 集計（append-only の再生なので冪等・順序非依存にする）。
    if event["event_id"] not in mem["evidence_ids"]:
        mem["evidence_ids"].append(event["event_id"])
        mem["evidence_ids"].sort()
        mem["derived"]["observation_count"] += 1
        mem["derived"]["trust_weights"].append(schemas.TRUST_WEIGHT.get(trust, 0.2))
        q = schemas.OUTCOME_QUALITY.get(outcome, 0.5)
        if outcome in schemas.VERIFIED_OUTCOMES or q >= 0.75:
            if q >= 0.5:
                mem["success_count"] += 1
                if outcome in schemas.VERIFIED_OUTCOMES:
                    mem["last_verified_at"] = occurred
            else:
                mem["failure_count"] += 1
        elif q < 0.5:
            mem["failure_count"] += 1
        else:
            mem["success_count"] += 1  # unverified_completion 等は弱い成功として計上
    mem["created_at"] = min(mem["created_at"] or occurred, occurred)
    mem["last_used_at"] = max(mem["last_used_at"] or occurred, occurred)
    # 反証（明示の失敗結果イベント）を counterevidence に残す。
    if outcome in ("verified_failure", "user_rejected") and \
            event["event_id"] not in mem["counterevidence_ids"]:
        mem["counterevidence_ids"].append(event["event_id"])
        mem["counterevidence_ids"].sort()
    return mem


def _sensitivity(event):
    return "high" if event.get("contains_sensitive_data") else "none"
