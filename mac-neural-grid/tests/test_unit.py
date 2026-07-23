# -*- coding: utf-8 -*-
"""Unit: ノード選択・ポリシー判定・ジョブ分割・ID生成・checksum・retry分類・path検証（§33）。"""

import os

import pytest

from mac_neural_grid import (scheduler, policy_engine, jobspec, ids, security,
                             retry, model_router)


def _node(nid, arch="arm64", trust="high", mem=16, labels=None, tools=None,
          active_jobs=0):
    return {"node_id": nid, "display_name": nid, "host": "localhost",
            "transport": "local", "trust": trust, "enabled": True,
            "labels": labels or ["trusted"],
            "capabilities": {"architecture": arch, "memory_gb": mem,
                             "tools": tools or {}, "models": [],
                             "current_load": {"active_jobs": active_jobs}}}


# ---------- ノード選択（能力ベース・非ラウンドロビン）----------

def test_capability_match_excludes_unmet_requirements():
    n = _node("n1", arch="x86_64")
    assert scheduler.capability_match(n, {"architecture": "arm64"}) == 0.0
    assert scheduler.capability_match(_node("n2", arch="arm64"),
                                     {"architecture": "arm64"}) > 0


def test_memory_requirement_excludes():
    assert scheduler.capability_match(_node("n", mem=8), {"memory_gb_min": 16}) == 0.0


def test_select_prefers_higher_trust_and_lower_load():
    nodes = [_node("busy", active_jobs=4), _node("free", active_jobs=0)]
    sel = scheduler.select_node(nodes, {}, {}, db=None)
    assert sel["node_id"] == "free"


def test_untrusted_node_not_selected():
    nodes = [_node("u", trust="untrusted")]
    assert scheduler.select_node(nodes, {}, {}, db=None) is None


# ---------- ポリシー判定 ----------

def test_risk_classification():
    assert policy_engine.classify_task_risk({"executor": "checksum"}) == "read_only"
    assert policy_engine.classify_task_risk({"executor": "document-summary"}) == "reversible"
    assert policy_engine.classify_task_risk(
        {"executor": "shell", "argv": ["rm", "-rf", "x"]}) == "high_risk"
    assert policy_engine.classify_task_risk({"executor": "external-api"}) == "high_risk"


def test_policy_blocks_external_api():
    ev = policy_engine.evaluate(
        {"name": "j", "tasks": [{"type": "t", "executor": "external-api"}]},
        {"external_ai_api": False}, [])
    assert not ev["ok"] and ev["violations"]


# ---------- ジョブ分割 ----------

def test_split_per_file(tmp_path):
    for i in range(3):
        (tmp_path / ("f%d.txt" % i)).write_text("x")
    spec = {"name": "j", "tasks": [{"type": "t", "executor": "checksum",
                                    "input_glob": "*.txt", "split": "per-file"}]}
    tasks, agg = jobspec.split_tasks(spec, str(tmp_path))
    assert len(tasks) == 3
    assert all(len(t["input"]) == 1 for t in tasks)


def test_job_normalize_wrapper():
    data = jobspec.normalize({"job": {"name": "x", "policy": "p"}, "tasks": []})
    assert data["name"] == "x" and data["policy"] == "p"


# ---------- ID / 冪等 ----------

def test_node_id_not_ip_based():
    a = ids.node_id("mac", "192.168.1.10")
    b = ids.node_id("mac", "10.0.0.5")
    assert a != b  # host を含むが IP を「そのまま ID」にはしない
    assert a.startswith("node-mac-")


def test_idempotency_key_stable():
    k1 = ids.idempotency_key("job", ["a", "b"], "default")
    k2 = ids.idempotency_key("job", ["b", "a"], "default")
    assert k1 == k2  # 入力順に非依存


# ---------- checksum / retry / path ----------

def test_checksum(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"hello")
    assert security.sha256_file(str(p)) == security.sha256_bytes(b"hello")


def test_retry_classification():
    assert retry.is_retryable("transient")
    assert not retry.is_retryable("permission_denied")
    assert retry.should_retry("transient", 0, 2)
    assert not retry.should_retry("deterministic_failure", 0, 2)


def test_path_traversal_blocked(tmp_path):
    with pytest.raises(security.SecurityError):
        security.safe_join(str(tmp_path), "../../etc/passwd")
    assert security.safe_join(str(tmp_path), "a", "b").startswith(str(tmp_path))


def test_model_router_confidential_never_external():
    r = model_router.route({"type": "summary", "executor": "document-summary"},
                           {"external_ai_api": False}, {"tools": {}})
    assert r["external"] is False
