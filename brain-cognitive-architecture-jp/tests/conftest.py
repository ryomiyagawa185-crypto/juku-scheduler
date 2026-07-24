# -*- coding: utf-8 -*-
"""pytest 共有フィクスチャ。scripts/ を import path に載せ、隔離した記憶ストアを用意する。"""

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(_HERE, "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, os.path.abspath(_SCRIPTS))

from brain_architecture import paths as paths_mod        # noqa: E402
from brain_architecture import event_store               # noqa: E402

# 決定性のため固定した「現在時刻」。将来時刻検出はこれを基準にする。
NOW = "2026-07-23T00:00:00"


@pytest.fixture()
def base_dir(tmp_path):
    return str(tmp_path / "brain-memory")


@pytest.fixture()
def paths(base_dir):
    p = paths_mod.resolve(base_dir, "project")
    paths_mod.ensure_dirs(p)
    return p


@pytest.fixture()
def observe(paths):
    """観測イベントを直接 append するヘルパ（occurred_at を自動でずらす）。"""
    counter = {"n": 0}

    def _obs(goal="g", situation="s", action="a", outcome="verified_success",
             source_trust="verified_local", scope="project", partition=None,
             occurred_at=None, day=None, kind="observation", extra=None, now=NOW):
        counter["n"] += 1
        if occurred_at is None:
            d = day or "2026-07-%02d" % (1 + (counter["n"] % 27))
            occurred_at = "%sT%02d:00:00" % (d, counter["n"] % 24)
        payload = {"goal": goal, "situation": situation, "action": action,
                   "outcome": outcome}
        if extra:
            payload.update(extra)
        p = paths_mod.resolve(paths["base"], scope)
        ev, status = event_store.append_event(
            p, kind, scope, payload, source="test", source_trust=source_trust,
            occurred_at=occurred_at, partition=partition, now=now)
        return ev, status
    return _obs
