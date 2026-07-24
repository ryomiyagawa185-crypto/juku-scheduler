# -*- coding: utf-8 -*-
"""event_store: 重複防止・content-addressed id・順序・サニタイズ。"""

from brain_architecture import event_store, paths as paths_mod
from tests.conftest import NOW


def test_exact_duplicate_is_suppressed(paths):
    ev1, s1 = event_store.append_event(paths, "observation", "project",
                                       {"goal": "g", "action": "a"},
                                       occurred_at="2026-07-01T10:00:00", now=NOW)
    ev2, s2 = event_store.append_event(paths, "observation", "project",
                                       {"goal": "g", "action": "a"},
                                       occurred_at="2026-07-01T10:00:00", now=NOW)
    assert s1 == "accepted"
    assert s2 == "duplicate"
    assert ev1["event_id"] == ev2["event_id"]
    assert len(event_store.all_events(paths)) == 1


def test_distinct_time_not_duplicate(paths):
    event_store.append_event(paths, "observation", "project", {"goal": "g"},
                             occurred_at="2026-07-01T10:00:00", now=NOW)
    event_store.append_event(paths, "observation", "project", {"goal": "g"},
                             occurred_at="2026-07-02T10:00:00", now=NOW)
    assert len(event_store.all_events(paths)) == 2


def test_ids_are_well_formed(paths):
    ev, _ = event_store.append_event(paths, "observation", "project", {"x": 1},
                                     occurred_at="2026-07-01T10:00:00", now=NOW)
    assert ev["event_id"].startswith("evt_")
    assert len(ev["event_id"]) == 20


def test_partition_isolation_in_id(paths):
    a, _ = event_store.append_event(paths, "observation", "client", {"g": "x"},
                                    occurred_at="2026-07-01T10:00:00",
                                    partition="acme", now=NOW)
    b, _ = event_store.append_event(paths, "observation", "client", {"g": "x"},
                                    occurred_at="2026-07-01T10:00:00",
                                    partition="globex", now=NOW)
    # 同内容・同時刻でもパーティションが違えば別イベント（消えない）。
    assert a["event_id"] != b["event_id"]
    assert len(event_store.all_events(paths)) == 2


def test_sanitization_strips_secret(paths):
    ev, _ = event_store.append_event(
        paths, "observation", "project",
        {"note": "my key is sk-ABCDEFGHIJKLMNOPQRSTUV and password=hunter2"},
        occurred_at="2026-07-01T10:00:00", now=NOW)
    assert ev["contains_sensitive_data"] is True
    dumped = str(ev["payload"])
    assert "hunter2" not in dumped
    assert "sk-ABCDEFGHIJKLMNOPQRSTUV" not in dumped
    assert "REDACTED" in dumped


def test_order_independent_hash(paths):
    ev_specs = [("2026-07-03T10:00:00", {"a": 1}),
                ("2026-07-01T10:00:00", {"b": 2}),
                ("2026-07-02T10:00:00", {"c": 3})]
    for oa, pl in ev_specs:
        event_store.append_event(paths, "observation", "project", pl,
                                 occurred_at=oa, now=NOW)
    h1 = event_store.ordered_event_hash(event_store.all_events(paths))

    # 別ストアへ逆順で入れても同じ順序ハッシュになる。
    p2 = paths_mod.resolve(paths["base"] + "-2", "project")
    paths_mod.ensure_dirs(p2)
    for oa, pl in reversed(ev_specs):
        event_store.append_event(p2, "observation", "project", pl,
                                 occurred_at=oa, now=NOW)
    h2 = event_store.ordered_event_hash(event_store.all_events(p2))
    assert h1 == h2


def test_future_event_quarantined(paths):
    ev, status = event_store.append_event(paths, "observation", "project", {"g": "g"},
                                          occurred_at="2099-01-01T00:00:00", now=NOW)
    assert status == "quarantined"
    assert ev["quarantined"] is True
    # 既定 replay からは除外される。
    visible = event_store.all_events(paths, include_future=False)
    assert ev["event_id"] not in {e["event_id"] for e in visible}
