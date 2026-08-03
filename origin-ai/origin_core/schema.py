"""JSON Schema 検証。jsonschema が無い環境でも最低限の検査は行う。

フォールバックは required と additionalProperties だけを見る縮小版。
「検証が通った」の意味が環境で変わらないよう、どちらを使ったかを
strict_available() で確認できるようにしてある。CI では必ず
jsonschema がある状態で回すこと（pyproject の dev 依存に入れている）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import ROOT

try:  # pragma: no cover - 環境依存
    import jsonschema

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    jsonschema = None
    _HAS_JSONSCHEMA = False


class ValidationError(Exception):
    pass


def strict_available() -> bool:
    return _HAS_JSONSCHEMA


@lru_cache(maxsize=32)
def load(name: str) -> dict:
    """schemas/ 配下のスキーマを名前で読む（例: "trace"）。"""
    path = ROOT / "schemas" / f"{name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate(instance: Any, schema_name: str) -> None:
    schema = load(schema_name)
    if _HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance, schema)
        except jsonschema.ValidationError as e:  # pragma: no cover - メッセージ整形のみ
            raise ValidationError(f"{schema_name}: {e.message} at {list(e.absolute_path)}") from e
        return
    _validate_minimal(instance, schema, schema_name)


def _validate_minimal(instance: Any, schema: dict, name: str) -> None:
    if schema.get("type") == "object":
        if not isinstance(instance, dict):
            raise ValidationError(f"{name}: object を期待したが {type(instance).__name__}")
        for key in schema.get("required", []):
            if key not in instance:
                raise ValidationError(f"{name}: 必須項目が無い: {key}")
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}))
            extra = set(instance) - allowed
            if extra:
                raise ValidationError(f"{name}: 未知の項目: {sorted(extra)}")


def path_for(name: str) -> Path:
    return ROOT / "schemas" / f"{name}.schema.json"
