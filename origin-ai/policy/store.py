"""状態ストア（SQLite）。

予算カウンタは複数プロセスから同時に更新され得る。JSON ファイルの
read-modify-write は競合で必ず取りこぼし、しかも取りこぼした側は
「予算をまだ使っていない」ことになるので **fail-open** する。
トランザクションで加算すること。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origin_core import ROOT

DEFAULT_PATH = ROOT / "state" / "origin.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spend (
    day        TEXT NOT NULL,
    skill_id   TEXT NOT NULL,
    usd        REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (day, skill_id)
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    scope       TEXT NOT NULL,
    target_hash TEXT NOT NULL,
    gate        TEXT NOT NULL,
    approver    TEXT NOT NULL,
    granted_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    one_shot    INTEGER NOT NULL,
    consumed_at TEXT,
    note        TEXT
);
CREATE INDEX IF NOT EXISTS approvals_lookup ON approvals (gate, target_hash);
CREATE TABLE IF NOT EXISTS completed_steps (
    idempotency_key TEXT PRIMARY KEY,
    completed_at    TEXT NOT NULL,
    outputs_hash    TEXT
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path) if path else DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn
