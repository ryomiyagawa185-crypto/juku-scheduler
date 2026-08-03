#!/usr/bin/env python3
"""traces/ と artifacts/{pii,privileged}/ が git に載っていないか検査する。

.gitignore は「うっかり」を防ぐが、git add -f は素通りする。
事件記録と生徒データを扱う以上、誤コミットは CI で落とす。
併せて、追跡対象ファイルに典型的な鍵の形が混ざっていないかも見る。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_PREFIXES = (
    "traces/",
    "state/",
    "artifacts/pii/",
    "artifacts/privileged/",
)

KEY_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "APIキーらしき文字列"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWSアクセスキー"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "秘密鍵"),
    (re.compile(r"(?i)\b(authorization|api[_-]?key|secret)\b\s*[:=]\s*['\"][^'\"]{16,}"), "資格情報の直書き"),
]

TEXT_SUFFIXES = {".py", ".md", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".txt", ".sh"}


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line for line in out.splitlines() if line]


def main() -> int:
    problems: list[str] = []
    files = tracked_files()

    for path in files:
        if any(path.startswith(p) for p in FORBIDDEN_PREFIXES):
            problems.append(f"追跡してはいけないパスが git に載っています: {path}")

    for path in files:
        p = ROOT / path
        if p.suffix not in TEXT_SUFFIXES or not p.exists():
            continue
        if p.name == Path(__file__).name:
            continue  # 自分自身のパターン定義は除外
        text = p.read_text(encoding="utf-8", errors="replace")
        for pattern, label in KEY_PATTERNS:
            if pattern.search(text):
                problems.append(f"{path}: {label} を検出")
                break

    if problems:
        print("秘密情報／個人情報の混入が疑われます:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1

    print(f"secret/pii scan: OK（{len(files)} ファイル）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
