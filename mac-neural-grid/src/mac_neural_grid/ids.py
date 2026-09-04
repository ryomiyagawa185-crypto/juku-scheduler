# -*- coding: utf-8 -*-
"""ids — 決定的な一意 ID と冪等キー（仕様 §22）。

job_id / task_id / attempt_id / idempotency_key / input_hash / policy_hash を定義。
同じジョブ（同じ内容 + idempotency_key）を再送しても二重実行しない設計の土台。
IP アドレスをノード ID に固定しない（§7）: node_id は表示名 + 内容ハッシュから作る。
"""

import hashlib
import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(text):
    s = _SLUG_RE.sub("-", str(text).lower()).strip("-")
    return s or "x"


def _h(*parts):
    payload = "\x1f".join(str(p) for p in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def node_id(display_name, host, arch="unknown"):
    """IP に依存しない安定 node_id。表示名 + host + arch の内容ハッシュ。"""
    return "node-%s-%s" % (slug(display_name), _h(display_name, host, arch)[:8])


def job_id(name, idempotency_key):
    return "job-%s-%s" % (slug(name), _h(name, idempotency_key)[:10])


def task_id(job, index, task_key):
    return "task-%s-%03d-%s" % (job.split("-")[-1], index, _h(job, index, task_key)[:6])


def attempt_id(task, attempt_no):
    return "att-%s-%d" % (task.split("-")[-1], attempt_no)


def input_hash(inputs):
    """入力集合（ファイルパス + サイズ + mtime の要約 or 明示値）の決定的ハッシュ。"""
    if isinstance(inputs, (list, tuple)):
        key = "|".join(sorted(str(i) for i in inputs))
    else:
        key = str(inputs)
    return "sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def policy_hash(policy):
    import json
    canon = json.dumps(policy or {}, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:32]


def idempotency_key(name, inputs, policy_name, extra=""):
    """内容アドレス的な冪等キー。同一入力・同一ポリシーなら同じキー。"""
    return _h(name, input_hash(inputs), policy_name, extra)[:16]
