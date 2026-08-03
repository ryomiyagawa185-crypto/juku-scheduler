"""トレースの形。

守る不変条件は「本文を書かない」と「シークレットをマスクする」。
additionalProperties: false が本文混入の防波堤になっているので、
その防波堤が実際に効くことをテストで固定しておく。
"""

from __future__ import annotations

import json

import pytest

from origin_core import schema, tracing


def _record(**overrides) -> dict:
    now = tracing.now_iso()
    base = {
        "trace_id": tracing.new_trace_id(),
        "plan_id": "plan-1",
        "plan_revision": 1,
        "step_id": "s1",
        "skill_id": "legal.sample",
        "skill_version": "1.0.0",
        "model_id": None,
        "prompt_hash": None,
        "pricing_version": "TEST",
        "input_tokens": 1200,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 900,
        "output_tokens": 800,
        "cost_usd": 0.024,
        "latency_ms": 1234,
        "started_at": now,
        "ended_at": now,
        "status": "ok",
        "block_reason": None,
        "gates_triggered": [],
        "approval_ref": None,
        "data_class": "privileged",
        "inputs_hash": "sha256:abc",
        "outputs_hash": "sha256:def",
        "artifact_refs": ["artifacts/privileged/case/answer.md"],
        "retry_count": 0,
        "error_class": None,
    }
    base.update(overrides)
    return base


def test_valid_record_is_written(tmp_path):
    tracer = tracing.Tracer(root=tmp_path)
    path = tracer.write(_record())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["skill_id"] == "legal.sample"


def test_body_in_a_trace_is_rejected(tmp_path):
    """本文を書こうとしたら、書かれる前に落ちること。"""
    if not schema.strict_available():
        pytest.skip("jsonschema が無い環境では additionalProperties を検査できない")
    tracer = tracing.Tracer(root=tmp_path)
    with pytest.raises(schema.ValidationError):
        tracer.write(_record(answer_text="被告は原告に対し金100万円を支払え"))
    assert not list(tmp_path.rglob("*.jsonl")), "違反レコードでファイルが作られている"


def test_missing_cache_fields_are_rejected(tmp_path):
    """キャッシュ階層を落とした古い形のレコードを通さない。"""
    record = _record()
    del record["cache_read_input_tokens"]
    tracer = tracing.Tracer(root=tmp_path)
    with pytest.raises(schema.ValidationError):
        tracer.write(record)


def test_secrets_are_masked(tmp_path, monkeypatch):
    monkeypatch.setenv("LINE_TOKEN", "super-secret-token-value")
    tracer = tracing.Tracer(root=tmp_path, secret_names=["LINE_TOKEN"])
    path = tracer.write(_record(block_reason="failed with super-secret-token-value"))
    text = path.read_text(encoding="utf-8")
    assert "super-secret-token-value" not in text
    assert tracing.MASK in text


def test_exception_text_goes_through_the_same_masker(monkeypatch):
    """実際の漏洩は inputs 経由より例外メッセージ経由で起きる。"""
    monkeypatch.setenv("LINE_TOKEN", "super-secret-token-value")
    masked = tracing.mask_exception(
        RuntimeError("POST failed: token=super-secret-token-value"), ["LINE_TOKEN"]
    )
    assert "super-secret-token-value" not in masked
    assert masked.startswith("RuntimeError:")
