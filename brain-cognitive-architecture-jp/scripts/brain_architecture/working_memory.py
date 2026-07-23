# -*- coding: utf-8 -*-
"""working_memory — 作業記憶層（仕様 §C）。

【生物学的知見】作業記憶は容量が限られ（数チャンク）、リハーサルで維持され、
維持されない項目は減衰・脱落すると考えられている。
【計算論的抽象化】少量の項目のみ保持。容量は固定でなく認知負荷と項目複雑さで変わる。
活性は時間で減衰し、リハーサルで回復。目標と無関係になった項目は削除する。
【実装上の近似】活性の指数減衰＋容量超過時の最小活性 eviction。全記憶をここに載せない。
"""

import math

from . import event_store
from . import validation

BASE_SLOTS = 7
MIN_SLOTS = 3
MAX_SLOTS = 9
TAU_SECONDS = 600.0          # 活性の半減に相当する時定数
ACTIVATION_FLOOR = 0.15      # これ未満は脱落


def capacity(cognitive_load=0.3, avg_complexity=0.3):
    """動的容量（項目数）。負荷・複雑さが高いほど減る（§C 固定値にしない）。"""
    slots = BASE_SLOTS - 3.0 * _clamp(cognitive_load) - 2.0 * _clamp(avg_complexity)
    return int(max(MIN_SLOTS, min(MAX_SLOTS, round(slots))))


def _now(now):
    return now or event_store.now_iso()


def _seconds(a, b):
    da, db = validation.parse_dt(a), validation.parse_dt(b)
    if da is None or db is None:
        return 0.0
    return max(0.0, (validation._to_naive(db) - validation._to_naive(da)).total_seconds())


def current_activation(item, now):
    """last_rehearsed_at からの経過で活性を指数減衰させた値。"""
    base = float(item.get("activation", 0.5))
    age = _seconds(item.get("last_rehearsed_at") or item.get("loaded_at"), now)
    return round(base * math.exp(-age / TAU_SECONDS), 4)


def new_state():
    return {"items": [], "capacity": capacity()}


def load(state, content_ref, goal_id, activation=0.7, complexity=0.3,
         ttl_seconds=600, now=None, cognitive_load=0.3):
    """項目を作業記憶へロードする。容量超過なら最小活性項目を脱落させる。"""
    now = _now(now)
    items = state.setdefault("items", [])
    avg_c = (sum(i.get("complexity", 0.3) for i in items) + complexity) / (len(items) + 1)
    state["capacity"] = capacity(cognitive_load, avg_c)
    item = {
        "item_id": "wm_" + event_store.content_hash(
            {"ref": content_ref, "g": goal_id, "t": now}).split(":")[1][:16],
        "content_ref": content_ref, "goal_id": goal_id,
        "activation": _clamp(activation), "complexity": _clamp(complexity),
        "loaded_at": now, "last_rehearsed_at": now,
        "expires_at": _plus_seconds(now, ttl_seconds),
    }
    # 同一 content_ref は再ロードでなくリハーサル扱い。
    for it in items:
        if it["content_ref"] == content_ref and it["goal_id"] == goal_id:
            return rehearse(state, it["item_id"], now=now)
    items.append(item)
    _evict(state, now)
    return item


def rehearse(state, item_id, now=None, boost=0.3, ttl_seconds=600):
    """リハーサルで活性と期限を回復する（§C 維持）。"""
    now = _now(now)
    for it in state.get("items", []):
        if it["item_id"] == item_id:
            it["activation"] = _clamp(current_activation(it, now) + boost)
            it["last_rehearsed_at"] = now
            it["expires_at"] = _plus_seconds(now, ttl_seconds)
            return it
    return None


def decay(state, now=None):
    """期限切れ・低活性の項目を脱落させ、脱落 id のリストを返す（§C 自動脱落）。"""
    now = _now(now)
    now_dt = validation._to_naive(validation.parse_dt(now))
    kept, dropped = [], []
    for it in state.get("items", []):
        exp_dt = validation._to_naive(validation.parse_dt(it.get("expires_at")))
        expired = (now_dt is not None and exp_dt is not None and now_dt >= exp_dt)
        act = current_activation(it, now)
        if expired or act < ACTIVATION_FLOOR:
            dropped.append(it["item_id"])
        else:
            it["activation"] = act
            it["last_rehearsed_at"] = now
            kept.append(it)
    state["items"] = kept
    return dropped


def evict_irrelevant(state, current_goal_id):
    """現在の目標と無関係になった項目を削除する（§C）。"""
    items = state.get("items", [])
    removed = [it["item_id"] for it in items if it.get("goal_id") != current_goal_id]
    state["items"] = [it for it in items if it.get("goal_id") == current_goal_id]
    return removed


def _evict(state, now):
    """容量超過時、最小活性の項目から脱落させる。"""
    items = state["items"]
    cap = state.get("capacity", capacity())
    if len(items) <= cap:
        return
    items.sort(key=lambda it: current_activation(it, now), reverse=True)
    state["items"] = items[:cap]


def chunk(state, key_fn=None):
    """項目を goal_id（既定）でチャンク化して {chunk_key: [item_id,...]} を返す（§C）。"""
    key_fn = key_fn or (lambda it: it.get("goal_id"))
    out = {}
    for it in state.get("items", []):
        out.setdefault(key_fn(it), []).append(it["item_id"])
    return out


def _plus_seconds(iso, seconds):
    dt = validation.parse_dt(iso)
    if dt is None:
        return iso
    import datetime
    return (dt + datetime.timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


def _clamp(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0
