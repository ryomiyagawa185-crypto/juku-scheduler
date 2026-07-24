# -*- coding: utf-8 -*-
"""Integration: localhost Worker でのジョブ配送・回収・分散・cancel・retry・再起動復元（§33）。"""

import json
import os

import pytest

from tests.conftest import run


def _job_yaml(tmp_path, glob="*.txt", policy="confidential-local-only", n=2):
    """テストは JSON ジョブ仕様を使う（PyYAML の有無に依存させない）。YAML は別途 guarded で検証。"""
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(n):
        (docs / ("d%d.txt" % i)).write_text("見出し。一文目です。二文目です。三文目です。\n")
    spec = tmp_path / "job.json"
    spec.write_text(json.dumps({
        "name": "itest", "policy": policy,
        "tasks": [{"type": "document-summary", "input_glob": "docs/" + glob,
                   "split": "per-file", "executor": "document-summary",
                   "requirements": {"capabilities": []}}],
        "aggregation": {"type": "merge-summaries", "node": "control"}},
        ensure_ascii=False))
    return str(spec)


def test_shipped_yaml_example_loads(home):
    """同梱 examples/sample-job.yaml が読める（PyYAML がある時のみ・宣言依存）。"""
    pytest.importorskip("yaml")
    from mac_neural_grid import jobspec, schemas
    example = os.path.join(os.path.dirname(__file__), "..", "examples", "sample-job.yaml")
    spec = jobspec.load_job(example)
    assert spec["name"] == "pdf-summary"
    assert schemas.validate(spec, schemas.JOB_SCHEMA) == []


def test_single_worker_job(home, tmp_path):
    run(home, "init")
    _, dl = run(home, "node", "list")
    for nd in dl["nodes"]:
        run(home, "node", "inspect", nd["node_id"])
    spec = _job_yaml(tmp_path, n=2)
    code, res = run(home, "job", "run", spec)
    assert code == 0 and res["ok"]
    assert res["summary"]["succeeded"] == 2
    _, st = run(home, "job", "status", res["job_id"])
    assert st["status"] == "succeeded"
    _, arts = run(home, "artifacts", "--job", res["job_id"])
    assert len(arts["artifacts"]) == 2
    for a in arts["artifacts"]:
        assert os.path.exists(a["path"])


def test_two_workers_distribute(grid, tmp_path):
    grid["add_worker"]("worker-a")
    grid["add_worker"]("worker-b")
    spec = _job_yaml(tmp_path, n=4)
    code, res = grid["run"]("job", "run", spec)
    assert res["summary"]["succeeded"] == 4
    _, st = grid["run"]("job", "status", res["job_id"])
    used = {t["node_id"] for t in st["tasks"]}
    assert len(used) >= 2  # 複数ノードへ分散


def test_verify_clean_after_run(home, tmp_path):
    run(home, "init")
    _, dl = run(home, "node", "list")
    for nd in dl["nodes"]:
        run(home, "node", "inspect", nd["node_id"])
    spec = _job_yaml(tmp_path, n=2)
    run(home, "job", "run", spec)
    code, v = run(home, "verify")
    assert code == 0 and v["ok"], v.get("problems")


def test_cancel_job(home, tmp_path):
    run(home, "init")
    spec = _job_yaml(tmp_path, n=2)
    _, created = run(home, "job", "create", spec)
    code, res = run(home, "job", "cancel", created["job_id"])
    assert res["ok"]
    _, st = run(home, "job", "status", created["job_id"])
    assert st["status"] == "cancelled"


def test_control_restart_rebuilds_state(home, tmp_path, open_db):
    """Control 再起動後、events からタスク状態を再構築できる（§31）。"""
    run(home, "init")
    _, dl = run(home, "node", "list")
    for nd in dl["nodes"]:
        run(home, "node", "inspect", nd["node_id"])
    spec = _job_yaml(tmp_path, n=2)
    _, res = run(home, "job", "run", spec)
    # 新しい DB ハンドル（＝再起動相当）で events から状態を再構築。
    db = open_db(home)
    rebuilt = db.rebuild_state(res["job_id"])
    stored = {t["task_id"]: t["status"] for t in db.tasks_of(res["job_id"])}
    for tid, status in stored.items():
        if status == "succeeded":
            assert rebuilt.get(tid) == "succeeded"


def test_idempotent_create(home, tmp_path):
    run(home, "init")
    spec = _job_yaml(tmp_path, n=2)
    _, a = run(home, "job", "create", spec)
    _, b = run(home, "job", "create", spec)
    assert a["job_id"] == b["job_id"] and b["reused"] is True
