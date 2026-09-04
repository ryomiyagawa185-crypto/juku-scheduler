# -*- coding: utf-8 -*-
"""プライバシー: 秘密の非保存（redact）・機密フラグ・要約とhash・保持期限。"""

import json

from brain_architecture import event_store
from tests.conftest import NOW

SECRETS = [
    "AKIAIOSFODNN7EXAMPLE",
    "sk-ant-abcdefghijklmnopqrstuvwxyz012345",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "-----BEGIN RSA PRIVATE KEY-----",
    "password: hunter2super",
    "user@example.com",
    "4111 1111 1111 1111",
]


def test_all_secret_categories_detected():
    for s in SECRETS:
        assert event_store.scan_sensitive(s), "未検出: %s" % s


def test_redaction_removes_original(paths):
    for i, s in enumerate(SECRETS):
        ev, _ = event_store.append_event(
            paths, "observation", "project", {"text": "context " + s},
            occurred_at="2026-07-%02dT10:00:00" % (i + 1), now=NOW)
        assert ev["contains_sensitive_data"] is True
    dump = json.dumps(event_store.all_events(paths), ensure_ascii=False)
    for s in SECRETS:
        assert s not in dump, "原文が残っている: %s" % s
    assert "REDACTED" in dump


def test_content_hash_present_for_dedup(paths):
    ev, _ = event_store.append_event(paths, "observation", "project", {"a": 1},
                                     occurred_at="2026-07-01T10:00:00", now=NOW)
    assert ev["content_hash"].startswith("sha256:")


def test_retention_field_preserved(paths):
    ev, _ = event_store.append_event(
        paths, "observation", "project",
        {"goal": "g", "situation": "s", "action": "a",
         "retention_until": "2026-12-31"},
        occurred_at="2026-07-01T10:00:00", now=NOW)
    assert ev["payload"]["retention_until"] == "2026-12-31"


def test_session_token_hashed_not_stored(paths):
    ev, _ = event_store.append_event(paths, "observation", "project", {"a": 1},
                                     occurred_at="2026-07-01T10:00:00",
                                     session="raw-session-token-123", now=NOW)
    assert ev["session_id_hash"].startswith("sha256:")
    assert "raw-session-token-123" not in json.dumps(ev)
