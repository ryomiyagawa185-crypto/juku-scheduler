# -*- coding: utf-8 -*-
"""validation — 軽量 JSON Schema バリデータ ＋ ドメイン不変条件検査（仕様 §16/§18）。

標準ライブラリのみ。type/required/properties/items/enum を解釈する小さな検証器と、
id 形状・日付形式・数値範囲・NaN/Inf・エッジ端点整合・将来時刻検出などの
認知アーキ固有の不変条件を検査する。jsonschema には依存しない（未導入環境で動く）。
"""

import datetime
import math
import re

from . import schemas

ID_RE = re.compile(r"^[a-z][a-z0-9_]*_[A-Za-z0-9]+$")     # evt_.., mem_.., edge_..
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?")
_JSON_TYPES = {
    "object": dict, "array": list, "string": str,
    "integer": int, "number": (int, float), "boolean": bool, "null": type(None),
}


def _type_ok(value, tspec):
    types = tspec if isinstance(tspec, list) else [tspec]
    for t in types:
        py = _JSON_TYPES.get(t)
        if py is None:
            return True
        # bool は int のサブクラスなので integer/number 判定から除外する。
        if t in ("integer", "number") and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def validate_schema(obj, schema, path="$", errors=None):
    """最小限の JSON Schema 検証。errors のリストを返す（空なら妥当）。"""
    if errors is None:
        errors = []
    t = schema.get("type")
    if t is not None and not _type_ok(obj, t):
        errors.append("%s: type != %s (got %s)" % (path, t, type(obj).__name__))
        return errors
    enum = schema.get("enum")
    if enum is not None and obj not in enum:
        errors.append("%s: enum 外 %r" % (path, obj))
    if isinstance(obj, dict):
        for req in schema.get("required", []):
            if req not in obj:
                errors.append("%s: required '%s' 欠落" % (path, req))
        props = schema.get("properties", {})
        for k, v in obj.items():
            if k in props:
                validate_schema(v, props[k], "%s.%s" % (path, k), errors)
    elif isinstance(obj, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, it in enumerate(obj):
                validate_schema(it, item_schema, "%s[%d]" % (path, i), errors)
    return errors


def validate_named(obj, name):
    schema = schemas.SCHEMAS_BY_NAME.get(name)
    if schema is None:
        return ["未知のスキーマ名: %s" % name]
    return validate_schema(obj, schema)


def parse_dt(s):
    """ISO 日付/日時をパース（失敗は None）。'Z' と時差オフセットに対応。"""
    if not s or not isinstance(s, str):
        return None
    txt = s.strip().replace("Z", "+00:00")
    for parse in (datetime.datetime.fromisoformat, _parse_date_only):
        try:
            return parse(txt)
        except (ValueError, TypeError):
            continue
    return None


def _parse_date_only(txt):
    d = datetime.date.fromisoformat(txt[:10])
    return datetime.datetime(d.year, d.month, d.day)


def is_future(occurred_at, now=None, tolerance_seconds=120):
    """occurred_at が now より未来か（将来時刻イベント検出・§18 chronology）。

    tz-aware/naive の差を吸収し、比較は naive UTC 相当へ寄せる。tolerance で
    軽微な時計ずれは許容する。パース不能は False（別途 schema エラーで捕捉）。
    """
    dt = parse_dt(occurred_at)
    if dt is None:
        return False
    now = now or datetime.datetime.now()
    a = _to_naive(dt)
    b = _to_naive(now if isinstance(now, datetime.datetime) else parse_dt(str(now)))
    if a is None or b is None:
        return False
    return (a - b).total_seconds() > tolerance_seconds


def _to_naive(dt):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def _finite_number(v):
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(fv) or math.isinf(fv):
        return None
    return fv


def validate_event(ev, now=None):
    """イベント1件を検査し (problems, warnings) を返す。"""
    problems = validate_schema(ev, schemas.EVENT_SCHEMA)[:]
    warnings = []
    eid = ev.get("event_id", "?")
    oa = ev.get("occurred_at")
    if oa is not None and not DATETIME_RE.match(str(oa)) and not DATE_RE.match(str(oa)):
        problems.append("%s: occurred_at の形式が不正: %r" % (eid, oa))
    elif is_future(oa, now=now):
        # 将来時刻は拒否/隔離の対象（§18）。ここでは problem として上げる。
        problems.append("%s: occurred_at が未来（拒否/隔離対象）: %r" % (eid, oa))
    if ev.get("contains_sensitive_data") is True:
        warnings.append("%s: contains_sensitive_data=true（要約/hash のみ保存すべき）" % eid)
    return problems, warnings


def validate_memory(mem):
    problems = validate_schema(mem, schemas.MEMORY_SCHEMA)[:]
    mid = mem.get("memory_id", "?")
    conf = _finite_number(mem.get("confidence"))
    if conf is None:
        problems.append("%s: confidence が数値でない/NaN" % mid)
    elif not (0.0 <= conf <= 1.0):
        problems.append("%s: confidence 範囲外[0,1]: %s" % (mid, conf))
    lvl, st = mem.get("level"), mem.get("status")
    if lvl in schemas.LEVEL_TO_STATUS and st is not None:
        # level と status の整合（L→status の粗い対応）。
        if schemas.LEVEL_TO_STATUS[lvl] != st and st not in (
                "conflicted", "deprecated", "archived", "rejected", "purged"):
            problems.append("%s: level=%s と status=%s が不整合" % (mid, lvl, st))
    return problems


def validate_snapshot(snap):
    """snapshot の構造/整合を検査し (problems, warnings) を返す。"""
    problems = validate_schema(snap, schemas.SNAPSHOT_SCHEMA)[:]
    warnings = []
    node_ids = set()
    for m in snap.get("memories", []):
        mid = m.get("memory_id")
        if mid in node_ids:
            problems.append("重複 memory_id: %s" % mid)
        node_ids.add(mid)
        problems.extend(validate_memory(m))
    seen = set()
    for e in snap.get("edges", []):
        s, t, rel = e.get("source"), e.get("target"), e.get("relation")
        key = (s, t, rel)
        if key in seen:
            problems.append("重複エッジ: %s" % (key,))
        seen.add(key)
        if rel not in schemas.RELATION_TYPES:
            problems.append("未知の関係型: %r (%s)" % (rel, e.get("edge_id")))
        derived = e.get("derived") or {}
        for k, v in derived.items():
            if isinstance(v, (int, float)) and _finite_number(v) is None:
                problems.append("edge.derived.%s が NaN/Inf: %s" % (k, e.get("edge_id")))
        if "raw" not in e:
            warnings.append("edge に raw（観測事実）が無い: %s" % e.get("edge_id"))
    return problems, warnings
