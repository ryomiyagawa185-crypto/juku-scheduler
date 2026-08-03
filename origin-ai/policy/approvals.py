"""承認レコード。

中心にあるのは **内容束縛**。承認は「このゲートを通ってよい」ではなく
「この内容がこのゲートを通ってよい」でなければならない。
束縛が無いと次が通ってしまう:

    ドラフトAを見て送信を承認 → 再生成でBになった → Bが送信される

実行直前に target_hash を再計算し、一致しなければ承認は無効。
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import store
from .gates import NO_BLANKET_APPROVAL

DEFAULT_TTL_SECONDS = 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class BlanketApprovalRefused(ValueError):
    """destructive-ops と legal-submission は毎回承認。まとめ承認は作らせない。"""


class ApprovalStore:
    def __init__(self, path: Path | str | None = None):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = store.connect(self._path)
        return self._conn

    def grant(
        self,
        gate: str,
        target_hash: str,
        *,
        scope: str = "step",
        approver: str = "user",
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        one_shot: bool = True,
        note: str | None = None,
    ) -> dict:
        if not one_shot and gate in NO_BLANKET_APPROVAL:
            raise BlanketApprovalRefused(
                f"{gate} は one_shot 承認のみ許可（毎回の承認が必要なゲート）"
            )
        now = _now()
        record = {
            "approval_id": str(uuid.uuid4()),
            "scope": scope,
            "target_hash": target_hash,
            "gate": gate,
            "approver": approver,
            "granted_at": now.isoformat(timespec="seconds"),
            "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(timespec="seconds"),
            "one_shot": one_shot,
            "consumed_at": None,
            "note": note,
        }
        with self.conn:
            self.conn.execute(
                "INSERT INTO approvals (approval_id, scope, target_hash, gate, approver, "
                "granted_at, expires_at, one_shot, consumed_at, note) "
                "VALUES (:approval_id, :scope, :target_hash, :gate, :approver, "
                ":granted_at, :expires_at, :one_shot, :consumed_at, :note)",
                {**record, "one_shot": int(one_shot)},
            )
        return record

    def find_valid(self, gate: str, target_hash: str, now: datetime | None = None) -> dict | None:
        """内容ハッシュが一致し、未失効・未消費の承認だけを返す。"""
        now = now or _now()
        rows = self.conn.execute(
            "SELECT * FROM approvals WHERE gate = ? AND target_hash = ?",
            (gate, target_hash),
        ).fetchall()
        for row in rows:
            if row["consumed_at"] is not None:
                continue
            if _parse(row["expires_at"]) <= now:
                continue
            return dict(row)
        return None

    def consume(self, approval_id: str, now: datetime | None = None) -> None:
        now = now or _now()
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                "UPDATE approvals SET consumed_at = ? "
                "WHERE approval_id = ? AND consumed_at IS NULL AND one_shot = 1",
                (now.isoformat(timespec="seconds"), approval_id),
            )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
