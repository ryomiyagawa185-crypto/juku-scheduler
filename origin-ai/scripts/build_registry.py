#!/usr/bin/env python3
"""SKILL.md フロントマター → registry/skills.jsonl を生成する。

台帳は生成物であって真実源ではない。手で編集された台帳は
--check で落ちる。これで「SKILL.md を直したのに台帳を忘れた」
というドリフトが構造的に起きなくなる。

    python scripts/build_registry.py           # 生成
    python scripts/build_registry.py --check   # 差分があれば exit 1（CI）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.legacy_skill import adapt  # noqa: E402
from origin_core import ROOT, schema  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DERIVED_KEYS = ("path",)


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        raise ValueError("フロントマター（---）で始まっていません")
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError("フロントマターが閉じていません")
    block = text[3:end].strip("\n")
    if yaml is None:  # pragma: no cover
        raise RuntimeError("PyYAML が必要です: pip install pyyaml")
    data = yaml.safe_load(block)
    if not isinstance(data, dict):
        raise ValueError("フロントマターが辞書ではありません")
    return data


def collect(root: Path | None = None) -> list[dict]:
    root = root or ROOT
    entries: list[dict] = []
    for skill_md in sorted((root / "skills").rglob("SKILL.md")):
        raw = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        entry = adapt(raw)
        schema.validate(entry, "skill.frontmatter")
        if entry.get("legacy_shim") and entry.get("stage") != "experimental":
            raise ValueError(
                f"{skill_md}: legacy_shim のスキルは stage を昇格できません "
                "（欠損フィールドを埋めてから昇格してください）"
            )
        entry["path"] = str(skill_md.parent.relative_to(root)).replace("\\", "/")
        entries.append(entry)
    entries.sort(key=lambda e: e["id"])
    return entries


def render(entries: list[dict]) -> str:
    return "".join(
        json.dumps(e, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for e in entries
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="生成し直して差分があれば失敗する")
    args = parser.parse_args()

    out_path = ROOT / "registry" / "skills.jsonl"
    rendered = render(collect())

    if args.check:
        current = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        if current != rendered:
            print(
                "registry/skills.jsonl が SKILL.md と一致しません。\n"
                "  python scripts/build_registry.py を実行して生成し直してください。\n"
                "  （台帳は生成物です。手で編集しないでください）",
                file=sys.stderr,
            )
            return 1
        print(f"registry: OK（{len(rendered.splitlines())} スキル）")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"registry: {len(rendered.splitlines())} スキルを書き出しました → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
