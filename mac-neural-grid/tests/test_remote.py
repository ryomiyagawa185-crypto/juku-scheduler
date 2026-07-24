# -*- coding: utf-8 -*-
"""Phase 2: SSH transport の argv 構築（injection 安全・host 鍵遵守）と、リモート配送の
制御フロー（ステージング→リモート Worker→フェッチ→checksum→collect）をネットワーク無しで検証。"""

import json
import os

import pytest

from mac_neural_grid import transport, security, dispatcher, ids, jobspec
from mac_neural_grid.database import Database
from tests.conftest import run


NODE = {"node_id": "node-mac-01", "host": "mac.local", "user": "operator",
        "transport": "ssh", "trust": "high", "enabled": True, "labels": ["trusted"],
        "capabilities": {"architecture": "arm64", "tools": {}, "models": [],
                         "current_load": {"active_jobs": 0}}}
SSH = {"strict_host_key_checking": "accept-new", "connect_timeout_s": 15, "batch_mode": True}


# ---------- 純関数 argv ビルダー ----------

def test_ssh_run_argv_honors_host_key_and_no_shell():
    argv = transport.ssh_run_argv(NODE, SSH, ["python3", "-m", "mac_neural_grid.worker"],
                                  env={"PYTHONPATH": "$HOME/.mac-neural-grid/pkg"})
    assert argv[0] == "ssh"
    assert "StrictHostKeyChecking=accept-new" in argv
    assert "BatchMode=yes" in argv
    assert "operator@mac.local" in argv
    # OpenSSH は destination 以降を command とするので `--` は付けない（remote へ literal 化しない）。
    assert "--" not in argv
    # argv 配列で渡す（シェル文字列連結でない）。
    assert argv[-3:] == ["python3", "-m", "mac_neural_grid.worker"]


def test_ssh_run_argv_rejects_space_arg():
    # 空白入りの引数は SSH 再分割で壊れるため拒否（python3 -c "code" を安全でない形で送らせない）。
    with pytest.raises(security.SecurityError):
        transport.ssh_run_argv(NODE, SSH, ["python3", "-c", "import os; print(1)"])


def test_ssh_no_strict_host_key_rejected():
    with pytest.raises(security.SecurityError):
        transport.ssh_opts({"strict_host_key_checking": "no"})


def test_ssh_target_rejects_injection():
    with pytest.raises(security.SecurityError):
        transport.ssh_target({"host": "mac.local; rm -rf /", "user": "op"})
    with pytest.raises(security.SecurityError):
        transport.ssh_target({"host": "mac.local", "user": "op$(whoami)"})


def test_rsync_argv_uses_ssh_and_delete():
    push = transport.rsync_push_argv(NODE, SSH, "/local/src/", "~/.mac-neural-grid/pkg/")
    assert push[0] == "rsync"
    assert "-e" in push
    e = push[push.index("-e") + 1]
    assert e.startswith("ssh ") and "StrictHostKeyChecking=accept-new" in e
    assert push[-1] == "operator@mac.local:~/.mac-neural-grid/pkg/"


def test_remote_inspect_entrypoint_prints_json():
    """リモートで実行される `python3 -m mac_neural_grid.discovery <id>` が能力 JSON を出す。"""
    import subprocess
    import sys
    src = os.path.dirname(os.path.dirname(os.path.abspath(transport.__file__)))
    r = subprocess.run([sys.executable, "-m", "mac_neural_grid.discovery", "node-x"],
                       env={**os.environ, "PYTHONPATH": src},
                       capture_output=True, text=True)
    assert r.returncode == 0
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert data["node_id"] == "node-x" and "tools" in data and "architecture" in data


def test_inspect_node_ssh_requires_allow_remote():
    from mac_neural_grid import discovery
    cap = discovery.inspect_node(NODE, allow_remote=False)
    assert cap.get("note") and "allow-remote" in cap["note"]


def test_ssh_transport_gated_without_approval():
    t = transport.SSHTransport(NODE, SSH, allow_remote=False)
    for call in (lambda: t.run(["ls"]),
                 lambda: t.put_file("/a", "/b"),
                 lambda: t.get_file("/a", "/b"),
                 lambda: t.ensure_worker()):
        with pytest.raises(security.SecurityError):
            call()


# ---------- リモート配送の制御フロー（sim transport で全経路）----------

def _make_job(home, tmp_path, n=3):
    run(home, "init")
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(n):
        (docs / ("d%d.txt" % i)).write_text("一文目。二文目。三文目。四文目。")
    spec = {"name": "remote-t", "policy": "confidential-local-only",
            "tasks": [{"type": "document-summary", "input": [str(docs / ("d%d.txt" % i))
                                                             for i in range(n)],
                       "executor": "document-summary", "requirements": {"capabilities": []}}]}
    # per-file 相当に分割するため input を1件ずつのタスクへ。
    spec["tasks"] = [{"type": "document-summary", "input": [str(docs / ("d%d.txt" % i))],
                      "executor": "document-summary", "requirements": {"capabilities": []}}
                     for i in range(n)]
    return spec


def test_remote_orchestration_end_to_end(home, tmp_path, open_db, paths_of):
    """ssh ノードへ sim transport で配送し、成果物を fetch して checksum 検証まで通す。"""
    spec = _make_job(home, tmp_path, n=3)
    # ssh ノードを登録（sim なので実接続しない）。
    run(home, "node", "add", "--host", "mac.local", "--user", "operator",
        "--transport", "ssh", "--name", "mac-01", "--trust", "high", "--labels", "trusted")
    db = open_db(home)
    paths = paths_of(home)
    # job を作成。
    jid = ids.job_id(spec["name"], ids.idempotency_key(spec["name"],
                     [i for t in spec["tasks"] for i in t["input"]], "confidential-local-only"))
    from mac_neural_grid import config as cfg
    policy = db.get_policy("confidential-local-only")
    db.create_job(jid, spec["name"], "confidential-local-only", spec,
                  ids.idempotency_key(spec["name"], "x", "p"), ids.policy_hash(policy))
    tasks, _ = jobspec.split_tasks(spec, str(tmp_path))
    for i, t in enumerate(tasks):
        db.create_task(ids.task_id(jid, i, jobspec.task_key(t, i)), jid, i, t["type"],
                       t["executor"], t, ids.input_hash(t.get("input") or []))

    # sim transport factory（別ディレクトリを「リモート」に見立てる）。
    remote_base = str(tmp_path / "REMOTE")

    def factory(node):
        return transport.LocalRemoteSimTransport(node, remote_base)

    result = dispatcher.dispatch_job(db, paths, jid, cfg.DEFAULT_CONFIG, policy,
                                     allow_remote=True, transport_factory=factory)
    assert result["ok"] and result["succeeded"] == 3, result
    # 成果物はローカルへ回収され checksum 登録済み。
    arts = db.artifacts_of(jid)
    assert len(arts) == 3
    for a in arts:
        assert os.path.exists(a["path"])
        assert security.sha256_file(a["path"]) == a["checksum"]
    # リモート側（sim）に作業が展開されたことを確認（= 実際にステージングされた）。
    assert os.path.isdir(os.path.join(remote_base, "jobs", jid))


def test_remote_denied_without_allow_remote(home, tmp_path, open_db, paths_of):
    """allow_remote=False（既定の for_node）だと ssh ノードは policy_denied で失敗する。"""
    spec = _make_job(home, tmp_path, n=1)
    _, added = run(home, "node", "add", "--host", "mac.local", "--user", "operator",
                   "--transport", "ssh", "--name", "mac-01", "--labels", "trusted")
    ssh_id = added["node"]["node_id"]
    # host 鍵確認済みとして trust を上げ、割当可能にする（そのうえで allow_remote 無しを検証）。
    run(home, "node", "trust", ssh_id, "--level", "high")
    # local ノードを無効化して ssh のみに。
    _, dl = run(home, "node", "list")
    for n in dl["nodes"]:
        if n["transport"] == "local":
            run(home, "node", "disable", n["node_id"])
    db = open_db(home)
    paths = paths_of(home)
    from mac_neural_grid import config as cfg
    policy = db.get_policy("confidential-local-only")
    jid = ids.job_id("d", "k")
    db.create_job(jid, "d", "confidential-local-only", spec, "k", ids.policy_hash(policy))
    tasks, _ = jobspec.split_tasks(spec, str(tmp_path))
    db.create_task(ids.task_id(jid, 0, "x"), jid, 0, tasks[0]["type"], tasks[0]["executor"],
                   tasks[0], ids.input_hash(tasks[0].get("input") or []))
    # allow_remote 未指定 → for_node が SSHTransport(allow_remote=False) を返し policy_denied。
    result = dispatcher.dispatch_job(db, paths, jid, cfg.DEFAULT_CONFIG, policy,
                                     allow_remote=False)
    statuses = {t["status"] for t in db.tasks_of(jid)}
    assert "failed" in statuses
