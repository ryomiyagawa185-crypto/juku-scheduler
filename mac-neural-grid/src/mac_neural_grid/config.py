# -*- coding: utf-8 -*-
"""config — パス解決と設定（仕様 §5/§16/§27/§30）。

Control 側の状態は Application Support 配下に置く（macOS）。他 OS では XDG 相当へ退避し、
テストは $MNG_HOME で上書きする。設定・ポリシーはコードから分離（§27）。秘密値は設定 JSON に
平文で置かず、macOS では Keychain 参照を推奨（§30）。本 MVP は Keychain を必須にしない。
"""

import os
import sys

from . import security

APP_NAME = "mac-neural-grid"


def home_dir():
    env = os.environ.get("MNG_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/%s" % APP_NAME)
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP_NAME)


def paths(home=None):
    base = os.path.abspath(os.path.expanduser(home or home_dir()))
    return {
        "home": base,
        "db": os.path.join(base, "grid.sqlite3"),
        "jobs": os.path.join(base, "jobs"),
        "artifacts": os.path.join(base, "artifacts"),
        "policies": os.path.join(base, "policies"),
        "config": os.path.join(base, "config.json"),
        "lock": os.path.join(base, ".lock"),
        "backups": os.path.join(base, "backups"),
        "logs": os.path.join(base, "logs"),
    }


DEFAULT_CONFIG = {
    "default_policy": "default",
    "default_timeout_s": 600,
    "default_max_retries": 2,
    "default_max_output_bytes": 5 * 1024 * 1024,
    "control_node_name": "control",
    "ssh": {
        # StrictHostKeyChecking は no にしない（§8）。accept-new は初回のみ受理し以後は固定。
        "strict_host_key_checking": "accept-new",
        "connect_timeout_s": 15,
        "batch_mode": True,
    },
}


def ensure_home(home=None):
    p = paths(home)
    for key in ("home", "jobs", "artifacts", "policies", "backups", "logs"):
        security.makedirs(p[key])
    if not os.path.exists(p["config"]):
        security.atomic_write_json(p["config"], DEFAULT_CONFIG)
    return p


def load_config(home=None):
    p = paths(home)
    if not os.path.exists(p["config"]):
        return dict(DEFAULT_CONFIG)
    import json
    try:
        with open(p["config"], encoding="utf-8") as f:
            cfg = json.load(f)
    except (ValueError, OSError):
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg or {})
    return merged
