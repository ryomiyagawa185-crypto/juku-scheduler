# -*- coding: utf-8 -*-
"""性質ベース（決定的擬似ランダム）: 任意順序で同一 snapshot・不変条件の保持。

Math.random/実時刻に依存しないよう、決定的な擬似乱数（線形合同法）で並べ替える。
"""

import itertools
import json

from brain_architecture import event_store, snapshot as snap_mod, paths as paths_mod
from tests.conftest import NOW

SPECS = [
    ("2026-07-01T10:00:00", {"goal": "g1", "situation": "s1", "action": "a1",
                             "outcome": "verified_success"}),
    ("2026-07-02T11:00:00", {"goal": "g1", "situation": "s1", "action": "a1",
                             "outcome": "verified_failure"}),
    ("2026-07-02T11:00:00", {"goal": "g2", "situation": "s2", "action": "a2",
                             "outcome": "unverified"}),
    ("2026-07-03T09:00:00", {"goal": "g3", "situation": "s3", "action": "a3",
                             "outcome": "retry_recovered"}),
    ("2026-07-01T10:00:00", {"goal": "g4", "situation": "s4", "action": "a4",
                             "outcome": "user_rejected"}),
]


def _build(base, order):
    p = paths_mod.resolve(base, "project")
    paths_mod.ensure_dirs(p)
    for i in order:
        oa, pl = SPECS[i]
        event_store.append_event(p, "observation", "project", pl,
                                 source_trust="verified_local", occurred_at=oa, now=NOW)
    return snap_mod.rebuild(p, scope="project", as_of="2026-08-01")


def test_all_permutations_same_snapshot(tmp_path):
    ref = None
    for k, perm in enumerate(itertools.permutations(range(len(SPECS)))):
        snap = _build(str(tmp_path / ("p%d" % k)), perm)
        blob = json.dumps({"m": snap["memories"], "e": snap["edges"],
                           "h": snap["source_event_hash"]}, sort_keys=True)
        if ref is None:
            ref = blob
        else:
            assert blob == ref, "順序 %s で snapshot が変化した" % (perm,)
        if k >= 24:  # 5! = 120。24 通りで十分な網羅。
            break


def test_invariants_hold(tmp_path):
    snap = _build(str(tmp_path / "inv"), range(len(SPECS)))
    for m in snap["memories"]:
        assert 0.0 <= m["confidence"] <= 1.0
        assert m["memory_id"].startswith("mem_")
        r = m["derived"]["retrievability"]
        assert 0.0 <= r <= 1.0
        assert m["success_count"] >= 0 and m["failure_count"] >= 0
    for e in snap["edges"]:
        assert e["edge_id"].startswith("edge_")
        assert "raw" in e
