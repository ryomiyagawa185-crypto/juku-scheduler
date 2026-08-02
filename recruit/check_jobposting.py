#!/usr/bin/env python3
"""採用ページの JobPosting 構造化データを検査する。

Google しごと検索（Google for Jobs）は、ページ内の JSON-LD を読んで求人を掲載する。
必須項目が欠けていると掲載されず、validThrough を過ぎた求人は掲載が止まる。
公開前とその後の定期確認のために、このスクリプトで機械的に検査する。

検査するもの:
  1. JSON-LD が JSON として妥当か
  2. JobPosting の必須項目（title / description / datePosted /
     hiringOrganization / jobLocation）が揃っているか
  3. jobLocation の住所が4項目（streetAddress / addressLocality /
     addressRegion / addressCountry）揃っているか
  4. validThrough が過去日になっていないか（掲載が止まる）
  5. identifier の value がページ間で重複していないか
  6. canonical リンクがあるか
  7. 【要確認】が本文に残っていないか（プレースホルダの公開事故を防ぐ）

使い方:
    python3 recruit/check_jobposting.py
    python3 recruit/check_jobposting.py --date 2026-12-01   # 指定日で期限を判定
"""

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
CANONICAL_RE = re.compile(r'<link[^>]+rel=["\']canonical["\']', re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"【要確認】")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

REQUIRED = ["title", "description", "datePosted", "hiringOrganization", "jobLocation"]
ADDRESS_FIELDS = [
    "streetAddress",
    "addressLocality",
    "addressRegion",
    "addressCountry",
]


def parse_day(value: str) -> date | None:
    """ISO 8601 の日付／日時文字列から日付部分を取り出す。"""
    head = value.strip()[:10]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date()
    except ValueError:
        return None


def check_page(path: Path, today: date, seen_ids: dict[str, Path]) -> list[str]:
    errors: list[str] = []
    html = path.read_text(encoding="utf-8")
    name = path.name

    if not CANONICAL_RE.search(html):
        errors.append(f"{name}: canonical リンクがありません")

    # HTMLコメント内の【要確認】は運用メモなので除外し、本文に出るものだけ検出する
    visible = HTML_COMMENT_RE.sub("", html)
    if PLACEHOLDER_RE.search(visible):
        errors.append(f"{name}: 本文に【要確認】が残っています（公開前に置き換えること）")

    blocks = LD_RE.findall(html)
    if not blocks:
        errors.append(f"{name}: JSON-LD がありません")
        return errors

    for i, raw in enumerate(blocks, 1):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            errors.append(f"{name}: JSON-LD #{i} が不正です（{e}）")
            continue

        if data.get("@type") != "JobPosting":
            continue  # Organization などは対象外

        for field in REQUIRED:
            if not data.get(field):
                errors.append(f"{name}: 必須項目 {field} がありません")

        addr = (data.get("jobLocation") or {}).get("address") or {}
        for field in ADDRESS_FIELDS:
            if not addr.get(field):
                errors.append(f"{name}: jobLocation.address.{field} がありません")

        posted = data.get("datePosted")
        if posted and parse_day(posted) is None:
            errors.append(f"{name}: datePosted の日付形式が不正です（{posted}）")

        through = data.get("validThrough")
        if through:
            day = parse_day(through)
            if day is None:
                errors.append(f"{name}: validThrough の日付形式が不正です（{through}）")
            elif day < today:
                errors.append(
                    f"{name}: validThrough が過去日です（{day}）。掲載が止まります"
                )
            elif (day - today).days <= 14:
                errors.append(
                    f"{name}: validThrough まで残り{(day - today).days}日です。更新してください"
                )
        else:
            errors.append(f"{name}: validThrough がありません（掲載が無期限になります）")

        ident = data.get("identifier") or {}
        value = ident.get("value") if isinstance(ident, dict) else None
        if not value:
            errors.append(f"{name}: identifier.value がありません")
        elif value in seen_ids:
            errors.append(f"{name}: identifier.value '{value}' が {seen_ids[value].name} と重複しています")
        else:
            seen_ids[value] = path

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="検査する HTML ファイル（省略時は recruit/*.html）")
    parser.add_argument("--date", help="期限判定の基準日（YYYY-MM-DD／省略時は本日）")
    args = parser.parse_args()

    today = date.today()
    if args.date:
        parsed = parse_day(args.date)
        if parsed is None:
            print(f"--date の形式が不正です: {args.date}", file=sys.stderr)
            return 2
        today = parsed

    targets = (
        [Path(p) for p in args.paths]
        if args.paths
        else sorted(Path(__file__).parent.glob("*.html"))
    )

    seen_ids: dict[str, Path] = {}
    all_errors: list[str] = []
    for path in targets:
        if not path.exists():
            print(f"見つかりません: {path}", file=sys.stderr)
            return 2
        all_errors.extend(check_page(path, today, seen_ids))

    if all_errors:
        for e in all_errors:
            print(e)
        print(f"\n{len(all_errors)}件の指摘があります。（基準日: {today}）")
        return 1

    print(f"{len(targets)}ページを検査。求人{len(seen_ids)}件、指摘なし。（基準日: {today}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
