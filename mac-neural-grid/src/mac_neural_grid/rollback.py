# -*- coding: utf-8 -*-
"""rollback — バックアップ/復元とジョブのロールバック（仕様 §16/§31/§37）。

DB と設定を checksum つきで backup し、破損時に復元する。ジョブのロールバックは、実行中/失敗の
タスクを cancelled にし、作業ディレクトリを掃除する（成果物 append-only の監査は残す）。
"""

import os
import shutil

from . import security
from .database import now_iso


def backup(paths, label="manual"):
    """DB + config を backups/ へ退避し checksum を併記する。"""
    security.makedirs(paths["backups"])
    made = []
    for key in ("db", "config"):
        src = paths[key]
        if not os.path.exists(src):
            continue
        digest = security.sha256_file(src)
        name = "%s.%s.%s.bak" % (os.path.basename(src), label, digest.split(":")[1][:12])
        dst = os.path.join(paths["backups"], name)
        shutil.copy2(src, dst)
        security.atomic_write(dst + ".sha256", digest + "  " + os.path.basename(src) + "\n")
        made.append({"src": src, "backup": dst, "checksum": digest})
    return {"ok": True, "at": now_iso(), "backups": made}


def restore(backup_path, target, dry_run=False):
    """backup を checksum 検証して target へ復元する。"""
    if not os.path.exists(backup_path):
        return {"ok": False, "error": "backup が無い: %s" % backup_path}
    data = open(backup_path, "rb").read()
    digest = security.sha256_bytes(data)
    sha = backup_path + ".sha256"
    if os.path.exists(sha):
        recorded = open(sha).read().split()[0]
        if recorded != digest:
            return {"ok": False, "error": "checksum 不一致（破損の疑い）"}
    if dry_run:
        return {"ok": True, "dry_run": True, "would_restore_to": target, "checksum": digest}
    security.assert_not_symlink(target)
    security.atomic_write_bytes(target, data)
    return {"ok": True, "restored_to": target, "checksum": digest}


def rollback_job(db, paths, job_id, clean_work=True, actor="cli"):
    """未完了タスクを cancelled にし、作業ディレクトリを掃除する（監査は残す）。"""
    changed = []
    for t in db.tasks_of(job_id):
        if t["status"] in ("running", "assigned", "pending", "retrying", "failed",
                            "timed_out", "lost"):
            db.set_task_status(t["task_id"], "cancelled", kind="task_cancelled")
            changed.append(t["task_id"])
    db.set_job_status(job_id, "cancelled")
    if clean_work:
        jd = os.path.join(paths["jobs"], job_id)
        for t in changed:
            wd = os.path.join(jd, t, "work")
            if os.path.isdir(wd):
                shutil.rmtree(wd, ignore_errors=True)
    db.audit(actor, "rollback_job", {"job_id": job_id, "cancelled_tasks": changed})
    return {"ok": True, "job_id": job_id, "cancelled": changed}
