# -*- coding: utf-8 -*-
"""logging — 秘密値を残さない構造化ログ（仕様 §24/§30）。

すべてのログ行を redact してから書く。秘密値・機密文書原文・API キーは残さない。
"""

import json
import sys

from . import security
from .database import now_iso


def event_line(kind, **fields):
    rec = {"ts": now_iso(), "kind": kind}
    rec.update(fields)
    return json.dumps(security.redact_obj(rec), ensure_ascii=False)


def emit(kind, stream=None, **fields):
    (stream or sys.stderr).write(event_line(kind, **fields) + "\n")


def write_log(path, kind, **fields):
    line = event_line(kind, **fields) + "\n"
    old = security.redact(open(path, encoding="utf-8").read()) if _exists(path) else ""
    security.atomic_write(path, old + line)


def _exists(path):
    import os
    return os.path.exists(path)
