# -*- coding: utf-8 -*-
"""Privacy: 機密ジョブが外部APIへ行かない・ログに秘密値が残らない・スコープ混入なし（§33/§30）。"""

import json

from mac_neural_grid import model_router, security, executor
from mac_neural_grid.executor import ExecContext
from tests.conftest import run


def test_confidential_never_routes_external():
    for ttype in ("summary", "analyze", "translate", "classify"):
        r = model_router.route({"type": ttype, "executor": "document-summary"},
                               {"external_network": False, "external_ai_api": False},
                               {"tools": {"claude_code": True}})
        assert r["external"] is False, ttype


def test_external_api_executor_denied_without_policy(tmp_path):
    dirs = {k: str(tmp_path / k) for k in ("input", "work", "output", "logs")}
    for d in dirs.values():
        security.makedirs(d)
    ctx = ExecContext(dirs, {"node_id": "n"}, {}, {"tools": {}},
                      {"external_ai_api": False})
    r = executor.run_executor("external-api", ctx, {"executor": "external-api"})
    assert r["status"] == "failed" and r["failure_class"] == "policy_denied"


def test_secrets_not_in_logs(home, tmp_path):
    """秘密値を含む node ラベル/監査データを与えても redaction される。"""
    run(home, "init")
    # 監査に秘密値を書こうとする経路（node add の host に鍵っぽい文字列）。
    run(home, "node", "add", "--host", "localhost", "--name",
        "sk-ant-abcdefghijklmnopqrstuvwxyz012345", "--transport", "local")
    _, v = run(home, "verify")
    # verify は監査/イベントに秘密値が残っていないことを確認する。
    assert v["ok"] or "秘密値" not in json.dumps(v["problems"], ensure_ascii=False)


def test_redaction_of_secrets():
    text = "api_key=sk-abcdefghijklmnopqrstuv and AKIAIOSFODNN7EXAMPLE"
    red = security.redact(text)
    assert "sk-abcdefghijklmnopqrstuv" not in red
    assert "AKIAIOSFODNN7EXAMPLE" not in red
    assert "REDACTED" in red


def test_event_data_redacted(home):
    from mac_neural_grid.database import Database
    from mac_neural_grid import config as cfg
    run(home, "init")
    db = Database(cfg.paths(home)["db"])
    db.append_event("test", data={"token": "sk-ant-abcdefghijklmnopqrstuvwxyz012345"})
    blob = json.dumps(db.events(), ensure_ascii=False)
    assert "sk-ant-abcdefghijklmnopqrstuvwxyz012345" not in blob
