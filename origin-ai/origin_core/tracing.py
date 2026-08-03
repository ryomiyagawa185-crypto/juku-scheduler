"""トレース書き出し。

守るべき不変条件は2つ。

1. **本文を書かない。** 記録するのはハッシュと artifacts へのポインタだけ。
   事件記録と生徒データを扱う以上、トレースに本文が入ると
   ログのローテートと保持期間の管理が丸ごと個人情報の問題になる。
   trace.schema.json の additionalProperties:false が防波堤で、
   ここでも書き出し前に検証している。

2. **宣言済みシークレットを必ずマスクする。** 実際の漏洩は
   inputs 経由よりも例外メッセージ経由で起きるので、
   例外整形も同じマスカを通すこと。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import ROOT, schema

MASK = "***REDACTED***"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_trace_id() -> str:
    return str(uuid.uuid4())


def mask(text: str, secret_names: Iterable[str]) -> str:
    """環境変数に入っている宣言済みシークレットの値を伏せる。"""
    out = text
    for name in secret_names:
        value = os.environ.get(name)
        if value and len(value) >= 6:
            out = out.replace(value, MASK)
    return out


def mask_exception(exc: BaseException, secret_names: Iterable[str]) -> str:
    return mask(f"{type(exc).__name__}: {exc}", secret_names)


class Tracer:
    def __init__(self, root: Path | None = None, secret_names: Iterable[str] = ()):
        self.root = Path(root) if root else ROOT / "traces"
        self.secret_names = list(secret_names)

    def path_for(self, when: datetime | None = None) -> Path:
        day = (when or datetime.now()).strftime("%Y-%m-%d")
        return self.root / day / "trace.jsonl"

    def write(self, record: dict[str, Any]) -> Path:
        """1行追記する。スキーマ違反なら書かずに例外を投げる。"""
        record = {k: self._mask_value(v) for k, v in record.items()}
        schema.validate(record, "trace")
        path = self.path_for()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return path

    def _mask_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return mask(value, self.secret_names)
        if isinstance(value, list):
            return [self._mask_value(v) for v in value]
        return value
