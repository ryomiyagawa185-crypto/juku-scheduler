# -*- coding: utf-8 -*-
"""回帰: replay 決定性・順序非依存・snapshot 安定。"""

import json

from brain_architecture import snapshot as snap_mod, event_store, paths as paths_mod
from tests.conftest import NOW

SPECS = [
    ("2026-07-03T10:00:00", {"goal": "g1", "situation": "s", "action": "a",
                             "outcome": "verified_success"}),
    ("2026-07-01T10:00:00", {"goal": "g2", "situation": "s", "action": "b",
                             "outcome": "verified_failure"}),
    ("2026-07-02T10:00:00", {"goal": "g1", "situation": "s", "action": "a",
                             "outcome": "verified_success"}),
]


def _fill(base, specs):
    p = paths_mod.resolve(base, "project")
    paths_mod.ensure_dirs(p)
    for oa, pl in specs:
        event_store.append_event(p, "observation", "project", pl,
                                 source="t", source_trust="verified_local",
                                 occurred_at=oa, now=NOW)
    return p


def test_rebuild_is_deterministic(tmp_path):
    p = _fill(str(tmp_path / "a"), SPECS)
    s1 = snap_mod.rebuild(p, scope="project", as_of="2026-08-01")
    s2 = snap_mod.rebuild(p, scope="project", as_of="2026-08-01")
    assert json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)


def test_insertion_order_independent(tmp_path):
    p1 = _fill(str(tmp_path / "fwd"), SPECS)
    p2 = _fill(str(tmp_path / "rev"), list(reversed(SPECS)))
    s1 = snap_mod.rebuild(p1, scope="project", as_of="2026-08-01")
    s2 = snap_mod.rebuild(p2, scope="project", as_of="2026-08-01")
    assert s1["source_event_hash"] == s2["source_event_hash"]
    # generated_at は両方 None なので memory/edge も一致する。
    assert json.dumps(s1["memories"], sort_keys=True) == \
        json.dumps(s2["memories"], sort_keys=True)


def test_adding_past_event_reflected_by_replay(tmp_path):
    base = str(tmp_path / "hist")
    p = _fill(base, SPECS)
    before = snap_mod.rebuild(p, scope="project", as_of="2026-08-01")
    # 過去日イベントを後から追加（snapshot を後退させず、ログに事実を足す）。
    event_store.append_event(p, "observation", "project",
                             {"goal": "g9", "situation": "old", "action": "z",
                              "outcome": "verified_success"},
                             source_trust="verified_local",
                             occurred_at="2026-06-15T10:00:00", now=NOW)
    after = snap_mod.rebuild(p, scope="project", as_of="2026-08-01")
    assert after["event_count"] == before["event_count"] + 1
    assert after["source_event_hash"] != before["source_event_hash"]
