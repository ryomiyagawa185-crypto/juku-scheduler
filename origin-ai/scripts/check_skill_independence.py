#!/usr/bin/env python3
"""スキル間の直接 import を拒否する。

禁止するのは skills.* → skills.* だけ。
skills.* → origin_core は **許可** する。

v0.1 は共通ユーティリティ層そのものを禁止していたが、
スキーマ検証やハッシュ計算のような純粋関数のために
メタスキル経由の LLM 往復を強いるのは、レイテンシもコストも桁で悪化する。
独立性が守りたいのは「スキルAの判断がスキルBに依存すること」であって
「共通の関数を使わないこと」ではない。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"^\s*(?:from\s+skills[\w.]*\s+import|import\s+skills[\w.]*)", re.M)


def main() -> int:
    violations: list[str] = []
    for py in sorted((ROOT / "skills").rglob("*.py")):
        text = py.read_text(encoding="utf-8", errors="replace")
        for match in PATTERN.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            violations.append(f"{py.relative_to(ROOT)}:{line_no}: {match.group(0).strip()}")

    if violations:
        print("スキル間の直接 import は禁止です（依存は depends_on に書き、台帳経由で解決すること）:",
              file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("skill independence: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
