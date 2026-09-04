# -*- coding: utf-8 -*-
"""作業記憶: 容量・自動脱落・リハーサル維持・目標無関係の削除・チャンク化。"""

from brain_architecture import working_memory as wm

T0 = "2026-07-23T10:00:00"


def _plus(iso, sec):
    return wm._plus_seconds(iso, sec)


def test_capacity_is_dynamic():
    assert wm.capacity(cognitive_load=0.0, avg_complexity=0.0) >= wm.capacity(
        cognitive_load=0.9, avg_complexity=0.9)
    assert wm.MIN_SLOTS <= wm.capacity(0.9, 0.9) <= wm.MAX_SLOTS


def test_over_capacity_evicts_lowest_activation():
    st = wm.new_state()
    for i in range(12):
        wm.load(st, "ref%d" % i, "goal", activation=0.3 + 0.05 * i, now=T0,
                cognitive_load=0.2)
    assert len(st["items"]) <= st["capacity"]


def test_rehearsal_maintains_item():
    st = wm.new_state()
    it = wm.load(st, "ref", "goal", activation=0.6, now=T0)
    later = _plus(T0, 900)  # 減衰後
    wm.rehearse(st, it["item_id"], now=later)
    assert wm.current_activation(st["items"][0], later) > 0.4


def test_decay_drops_expired():
    st = wm.new_state()
    wm.load(st, "ref", "goal", activation=0.6, ttl_seconds=60, now=T0)
    dropped = wm.decay(st, now=_plus(T0, 120))
    assert dropped and st["items"] == []


def test_evict_irrelevant_by_goal():
    st = wm.new_state()
    wm.load(st, "a", "goalA", now=T0)
    wm.load(st, "b", "goalB", now=T0)
    removed = wm.evict_irrelevant(st, "goalA")
    assert removed
    assert all(i["goal_id"] == "goalA" for i in st["items"])


def test_chunking_groups_by_goal():
    st = wm.new_state()
    wm.load(st, "a", "g1", now=T0)
    wm.load(st, "b", "g1", now=T0)
    wm.load(st, "c", "g2", now=T0)
    chunks = wm.chunk(st)
    assert set(chunks) == {"g1", "g2"}
    assert len(chunks["g1"]) == 2
