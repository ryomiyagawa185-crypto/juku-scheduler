"""予算。日次上限と1呼び出し上限。

ここで例外を握りつぶさないこと。呼び出し元（decide）が例外を
BLOCK に変換する。「ストアが読めないので通す」は最悪の故障モード。
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from . import store


class BudgetStore:
    def __init__(self, path: Path | str | None = None):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = store.connect(self._path)
        return self._conn

    def _today(self) -> str:
        return date.today().isoformat()

    def spent_today(self, skill_id: str) -> float:
        row = self.conn.execute(
            "SELECT usd FROM spend WHERE day = ? AND skill_id = ?",
            (self._today(), skill_id),
        ).fetchone()
        return float(row["usd"]) if row else 0.0

    def spend(self, skill_id: str, usd: float) -> float:
        """アトミックに加算して加算後の残高を返す。"""
        day = self._today()
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                "INSERT INTO spend (day, skill_id, usd) VALUES (?, ?, ?) "
                "ON CONFLICT(day, skill_id) DO UPDATE SET usd = usd + excluded.usd",
                (day, skill_id, usd),
            )
        return self.spent_today(skill_id)

    def has_headroom(self, skill_id: str, usd: float, daily_cap: float) -> bool:
        return self.spent_today(skill_id) + usd <= daily_cap + 1e-12

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
