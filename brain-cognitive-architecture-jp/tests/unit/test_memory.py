# -*- coding: utf-8 -*-
"""記憶: パターン分離・部分手掛かり検索・誤補完抑制・スコープ漏洩・減衰・安全記憶保持。"""

from brain_architecture import snapshot as snap_mod, retrieval, learning


def _snap(paths, **kw):
    return snap_mod.rebuild(paths, scope="project", **kw)


def test_pattern_separation_similar_but_distinct(observe, paths):
    observe(goal="deploy", situation="macos", action="use gsed")
    observe(goal="deploy", situation="linux", action="use sed")  # 状況が違う=別物
    snap = _snap(paths)
    episodics = [m for m in snap["memories"] if m["type"] == "episodic"]
    assert len(episodics) == 2  # 似ているが混同しない


def test_same_context_aggregates(observe, paths):
    observe(goal="deploy", situation="macos", action="gsed", outcome="verified_success")
    observe(goal="deploy", situation="macos", action="gsed", outcome="verified_success")
    snap = _snap(paths)
    ep = [m for m in snap["memories"] if m["type"] == "episodic"]
    assert len(ep) == 1
    assert ep[0]["success_count"] == 2


def test_partial_cue_retrieval(observe, paths):
    observe(goal="configure nginx reverse proxy", situation="prod",
            action="edit nginx.conf")
    snap = _snap(paths)
    res = retrieval.retrieve(snap, {"keywords": ["nginx", "proxy"]},
                             query_scope="project")
    assert res["results"], "部分手掛かりで想起できるべき"
    assert res["knowledge_state"] in ("known_verified", "known_unverified")


def test_false_completion_suppressed(observe, paths):
    observe(goal="configure nginx", situation="prod", action="edit conf")
    snap = _snap(paths)
    res = retrieval.retrieve(snap, {"keywords": ["quantum", "banana", "helicopter"]},
                             query_scope="project", include_suppressed=True)
    assert res["results"] == []                 # でっち上げない
    assert res["knowledge_state"] == "not_retrieved"   # 存在しない(unknown)ではない


def test_scope_leakage_prevented(observe, paths):
    observe(goal="secret plan", situation="acme case", action="do x",
            scope="client", partition="acme")
    snap = snap_mod.rebuild(paths, scope="client")
    # 別顧客(globex)の文脈では acme の記憶を想起しない。
    res = retrieval.retrieve(snap, {"keywords": ["secret", "plan", "acme"]},
                             query_scope="client", query_partition="globex")
    assert res["results"] == []
    # 同一顧客(acme)なら想起できる。
    res2 = retrieval.retrieve(snap, {"keywords": ["secret", "plan", "acme"]},
                              query_scope="client", query_partition="acme")
    assert res2["results"]


def test_narrow_scope_not_overgeneralized(observe, paths):
    # session スコープの一回限りは project クエリへ勝手に適用しない（§5）。
    observe(goal="one off tweak", situation="temp", action="hack", scope="session")
    snap = snap_mod.rebuild(paths, scope="session")
    res = retrieval.retrieve(snap, {"keywords": ["one", "off", "tweak"]},
                             query_scope="project")
    assert res["results"] == []  # session(狭) は project(広) へ generalize しない


def test_old_memory_decays(observe, paths):
    observe(goal="old thing", situation="s", action="a", outcome="unverified",
            source_trust="untrusted_external", occurred_at="2026-01-01T00:00:00")
    snap = snap_mod.rebuild(paths, scope="project", as_of="2026-12-31")
    m = next(m for m in snap["memories"] if m["type"] == "episodic")
    assert m["derived"]["retrievability"] < 0.2  # 大きく減衰


def test_safety_memory_not_decayed(observe, paths):
    # 明示ユーザー方針は時間減衰で消さない（§7）。
    observe(goal="never rm -rf /", situation="policy", action="forbid",
            outcome="verified_success", source_trust="user_explicit",
            occurred_at="2026-01-01T00:00:00")
    snap = snap_mod.rebuild(paths, scope="project", as_of="2030-12-31")
    m = next(m for m in snap["memories"] if m["type"] == "episodic")
    assert m["derived"]["protected"] is True
    assert m["derived"]["retrievability"] >= 0.5
    assert learning.forgetting_action(m, "2030-12-31") == "none"
