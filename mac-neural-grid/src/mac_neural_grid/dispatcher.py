# -*- coding: utf-8 -*-
"""dispatcher — ジョブ配送の中核（仕様 §6/§9/§16/§19/§20/§21/§22）。

各タスクについて: scheduler で割当先を選定 → 専用作業ディレクトリを用意 → 入力を staging →
envelope を作成（payload_hash・expires_at つき）→ Worker を*実プロセス隔離*で実行（localhost は
subprocess、リモートは要承認）→ result.json を回収 → 成果物を checksum 検証つきで登録 →
失敗は分類して再試行（別ノード）。冪等（idempotency_key）で二重実行を避ける。
"""

import os
import posixpath
import subprocess
import sys

from . import security, ids, jobspec, scheduler, retry, artifact_store
from . import config as config_mod
from .database import now_iso
from .transport import for_node
from . import worker as worker_mod

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _plus_seconds(iso, seconds):
    import datetime
    dt = datetime.datetime.fromisoformat(iso)
    return (dt + datetime.timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


def build_envelope(job_id, task_id, attempt_id, node, task_spec, capabilities, policy,
                   limits, work_base, result_destination, ttl_s=3600):
    """配送 envelope（§9）。payload_hash と expires_at で完全性・期限を担保。"""
    # 入力は input/ 直下の basename として渡す（worker が作業ディレクトリ内に制限）。
    staged = {**task_spec, "input": [os.path.basename(p) for p in (task_spec.get("input") or [])]}
    payload = {"task_spec": staged, "capabilities": capabilities, "policy": policy,
               "limits": limits, "node": {"node_id": node["node_id"],
                                          "capabilities": capabilities}}
    created = now_iso()
    env = {
        "protocol_version": "mng/1", "job_id": job_id, "task_id": task_id,
        "attempt_id": attempt_id, "node_id": node["node_id"], "command_type": "execute",
        "payload_hash": security.payload_hash(payload), "created_at": created,
        "expires_at": _plus_seconds(created, ttl_s),
        "permissions": {"allowed_executors": [staged.get("executor")],
                        "external_ai_api": bool(policy.get("external_ai_api"))},
        "resource_limits": limits, "result_destination": result_destination,
        "work_base": work_base, "payload": payload,
    }
    return env


def _stage_inputs(task_spec, input_dir):
    security.makedirs(input_dir)
    for src in task_spec.get("input") or []:
        if os.path.exists(src):
            dst = security.safe_join(input_dir, os.path.basename(src))
            security.atomic_write_bytes(dst, open(src, "rb").read())


def _run_worker_subprocess(envelope_path, long_running=False):
    """Worker を実プロセス隔離で起動（localhost）。darwin では caffeinate でスコープ。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = _SRC_DIR + os.pathsep + env.get("PYTHONPATH", "")
    argv = [sys.executable, "-m", "mac_neural_grid.worker", "--envelope", envelope_path]
    if long_running and sys.platform == "darwin":
        # 特定プロセスにスコープ: caffeinate は worker 終了で自動的に解放（§19）。
        argv = ["caffeinate", "-i"] + argv
    proc = subprocess.run(argv, env=env, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _execute(transport, job_id, task_id, attempt_id, node, spec, caps, policy, limits,
             local_task_dir, local_dirs):
    """transport に応じて Worker を実行し、local_task_dir に result.json / output/ を残す。

    local: subprocess で worker を起動（work_base はローカル）。
    remote(ssh/sim): 入力を remote へ staging → remote worker 起動 → result/output/manifest を
    checksum つきで fetch（一時名→checksum→原子的改名は artifact_store.collect が担保）。
    """
    ttl = max(3600, int(limits["timeout_s"]) * 2)
    if getattr(transport, "remote", False):
        remote_root = transport.remote_task_root(job_id, task_id)
        transport.ensure_worker()
        for src in spec.get("input") or []:
            if os.path.exists(src):
                transport.put_file(src, posixpath.join(remote_root, "input",
                                                        os.path.basename(src)))
        env = build_envelope(job_id, task_id, attempt_id, node, spec, caps, policy, limits,
                             remote_root, posixpath.join(remote_root, "result.json"),
                             ttl_s=ttl)
        env_local = security.safe_join(local_task_dir, "envelope-%s.json" % attempt_id)
        security.atomic_write_json(env_local, env)
        transport.put_file(env_local, posixpath.join(remote_root, "envelope.json"))
        r = transport.run(["python3", "-m", "mac_neural_grid.worker", "--envelope",
                           posixpath.join(remote_root, "envelope.json")],
                          timeout=limits["timeout_s"],
                          env={"PYTHONPATH": transport.pythonpath()},
                          allowlist=security.DEFAULT_COMMAND_ALLOWLIST)
        for name in ("result.json", "manifest.json"):
            try:
                transport.get_file(posixpath.join(remote_root, name),
                                   security.safe_join(local_task_dir, name))
            except Exception:  # noqa: BLE001 — fetch 失敗は下で node_offline 扱い
                pass
        transport.get_dir(posixpath.join(remote_root, "output"), local_dirs["output"])
        return _json_file(security.safe_join(local_task_dir, "result.json")) or {
            "status": "failed", "failure_class": "node_offline",
            "stderr_excerpt": (r.get("stderr") or r.get("stdout") or "")[:500]}
    # local
    env = build_envelope(job_id, task_id, attempt_id, node, spec, caps, policy, limits,
                         local_task_dir, security.safe_join(local_task_dir, "result.json"),
                         ttl_s=ttl)
    env_path = security.safe_join(local_task_dir, "envelope-%s.json" % attempt_id)
    security.atomic_write_json(env_path, env)
    rc, out, err = _run_worker_subprocess(env_path, long_running=limits["timeout_s"] >= 300)
    return _json_file(env["result_destination"]) or {
        "status": "failed", "failure_class": "unknown", "stderr_excerpt": (err or out)[:500]}


def dispatch_job(db, paths, job_id, config=None, policy=None, exclude_global=None,
                 allow_remote=False, actor="cli", transport_factory=None):
    """ジョブの全 pending タスクを配送・回収する。冪等・再試行つき。

    transport_factory(node) を渡すと transport 生成を差し替えられる（テストで remote 経路を
    ネットワーク無しに検証するための注入点）。既定は for_node（local / ssh）。
    """
    config = config or config_mod.DEFAULT_CONFIG
    policy = policy or {}
    job = db.get_job(job_id)
    if job is None:
        return {"ok": False, "error": "job が無い: %s" % job_id}
    nodes = db.list_nodes(enabled_only=True)
    if not nodes:
        return {"ok": False, "error": "有効なノードが無い（node add で登録）"}
    if transport_factory is None:
        def transport_factory(node):
            return for_node(node, config.get("ssh"), allow_remote=allow_remote)
    db.set_job_status(job_id, "running")
    db.audit(actor, "dispatch_job", {"job_id": job_id, "nodes": [n["node_id"] for n in nodes]})
    max_retries = config.get("default_max_retries", 2)
    # 機密ポリシー等の allowed_nodes.labels をスケジューラ要件へ反映（§27）。
    policy_labels = (policy.get("allowed_nodes") or {}).get("labels") or []

    results = []
    for task in db.tasks_of(job_id):
        if task["status"] in ("succeeded", "cancelled"):
            continue
        spec = _json(task["spec"])
        limits = {"timeout_s": spec.get("timeout_s") or config.get("default_timeout_s", 600),
                  "max_output_bytes": spec.get("max_output_bytes")
                  or config.get("default_max_output_bytes", 5 << 20)}
        tried_nodes = set()
        final = None
        req = dict(spec.get("requirements") or {})
        if policy_labels:
            req["labels"] = sorted(set(req.get("labels", [])) | set(policy_labels))
        for attempt_no in range(max_retries + 1):
            sel = scheduler.select_node(nodes, req, policy, db, exclude=tried_nodes)
            if sel is None:
                final = {"status": "lost", "failure_class": "node_offline",
                         "stderr_excerpt": "割当可能なノードが無い"}
                db.set_task_status(task["task_id"], "lost", kind="task_lost")
                break
            node = db.get_node(sel["node_id"])
            tried_nodes.add(node["node_id"])
            # 割当ごとに in-memory の負荷を加算し、以降のタスクを他ノードへ分散させる
            # （データ並列の実分担・§11）。raw の DB 値は変えない。
            for n in nodes:
                if n["node_id"] == node["node_id"]:
                    cl = n.setdefault("capabilities", {}).setdefault("current_load", {})
                    cl["active_jobs"] = cl.get("active_jobs", 0) + 1
            attempt_id = ids.attempt_id(task["task_id"], attempt_no)
            task_dir = security.safe_join(paths["jobs"], job_id, task["task_id"])
            dirs = {k: security.safe_join(task_dir, k)
                    for k in ("input", "work", "output", "logs")}
            for d in dirs.values():
                security.makedirs(d)
            _stage_inputs(spec, dirs["input"])   # local ステージング（remote は _execute 内）
            db.incr_task_attempts(task["task_id"])
            db.set_task_status(task["task_id"], "assigned", node_id=node["node_id"],
                               kind="task_assigned")
            db.set_task_status(task["task_id"], "running", node_id=node["node_id"],
                               kind="task_started")
            db.audit(actor, "dispatch_task", {"task_id": task["task_id"],
                                              "node_id": node["node_id"],
                                              "attempt": attempt_no, "transport": None,
                                              "why": sel})
            started = now_iso()
            try:
                transport = transport_factory(node)
            except security.SecurityError as exc:
                final = {"status": "failed", "failure_class": "policy_denied",
                         "stderr_excerpt": str(exc)}
                db.set_task_status(task["task_id"], "failed", kind="task_failed")
                break
            try:
                result = _execute(transport, job_id, task["task_id"], attempt_id, node,
                                  spec, node.get("capabilities"), policy, limits,
                                  task_dir, dirs)
            except security.SecurityError as exc:
                # リモート実行が未承認（allow_remote=False）等はここに来る。
                db.set_task_status(task["task_id"], "failed", kind="task_failed")
                final = {"status": "failed", "failure_class": "policy_denied",
                         "stderr_excerpt": str(exc)}
                break
            fc = retry.classify(result)
            db.record_attempt({"attempt_id": attempt_id, "task_id": task["task_id"],
                               "attempt_no": attempt_no, "node_id": node["node_id"],
                               "status": result.get("status"),
                               "exit_code": result.get("exit_code"), "failure_class": fc,
                               "duration_s": result.get("duration_s"),
                               "started_at": started, "ended_at": now_iso()})

            if result.get("status") == "succeeded":
                manifest = _json_file(security.safe_join(task_dir, "manifest.json"))
                registered = artifact_store.collect(
                    db, task["task_id"], dirs["output"],
                    central_dir=security.safe_join(paths["artifacts"], job_id),
                    manifest=manifest)
                db.set_task_status(task["task_id"], "succeeded", node_id=node["node_id"],
                                   kind="task_succeeded")
                final = {"status": "succeeded", "artifacts": registered,
                         "node_id": node["node_id"]}
                break

            if retry.should_retry(fc, attempt_no, max_retries):
                db.set_task_status(task["task_id"], "retrying", kind="task_retrying")
                continue
            status = result.get("status")
            status = status if status in ("timed_out", "quarantined") else "failed"
            db.set_task_status(task["task_id"], status, node_id=node["node_id"],
                               kind="task_%s" % status)
            final = {"status": status, "failure_class": fc,
                     "stderr_excerpt": result.get("stderr_excerpt")}
            break
        results.append({"task_id": task["task_id"], **(final or {})})

    # 集約タスク（control ノードで実行・§10）。
    agg = _json(job["spec"]).get("aggregation")
    aggregation = _run_aggregation(db, paths, job_id, agg) if agg else None

    tasks = db.tasks_of(job_id)
    succ = sum(1 for t in tasks if t["status"] == "succeeded")
    if succ == len(tasks):
        db.set_job_status(job_id, "succeeded")
    elif succ == 0:
        db.set_job_status(job_id, "failed")
    else:
        db.set_job_status(job_id, "partial")
    return {"ok": True, "job_id": job_id, "results": results,
            "succeeded": succ, "total": len(tasks), "aggregation": aggregation}


def _run_aggregation(db, paths, job_id, agg):
    """成果物を control ノードで集約する（merge-summaries: 全 .md を連結）。"""
    atype = (agg or {}).get("type", "merge")
    arts = db.artifacts_of(job_id)
    merged_dir = security.safe_join(paths["artifacts"], job_id, "_aggregate")
    security.makedirs(merged_dir)
    body = ["# 集約結果 (%s) job=%s\n" % (atype, job_id)]
    for a in arts:
        if a["path"].endswith(".md") and os.path.exists(a["path"]):
            body.append("\n<!-- %s (%s) -->\n" % (os.path.basename(a["path"]), a["checksum"]))
            body.append(open(a["path"], encoding="utf-8", errors="replace").read())
    out = security.safe_join(merged_dir, "aggregate.md")
    security.atomic_write(out, "".join(body))
    return {"type": atype, "path": out, "checksum": security.sha256_file(out),
            "inputs": len(arts)}


def _json(text):
    import json
    try:
        return json.loads(text) if isinstance(text, str) else (text or {})
    except ValueError:
        return {}


def _json_file(path):
    import json
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None
