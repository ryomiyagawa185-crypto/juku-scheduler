#!/usr/bin/env python3
"""求人票の本文を、Indeed の「仕事内容」欄にそのまま貼れるプレーンテキストに変換する。

求人票は Markdown で書いてあるため、`###` や `**` をそのまま貼ると
Indeed の入力欄では記号が文字として表示されてしまう。
このスクリプトは記号を落とし、見出しと箇条書きだけを残した平文にする。

  ### ■ 見出し      →  ■ 見出し
  **強調**          →  強調
  - 項目            →  ・項目
  | 表 | 組み |     →  表：組み
  > 引用            →  （行頭の > を除去）

出力先: recruitment/indeed/plaintext/<番号>_<職種>.txt

使い方:
    python3 recruitment/indeed/to_plaintext.py            # 全求人票を変換
    python3 recruitment/indeed/to_plaintext.py 17 11 14   # 番号を指定
"""

import re
import sys
from pathlib import Path

BODY_MARKER = "## 仕事内容（本文コピペ用）"
OUT_DIR = Path(__file__).parent / "plaintext"

TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def convert(md: str) -> str:
    idx = md.find(BODY_MARKER)
    if idx == -1:
        return ""
    body = md[idx + len(BODY_MARKER) :]

    out: list[str] = []
    for line in body.splitlines():
        s = line.rstrip()

        # 水平線は削る
        if s.strip() in ("---", "***", "___"):
            continue
        # 表の区切り行は削る
        if TABLE_SEP_RE.match(s):
            continue

        # 表の行は「見出し：内容」に畳む
        if s.strip().startswith("|") and s.strip().endswith("|"):
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            cells = [c for c in cells if c]
            s = "　".join(cells) if len(cells) < 2 else f"{cells[0]}：{'　'.join(cells[1:])}"

        # 見出し記号を落とす
        s = re.sub(r"^#{1,6}\s*", "", s)
        # 引用記号を落とす
        s = re.sub(r"^>\s?", "", s)
        # 箇条書きを中黒に
        s = re.sub(r"^(\s*)[-*+]\s+", lambda m: m.group(1) + "・", s)
        # 番号付きリストはそのまま（1. 2. の形は Indeed でも読める）
        # 強調・コード・リンクの記法を落とす
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", s)
        s = re.sub(r"`(.+?)`", r"\1", s)
        s = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1（\2）", s)
        s = s.replace("~~", "")

        out.append(s)

    # 空行が3つ以上続くのを2つに詰める
    text = "\n".join(out).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text + "\n"


def main() -> int:
    here = Path(__file__).parent
    wanted = {a.zfill(2) for a in sys.argv[1:]}

    files = sorted(
        p for p in here.glob("*.md") if re.match(r"^(?!00_)\d{2}_", p.name)
    )
    if wanted:
        files = [p for p in files if p.name[:2] in wanted]
        missing = wanted - {p.name[:2] for p in files}
        if missing:
            print(f"該当する求人票がありません: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    if not files:
        print("変換対象がありません。", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(exist_ok=True)
    for p in files:
        text = convert(p.read_text(encoding="utf-8"))
        if not text.strip():
            print(f"本文が取り出せません: {p.name}", file=sys.stderr)
            return 2
        dest = OUT_DIR / (p.stem + ".txt")
        dest.write_text(text, encoding="utf-8")
        chars = len(text.replace("\n", ""))
        print(f"生成: {dest.relative_to(here.parent.parent)}  ({chars:,}文字)")

    print(f"\n{len(files)}件を変換しました。Indeed の「仕事内容」欄にそのまま貼れます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
