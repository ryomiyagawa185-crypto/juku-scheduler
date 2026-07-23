# -*- coding: utf-8 -*-
"""database — SQLite ストア（仕様 §23）。events は append-only、状態はそこから再構築可能。

テーブル: nodes, capabilities, jobs, tasks, attempts, artifacts, events, policies, audit_log。
ジョブ/タスクの現在状態は高速参照のため列にも持つが、events から `rebuild_state()` で再計算でき、
Control Node 再起動後の復元（§31）と verify（§37）に用いる。
"""

import datetime
import json
import os
import sqlite3

from . import security

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
  node_id TEXT PRIMARY KEY, display_name TEXT, host TEXT, user TEXT,
  transport TEXT, trust TEXT, labels TEXT, work_root TEXT, enabled INTEGER,
  host_key_fingerprint TEXT, added_at TEXT, last_heartbeat TEXT
);
CREATE TABLE IF NOT EXISTS capabilities (
  node_id TEXT PRIMARY KEY, data TEXT, collected_at TEXT,
  FOREIGN KEY(node_id) REFERENCES nodes(node_id)
);
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY, name TEXT, policy TEXT, spec TEXT,
  status TEXT, priority REAL, idempotency_key TEXT UNIQUE,
  policy_hash TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY, job_id TEXT, seq INTEGER, type TEXT, executor TEXT,
  spec TEXT, status TEXT, node_id TEXT, attempts INTEGER, input_hash TEXT,
  created_at TEXT, updated_at TEXT,
  FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);
CREATE TABLE IF NOT EXISTS attempts (
  attempt_id TEXT PRIMARY KEY, task_id TEXT, attempt_no INTEGER, node_id TEXT,
  status TEXT, exit_code INTEGER, failure_class TEXT, duration_s REAL,
  started_at TEXT, ended_at TEXT,
  FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT PRIMARY KEY, task_id TEXT, path TEXT, checksum TEXT,
  size_bytes INTEGER, created_at TEXT,
  FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, job_id TEXT, task_id TEXT,
  attempt_id TEXT, kind TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS policies (name TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS audit_log (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, data TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_job ON tasks(job_id);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
"""

# events.kind → task/job のライフサイクル遷移マップ（rebuild で使用）。
_TASK_TRANSITIONS = {
    "task_created": "pending", "task_assigned": "assigned", "task_started": "running",
    "task_succeeded": "succeeded", "task_failed": "failed", "task_retrying": "retrying",
    "task_cancel_requested": "cancel_requested", "task_cancelled": "cancelled",
    "task_timed_out": "timed_out", "task_lost": "lost", "task_quarantined": "quarantined",
}


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


class Database(object):
    def __init__(self, path):
        self.path = path
        security.makedirs(os.path.dirname(os.path.abspath(path)))
        new = not os.path.exists(path)
        self.conn = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA_SQL)
        if new:
            security.chmod(path, security.FILE_MODE)

    def close(self):
        self.conn.close()

    # ---------- events（append-only）----------
    def append_event(self, kind, job_id=None, task_id=None, attempt_id=None, data=None):
        self.conn.execute(
            "INSERT INTO events(ts,job_id,task_id,attempt_id,kind,data) VALUES(?,?,?,?,?,?)",
            (now_iso(), job_id, task_id, attempt_id, kind,
             json.dumps(security.redact_obj(data or {}), ensure_ascii=False)))

    def events(self, job_id=None):
        if job_id:
            cur = self.conn.execute(
                "SELECT * FROM events WHERE job_id=? ORDER BY seq", (job_id,))
        else:
            cur = self.conn.execute("SELECT * FROM events ORDER BY seq")
        return [dict(r) for r in cur.fetchall()]

    def audit(self, actor, action, data=None):
        self.conn.execute(
            "INSERT INTO audit_log(ts,actor,action,data) VALUES(?,?,?,?)",
            (now_iso(), actor, action,
             json.dumps(security.redact_obj(data or {}), ensure_ascii=False)))

    def audit_entries(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM audit_log ORDER BY seq").fetchall()]

    # ---------- nodes ----------
    def upsert_node(self, node):
        self.conn.execute(
            """INSERT INTO nodes(node_id,display_name,host,user,transport,trust,labels,
                 work_root,enabled,host_key_fingerprint,added_at,last_heartbeat)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(node_id) DO UPDATE SET display_name=excluded.display_name,
                 host=excluded.host,user=excluded.user,transport=excluded.transport,
                 trust=excluded.trust,labels=excluded.labels,work_root=excluded.work_root,
                 enabled=excluded.enabled,host_key_fingerprint=excluded.host_key_fingerprint,
                 last_heartbeat=excluded.last_heartbeat""",
            (node["node_id"], node["display_name"], node["host"], node.get("user"),
             node["transport"], node["trust"], json.dumps(node.get("labels", [])),
             node.get("work_root"), int(node.get("enabled", True)),
             node.get("host_key_fingerprint"), node.get("added_at", now_iso()),
             node.get("last_heartbeat")))

    def get_node(self, node_id):
        r = self.conn.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
        return self._node_row(r) if r else None

    def list_nodes(self, enabled_only=False):
        q = "SELECT * FROM nodes" + (" WHERE enabled=1" if enabled_only else "")
        return [self._node_row(r) for r in self.conn.execute(q + " ORDER BY node_id")]

    def _node_row(self, r):
        d = dict(r)
        d["labels"] = json.loads(d.get("labels") or "[]")
        d["enabled"] = bool(d.get("enabled"))
        cap = self.conn.execute(
            "SELECT data FROM capabilities WHERE node_id=?", (d["node_id"],)).fetchone()
        d["capabilities"] = json.loads(cap["data"]) if cap else {}
        return d

    def remove_node(self, node_id):
        self.conn.execute("DELETE FROM capabilities WHERE node_id=?", (node_id,))
        self.conn.execute("DELETE FROM nodes WHERE node_id=?", (node_id,))

    def set_capabilities(self, node_id, cap):
        self.conn.execute(
            "INSERT INTO capabilities(node_id,data,collected_at) VALUES(?,?,?) "
            "ON CONFLICT(node_id) DO UPDATE SET data=excluded.data,"
            "collected_at=excluded.collected_at",
            (node_id, json.dumps(cap, ensure_ascii=False), cap.get("collected_at", now_iso())))

    # ---------- jobs / tasks ----------
    def create_job(self, job_id, name, policy, spec, idempotency_key, policy_hash,
                   priority=0.0):
        self.conn.execute(
            "INSERT INTO jobs(job_id,name,policy,spec,status,priority,idempotency_key,"
            "policy_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (job_id, name, policy, json.dumps(spec, ensure_ascii=False), "pending",
             priority, idempotency_key, policy_hash, now_iso(), now_iso()))
        self.append_event("job_created", job_id=job_id, data={"name": name})

    def find_job_by_idempotency(self, key):
        r = self.conn.execute("SELECT * FROM jobs WHERE idempotency_key=?", (key,)).fetchone()
        return dict(r) if r else None

    def get_job(self, job_id):
        r = self.conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return dict(r) if r else None

    def list_jobs(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC")]

    def set_job_status(self, job_id, status):
        self.conn.execute("UPDATE jobs SET status=?,updated_at=? WHERE job_id=?",
                          (status, now_iso(), job_id))
        self.append_event("job_%s" % status, job_id=job_id)

    def create_task(self, task_id, job_id, seq, ttype, executor, spec, input_hash):
        self.conn.execute(
            "INSERT INTO tasks(task_id,job_id,seq,type,executor,spec,status,node_id,"
            "attempts,input_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, job_id, seq, ttype, executor, json.dumps(spec, ensure_ascii=False),
             "pending", None, 0, input_hash, now_iso(), now_iso()))
        self.append_event("task_created", job_id=job_id, task_id=task_id,
                          data={"type": ttype, "executor": executor})

    def get_task(self, task_id):
        r = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(r) if r else None

    def tasks_of(self, job_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM tasks WHERE job_id=? ORDER BY seq", (job_id,))]

    def set_task_status(self, task_id, status, node_id=None, kind=None):
        job = self.get_task(task_id)["job_id"]
        if node_id is not None:
            self.conn.execute("UPDATE tasks SET status=?,node_id=?,updated_at=? WHERE task_id=?",
                              (status, node_id, now_iso(), task_id))
        else:
            self.conn.execute("UPDATE tasks SET status=?,updated_at=? WHERE task_id=?",
                              (status, now_iso(), task_id))
        self.append_event(kind or ("task_%s" % status), job_id=job, task_id=task_id,
                          data={"node_id": node_id})

    def incr_task_attempts(self, task_id):
        self.conn.execute("UPDATE tasks SET attempts=attempts+1 WHERE task_id=?", (task_id,))

    def record_attempt(self, attempt):
        self.conn.execute(
            "INSERT INTO attempts(attempt_id,task_id,attempt_no,node_id,status,exit_code,"
            "failure_class,duration_s,started_at,ended_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (attempt["attempt_id"], attempt["task_id"], attempt["attempt_no"],
             attempt.get("node_id"), attempt["status"], attempt.get("exit_code"),
             attempt.get("failure_class"), attempt.get("duration_s"),
             attempt.get("started_at"), attempt.get("ended_at")))

    def add_artifact(self, artifact_id, task_id, path, checksum, size_bytes):
        self.conn.execute(
            "INSERT OR REPLACE INTO artifacts(artifact_id,task_id,path,checksum,size_bytes,"
            "created_at) VALUES(?,?,?,?,?,?)",
            (artifact_id, task_id, path, checksum, size_bytes, now_iso()))
        self.append_event("artifact_stored", task_id=task_id,
                          data={"checksum": checksum, "size_bytes": size_bytes})

    def artifacts_of(self, job_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT a.* FROM artifacts a JOIN tasks t ON a.task_id=t.task_id "
            "WHERE t.job_id=? ORDER BY a.created_at", (job_id,))]

    # ---------- policies ----------
    def put_policy(self, name, data):
        self.conn.execute("INSERT OR REPLACE INTO policies(name,data) VALUES(?,?)",
                          (name, json.dumps(data, ensure_ascii=False)))

    def get_policy(self, name):
        r = self.conn.execute("SELECT data FROM policies WHERE name=?", (name,)).fetchone()
        return json.loads(r["data"]) if r else None

    def list_policies(self):
        return {r["name"]: json.loads(r["data"])
                for r in self.conn.execute("SELECT * FROM policies")}

    # ---------- state rebuild（§23/§31）----------
    def rebuild_state(self, job_id):
        """events から各タスクの状態を再構築して返す（現在の列値の検証に使う）。"""
        state = {}
        for ev in self.events(job_id):
            tid = ev.get("task_id")
            kind = ev.get("kind")
            if tid and kind in _TASK_TRANSITIONS:
                state[tid] = _TASK_TRANSITIONS[kind]
        return state
