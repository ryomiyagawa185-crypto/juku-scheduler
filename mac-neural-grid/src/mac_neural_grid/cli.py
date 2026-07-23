# -*- coding: utf-8 -*-
"""cli — mac-neural-grid のコマンド入口（仕様 §25/§26/§37）。

read-only（doctor/node list/inspect/capabilities/job plan/status/list/inspect/logs/
artifacts/models/policy/config/verify/dashboard）は状態を破壊しない。書込は file_lock 下。
数値・状態遷移は決定的コードのみが行う。
"""

import argparse
import json
import os
import sys

from . import __version__
from . import config as config_mod
from . import security, ids, jobspec, schemas, inventory, discovery, dispatcher
from . import scheduler, policy_engine, model_router, nlplan, rollback, retry
from .database import Database, now_iso

BUILTIN_POLICIES = {
    "default": {"external_network": True, "external_ai_api": False,
                "prefer_local_models": True},
    "confidential-local-only": {"external_network": False, "external_ai_api": False,
                                "artifact_encryption": True,
                                "allowed_nodes": {"labels": ["trusted"]}},
    "low-cost": {"prefer_local_models": True, "external_api_budget_usd": 1.0,
                 "external_ai_api": False},
    "fast": {"max_nodes": 5, "external_ai_api": False},
}


class Ctx(object):
    def __init__(self, args, create=False):
        self.home = getattr(args, "home", None)
        self.paths = config_mod.paths(self.home)
        if create:
            config_mod.ensure_home(self.home)
        self.config = config_mod.load_config(self.home)
        self.db = Database(self.paths["db"])
        self._seed_policies()

    def _seed_policies(self):
        if not self.db.list_policies():
            for name, data in BUILTIN_POLICIES.items():
                self.db.put_policy(name, data)

    def lock(self):
        return security.file_lock(self.paths["lock"])

    def policy(self, name):
        return self.db.get_policy(name or self.config.get("default_policy", "default")) or {}


def _out(obj, as_json):
    print(json.dumps(obj, ensure_ascii=False, indent=2) if as_json else _human(obj))


def _human(obj):
    return obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2)


# ---------------- commands ----------------

def cmd_init(args):
    ctx = Ctx(args, create=True)
    with ctx.lock():
        # localhost を既定ノードとして登録（transport=local）。
        if not ctx.db.get_node(ids.node_id("localhost", "localhost")):
            inventory.add_node(ctx.db, "localhost", name="localhost", transport="local",
                               labels=["control", "trusted"], trust="high")
    return {"ok": True, "home": ctx.paths["home"], "version": __version__,
            "nodes": len(ctx.db.list_nodes()), "policies": list(ctx.db.list_policies())}


def cmd_doctor(args):
    ctx = Ctx(args, create=True)
    cap = discovery.inspect_local("control")
    checks = {
        "home_exists": os.path.isdir(ctx.paths["home"]),
        "db_ok": os.path.exists(ctx.paths["db"]),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "nodes_registered": len(ctx.db.list_nodes()),
        "control_tools": {k: v for k, v in cap["tools"].items() if v},
        "ssh_available": bool(cap["tools"].get("rsync") is not None),
    }
    warnings = []
    if len(ctx.db.list_nodes()) == 0:
        warnings.append("ノード未登録。`node add` で登録してください。")
    if sys.platform != "darwin":
        warnings.append("非 macOS 環境: 一部の能力調査は degrade します（本番は macOS 想定）。")
    return {"ok": True, "checks": checks, "warnings": warnings}


def cmd_node_add(args):
    ctx = Ctx(args, create=True)
    with ctx.lock():
        node = inventory.add_node(
            ctx.db, args.host, user=args.user, name=args.name,
            transport=args.transport, labels=_split(args.labels),
            work_root=args.work_root, trust=args.trust,
            host_key_fingerprint=args.host_key)
    hint = ("リモート SSH ノードは host 鍵確認後に `node trust <id> --level medium|high`。"
            if node["transport"] == "ssh" else None)
    return {"ok": True, "node": node, "hint": hint}


def cmd_node_list(args):
    ctx = Ctx(args)
    return {"nodes": [{"node_id": n["node_id"], "display_name": n["display_name"],
                       "host": n["host"], "transport": n["transport"],
                       "trust": n["trust"], "enabled": n["enabled"],
                       "labels": n["labels"],
                       "arch": (n["capabilities"].get("architecture"))}
                      for n in ctx.db.list_nodes()]}


def cmd_node_inspect(args):
    ctx = Ctx(args)
    nid = _resolve_node(ctx, args.node)
    with ctx.lock():
        cap = inventory.inspect(ctx.db, nid)
    return {"node_id": nid, "capabilities": cap}


def cmd_node_ping(args):
    ctx = Ctx(args)
    return {"node_id": args.node, "probe": inventory.ping(ctx.db, _resolve_node(ctx, args.node),
                                                          ctx.config)}


def cmd_node_trust(args):
    ctx = Ctx(args)
    with ctx.lock():
        node = inventory.set_trust(ctx.db, _resolve_node(ctx, args.node), args.level)
    return {"ok": True, "node_id": node["node_id"], "trust": node["trust"]}


def cmd_node_disable(args):
    ctx = Ctx(args)
    with ctx.lock():
        node = inventory.set_enabled(ctx.db, _resolve_node(ctx, args.node), False)
    return {"ok": True, "node_id": node["node_id"], "enabled": node["enabled"]}


def cmd_node_remove(args):
    ctx = Ctx(args)
    with ctx.lock():
        inventory.remove_node(ctx.db, _resolve_node(ctx, args.node))
    return {"ok": True, "removed": args.node}


def cmd_capabilities(args):
    ctx = Ctx(args)
    return {"nodes": [{"node_id": n["node_id"], "capabilities": n["capabilities"]}
                      for n in ctx.db.list_nodes()]}


def cmd_models(args):
    ctx = Ctx(args)
    out = {}
    for n in ctx.db.list_nodes():
        cap = n["capabilities"]
        out[n["node_id"]] = {"local_models": cap.get("models", []),
                             "claude_code": (cap.get("tools") or {}).get("claude_code"),
                             "ollama": (cap.get("tools") or {}).get("ollama")}
    return {"models": out,
            "routing": "機密は外部 API 不使用。決定的処理を優先（model_router）。"}


def _load_and_split(args, ctx):
    if getattr(args, "prompt", None):
        planned = nlplan.plan(args.prompt, inputs=args.inputs)
        spec = planned["job"]
        base = "."
        return spec, base, planned
    spec = jobspec.load_job(args.spec)
    errors = schemas.validate(spec, schemas.JOB_SCHEMA)
    if errors:
        raise ValueError("job schema 違反: %s" % "; ".join(errors))
    return spec, os.path.dirname(os.path.abspath(args.spec)), None


def cmd_job_plan(args):
    ctx = Ctx(args)
    spec, base, planned = _load_and_split(args, ctx)
    tasks, agg = jobspec.split_tasks(spec, base)
    nodes = ctx.db.list_nodes(enabled_only=True)
    policy = ctx.policy(spec.get("policy"))
    assign = []
    for i, t in enumerate(tasks):
        sel = scheduler.select_node(nodes, t.get("requirements"), policy, ctx.db)
        route = model_router.route(t, policy, sel and ctx.db.get_node(sel["node_id"])
                                   ["capabilities"] if sel else None)
        assign.append({"seq": i, "type": t["type"], "executor": t["executor"],
                       "node": sel["node_id"] if sel else None,
                       "score": sel["score"] if sel else None, "routing": route})
    ev = policy_engine.evaluate(spec, policy, nodes)
    out = {"job_name": spec.get("name"), "policy": spec.get("policy"),
           "task_count": len(tasks), "assignments": assign,
           "aggregation": agg, "risk": ev["risk"],
           "requires_approval": ev["requires_approval"], "violations": ev["violations"]}
    if planned:
        out["nl_plan"] = {k: planned[k] for k in ("intent", "constraints",
                                                  "requires_approval", "needs_clarification",
                                                  "note")}
    if ev["requires_approval"]:
        out["approval"] = policy_engine.approval_prompt(spec, [a for a in assign], policy)
    return out


def _create_job(ctx, spec, base):
    tasks, agg = jobspec.split_tasks(spec, base)
    inputs_all = [i for t in tasks for i in (t.get("input") or [])]
    pol_name = spec.get("policy") or ctx.config.get("default_policy", "default")
    idk = ids.idempotency_key(spec.get("name", "job"), inputs_all, pol_name)
    existing = ctx.db.find_job_by_idempotency(idk)
    if existing:
        return existing["job_id"], True
    jid = ids.job_id(spec.get("name", "job"), idk)
    policy = ctx.db.get_policy(pol_name) or {}
    ctx.db.create_job(jid, spec.get("name", "job"), pol_name, spec, idk,
                      ids.policy_hash(policy), priority=spec.get("priority", 0.0))
    for i, t in enumerate(tasks):
        tid = ids.task_id(jid, i, jobspec.task_key(t, i))
        ctx.db.create_task(tid, jid, i, t["type"], t["executor"], t,
                           ids.input_hash(t.get("input") or []))
    ctx.db.set_job_status(jid, "planned")
    return jid, False


def cmd_job_create(args):
    ctx = Ctx(args, create=True)
    spec, base, _ = _load_and_split(args, ctx)
    with ctx.lock():
        jid, reused = _create_job(ctx, spec, base)
    return {"ok": True, "job_id": jid, "reused": reused,
            "tasks": len(ctx.db.tasks_of(jid))}


def cmd_job_run(args):
    ctx = Ctx(args, create=True)
    spec, base, _ = _load_and_split(args, ctx)
    nodes = ctx.db.list_nodes(enabled_only=True)
    policy = ctx.policy(spec.get("policy"))
    ev = policy_engine.evaluate(spec, policy, nodes)
    if ev["violations"]:
        return {"ok": False, "error": "ポリシー違反", "violations": ev["violations"]}
    if ev["requires_approval"] and not args.yes:
        with ctx.lock():
            jid, _ = _create_job(ctx, spec, base)
        return {"ok": False, "requires_approval": True, "job_id": jid,
                "approval": policy_engine.approval_prompt(spec, None, policy),
                "hint": "確認のうえ `job dispatch %s --yes` で実行" % jid}
    with ctx.lock():
        jid, _ = _create_job(ctx, spec, base)
        result = dispatcher.dispatch_job(ctx.db, ctx.paths, jid, ctx.config, policy)
    return {"ok": result["ok"], "job_id": jid, "summary": result}


def cmd_job_dispatch(args):
    ctx = Ctx(args, create=True)
    job = ctx.db.get_job(args.job)
    if job is None:
        return {"ok": False, "error": "job が無い: %s" % args.job}
    policy = ctx.policy(job.get("policy"))
    spec = json.loads(job["spec"])
    ev = policy_engine.evaluate(spec, policy, ctx.db.list_nodes(enabled_only=True))
    if ev["requires_approval"] and not args.yes:
        return {"ok": False, "requires_approval": True, "job_id": args.job,
                "approval": policy_engine.approval_prompt(spec, None, policy)}
    with ctx.lock():
        result = dispatcher.dispatch_job(ctx.db, ctx.paths, args.job, ctx.config, policy)
    return {"ok": result["ok"], "summary": result}


def cmd_job_status(args):
    ctx = Ctx(args)
    job = ctx.db.get_job(args.job)
    if job is None:
        return {"ok": False, "error": "job が無い"}
    tasks = ctx.db.tasks_of(args.job)
    return {"job_id": args.job, "name": job["name"], "status": job["status"],
            "policy": job["policy"],
            "tasks": [{"task_id": t["task_id"], "type": t["type"],
                       "executor": t["executor"], "status": t["status"],
                       "node_id": t["node_id"], "attempts": t["attempts"]}
                      for t in tasks],
            "progress": {"succeeded": sum(1 for t in tasks if t["status"] == "succeeded"),
                         "total": len(tasks)}}


def cmd_job_list(args):
    ctx = Ctx(args)
    return {"jobs": [{"job_id": j["job_id"], "name": j["name"], "status": j["status"],
                      "policy": j["policy"], "created_at": j["created_at"]}
                     for j in ctx.db.list_jobs()]}


def cmd_job_inspect(args):
    ctx = Ctx(args)
    job = ctx.db.get_job(args.job)
    if job is None:
        return {"ok": False, "error": "job が無い"}
    return {"job": {k: job[k] for k in ("job_id", "name", "status", "policy",
                                        "created_at", "idempotency_key", "policy_hash")},
            "spec": json.loads(job["spec"]),
            "rebuilt_state": ctx.db.rebuild_state(args.job),
            "artifacts": ctx.db.artifacts_of(args.job)}


def cmd_job_cancel(args):
    ctx = Ctx(args)
    with ctx.lock():
        res = rollback.rollback_job(ctx.db, ctx.paths, args.job)
    return res


def cmd_job_retry(args):
    ctx = Ctx(args, create=True)
    job = ctx.db.get_job(args.job)
    if job is None:
        return {"ok": False, "error": "job が無い"}
    # 失敗系タスクを pending に戻して再配送（再試行可能な失敗のみ意味を持つ）。
    with ctx.lock():
        for t in ctx.db.tasks_of(args.job):
            if t["status"] in ("failed", "timed_out", "lost"):
                ctx.db.set_task_status(t["task_id"], "pending", kind="task_created")
        policy = ctx.policy(job.get("policy"))
        result = dispatcher.dispatch_job(ctx.db, ctx.paths, args.job, ctx.config, policy)
    return {"ok": result["ok"], "summary": result}


def cmd_logs(args):
    ctx = Ctx(args)
    evs = ctx.db.events(args.job)
    if args.job is None:
        evs = evs[-args.tail:]
    return {"job_id": args.job, "events": [
        {"seq": e["seq"], "ts": e["ts"], "kind": e["kind"], "task_id": e["task_id"],
         "data": json.loads(e["data"] or "{}")} for e in evs]}


def cmd_artifacts(args):
    ctx = Ctx(args)
    return {"artifacts": ctx.db.artifacts_of(args.job)}


def cmd_policy(args):
    ctx = Ctx(args)
    if args.name:
        return {"policy": args.name, "data": ctx.db.get_policy(args.name)}
    return {"policies": ctx.db.list_policies()}


def cmd_config(args):
    ctx = Ctx(args)
    return {"home": ctx.paths["home"], "config": ctx.config}


def cmd_dashboard(args):
    ctx = Ctx(args)
    nodes = ctx.db.list_nodes()
    jobs = ctx.db.list_jobs()
    by_status = {}
    for j in jobs:
        by_status[j["status"]] = by_status.get(j["status"], 0) + 1
    return {"nodes": len(nodes), "enabled_nodes": sum(1 for n in nodes if n["enabled"]),
            "jobs_total": len(jobs), "jobs_by_status": by_status,
            "recent_jobs": [{"job_id": j["job_id"], "status": j["status"]}
                            for j in jobs[:5]]}


def cmd_worker(args):
    # Worker 常駐(launchd)は Phase 2・明示承認後（§28/§36）。ここでは案内のみ。
    return {"ok": False, "action": args.worker_action,
            "note": "Worker 常駐(launchd)は Phase 2。launchd/ のテンプレートを手動検証し、"
                    "明示承認後に `launchctl load` してください（本 MVP は自動登録しない・§28/§36）。"}


def cmd_backup(args):
    ctx = Ctx(args)
    with ctx.lock():
        return rollback.backup(ctx.paths, label=args.label or "manual")


def cmd_restore(args):
    ctx = Ctx(args)
    target = args.to or (ctx.paths["db"] if "sqlite" in (args.backup or "") else ctx.paths["config"])
    return rollback.restore(args.backup, target, dry_run=args.dry_run)


def cmd_verify(args):
    """読取専用の整合性検査（副作用なし・§37）。"""
    ctx = Ctx(args)
    problems, warnings = [], []
    for n in ctx.db.list_nodes():
        errs = schemas.validate(n, schemas.NODE_SCHEMA)
        problems += ["node %s: %s" % (n["node_id"], e) for e in errs]
    for name, data in ctx.db.list_policies().items():
        problems += ["policy %s: %s" % (name, e)
                     for e in schemas.validate(data, schemas.POLICY_SCHEMA)]
    # events からの状態再構築と、格納された task status の一致（§23/§31）。
    for j in ctx.db.list_jobs():
        rebuilt = ctx.db.rebuild_state(j["job_id"])
        for t in ctx.db.tasks_of(j["job_id"]):
            rs = rebuilt.get(t["task_id"])
            if rs is not None and rs != t["status"] and t["status"] not in (
                    "cancelled", "pending"):
                warnings.append("状態不一致 %s: stored=%s rebuilt=%s"
                                % (t["task_id"], t["status"], rs))
    # 監査ログ・イベントに秘密値が残っていないか。
    blob = json.dumps(ctx.db.audit_entries() + ctx.db.events(), ensure_ascii=False)
    if security.contains_secret(blob):
        problems.append("監査ログ/イベントに秘密値の疑い（redaction 漏れ）")
    # 成果物 checksum の一致。
    for j in ctx.db.list_jobs():
        for a in ctx.db.artifacts_of(j["job_id"]):
            if os.path.exists(a["path"]):
                if security.sha256_file(a["path"]) != a["checksum"]:
                    problems.append("成果物 checksum 不一致: %s" % a["path"])
    return {"ok": len(problems) == 0, "n_problems": len(problems),
            "problems": problems, "warnings": warnings[:50]}


def cmd_shell(args):
    """対話モード（§26）。自然言語は nlplan で構造化計画を表示（推測実行しない）。"""
    ctx = Ctx(args, create=True)
    print("mac-neural-grid 対話モード。'help' で例、'quit' で終了。")
    while True:
        try:
            line = input("grid> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        if line == "help":
            print("例: 空いているMacを表示 / このフォルダを要約して / status / nodes")
            continue
        if line in ("nodes", "ノード"):
            _out(cmd_node_list(args), True)
            continue
        if line in ("status", "状態"):
            _out(cmd_dashboard(args), True)
            continue
        planned = nlplan.plan(line)
        print("構造化計画（実行はしません。job run で実行してください）:")
        print(json.dumps({"intent": planned["intent"], "job": planned["job"],
                          "requires_approval": planned["requires_approval"],
                          "note": planned["note"]}, ensure_ascii=False, indent=2))
    return {"ok": True}


# ---------------- helpers ----------------

def _split(s):
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _resolve_node(ctx, ref):
    if ctx.db.get_node(ref):
        return ref
    if ref in ("localhost", "127.0.0.1"):
        nid = ids.node_id("localhost", "localhost")
        if ctx.db.get_node(nid):
            return nid
    for n in ctx.db.list_nodes():
        if n["display_name"] == ref or n["host"] == ref:
            return n["node_id"]
    return ref


# ---------------- parser ----------------

def build_parser():
    p = argparse.ArgumentParser(prog="mac-neural-grid",
                                description="複数 Mac を安全に統括する分散 AI ジョブ実行 CLI")
    p.add_argument("--home", help="Control 状態のルート（既定は Application Support / $MNG_HOME）")
    p.add_argument("--json", action="store_true", help="JSON 出力")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初期化")
    sub.add_parser("doctor", help="環境診断（読取専用）")
    sub.add_parser("capabilities", help="全ノードの能力台帳")
    sub.add_parser("models", help="ノード別の利用可能モデル")
    sub.add_parser("dashboard", help="概況")
    sub.add_parser("verify", help="整合性検査（読取専用・無副作用）")
    sub.add_parser("shell", help="対話モード")

    na = sub.add_parser("node", help="ノード管理")
    nsub = na.add_subparsers(dest="node_action", required=True)
    a = nsub.add_parser("add"); a.add_argument("--host", required=True)
    a.add_argument("--user"); a.add_argument("--name"); a.add_argument("--transport",
                                                                       choices=["local", "ssh"])
    a.add_argument("--labels"); a.add_argument("--work-root", dest="work_root")
    a.add_argument("--trust", default="medium", choices=schemas.TRUST_LEVELS)
    a.add_argument("--host-key", dest="host_key")
    for name in ("list",):
        nsub.add_parser(name)
    for name in ("inspect", "ping", "remove", "disable"):
        sp = nsub.add_parser(name); sp.add_argument("node")
    t = nsub.add_parser("trust"); t.add_argument("node"); t.add_argument(
        "--level", required=True, choices=schemas.TRUST_LEVELS)

    jb = sub.add_parser("job", help="ジョブ")
    jsub = jb.add_subparsers(dest="job_action", required=True)
    for name in ("create", "plan", "run"):
        sp = jsub.add_parser(name)
        sp.add_argument("spec", nargs="?")
        sp.add_argument("--prompt"); sp.add_argument("--inputs")
        if name in ("run",):
            sp.add_argument("--yes", action="store_true", help="high_risk を承認して実行")
    d = jsub.add_parser("dispatch"); d.add_argument("job"); d.add_argument("--yes",
                                                                           action="store_true")
    for name in ("status", "inspect", "cancel", "retry"):
        sp = jsub.add_parser(name); sp.add_argument("job")
    jsub.add_parser("list")

    lg = sub.add_parser("logs"); lg.add_argument("--job"); lg.add_argument("--tail", type=int,
                                                                           default=50)
    lg.add_argument("--follow", action="store_true", help="(MVP: 単発表示)")
    ar = sub.add_parser("artifacts"); ar.add_argument("--job", required=True)
    po = sub.add_parser("policy"); po.add_argument("name", nargs="?")
    sub.add_parser("config")

    wk = sub.add_parser("worker"); wk.add_argument("worker_action",
                                                   choices=["install", "start", "stop", "status"])
    bk = sub.add_parser("backup"); bk.add_argument("--label")
    rs = sub.add_parser("restore"); rs.add_argument("--backup", required=True)
    rs.add_argument("--to"); rs.add_argument("--dry-run", dest="dry_run", action="store_true")
    return p


def _dispatch(args):
    table = {
        ("init",): cmd_init, ("doctor",): cmd_doctor, ("capabilities",): cmd_capabilities,
        ("models",): cmd_models, ("dashboard",): cmd_dashboard, ("verify",): cmd_verify,
        ("shell",): cmd_shell, ("logs",): cmd_logs, ("artifacts",): cmd_artifacts,
        ("policy",): cmd_policy, ("config",): cmd_config, ("worker",): cmd_worker,
        ("backup",): cmd_backup, ("restore",): cmd_restore,
        ("node", "add"): cmd_node_add, ("node", "list"): cmd_node_list,
        ("node", "inspect"): cmd_node_inspect, ("node", "ping"): cmd_node_ping,
        ("node", "trust"): cmd_node_trust, ("node", "disable"): cmd_node_disable,
        ("node", "remove"): cmd_node_remove,
        ("job", "create"): cmd_job_create, ("job", "plan"): cmd_job_plan,
        ("job", "run"): cmd_job_run, ("job", "dispatch"): cmd_job_dispatch,
        ("job", "status"): cmd_job_status, ("job", "list"): cmd_job_list,
        ("job", "inspect"): cmd_job_inspect, ("job", "cancel"): cmd_job_cancel,
        ("job", "retry"): cmd_job_retry,
    }
    if args.cmd == "node":
        return table[("node", args.node_action)]
    if args.cmd == "job":
        return table[("job", args.job_action)]
    return table[(args.cmd,)]


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        fn = _dispatch(args)
        result = fn(args)
    except (ValueError, KeyError, security.SecurityError) as exc:
        _out({"ok": False, "error": str(exc), "type": type(exc).__name__},
             getattr(args, "json", False))
        return 1
    _out(result, getattr(args, "json", False))
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    return 0
