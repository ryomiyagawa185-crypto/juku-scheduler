#!/usr/bin/env python3
"""指定した求人票から、ローカルのClaude Codeへ渡す投稿依頼文を組み立てる。

リモートセッション（claude.ai・GitHub連携）にはブラウザ操作のMCPが繋がっていないため、
Indeedへの投稿はローカルのClaude Code（claude-in-chrome MCPが常駐している環境）で行う。
このスクリプトは、その依頼文を求人票から自動生成する。

求人票の「▼ Indeed 入力フォーム対応表」をそのまま読むので、
条件を変えても依頼文が古くならない。

使い方:
    python3 recruitment/indeed/make_briefing.py 17
    python3 recruitment/indeed/make_briefing.py 17 --out /tmp/briefing.md
"""

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
TABLE_MARKER = "## ▼ Indeed 入力フォーム対応表"
BODY_MARKER = "## 仕事内容（本文コピペ用）"
ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
HEADER_KEYS = {"入力欄", "項目"}


def find_posting(number: str) -> Path:
    number = number.zfill(2)
    hits = [
        p
        for p in sorted(HERE.glob("*.md"))
        if re.match(r"^(?!00_)\d{2}_", p.name) and p.name.startswith(number + "_")
    ]
    if not hits:
        raise SystemExit(f"求人票が見つかりません: {number}")
    return hits[0]


def extract_fields(md: str) -> list[tuple[str, str]]:
    start = md.find(TABLE_MARKER)
    if start == -1:
        raise SystemExit("「▼ Indeed 入力フォーム対応表」が見つかりません")
    chunk = md[start + len(TABLE_MARKER) :]
    end = chunk.find("\n---")
    if end != -1:
        chunk = chunk[:end]

    fields: list[tuple[str, str]] = []
    for line in chunk.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        key, value = m.group(1).strip(), m.group(2).strip()
        if key in HEADER_KEYS or set(key) <= set("-: ") or not value:
            continue
        if set(value) <= set("-: "):
            continue
        fields.append((key, value))
    if not fields:
        raise SystemExit("対応表から項目を読み取れませんでした")
    return fields


def build(number: str, path: Path, body_rel: str) -> str:
    md = path.read_text(encoding="utf-8")

    if "【要確認】" in md.split(BODY_MARKER)[-1]:
        raise SystemExit(
            f"{path.name} の本文に【要確認】が残っています。確定してから実行してください。"
        )

    fields = extract_fields(md)
    rows = "\n".join(f"| {k} | {v} |" for k, v in fields)
    table = "| 入力欄 | 入力内容 |\n|---|---|\n" + rows

    return f"""# 依頼：Indeed へ求人を1件、無料掲載で投稿してください

あなたはローカルのClaude Codeで、Chrome操作のMCP（claude-in-chrome）が使える環境にいます。
以下の求人を Indeed に投稿してください。**投稿するのはこの1件だけです。**

## 1. 手順

1. Chrome操作ツールを読み込む
   `ToolSearch: select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__find,mcp__claude-in-chrome__get_page_text`
2. `tabs_context_mcp {{createIfEmpty:true}}` → Indeed の求人管理画面（employers.indeed.com）を開く
   すでにログイン済みのタブが開いている場合は、そのタブを使う
3. 「求人を掲載」から新規作成に入る
4. 下記の値を各欄に入力する（**画面の項目名と完全一致しないことがあります。意味で対応づけてください**）
5. 「仕事内容」欄には、次のファイルの中身を**全文**貼り付ける
   `{body_rel}`（リポジトリ直下からの相対パス）
6. 内容を確認し、投稿する

## 2. 入力する値

{table}

**応募連絡先メール**：musasinokobetu.daily@gmail.com

## 3. 絶対に守ること

| # | ルール | 理由 |
|---|---|---|
| 1 | **スポンサー（有料掲載）は必ずオフ**。予算設定・課金の画面が出たら止めてユーザーに確認する | 無料掲載の運用。意図しない課金を避けるため |
| 2 | **投稿するのはこの1件だけ**。他の求人を新規作成しない | 同一勤務地で複数出すと重複判定で表示順が落ちる |
| 3 | **既存の掲載中求人を編集・停止・削除しない** | ローテーション運用を壊さないため |
| 4 | 職種名に「急募」「★」「高収入」等を足さない。**表の値をそのまま使う** | Indeed の掲載ガイドライン違反になる |
| 5 | 給与を「応相談」に変えない。下限額を必ず入れる | 同上 |
| 6 | ログイン画面が出たら**認証は代行せず**ユーザーに依頼する | 認証情報は扱わない |
| 7 | 本文を要約・短縮しない。ファイルの中身をそのまま貼る | 検査済みの原稿。改変すると重複判定の設計が崩れる |

## 4. 終わったら報告すること

- 掲載できたか（できていれば求人のURL）
- 画面上の最終的な職種名・給与表示（意図とずれていないかの確認用）
- スポンサー設定がオフになっていること
- 途中で出た警告・エラーがあればその内容

## 5. 補足

- この求人の詳細な狙いと運用ルールは `recruitment/indeed/00_運用戦略_数学英語採用.md` にあります
- 本文を直したくなった場合は `{path.name}` を編集し、
  `python3 recruitment/indeed/to_plaintext.py {number}` で貼り付け用テキストを再生成してください
- **今週出すのはこの1本だけです。** 次は約1週間後に別の求人を追加する運用です
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("number", help="求人票の番号（例: 17）")
    ap.add_argument("--out", help="書き出し先。省略時は標準出力")
    args = ap.parse_args()

    path = find_posting(args.number)
    number = args.number.zfill(2)
    body_file = HERE / "plaintext" / (path.stem + ".txt")
    if not body_file.exists():
        raise SystemExit(
            f"貼り付け用テキストがありません。先に実行してください:\n"
            f"  python3 recruitment/indeed/to_plaintext.py {number}"
        )

    body_rel = str(body_file.relative_to(HERE.parent.parent))
    text = build(number, path, body_rel)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"依頼文を書き出しました: {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
