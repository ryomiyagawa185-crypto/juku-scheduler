# -*- coding: utf-8 -*-
"""時系列: 過去追加・replay・同一時刻・タイムゾーン・順序非依存・将来時刻の拒否/隔離。"""

from brain_architecture import (event_store, snapshot as snap_mod,
                                paths as paths_mod, validation)
from tests.conftest import NOW


def test_same_timestamp_events_ordered_by_id(paths):
    a, _ = event_store.append_event(paths, "observation", "project", {"k": "a"},
                                    occurred_at="2026-07-01T10:00:00", now=NOW)
    b, _ = event_store.append_event(paths, "observation", "project", {"k": "b"},
                                    occurred_at="2026-07-01T10:00:00", now=NOW)
    evs = event_store.all_events(paths)
    ids = [e["event_id"] for e in evs]
    assert ids == sorted([a["event_id"], b["event_id"]])  # 決定的 tie-break


def test_timezone_normalized(paths):
    # 同じ瞬間を別オフセットで表す2イベントは、順序比較で一貫する。
    event_store.append_event(paths, "observation", "project", {"k": "utc"},
                             occurred_at="2026-07-01T09:00:00+00:00", now=NOW)
    event_store.append_event(paths, "observation", "project", {"k": "jst"},
                             occurred_at="2026-07-01T18:00:01+09:00", now=NOW)
    evs = event_store.all_events(paths)
    # jst(=09:00:01 UTC) は utc(09:00:00) の後になる。
    assert evs[0]["payload"]["k"] == "utc"
    assert evs[1]["payload"]["k"] == "jst"


def test_future_event_rejected_from_replay(paths):
    event_store.append_event(paths, "observation", "project",
                             {"goal": "past", "situation": "s", "action": "a",
                              "outcome": "verified_success"},
                             source_trust="verified_local",
                             occurred_at="2026-07-01T10:00:00", now=NOW)
    ev, status = event_store.append_event(
        paths, "observation", "project",
        {"goal": "future", "situation": "s", "action": "z"},
        occurred_at="2099-01-01T00:00:00", now=NOW)
    assert status == "quarantined"
    snap = snap_mod.rebuild(paths, scope="project")  # include_future=False 既定
    goals = {(m.get("content") or {}).get("goal") for m in snap["memories"]}
    assert "future" not in goals
    assert "past" in goals


def test_is_future_detection():
    assert validation.is_future("2099-01-01T00:00:00", now=NOW)
    assert not validation.is_future("2020-01-01T00:00:00", now=NOW)


def test_replay_reflects_backfilled_history(tmp_path):
    p = paths_mod.resolve(str(tmp_path / "m"), "project")
    paths_mod.ensure_dirs(p)
    event_store.append_event(p, "observation", "project",
                             {"goal": "g", "situation": "s", "action": "new",
                              "outcome": "verified_success"},
                             source_trust="verified_local",
                             occurred_at="2026-07-10T10:00:00", now=NOW)
    s_before = snap_mod.rebuild(p, scope="project", as_of="2026-07-31")
    # 後から過去の事実を追加（時間を巻き戻さず、ログに足して replay）。
    event_store.append_event(p, "observation", "project",
                             {"goal": "g", "situation": "s", "action": "new",
                              "outcome": "verified_success"},
                             source_trust="verified_local",
                             occurred_at="2026-07-05T10:00:00", now=NOW)
    s_after = snap_mod.rebuild(p, scope="project", as_of="2026-07-31")
    ep_before = next(m for m in s_before["memories"] if m["type"] == "episodic")
    ep_after = next(m for m in s_after["memories"] if m["type"] == "episodic")
    assert ep_after["success_count"] == ep_before["success_count"] + 1
    assert ep_after["created_at"] <= ep_before["created_at"]  # 最古が前倒し
