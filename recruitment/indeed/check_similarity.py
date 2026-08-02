#!/usr/bin/env python3
"""Indeed 求人票どうしの類似度を測り、同時掲載してはいけない組み合わせを検出する。

Indeed は「同一企業・同一勤務地・似た本文」の求人を重複と判定し、
片方の表示順を落とすか、掲載自体を止める。当塾は勤務地が1つしかないため、
本文の似方だけが分かれ目になる。

このスクリプトは各求人票の「本文コピペ用」部分を取り出し、
文字3-gram の Jaccard 係数で総当たり比較する。閾値を超えた組は
同時掲載を避けるべき組み合わせとして報告する。

判定:
  0.60 以上  危険  同時掲載しない（重複と見なされる可能性が高い）
  0.45 以上  注意  同時掲載するなら、どちらかを書き分ける
  0.45 未満  問題なし

使い方:
    python3 recruitment/indeed/check_similarity.py
    python3 recruitment/indeed/check_similarity.py --live 09 14 17   # 同時掲載する組だけ検査
    python3 recruitment/indeed/check_similarity.py --top 15          # 上位15組を表示
"""

import argparse
import re
import sys
from itertools import combinations
from pathlib import Path

BODY_MARKER = "## 仕事内容（本文コピペ用）"
TITLE_RE = re.compile(r"^\|\s*職種名[^|]*\|\s*(.+?)\s*\|", re.MULTILINE)
NOISE_RE = re.compile(r"[\s　#*|>`\-–—…]+")

DANGER = 0.60
WARN = 0.45
NGRAM = 3


def load_body(path: Path) -> str:
    """求人票から、Indeed に貼る本文だけを取り出して正規化する。"""
    text = path.read_text(encoding="utf-8")
    idx = text.find(BODY_MARKER)
    if idx == -1:
        return ""
    body = text[idx + len(BODY_MARKER) :]
    # 【要確認】などの運用メモは掲載されないので除外する
    body = body.replace("【要確認】", "")
    return NOISE_RE.sub("", body)


def load_title(path: Path) -> str:
    m = TITLE_RE.search(path.read_text(encoding="utf-8"))
    return m.group(1).strip() if m else ""


def shingles(text: str, n: int = NGRAM) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def label(score: float) -> str:
    if score >= DANGER:
        return "危険"
    if score >= WARN:
        return "注意"
    return "問題なし"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        nargs="*",
        help="同時掲載する求人の番号（例: --live 11 17 18）。指定するとその組だけ検査する",
    )
    parser.add_argument("--top", type=int, default=12, help="表示する組数（既定12）")
    args = parser.parse_args()

    here = Path(__file__).parent
    files = sorted(p for p in here.glob("*.md") if re.match(r"^\d{2}_", p.name))

    if args.live:
        wanted = {n.zfill(2) for n in args.live}
        files = [p for p in files if p.name[:2] in wanted]
        missing = wanted - {p.name[:2] for p in files}
        if missing:
            print(f"該当する求人票がありません: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    if len(files) < 2:
        print("比較には2件以上の求人票が必要です。", file=sys.stderr)
        return 2

    bodies = {p: shingles(load_body(p)) for p in files}
    titles = {p: load_title(p) for p in files}

    empty = [p.name for p in files if not bodies[p]]
    if empty:
        print(f"本文が取り出せませんでした: {', '.join(empty)}", file=sys.stderr)
        return 2

    scored = sorted(
        (
            (jaccard(bodies[a], bodies[b]), a, b)
            for a, b in combinations(files, 2)
        ),
        reverse=True,
    )

    danger = [s for s in scored if s[0] >= DANGER]
    warn = [s for s in scored if WARN <= s[0] < DANGER]

    print(f"求人票 {len(files)}件、{len(scored)}組を比較しました。\n")
    print(f"{'類似度':>6}  {'判定':<6} 組み合わせ")
    print("-" * 78)
    for score, a, b in scored[: args.top]:
        print(f"{score:>6.3f}  {label(score):<6} {a.name[:2]} × {b.name[:2]}  "
              f"{a.name[3:-3]} / {b.name[3:-3]}")

    # 職種名の重複も見る（Indeed の重複判定で最も効く要素）
    dup_titles = [
        (a, b) for a, b in combinations(files, 2) if titles[a] and titles[a] == titles[b]
    ]
    if dup_titles:
        print("\n■ 職種名が完全に一致している組（必ず書き分けること）")
        for a, b in dup_titles:
            print(f"  {a.name[:2]} × {b.name[:2]}: 「{titles[a]}」")

    print()
    if danger:
        print(f"■ 危険（同時掲載しない）: {len(danger)}組")
        for score, a, b in danger:
            print(f"  {a.name[:2]} × {b.name[:2]}  類似度 {score:.3f}")
    if warn:
        print(f"■ 注意（同時掲載するなら書き分ける）: {len(warn)}組")
        for score, a, b in warn:
            print(f"  {a.name[:2]} × {b.name[:2]}  類似度 {score:.3f}")
    if not danger and not warn:
        print("同時掲載を避けるべき組み合わせはありません。")

    return 1 if danger else 0


if __name__ == "__main__":
    sys.exit(main())
