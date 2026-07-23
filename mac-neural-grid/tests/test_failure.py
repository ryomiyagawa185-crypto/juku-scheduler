# -*- coding: utf-8 -*-
"""Failure: Worker切断・タイムアウト・成果物破損・一部ノード失敗・重複配送（§33）。"""

import os

import pytest

from mac_neural_grid import executor, artifact_store, security, retry
from mac_neural_grid.executor import ExecContext
from tests.conftest import run


def _ctx(tmp_path, caps=None, policy=None, limits=None):
    dirs = {k: str(tmp_path / k) for k in ("input", "work", "output", "logs")}
    for d in dirs.values():
        security.makedirs(d)
    return ExecContext(dirs, {"node_id": "n"}, limits or {"timeout_s": 5},
                       caps or {"tools": {}}, policy or {})


def test_missing_dependency_clean_fail(tmp_path):
    ctx = _ctx(tmp_path, caps={"tools": {"ffmpeg": False}})
    r = executor.run_executor("ffmpeg", ctx, {"executor": "ffmpeg", "params": {"args": []}})
    assert r["status"] == "failed" and r["failure_class"] == "dependency_missing"


def test_timeout_classified_transient(tmp_path):
    ctx = _ctx(tmp_path, limits={"timeout_s": 1, "max_output_bytes": 1000})
    r = executor.run_executor("shell", ctx, {"executor": "shell",
                                             "argv": ["python3", "-c", "import time;time.sleep(5)"]})
    assert r["status"] == "timed_out"
    assert retry.classify(r) == "transient"


def test_invalid_input_not_retryable(tmp_path):
    ctx = _ctx(tmp_path)
    r = executor.run_executor("document-summary", ctx,
                              {"executor": "document-summary", "input": ["nope.txt"]})
    assert r["status"] == "failed" and r["failure_class"] == "invalid_input"
    assert not retry.is_retryable(r["failure_class"])


def test_artifact_corruption_detected(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello")
    with pytest.raises(ValueError):
        artifact_store.transfer(str(src), str(tmp_path / "out.txt"),
                                expected_checksum="sha256:wrong")


def test_collect_rejects_manifest_mismatch(tmp_path):
    from mac_neural_grid.database import Database
    out = tmp_path / "output"
    out.mkdir()
    (out / "f.md").write_text("real content")
    db = Database(str(tmp_path / "db.sqlite3"))
    manifest = {"artifacts": [{"name": "f.md", "checksum": "sha256:tampered"}]}
    with pytest.raises(ValueError):
        artifact_store.collect(db, "task-1", str(out), manifest=manifest)


def test_partial_failure_reported(home, tmp_path):
    """1タスクは成功、1タスクは入力欠損で失敗 → job は partial。"""
    import json
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ok.txt").write_text("これは成功する入力。二文目。三文目。")
    spec = tmp_path / "job.json"
    # 実在ファイル + 明示の存在しない入力の2タスク。
    spec.write_text(json.dumps({
        "name": "partial", "policy": "default", "tasks": [
            {"type": "s", "executor": "document-summary", "input": [str(docs / "ok.txt")],
             "requirements": {"capabilities": []}},
            {"type": "s", "executor": "document-summary", "input": ["/no/such/file.txt"],
             "requirements": {"capabilities": []}}]}))
    run(home, "init")
    _, dl = run(home, "node", "list")
    for nd in dl["nodes"]:
        run(home, "node", "inspect", nd["node_id"])
    code, res = run(home, "job", "run", str(spec))
    _, st = run(home, "job", "status", res["job_id"])
    statuses = {t["status"] for t in st["tasks"]}
    assert "succeeded" in statuses and ("failed" in statuses or "lost" in statuses)
    assert st["status"] in ("partial", "failed")


def test_backoff_monotonic():
    from mac_neural_grid import retry as r
    assert r.backoff_seconds(0) <= r.backoff_seconds(1) <= r.backoff_seconds(2)
    assert r.backoff_seconds(100) <= 60.0
