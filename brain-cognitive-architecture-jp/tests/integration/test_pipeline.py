# -*- coding: utf-8 -*-
"""統合: 実行ループ全体・昇格フロー・オフライン統合は候補のみ・読取専用の無副作用。"""

import hashlib
import json
import os

import pytest

from brain_architecture import cli


def run(base, *argv):
    """CLI を JSON モードで実行し、stdout の JSON を返す。"""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(["--dir", base, "--json", *argv])
    out = buf.getvalue().strip()
    return code, (json.loads(out) if out else None)


def _tree_digest(base):
    h = hashlib.sha256()
    for root, _dirs, files in os.walk(base):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            h.update(p.encode())
            h.update(open(p, "rb").read())
    return h.hexdigest()


@pytest.fixture()
def initialized(tmp_path):
    base = str(tmp_path / "mem")
    run(base, "init")
    return base


def test_full_cognitive_loop(initialized):
    base = initialized
    # sense → store（複数観測で同一エピソードを裏付け）
    for day in ("2026-07-01", "2026-07-02", "2026-07-03"):
        code, r = run(base, "--scope", "project", "observe",
                      "--goal", "deploy app", "--situation", "macos sed differs",
                      "--action", "use gsed", "--outcome", "verified_success",
                      "--source-trust", "verified_local",
                      "--occurred-at", "%sT10:00:00" % day)
        assert code == 0 and r["ok"]
    # retrieve → メタ認知
    code, r = run(base, "--scope", "project", "retrieve", "--cue",
                  '{"keywords":["sed","macos","gsed"]}')
    assert r["results"] and r["metacognition"] in ("known_verified", "known_unverified")
    # report
    code, rep = run(base, "--scope", "project", "report")
    assert rep["event_count"] == 3
    # verify OK
    code, v = run(base, "--scope", "project", "verify")
    assert code == 0 and v["ok"] and v["deterministic"]


def test_promotion_flow_requires_evidence_and_approval(initialized):
    base = initialized
    for day in ("2026-07-01", "2026-07-02"):
        run(base, "observe", "--goal", "g", "--situation", "s", "--action", "a",
            "--outcome", "verified_success", "--source-trust", "verified_local",
            "--occurred-at", "%sT10:00:00" % day)
    _, r = run(base, "retrieve", "--cue", '{"keywords":["g","s","a"]}')
    mid = r["results"][0]["memory_id"]
    # 証拠なし → 拒否
    _, d0 = run(base, "promote", "--memory", mid, "--level", "L1")
    assert d0["authorized"] is False
    # L1 証拠あり → 承認
    _, d1 = run(base, "promote", "--memory", mid, "--level", "L1", "--evidence",
                '{"event_valid":true,"source_recorded":true,"sensitive_removed":true}',
                "--approver", "user:test")
    assert d1["ok"] and d1["authorized"]
    # L5（憲法）は人間承認なしでは不可
    _, d5 = run(base, "promote", "--memory", mid, "--level", "L5", "--evidence",
                '{"human_approval":false}')
    assert d5["authorized"] is False


def test_consolidation_is_candidate_only(initialized):
    base = initialized
    for day in ("2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"):
        run(base, "observe", "--goal", "recurring task", "--situation", "ctx",
            "--action", "step-%s" % day[-2:], "--outcome", "verified_success",
            "--source-trust", "verified_local", "--occurred-at", "%sT10:00:00" % day)
    _, dry = run(base, "consolidate")
    assert dry["dry_run"] is True and dry["written_proposals"] == []
    # 昇格イベントは作られていない（候補のみ）。
    _, rep = run(base, "report")
    assert rep["stats"]["by_level"].get("L5", 0) == 0


def test_readonly_commands_have_no_side_effects(initialized):
    base = initialized
    run(base, "observe", "--goal", "g", "--situation", "s", "--action", "a",
        "--occurred-at", "2026-07-01T10:00:00")
    before = _tree_digest(base)
    run(base, "verify")
    run(base, "replay", "--dry-run")
    run(base, "consolidate")
    run(base, "decay")
    run(base, "attention", "--stimulus", '{"content":"x"}', "--goal", '{"keywords":["g"]}')
    run(base, "retrieve", "--cue", '{"keywords":["g"]}')
    run(base, "predict", "--expected", "0.5", "--outcome", "verified_success")
    run(base, "report")
    after = _tree_digest(base)
    assert before == after, "読取/ dry-run コマンドが副作用を持つべきでない"


def test_replay_persists_only_without_dry_run(initialized):
    base = initialized
    run(base, "observe", "--goal", "g", "--situation", "s", "--action", "a",
        "--occurred-at", "2026-07-01T10:00:00")
    _, r = run(base, "--scope", "project", "replay")
    assert "written" in r and os.path.exists(r["written"])
