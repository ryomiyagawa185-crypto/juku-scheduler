# -*- coding: utf-8 -*-
"""cli — コマンドライン入口（仕様 §17）。

実装コマンド: init observe attention working-memory retrieve predict choose
feedback consolidate decay propose promote reject rollback report verify
replay migrate。

安全則:
  - verify / dry-run / attention / retrieve / predict / choose / report は読取専用
    （ファイルを書き換えない）。
  - 書込コマンドは file_lock 下で直列化する。
  - 数値・状態遷移は本モジュール（決定的 Python）だけが行う。
"""

import argparse
import json
import os
import sys

from . import __version__
from . import paths as paths_mod
from . import secure_io
from . import event_store
from . import validation
from . import snapshot as snap_mod
from . import attention as attn
from . import working_memory as wm
from . import retrieval
from . import prediction
from . import policy_selection
from . import metacognition
from . import consolidation
from . import learning
from . import proposals as prop_mod
from . import executive
from . import inhibition
from . import migrations
from . import synapse_bridge
from . import semantic_memory


def _out(obj, as_json):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(_human(obj))


def _human(obj):
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _load_json_arg(value):
    """--foo が '@path' ならファイル、'{...}' なら JSON 文字列としてパース。"""
    if value is None:
        return None
    if value.startswith("@"):
        return secure_io.read_json(value[1:])
    try:
        return json.loads(value)
    except ValueError:
        return {"text": value}


def _paths(args):
    return paths_mod.resolve(getattr(args, "dir", None), getattr(args, "scope", None)
                             or paths_mod.DEFAULT_SCOPE)


def _lock(paths):
    return secure_io.file_lock(paths["base"], paths["lock"])


# ---------------- commands ----------------

def cmd_init(args):
    paths = _paths(args)
    with _lock(paths):
        paths_mod.ensure_dirs(paths)
        migrations.stamp(paths, {"engine_version": __version__})
    return {"ok": True, "base": paths["base"], "scope": paths["scope"],
            "schema_version": migrations.current_version(paths),
            "synapse": synapse_bridge.status()}


def cmd_observe(args):
    paths = _paths(args)
    if args.event:
        obj = secure_io.read_json(args.event)
        if obj is None:
            return {"ok": False, "error": "event ファイルを読めない: %s" % args.event}
        norm = event_store.event_from_file(obj, default_scope=paths["scope"])
    else:
        payload = {k: v for k, v in {
            "what": args.what, "situation": args.situation, "goal": args.goal_text,
            "action": args.action, "outcome": args.outcome,
            "success_basis": args.success_basis, "confirmed_by": args.confirmed_by,
        }.items() if v is not None}
        norm = {"kind": args.kind, "scope": paths["scope"], "partition": args.partition,
                "payload": payload, "source": args.source,
                "source_trust": args.source_trust, "occurred_at": args.occurred_at,
                "session": args.session}
    # 汚染検査（未信頼テキスト内の埋め込み命令を警告・§10）。
    injection = inhibition.scan_injection(norm.get("payload"))
    with _lock(paths):
        paths_mod.ensure_dirs(paths)
        ev, status = event_store.append_event(
            paths, norm["kind"], norm["scope"], norm["payload"],
            source=norm.get("source", "unknown"),
            source_trust=norm.get("source_trust", "untrusted_external"),
            occurred_at=norm.get("occurred_at"), session=norm.get("session"),
            partition=norm.get("partition"))
    return {"ok": True, "event_id": ev["event_id"], "status": status,
            "contains_sensitive_data": ev["contains_sensitive_data"],
            "sensitive_categories": ev.get("sensitive_categories"),
            "injection_paths": injection,
            "note": ("未信頼テキストに命令を検出。事実候補にはできるが行動規則へ昇格禁止(§10)"
                     if injection else None)}


def cmd_attention(args):
    stim = _load_json_arg(args.stimulus) or {}
    goal = _load_json_arg(args.goal) or {}
    context = _load_json_arg(args.context) or {}
    if isinstance(stim, list):
        return {"ranked": attn.rank(stim, goal, context, capacity=args.capacity)}
    return attn.score(stim, goal, context)


def cmd_working_memory(args):
    paths = _paths(args)
    wm_path = os.path.join(paths["scope_dir"], "working_memory.json")
    state = secure_io.read_json(wm_path) or wm.new_state()
    action = args.action
    result = {"action": action}
    write = False
    if action == "show":
        pass
    elif action == "load":
        item = wm.load(state, args.ref, args.goal_id, activation=args.activation,
                       complexity=args.complexity, now=args.now,
                       cognitive_load=args.cognitive_load)
        result["loaded"] = item["item_id"]
        write = True
    elif action == "rehearse":
        result["rehearsed"] = bool(wm.rehearse(state, args.item, now=args.now))
        write = True
    elif action == "decay":
        result["dropped"] = wm.decay(state, now=args.now)
        write = True
    elif action == "evict-irrelevant":
        result["removed"] = wm.evict_irrelevant(state, args.goal_id)
        write = True
    elif action == "clear":
        state = wm.new_state()
        write = True
    result["capacity"] = state.get("capacity")
    result["items"] = [{"item_id": i["item_id"], "content_ref": i["content_ref"],
                        "goal_id": i["goal_id"],
                        "activation": wm.current_activation(i, args.now or
                                                            event_store.now_iso())}
                       for i in state.get("items", [])]
    result["chunks"] = wm.chunk(state)
    if write and not args.dry_run:
        with _lock(paths):
            paths_mod.ensure_dirs(paths)
            secure_io.makedirs(paths["scope_dir"])
            secure_io.atomic_write_json(wm_path, state)
    return result


def cmd_retrieve(args):
    paths = _paths(args)
    snapshot = snap_mod.rebuild(paths, scope=paths["scope"], as_of=args.as_of)
    cue = _load_json_arg(args.cue) or _load_json_arg(args.goal) or {}
    res = retrieval.retrieve(snapshot, cue, query_scope=paths["scope"],
                             query_partition=args.partition,
                             limit=args.limit, include_suppressed=args.show_suppressed)
    res["metacognition"] = metacognition.classify(res, as_of=snapshot["as_of"])
    return res


def cmd_predict(args):
    context = _load_json_arg(args.context) or {}
    return prediction.evaluate(args.expected, args.outcome, context)


def cmd_choose(args):
    candidates = _load_json_arg(args.candidates)
    context = _load_json_arg(args.context) or {}
    if isinstance(candidates, dict):
        candidates = candidates.get("candidates", [])
    return policy_selection.select(candidates or [], context, explore=not args.no_explore)


def cmd_feedback(args):
    paths = _paths(args)
    if args.event:
        obj = secure_io.read_json(args.event)
        norm = event_store.event_from_file(obj, default_scope=paths["scope"])
        norm["kind"] = "feedback"
    else:
        payload = {"memory_id": args.memory, "outcome": args.outcome,
                   "expected": args.expected}
        norm = {"kind": "feedback", "scope": paths["scope"],
                "partition": args.partition, "payload": payload,
                "source": args.source, "source_trust": args.source_trust,
                "occurred_at": args.occurred_at}
    with _lock(paths):
        paths_mod.ensure_dirs(paths)
        ev, status = event_store.append_event(
            paths, "feedback", norm["scope"], norm["payload"],
            source=norm.get("source", "unknown"),
            source_trust=norm.get("source_trust", "verified_local"),
            occurred_at=norm.get("occurred_at"), partition=norm.get("partition"))
    return {"ok": True, "event_id": ev["event_id"], "status": status}


def cmd_consolidate(args):
    paths = _paths(args)
    dry = not args.apply
    if dry:
        return consolidation.consolidate(paths, scope=paths["scope"],
                                         as_of=args.as_of, dry_run=True)
    with _lock(paths):
        paths_mod.ensure_dirs(paths)
        return consolidation.consolidate(paths, scope=paths["scope"],
                                         as_of=args.as_of, dry_run=False)


def cmd_decay(args):
    """読取専用: as_of 時点の忘却推奨（想起抑制/検索除外）を報告する（truth は変えない）。"""
    paths = _paths(args)
    snapshot = snap_mod.rebuild(paths, scope=paths["scope"], as_of=args.as_of)
    rows = []
    for m in snapshot["memories"]:
        d = m.get("derived") or {}
        act = learning.forgetting_action(m, snapshot["as_of"])
        if act != "none" or d.get("retrievability", 1.0) < 0.3:
            rows.append({"memory_id": m["memory_id"], "status": m["status"],
                         "retrievability": d.get("retrievability"),
                         "forgetting": act, "protected": d.get("protected")})
    return {"as_of": snapshot["as_of"], "recommendations": rows,
            "note": "忘却は削除でなく想起抑制/検索除外。保護記憶は減衰で消さない(§7)。"}


def cmd_propose(args):
    paths = _paths(args)
    body = _load_json_arg(args.from_file) if args.from_file else {}
    body = body or {}
    proposal = prop_mod.make_proposal(
        args.type, rationale=args.rationale or body.get("rationale", ""),
        scope=paths["scope"], target_level=args.level or body.get("target_level"),
        evidence_ids=body.get("evidence_ids"), diff=body.get("diff"),
        expected_effect=body.get("expected_effect"),
        side_effects=body.get("side_effects"),
        counterexamples=body.get("counterexamples"), memory=body.get("memory"))
    if not args.dry_run:
        with _lock(paths):
            paths_mod.ensure_dirs(paths)
            prop_mod.write_proposal(paths, proposal)
    return {"ok": True, "proposal_id": proposal["proposal_id"],
            "status": proposal["status"], "dry_run": args.dry_run,
            "guard": executive.guard_self_modification(proposal)}


def cmd_promote(args):
    paths = _paths(args)
    snapshot = snap_mod.rebuild(paths, scope=paths["scope"], as_of=args.as_of)
    mem = next((m for m in snapshot["memories"] if m["memory_id"] == args.memory), None)
    if mem is None:
        return {"ok": False, "error": "memory が見つからない: %s" % args.memory}
    evidence = _load_json_arg(args.evidence) or {}
    decision = executive.authorize_promotion(
        mem, args.level, evidence, snapshot=snapshot, approver=args.approver,
        human_approval=args.human_approval)
    audit = {"cmd": "promote", "memory_id": args.memory, "target_level": args.level,
             "decision": decision}
    if not decision["authorized"]:
        _write_audit(paths, audit, args.dry_run)
        return {"ok": False, "authorized": False, "reasons": decision["reasons"]}
    if args.dry_run:
        return {"ok": True, "authorized": True, "dry_run": True, "decision": decision}
    body = dict(mem)
    body["level"] = args.level
    payload = {"memory": body, "target_level": args.level,
               "approver": args.approver, "proposal_id": args.proposal,
               "evidence_ids": evidence.get("evidence_ids", [])}
    with _lock(paths):
        paths_mod.ensure_dirs(paths)
        # 昇格前に現行 snapshot を backup（rollback 用・§16）。
        _backup_snapshot(paths)
        ev, status = event_store.append_event(
            paths, "promotion", paths["scope"], payload,
            source="executive", source_trust="user_confirmed",
            occurred_at=args.occurred_at, partition=args.partition, sanitize=False)
        _write_audit(paths, {**audit, "event_id": ev["event_id"]}, dry_run=False)
    return {"ok": True, "authorized": True, "event_id": ev["event_id"],
            "level": args.level}


def cmd_reject(args):
    paths = _paths(args)
    if args.proposal:
        with _lock(paths):
            p = prop_mod.set_status(paths, args.proposal, "rejected", approver=args.approver)
        return {"ok": p is not None, "proposal_id": args.proposal, "status": "rejected"}
    if args.memory:
        payload = {"memory_id": args.memory, "to_status": args.to_status,
                   "reason": args.reason, "approver": args.approver}
        with _lock(paths):
            paths_mod.ensure_dirs(paths)
            ev, _ = event_store.append_event(
                paths, "retraction", paths["scope"], payload, source="executive",
                source_trust="user_confirmed", partition=args.partition, sanitize=False)
        return {"ok": True, "event_id": ev["event_id"], "memory_id": args.memory,
                "to_status": args.to_status}
    return {"ok": False, "error": "--proposal か --memory を指定"}


def cmd_rollback(args):
    """backups/ から checksum 検証つきでファイルを復元する（§16）。"""
    paths = _paths(args)
    backup = args.backup
    if not backup or not os.path.exists(backup):
        return {"ok": False, "error": "backup が見つからない: %s" % backup}
    sha_path = backup + ".sha256"
    data = open(backup, "rb").read()
    digest = secure_io.sha256_bytes(data)
    if os.path.exists(sha_path):
        recorded = secure_io.read_text(sha_path).split()[0]
        if recorded != digest:
            return {"ok": False, "error": "checksum 不一致（破損の疑い）"}
    if args.dry_run:
        return {"ok": True, "dry_run": True, "would_restore_to": args.to,
                "checksum": digest}
    with _lock(paths):
        secure_io.atomic_write_bytes(args.to, data)
    return {"ok": True, "restored_to": args.to, "checksum": digest}


def cmd_report(args):
    paths = _paths(args)
    snapshot = snap_mod.rebuild(paths, scope=paths["scope"], as_of=args.as_of)
    epi = metacognition.epistemic_report(snapshot, as_of=snapshot["as_of"])
    return {"scope": paths["scope"], "as_of": snapshot["as_of"],
            "event_count": snapshot["event_count"],
            "source_event_hash": snapshot["source_event_hash"],
            "stats": snapshot["stats"], "epistemic": epi,
            "synapse": synapse_bridge.status()}


def cmd_verify(args):
    """読取専用の整合性検査（一切書き込まない・§16）。"""
    paths = _paths(args)
    problems, warnings = [], []
    events = event_store.all_events(paths)
    now = args.now
    for ev in events:
        p, w = validation.validate_event(ev, now=now)
        problems.extend(p)
        warnings.extend(w)
    # 決定性: 2回 rebuild して一致するか（generated_at は None で比較可能）。
    s1 = snap_mod.rebuild(paths, scope=paths["scope"], as_of=args.as_of)
    s2 = snap_mod.rebuild(paths, scope=paths["scope"], as_of=args.as_of)
    if json.dumps(s1, sort_keys=True) != json.dumps(s2, sort_keys=True):
        problems.append("replay が非決定的（2回の rebuild が不一致）")
    ps, ws = validation.validate_snapshot(s1)
    problems.extend(ps)
    warnings.extend(ws)
    # backup checksum 検証。
    for fn in _iter_backups(paths):
        if fn.endswith(".sha256"):
            continue
        sha = fn + ".sha256"
        if os.path.exists(sha):
            rec = secure_io.read_text(sha).split()[0]
            if secure_io.sha256_bytes(open(fn, "rb").read()) != rec:
                problems.append("backup checksum 不一致: %s" % fn)
    ok = len(problems) == 0
    return {"ok": ok, "n_events": len(events), "n_problems": len(problems),
            "problems": problems, "warnings": warnings[:50],
            "deterministic": "replay が非決定的" not in " ".join(problems)}


def cmd_replay(args):
    paths = _paths(args)
    events = event_store.all_events(paths, since=args.since, until=args.until)
    snapshot = snap_mod.rebuild(paths, scope=paths["scope"], as_of=args.as_of)
    result = {"scope": paths["scope"], "as_of": snapshot["as_of"],
              "event_count": snapshot["event_count"],
              "source_event_hash": snapshot["source_event_hash"],
              "n_memories": snapshot["stats"]["n_memories"],
              "dry_run": args.dry_run}
    if not args.dry_run:
        with _lock(paths):
            paths_mod.ensure_dirs(paths)
            secure_io.makedirs(paths["scope_dir"])
            persisted = dict(snapshot)
            persisted["generated_at"] = event_store.now_iso()
            secure_io.atomic_write_json(paths["memory"], persisted)
        result["written"] = paths["memory"]
    return result


def cmd_migrate(args):
    paths = _paths(args)
    if args.dry_run:
        return migrations.migrate(paths, dry_run=True)
    with _lock(paths):
        paths_mod.ensure_dirs(paths)
        return migrations.migrate(paths, dry_run=False)


# ---------------- helpers ----------------

def _backup_snapshot(paths):
    if os.path.exists(paths["memory"]):
        secure_io.backup_file(paths["memory"], paths["backups"], label="pre-promote")


def _write_audit(paths, record, dry_run):
    if dry_run:
        return
    import datetime
    secure_io.makedirs(paths["audit"])
    day = validation.parse_dt(event_store.now_iso())
    day = day.date().isoformat() if day else "unknown"
    record = dict(record)
    record["recorded_at"] = event_store.now_iso()
    secure_io.append_jsonl(os.path.join(paths["audit"], "%s.jsonl" % day), record)


def _iter_backups(paths):
    d = paths["backups"]
    if not os.path.isdir(d):
        return
    for fn in sorted(os.listdir(d)):
        yield os.path.join(d, fn)


# ---------------- parser ----------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="brain-cognitive-architecture-jp",
        description="監査可能な適応型認知アーキテクチャ (brain_architecture)")
    p.add_argument("--dir", help="記憶ルート（既定 ~/.claude/brain-memory 或いは "
                   "$BRAIN_MEMORY_DIR）")
    p.add_argument("--scope", default=paths_mod.DEFAULT_SCOPE, help="スコープ")
    p.add_argument("--partition", default=None, help="パーティション（顧客/組織等の隔離キー）")
    p.add_argument("--json", action="store_true", help="JSON 出力")
    p.add_argument("--as-of", dest="as_of", default=None, help="評価基準日 YYYY-MM-DD")
    p.add_argument("--now", default=None, help="現在時刻の上書き（テスト/決定性用）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="記憶ストアを初期化")

    o = sub.add_parser("observe", help="観測イベントを append（感覚ゲート）")
    o.add_argument("--event", help="イベント JSON ファイル")
    o.add_argument("--kind", default="observation")
    o.add_argument("--what")
    o.add_argument("--situation")
    o.add_argument("--goal", dest="goal_text")
    o.add_argument("--action")
    o.add_argument("--outcome")
    o.add_argument("--success-basis", dest="success_basis")
    o.add_argument("--confirmed-by", dest="confirmed_by")
    o.add_argument("--source", default="user_report")
    o.add_argument("--source-trust", dest="source_trust", default="untrusted_external")
    o.add_argument("--occurred-at", dest="occurred_at")
    o.add_argument("--session")

    a = sub.add_parser("attention", help="注意プロファイルを計算（読取専用）")
    a.add_argument("--stimulus", required=True, help="刺激 JSON（@file か '{...}'）")
    a.add_argument("--goal", help="目標 JSON")
    a.add_argument("--context", help="文脈 JSON")
    a.add_argument("--capacity", type=int, default=5)

    w = sub.add_parser("working-memory", help="作業記憶の操作")
    w.add_argument("--action", default="show",
                   choices=["show", "load", "rehearse", "decay", "evict-irrelevant",
                            "clear"])
    w.add_argument("--ref", help="content_ref（記憶ID等）")
    w.add_argument("--goal-id", dest="goal_id")
    w.add_argument("--item", help="item_id（rehearse 用）")
    w.add_argument("--activation", type=float, default=0.7)
    w.add_argument("--complexity", type=float, default=0.3)
    w.add_argument("--cognitive-load", dest="cognitive_load", type=float, default=0.3)
    w.add_argument("--dry-run", dest="dry_run", action="store_true")

    r = sub.add_parser("retrieve", help="部分手掛かり検索（読取専用）")
    r.add_argument("--cue", help="手掛かり JSON か文字列")
    r.add_argument("--goal", help="目標 JSON（cue 未指定時）")
    r.add_argument("--limit", type=int, default=8)
    r.add_argument("--show-suppressed", dest="show_suppressed", action="store_true")

    pr = sub.add_parser("predict", help="予測誤差を計算（読取専用）")
    pr.add_argument("--expected", type=float, required=True, help="成功見込み 0..1")
    pr.add_argument("--outcome", required=True, help="結果区分")
    pr.add_argument("--context", help="文脈 JSON")

    c = sub.add_parser("choose", help="方策選択（読取専用）")
    c.add_argument("--candidates", required=True, help="候補配列 JSON（@file 可）")
    c.add_argument("--context", help="文脈 JSON")
    c.add_argument("--no-explore", dest="no_explore", action="store_true")

    fb = sub.add_parser("feedback", help="結果フィードバックを append")
    fb.add_argument("--event")
    fb.add_argument("--memory")
    fb.add_argument("--outcome", default="unverified")
    fb.add_argument("--expected", type=float)
    fb.add_argument("--source", default="verified_local")
    fb.add_argument("--source-trust", dest="source_trust", default="verified_local")
    fb.add_argument("--occurred-at", dest="occurred_at")

    cs = sub.add_parser("consolidate", help="オフライン統合（既定 dry-run・候補のみ）")
    cs.add_argument("--apply", action="store_true", help="候補を proposals へ書き込む")

    sub.add_parser("decay", help="忘却推奨を報告（読取専用）")

    pp = sub.add_parser("propose", help="自己改変候補を作成")
    pp.add_argument("--type", required=True,
                    choices=["semantic", "procedure", "edge", "deprecation",
                             "skill_change"])
    pp.add_argument("--rationale")
    pp.add_argument("--level", help="target_level L0..L5")
    pp.add_argument("--from", dest="from_file", help="提案 body JSON ファイル")
    pp.add_argument("--dry-run", dest="dry_run", action="store_true")

    pm = sub.add_parser("promote", help="記憶を昇格（executive 認可＋人間承認）")
    pm.add_argument("--memory", required=True)
    pm.add_argument("--level", required=True, choices=["L1", "L2", "L3", "L4", "L5"])
    pm.add_argument("--evidence", help="証拠 JSON（@file 可）")
    pm.add_argument("--approver")
    pm.add_argument("--proposal")
    pm.add_argument("--human-approval", dest="human_approval", action="store_true")
    pm.add_argument("--occurred-at", dest="occurred_at")
    pm.add_argument("--dry-run", dest="dry_run", action="store_true")

    rj = sub.add_parser("reject", help="提案を却下 or 記憶を廃止")
    rj.add_argument("--proposal")
    rj.add_argument("--memory")
    rj.add_argument("--to-status", dest="to_status", default="deprecated",
                    choices=["deprecated", "archived", "rejected", "purged"])
    rj.add_argument("--reason")
    rj.add_argument("--approver")
    rj.add_argument("--occurred-at", dest="occurred_at")

    rb = sub.add_parser("rollback", help="backup から checksum 検証つきで復元")
    rb.add_argument("--backup", required=True, help="backup ファイルパス")
    rb.add_argument("--to", required=True, help="復元先パス")
    rb.add_argument("--dry-run", dest="dry_run", action="store_true")

    sub.add_parser("report", help="認知レポート（読取専用）")

    v = sub.add_parser("verify", help="整合性検査（読取専用・無副作用）")

    rp = sub.add_parser("replay", help="event log から snapshot を再構築")
    rp.add_argument("--since", help="YYYY-MM-DD 以降")
    rp.add_argument("--until", help="YYYY-MM-DD 以前")
    rp.add_argument("--dry-run", dest="dry_run", action="store_true")

    mg = sub.add_parser("migrate", help="スキーマ移行")
    mg.add_argument("--dry-run", dest="dry_run", action="store_true")

    return p


_DISPATCH = {
    "init": cmd_init, "observe": cmd_observe, "attention": cmd_attention,
    "working-memory": cmd_working_memory, "retrieve": cmd_retrieve,
    "predict": cmd_predict, "choose": cmd_choose, "feedback": cmd_feedback,
    "consolidate": cmd_consolidate, "decay": cmd_decay, "propose": cmd_propose,
    "promote": cmd_promote, "reject": cmd_reject, "rollback": cmd_rollback,
    "report": cmd_report, "verify": cmd_verify, "replay": cmd_replay,
    "migrate": cmd_migrate,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    fn = _DISPATCH.get(args.cmd)
    if fn is None:
        print("未知のコマンド: %s" % args.cmd, file=sys.stderr)
        return 2
    try:
        result = fn(args)
    except Exception as exc:  # noqa: BLE001 — CLI 境界で失敗を JSON 化する
        _out({"ok": False, "error": str(exc), "type": type(exc).__name__},
             getattr(args, "json", False))
        return 1
    _out(result, getattr(args, "json", False))
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    if args.cmd == "verify" and isinstance(result, dict) and not result.get("ok"):
        return 1
    return 0
