# -*- coding: utf-8 -*-
"""pytest 共有フィクスチャ。src/ を import path に載せ、隔離した Control home を用意する。"""

import contextlib
import io
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from mac_neural_grid import cli               # noqa: E402
from mac_neural_grid.database import Database  # noqa: E402
from mac_neural_grid import config as config_mod  # noqa: E402


@pytest.fixture()
def home(tmp_path):
    return str(tmp_path / "mng-home")


def run(home, *argv):
    """CLI を JSON モードで実行し (exit_code, parsed) を返す。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(["--home", home, "--json", *argv])
    out = buf.getvalue().strip()
    return code, (json.loads(out) if out else None)


@pytest.fixture()
def grid(home):
    """init 済み + localhost ノードを inspect したグリッドを返すヘルパ。"""
    run(home, "init")

    def _add_worker(name):
        run(home, "node", "add", "--host", "localhost", "--name", name,
            "--transport", "local", "--labels", "trusted", "--trust", "high")
        c, d = run(home, "node", "list")
        for n in d["nodes"]:
            run(home, "node", "inspect", n["node_id"])

    # localhost を inspect（init で登録済み）。
    _, d = run(home, "node", "list")
    for n in d["nodes"]:
        run(home, "node", "inspect", n["node_id"])
    return {"home": home, "run": (lambda *a: run(home, *a)), "add_worker": _add_worker}


@pytest.fixture()
def paths_of():
    return lambda home: config_mod.paths(home)


@pytest.fixture()
def open_db():
    return lambda home: Database(config_mod.paths(home)["db"])
