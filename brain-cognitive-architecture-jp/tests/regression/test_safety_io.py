# -*- coding: utf-8 -*-
"""安全性: symlink 拒否・path traversal・競合書込・中断復旧・壊れたJSON・巨大入力・
dry-run 無副作用・rollback。"""

import json
import os
import threading

import pytest

from brain_architecture import secure_io, event_store, paths as paths_mod
from tests.conftest import NOW


def test_symlink_write_refused(tmp_path):
    target = tmp_path / "real.json"
    target.write_text("{}")
    link = tmp_path / "link.json"
    os.symlink(str(target), str(link))
    with pytest.raises(OSError):
        secure_io.atomic_write(str(link), "malicious")


def test_atomic_write_permissions(tmp_path):
    p = str(tmp_path / "d" / "f.json")
    secure_io.atomic_write_json(p, {"a": 1})
    mode = os.stat(p).st_mode & 0o777
    assert mode == 0o600
    parent_mode = os.stat(os.path.dirname(p)).st_mode & 0o777
    assert parent_mode == 0o700


def test_path_traversal_scope_rejected(tmp_path):
    with pytest.raises(ValueError):
        paths_mod.resolve(str(tmp_path), "../../etc")


def test_broken_jsonl_line_skipped(paths):
    event_store.append_event(paths, "observation", "project", {"g": "ok"},
                             occurred_at="2026-07-01T10:00:00", now=NOW)
    shard = paths_mod.event_shard(paths, "2026-07")
    with open(shard, "a", encoding="utf-8") as f:
        f.write("{not valid json\n")
    evs = event_store.all_events(paths)
    assert len(evs) == 1  # 壊れた行は飛ばす


def test_concurrent_appends_serialize(paths):
    def worker(i):
        event_store.append_event(paths, "observation", "project", {"n": i},
                                 occurred_at="2026-07-01T%02d:00:00" % i, now=NOW)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(event_store.all_events(paths)) == 10


def test_huge_input_handled(paths):
    big = "x" * 200000
    ev, status = event_store.append_event(paths, "observation", "project",
                                          {"blob": big},
                                          occurred_at="2026-07-01T10:00:00", now=NOW)
    assert status == "accepted"


def test_backup_and_rollback(tmp_path):
    target = str(tmp_path / "memory.json")
    secure_io.atomic_write_json(target, {"v": 1})
    backups = str(tmp_path / "backups")
    bpath, digest = secure_io.backup_file(target, backups, label="t")
    assert bpath and os.path.exists(bpath + ".sha256")
    secure_io.atomic_write_json(target, {"v": 2})
    data = open(bpath, "rb").read()
    assert secure_io.sha256_bytes(data) == digest
    secure_io.atomic_write_bytes(target, data)
    assert json.load(open(target)) == {"v": 1}


def test_interrupt_leaves_no_partial(tmp_path, monkeypatch):
    target = str(tmp_path / "f.json")
    secure_io.atomic_write_json(target, {"ok": 1})

    real_replace = os.replace

    def boom(a, b):
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        secure_io.atomic_write_json(target, {"broken": 1})
    monkeypatch.setattr(os, "replace", real_replace)
    # 元ファイルは無傷、tmp は残らない。
    assert json.load(open(target)) == {"ok": 1}
    leftovers = [f for f in os.listdir(tmp_path) if f.startswith(".brain-")]
    assert leftovers == []
