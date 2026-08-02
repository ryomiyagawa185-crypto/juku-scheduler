#!/usr/bin/env python3
"""recruit/*.html から、WordPress 固定ページ貼り付け用のHTMLを生成する。

WordPress のメディアライブラリは .html / .css / .zip を受け付けないため、
ファイルを置く方式が使えない環境がある。そこで各ページを

  - CSSを .mk-recruit 配下にスコープして inline 化（テーマのCSSと干渉させない）
  - サイト共通のヘッダ・フッタを除去（テーマ側が出すため）
  - ページ内リンクを WordPress の URL 構造（/recruit/koushi/ 形式）へ書き換え
  - canonical を除去（SEOプラグインが自動出力するため二重定義を避ける）
  - JSON-LD はそのまま同梱

という「カスタムHTMLブロックに貼れば完成する1枚」に変換する。

使い方:
    python3 recruit/build_wordpress.py
    → recruit-wordpress/ に生成される
"""

import re
import sys
from pathlib import Path

SRC = Path(__file__).parent
OUT = SRC.parent / "recruit-wordpress"

# ファイル名 → WordPress の固定ページURL
SLUGS = {
    "index.html": "/recruit/",
    "koushi.html": "/recruit/koushi/",
    "koushi-chuju.html": "/recruit/koushi-chuju/",
    "koushi-kokosei.html": "/recruit/koushi-kokosei/",
    "jimu.html": "/recruit/jimu/",
}

WRAPPER = "mk-recruit"

MAIN_RE = re.compile(r"<main class=\"wrap\">(.*?)</main>", re.DOTALL)
LD_RE = re.compile(
    r'<script type="application/ld\+json">.*?</script>', re.DOTALL
)
H1_OPEN_RE = re.compile(r"<h1>")
H1_CLOSE_RE = re.compile(r"</h1>")


def parse_rules(css: str) -> list[tuple[str, str]]:
    """CSSを (セレクタ, 宣言ブロック) の並びに分解する。

    @media のような入れ子ブロックも、対応する閉じ括弧まで正しく1件として拾う。
    """
    rules: list[tuple[str, str]] = []
    i, n = 0, len(css)
    while i < n:
        open_at = css.find("{", i)
        if open_at == -1:
            break
        prelude = css[i:open_at].strip()
        depth, k = 1, open_at + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        rules.append((prelude, css[open_at + 1 : k - 1]))
        i = k
    return rules


def scope_selector(selectors: str) -> str:
    """セレクタを .mk-recruit 配下へ書き換える。落とす場合は空文字を返す。"""
    scoped: list[str] = []
    for sel in selectors.split(","):
        sel = sel.strip()
        if not sel:
            continue
        if sel in (":root", "body"):
            # テーマ側の CSS 変数（--bg など）を汚さないよう、変数も内側に閉じ込める
            scoped.append(f".{WRAPPER}")
        elif sel == "html":
            continue  # html への指定はテーマ側に任せる
        elif sel == "*":
            scoped.append(f".{WRAPPER} *")
        else:
            scoped.append(f".{WRAPPER} {sel}")
    return ", ".join(scoped)


def scope_css(css: str) -> str:
    """style.css の全セレクタを .mk-recruit 配下に閉じ込める。"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)

    blocks: list[str] = []
    for prelude, body in parse_rules(css):
        if prelude.startswith("@"):
            inner = [
                f"  {scope_selector(p)} {{{b.strip()}}}"
                for p, b in parse_rules(body)
                if scope_selector(p)
            ]
            if inner:
                blocks.append(prelude + " {\n" + "\n".join(inner) + "\n}")
        else:
            sel = scope_selector(prelude)
            if sel:
                blocks.append(f"{sel} {{{body.strip()}}}")
    return "\n".join(blocks)


def rewrite_links(html: str) -> str:
    """相対リンクを WordPress の固定ページURLへ書き換える。"""
    for filename, url in SLUGS.items():
        html = html.replace(f'href="./{filename}"', f'href="{url}"')
    html = html.replace('href="./"', 'href="/recruit/"')
    return html


def build(path: Path, css: str) -> str:
    html = path.read_text(encoding="utf-8")

    main = MAIN_RE.search(html)
    if not main:
        raise SystemExit(f"{path.name}: <main class=\"wrap\"> が見つかりません")
    content = main.group(1).strip()

    # テーマが固定ページタイトルを h1 で出すため、本文側は h2 へ降格する
    content = H1_OPEN_RE.sub('<h2 class="hero-title">', content)
    content = H1_CLOSE_RE.sub("</h2>", content)

    content = rewrite_links(content)

    ld_blocks = LD_RE.findall(html)

    parts = [
        "<!-- 武蔵野個別指導塾 採用ページ｜WordPress 固定ページ貼り付け用 -->",
        "<!-- カスタムHTMLブロックに、このファイルの中身を全部貼り付けてください -->",
        "<style>",
        scope_css(css),
        "</style>",
        f'<div class="{WRAPPER} wrap">',
        content,
        "</div>",
        *ld_blocks,
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    css = (SRC / "style.css").read_text(encoding="utf-8")
    OUT.mkdir(exist_ok=True)

    made = []
    for filename in SLUGS:
        src = SRC / filename
        if not src.exists():
            print(f"見つかりません: {src}", file=sys.stderr)
            return 2
        dest = OUT / filename
        dest.write_text(build(src, css), encoding="utf-8")
        made.append(dest)

    for p in made:
        print(f"生成: {p.relative_to(SRC.parent)}  ({p.stat().st_size:,} バイト)")
    print(f"\n{len(made)}ファイルを生成しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
