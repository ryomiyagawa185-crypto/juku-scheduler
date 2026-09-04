#!/usr/bin/env python3
"""ハローワーク求人申込書の入力欄の文字数制限をチェックする。

各 .md ファイル中の、

    <!-- LIMIT 30x9 仕事内容 -->
    ```
    （本文）
    ```

という形のブロックを見つけ、直後のコードブロックが
「1行あたり30文字以内・9行以内」に収まっているか検査する。

全角・半角の別なく1文字を1文字として数える（ハローワークの入力欄は
全角換算だが、半角文字は0.5文字ではなく1文字分の枠を使う運用のため、
安全側に倒して等価に数える）。

使い方:
    python3 recruitment/hellowork/check_limits.py
    python3 recruitment/hellowork/check_limits.py path/to/file.md
"""

import re
import sys
from pathlib import Path

LIMIT_RE = re.compile(r"<!--\s*LIMIT\s+(\d+)x(\d+)(?:\s+(.*?))?\s*-->")
FENCE_RE = re.compile(r"^\s*```")


def check_file(path: Path) -> list[str]:
    """1ファイルを検査し、違反メッセージのリストを返す。"""
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        m = LIMIT_RE.search(lines[i])
        if not m:
            i += 1
            continue

        max_chars, max_lines = int(m.group(1)), int(m.group(2))
        label = (m.group(3) or "").strip() or "（無題）"
        marker_lineno = i + 1

        # 直後のコードフェンスを探す（空行は読み飛ばす）
        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        if j >= len(lines) or not FENCE_RE.match(lines[j]):
            errors.append(
                f"{path}:{marker_lineno}: LIMIT マーカーの直後にコードブロックがありません（{label}）"
            )
            i += 1
            continue

        # フェンスの中身を集める
        body: list[tuple[int, str]] = []
        k = j + 1
        while k < len(lines) and not FENCE_RE.match(lines[k]):
            body.append((k + 1, lines[k]))
            k += 1

        if len(body) > max_lines:
            errors.append(
                f"{path}:{marker_lineno}: {label} は {len(body)}行（上限{max_lines}行）"
            )
        for lineno, text in body:
            n = len(text.rstrip())
            if n > max_chars:
                errors.append(
                    f"{path}:{lineno}: {label} の行が {n}文字（上限{max_chars}文字）: {text.rstrip()}"
                )
        i = k + 1
    return errors


def main() -> int:
    args = sys.argv[1:]
    targets = (
        [Path(a) for a in args]
        if args
        else sorted(Path(__file__).parent.glob("*.md"))
    )

    all_errors: list[str] = []
    for path in targets:
        if not path.exists():
            print(f"見つかりません: {path}", file=sys.stderr)
            return 2
        all_errors.extend(check_file(path))

    if all_errors:
        for e in all_errors:
            print(e)
        print(f"\n{len(all_errors)}件の超過があります。")
        return 1

    print(f"{len(targets)}ファイルを検査。文字数制限の超過はありません。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
