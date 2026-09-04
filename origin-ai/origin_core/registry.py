"""台帳の読み取り。

台帳は **生成物** であり、真実源は各スキルの SKILL.md フロントマター。
書き込みは scripts/build_registry.py だけが行う。手で編集しないこと。
（v0.1 は SKILL.md と台帳の両方に version/budget/gates を書く設計だったが、
必ずずれるので、ずれようのない構造に変えてある。）
"""

from __future__ import annotations

import json
from pathlib import Path

from . import ROOT


class SkillNotFound(KeyError):
    pass


def registry_path() -> Path:
    return ROOT / "registry" / "skills.jsonl"


def load(path: Path | None = None) -> dict[str, dict]:
    p = Path(path) if path else registry_path()
    if not p.exists():
        return {}
    entries: dict[str, dict] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        entries[entry["id"]] = entry
    return entries


def get(skill_id: str, path: Path | None = None) -> dict:
    entries = load(path)
    if skill_id not in entries:
        raise SkillNotFound(skill_id)
    return entries[skill_id]
