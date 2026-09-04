# -*- coding: utf-8 -*-
"""paths — 可変記憶の保存レイアウト解決（スキル本体とは分離する・仕様 §14/§15）。

正本は append-only イベントログ。snapshot / relation graph は派生物であり、
イベントログから replay で再構築できる。既定の記憶ルートは
``~/.claude/brain-memory``。スコープ（session..global）ごとに派生 snapshot を
別ファイルに保持する。

  <dir>/events/YYYY-MM.jsonl        append-only イベントログ（不変な事実・全scope共有）
  <dir>/scopes/<scope>/memory.json  当該 scope の派生 snapshot（再生成可能）
  <dir>/snapshots/                  明示スナップショット（consolidate 時など）
  <dir>/proposals/OPEN.md + *.json  候補（仮説）台帳
  <dir>/audit/YYYY-MM-DD.jsonl      決定記録（説明可能性・§13）
  <dir>/backups/                    昇格前後の backup（+.sha256）
  <dir>/.lock                       クリティカルセクションの advisory ロック
  <dir>/CHANGELOG.md                承認済み変更の履歴
"""

import os

DEFAULT_SCOPE = "project"
SCOPES = ("session", "task", "project", "client", "organization",
          "user", "machine", "global")


def default_base_dir():
    """既定の記憶ルート。環境変数 BRAIN_MEMORY_DIR で上書き可能。"""
    env = os.environ.get("BRAIN_MEMORY_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.expanduser("~/.claude/brain-memory"))


def _safe_scope(scope):
    scope = (scope or DEFAULT_SCOPE).strip()
    # path traversal 対策: スコープ名は英数と一部記号のみ許可（§16）。
    if not scope or any(c in scope for c in ("/", "\\", "..", "\x00")):
        raise ValueError("不正なスコープ名: %r" % scope)
    return scope


def resolve(base_dir=None, scope=DEFAULT_SCOPE):
    base = os.path.abspath(os.path.expanduser(base_dir or default_base_dir()))
    scope = _safe_scope(scope)
    scope_dir = os.path.join(base, "scopes", scope)
    return {
        "base": base,
        "scope": scope,
        "events": os.path.join(base, "events"),
        "scopes": os.path.join(base, "scopes"),
        "scope_dir": scope_dir,
        "memory": os.path.join(scope_dir, "memory.json"),
        "snapshots": os.path.join(base, "snapshots"),
        "proposals": os.path.join(base, "proposals"),
        "proposals_open": os.path.join(base, "proposals", "OPEN.md"),
        "audit": os.path.join(base, "audit"),
        "backups": os.path.join(base, "backups"),
        "lock": os.path.join(base, ".lock"),
        "changelog": os.path.join(base, "CHANGELOG.md"),
        "meta": os.path.join(base, "meta.json"),
    }


def event_shard(paths, ym):
    """月次シャードのパス（ym='YYYY-MM'）。"""
    return os.path.join(paths["events"], "%s.jsonl" % ym)


def ensure_dirs(paths):
    from . import secure_io
    for key in ("base", "events", "scopes", "scope_dir", "snapshots",
                "proposals", "audit", "backups"):
        secure_io.makedirs(paths[key])
