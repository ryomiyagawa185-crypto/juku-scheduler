#!/usr/bin/env python3
"""echo スキルの実行層。

スキルの実行スクリプトの規約:
- stdin から {"inputs": {...}, "dry_run": bool} を受け取る
- stdout に JSON を1つ書く
- 異常時は非ゼロで終了し、stderr に理由を書く（本文や秘密情報を書かない）
- dry_run が true のとき、副作用を起こしてはならない
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = ROOT / "artifacts" / "open" / "echo"


def atomic_write(path: Path, text: str) -> None:
    """一時ファイル + rename。半端な成果物を残さない。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main() -> int:
    payload = json.load(sys.stdin)
    inputs = payload.get("inputs", {})
    dry_run = bool(payload.get("dry_run"))

    message = inputs.get("message")
    if not isinstance(message, str) or not message:
        print("message（文字列）が必要です", file=sys.stderr)
        return 1

    written = None
    if not dry_run:
        target = OUT_DIR / "echo.txt"
        atomic_write(target, message + "\n")
        written = str(target.relative_to(ROOT))

    json.dump({"echo": message, "written": written}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
