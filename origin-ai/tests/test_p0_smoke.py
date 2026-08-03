"""P0 の完了基準：手書きの plan で echo スキルが動く。

台帳が生成物であること（S1）と、その一周が通ることをここで固定する。
"""

from __future__ import annotations

import json

from adapters.legacy_skill import adapt, missing_fields
from origin_core import ROOT, schema, tracing
from orchestrator.runner import run_plan
from policy.decide import ALLOW_PLACEHOLDER_ENV
from scripts.build_registry import collect, render


def test_registry_is_generated_from_skill_md():
    entries = collect()
    ids = {e["id"] for e in entries}
    assert "meta.echo" in ids
    for e in entries:
        schema.validate({k: v for k, v in e.items() if k != "path"}, "skill.frontmatter")


def test_registry_file_matches_generation():
    """手で編集された台帳はここで落ちる（--check と同じ検査）。"""
    current = (ROOT / "registry" / "skills.jsonl").read_text(encoding="utf-8")
    assert current == render(collect()), (
        "registry/skills.jsonl が SKILL.md と一致しません。"
        "python scripts/build_registry.py で生成し直してください"
    )


def test_legacy_shim_fills_conservative_defaults():
    adapted = adapt({"id": "legacy.sample", "version": "1.0.0"})
    assert adapted["risk"] == "high"
    assert adapted["data_class"] == "pii"
    assert adapted["stage"] == "experimental"
    assert "external-send" in adapted["gates"]
    assert adapted["legacy_shim"] is True
    assert "risk" in missing_fields({"id": "legacy.sample", "version": "1.0.0"})


def test_plan_runs_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv(ALLOW_PLACEHOLDER_ENV, "1")  # 単価未記入でのデモは明示的オプトイン
    tracer = tracing.Tracer(root=tmp_path / "traces")

    results = run_plan(
        ROOT / "plans" / "echo.plan.json",
        tracer=tracer,
        state_path=tmp_path / "origin.db",
    )

    assert len(results) == 1
    assert results[0]["status"] == "ok", results[0].get("block_reason")
    assert results[0]["cost_usd"] == 0.001

    written = ROOT / "artifacts" / "open" / "echo" / "echo.txt"
    assert written.exists()

    traces = list((tmp_path / "traces").rglob("*.jsonl"))
    assert traces, "トレースが書かれていない"
    record = json.loads(traces[0].read_text(encoding="utf-8").splitlines()[0])
    assert record["skill_id"] == "meta.echo"
    assert "message" not in json.dumps(record), "トレースに本文が漏れている"


def test_second_run_is_skipped_by_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv(ALLOW_PLACEHOLDER_ENV, "1")
    state = tmp_path / "origin.db"
    tracer = tracing.Tracer(root=tmp_path / "traces")

    first = run_plan(ROOT / "plans" / "echo.plan.json", tracer=tracer, state_path=state)
    second = run_plan(ROOT / "plans" / "echo.plan.json", tracer=tracer, state_path=state)

    assert first[0]["status"] == "ok"
    assert second[0]["status"] == "skipped_idempotent"
