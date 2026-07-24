# -*- coding: utf-8 -*-
"""schemas/*.json が schemas.py と同期していること・軽量バリデータの健全性。"""

import json
import os

from brain_architecture import schemas, validation

_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "schemas")


def _load(name):
    with open(os.path.join(_SCHEMA_DIR, "%s.schema.json" % name),
              encoding="utf-8") as f:
        return json.load(f)


def test_schema_files_sync_with_python():
    for name, py in schemas.SCHEMAS_BY_NAME.items():
        if name == "snapshot":
            continue
        doc = _load(name)
        for key in ("type", "required", "properties"):
            if key in py:
                assert doc.get(key) == py[key], "%s.%s が不同期" % (name, key)


def test_validator_type_and_enum():
    assert validation.validate_schema(5, {"type": "integer"}) == []
    assert validation.validate_schema(True, {"type": "integer"})  # bool != integer
    assert validation.validate_schema("x", {"enum": ["a", "b"]})
    assert validation.validate_schema("a", {"enum": ["a", "b"]}) == []


def test_relation_types_have_inhibitory_flag():
    for r, meta in schemas.RELATION_TYPES.items():
        assert "inhibitory" in meta and "direction" in meta
    assert "inhibits" in schemas.INHIBITORY_RELATIONS
    assert "must_not_promote" in schemas.INHIBITORY_RELATIONS


def test_level_status_mapping_complete():
    for lv in schemas.LEVELS:
        assert lv in schemas.LEVEL_TO_STATUS


def test_all_scopes_have_breadth():
    for s in schemas.SCOPES:
        assert s in schemas.SCOPE_BREADTH
