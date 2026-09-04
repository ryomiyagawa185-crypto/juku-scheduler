# -*- coding: utf-8 -*-
"""event_store — append-only イベントログ（正本・不変な事実／仕様 §15/§A）。

イベントは ``<dir>/events/YYYY-MM.jsonl`` に1行ずつ追記され、二度と書き換えない。
snapshot は本ログから replay で再構築される派生物にすぎない。

感覚・入力ゲート（§A）の一部として、原文プロンプト・秘密情報・個人情報は保存せず、
構造化要約 ＋ content_hash のみを刻む（§11）。exact-duplicate は content-addressed
id で自然に排除され、replay 順序は挿入順に依存しない（occurred_at, event_id）。
"""

import datetime
import hashlib
import json
import os
import re

from . import secure_io
from . import paths as paths_mod
from . import validation

# --- 秘密情報・個人情報の検出パターン（§11）。ヒットしたら原文を保存しない ---
_SENSITIVE_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("password_kv", re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b\s*[:=]\s*\S+")),
    ("env_assignment", re.compile(r"(?m)^[A-Z][A-Z0-9_]*_(KEY|SECRET|TOKEN|PASSWORD)\s*=\s*\S+")),
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("jp_mynumber", re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("cookie", re.compile(r"(?i)\b(session|sid|csrftoken|connect\.sid)\b\s*[:=]\s*\S+")),
]


def scan_sensitive(text):
    """テキストから機密カテゴリを検出し、ヒットしたカテゴリ名の集合を返す。"""
    if not isinstance(text, str):
        return set()
    hits = set()
    for name, rx in _SENSITIVE_PATTERNS:
        if rx.search(text):
            hits.add(name)
    return hits


def redact(text):
    """機密トークンを [REDACTED:<cat>] へ置換する（保存前サニタイズ）。"""
    if not isinstance(text, str):
        return text
    out = text
    for name, rx in _SENSITIVE_PATTERNS:
        out = rx.sub("[REDACTED:%s]" % name, out)
    return out


def scan_payload(payload):
    """payload（dict/str/list）を再帰走査し、機密カテゴリ集合を返す。"""
    hits = set()

    def walk(v):
        if isinstance(v, str):
            hits.update(scan_sensitive(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(payload)
    return hits


def redact_payload(payload):
    """payload を再帰的にサニタイズ（原文は残さない）。"""
    if isinstance(payload, str):
        return redact(payload)
    if isinstance(payload, dict):
        return {k: redact_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [redact_payload(v) for v in payload]
    return payload


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def content_hash(payload):
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def session_hash(token):
    if not token:
        return None
    return "sha256:" + hashlib.sha256(str(token).encode("utf-8")).hexdigest()[:32]


def make_event_id(kind, scope, occurred_at, chash, partition=None):
    """content-addressed な event_id。同一(kind,scope,partition,occurred_at,内容)なら同一 id。

    → exact-duplicate は自然に排除され、replay は挿入順に依存しない。partition を
    含めるので、異なる顧客の同内容イベントが衝突・消失しない（§5 漏洩防止）。
    """
    payload = "%s#%s#%s#%s#%s" % (kind, scope, partition or "", occurred_at, chash)
    return "evt_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def ym_of(occurred_at):
    dt = validation.parse_dt(occurred_at)
    if dt is None:
        return datetime.date.today().isoformat()[:7]
    return dt.strftime("%Y-%m")


def _read_shard(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue  # 壊れた1行は飛ばす（§18 壊れたJSON耐性）
            if isinstance(ev, dict) and ev.get("event_id"):
                out.append(ev)
    return out


def _sort_key(ev):
    dt = validation.parse_dt(ev.get("occurred_at"))
    ts = validation._to_naive(dt)
    # 未パースは末尾へ（大きな番兵）。tie-break は content-addressed な event_id。
    ts_key = ts.isoformat() if ts is not None else "9999-12-31T23:59:59"
    return (ts_key, str(ev.get("event_id", "")))


def all_events(paths, scope=None, since=None, until=None, include_future=True):
    """全シャードを決定的順序 (occurred_at, event_id) で返す。挿入順に非依存。

    scope 指定時はその scope に絞る。since/until は occurred_at の日付境界。
    include_future=False で将来時刻イベントを除外（隔離・§18）。
    """
    evdir = paths["events"]
    events = []
    if os.path.isdir(evdir):
        for fn in sorted(os.listdir(evdir)):
            if fn.endswith(".jsonl"):
                events.extend(_read_shard(os.path.join(evdir, fn)))
    # content-addressed id による重複排除（決定的エミッタの再実行を冪等化）。
    seen, deduped = set(), []
    for e in events:
        eid = e.get("event_id")
        if eid in seen:
            continue
        seen.add(eid)
        deduped.append(e)
    events = deduped
    if scope is not None:
        events = [e for e in events if e.get("scope") == scope]
    if since is not None:
        events = [e for e in events if str(e.get("occurred_at", ""))[:10] >= since]
    if until is not None:
        events = [e for e in events if str(e.get("occurred_at", ""))[:10] <= until]
    if not include_future:
        events = [e for e in events if not validation.is_future(e.get("occurred_at"))]
    events.sort(key=_sort_key)
    return events


def ordered_event_hash(events):
    """順序付きイベント id 列の integrity hash（snapshot 出所検証・§15）。"""
    joined = "|".join(e.get("event_id", "") for e in events)
    return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()


def event_identity_exists(paths, event_id):
    for e in all_events(paths):
        if e.get("event_id") == event_id:
            return True
    return False


def append_event(paths, kind, scope, payload, source="unknown",
                 source_trust="untrusted_external", occurred_at=None,
                 session=None, sanitize=True, now=None, partition=None):
    """1イベントを append-only ログへ追記し (event, status) を返す。

    status: "accepted" | "duplicate" | "quarantined"（将来時刻）。
    sanitize=True で payload をサニタイズし、機密検出時は contains_sensitive_data を
    立てる（原文は保存しない）。
    """
    occurred_at = occurred_at or now_iso()
    sensitive_hits = scan_payload(payload)
    clean_payload = redact_payload(payload) if sanitize else payload
    chash = content_hash(payload)  # hash は原文ベース（同一原文の重複検知のため）
    event_id = make_event_id(kind, scope, occurred_at, chash, partition)
    status = "accepted"
    # 将来時刻イベントは隔離（受け入れるが quarantined 印を付け、replay で除外可能）。
    if validation.is_future(occurred_at, now=now):
        status = "quarantined"
    event = {
        "event_id": event_id,
        "kind": kind,
        "occurred_at": occurred_at,
        "recorded_at": now_iso(),
        "seq": _next_seq(paths),
        "scope": scope,
        "partition": partition,
        "source": source,
        "source_trust": source_trust,
        "session_id_hash": session_hash(session),
        "contains_sensitive_data": bool(sensitive_hits),
        "sensitive_categories": sorted(sensitive_hits),
        "content_hash": chash,
        "quarantined": (status == "quarantined"),
        "payload": clean_payload,
    }
    # content-addressed id による exact-duplicate 抑制（§A 重複イベント排除）。
    if event_identity_exists(paths, event_id):
        return event, "duplicate"
    secure_io.append_jsonl(paths_mod.event_shard(paths, ym_of(occurred_at)), event)
    return event, status


def _next_seq(paths):
    return len(all_events(paths))


def event_from_file(obj, default_scope="project"):
    """外部 JSON（event.json）を append_event の引数へ正規化する。"""
    payload = obj.get("payload")
    if payload is None:
        # payload を持たない素の入力は、既知メタ以外を payload に畳み込む。
        meta_keys = {"kind", "scope", "source", "source_trust", "occurred_at",
                     "session", "content", "contains_sensitive_data"}
        payload = {k: v for k, v in obj.items() if k not in meta_keys}
        if "content" in obj:
            payload["content"] = obj["content"]
    return {
        "kind": obj.get("kind", "observation"),
        "scope": obj.get("scope", default_scope),
        "partition": obj.get("partition"),
        "payload": payload,
        "source": obj.get("source") or obj.get("source_type", "unknown"),
        "source_trust": obj.get("source_trust", "untrusted_external"),
        "occurred_at": obj.get("occurred_at"),
        "session": obj.get("session"),
    }
