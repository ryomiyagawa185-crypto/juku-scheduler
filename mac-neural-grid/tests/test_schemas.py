# -*- coding: utf-8 -*-
"""schemas/*.json が src/mac_neural_grid/schemas.py と同期していること。"""

import json
import os

from mac_neural_grid import schemas

_DIR = os.path.join(os.path.dirname(__file__), "..", "schemas")


def test_schema_files_sync():
    for name, py in schemas.SCHEMAS_BY_NAME.items():
        with open(os.path.join(_DIR, "%s.schema.json" % name), encoding="utf-8") as f:
            doc = json.load(f)
        for key in ("type", "required", "properties"):
            if key in py:
                assert doc.get(key) == py[key], "%s.%s 不同期" % (name, key)


def test_validator_basics():
    assert schemas.validate(5, {"type": "integer"}) == []
    assert schemas.validate(True, {"type": "integer"})   # bool != integer
    assert schemas.validate("z", {"enum": ["a", "b"]})
