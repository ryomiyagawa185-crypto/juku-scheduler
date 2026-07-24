# -*- coding: utf-8 -*-
"""migrations — 記憶ストアのバージョン管理（仕様 §17）。

正本は append-only イベントログなので、多くの移行は「snapshot 再構築」で足りる。
破壊的なイベント形式変更が必要な場合のみ、新イベントを追記する形（過去は書き換えない）で
移行する。meta.json に schema_version を刻む。
"""

from . import secure_io
from . import __schema_version__

# (from_version, to_version, description, fn) の順序付きリスト。
_MIGRATIONS = [
    # 初版。将来 ("1.0.0","1.1.0", ...) を追加していく。
]


def read_meta(paths):
    return secure_io.read_json(paths["meta"], default={}) or {}


def current_version(paths):
    return read_meta(paths).get("schema_version", "0.0.0")


def stamp(paths, extra=None):
    meta = read_meta(paths)
    meta["schema_version"] = __schema_version__
    if extra:
        meta.update(extra)
    secure_io.atomic_write_json(paths["meta"], meta)
    return meta


def plan(paths):
    """未適用の移行一覧を返す（dry-run 用）。"""
    cur = current_version(paths)
    return [{"from": f, "to": t, "desc": d}
            for (f, t, d, _fn) in _MIGRATIONS if f >= cur]


def migrate(paths, dry_run=True):
    cur = current_version(paths)
    todo = plan(paths)
    applied = []
    if not dry_run:
        for (f, t, d, fn) in _MIGRATIONS:
            if f >= cur:
                fn(paths)
                applied.append({"from": f, "to": t, "desc": d})
        stamp(paths)
    return {"dry_run": dry_run, "from_version": cur,
            "target_version": __schema_version__, "planned": todo,
            "applied": applied}
