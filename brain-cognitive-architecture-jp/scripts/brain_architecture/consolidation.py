# -*- coding: utf-8 -*-
"""consolidation — 睡眠・オフライン統合に着想を得た固定化層（仕様 §M）。

【生物学的知見】睡眠中に海馬のエピソードが再生され、新皮質へ転送・統合されて
スキーマ化されるとする説がある（単なる定期バッチではない）。
【計算論的抽象化】重複整理・クラスタリング・仮説的意味記憶の生成・矛盾検出・
信頼度再計算・古記憶の減衰・固定化候補生成・過学習検出・回帰確認を行う。
【実装上の近似】本層は本番知識を自動変更しない。原則「候補（proposal）生成」まで。
dry-run では一切ファイルを書かない。SessionEnd 等の短い終了処理では実行しない。
"""

from . import snapshot as snap_mod
from . import semantic_memory
from . import inhibition
from . import learning
from . import proposals as prop_mod
from . import episodic_memory


CORROBORATION_MIN = 2   # 仮説的意味記憶の生成に必要な独立エピソード数


def _episode_clusters(memories):
    """エピソードを正規化 goal でクラスタリングする（related episodes の束ね）。"""
    clusters = {}
    for m in memories:
        if m.get("type") != "episodic":
            continue
        goal = episodic_memory._norm((m.get("content") or {}).get("goal"))
        key = (m.get("scope"), m.get("partition"), goal)
        clusters.setdefault(key, []).append(m)
    return clusters


def _hypothesize_semantics(clusters, as_of):
    """十分に裏付けられたクラスタから仮説的意味記憶の候補を作る（自動昇格しない）。"""
    candidates = []
    for (scope, partition, goal), eps in sorted(clusters.items(),
                                                key=lambda kv: str(kv[0])):
        if not goal or len(eps) < CORROBORATION_MIN:
            continue
        succ = sum(e.get("success_count", 0) for e in eps)
        fail = sum(e.get("failure_count", 0) for e in eps)
        if succ < CORROBORATION_MIN or fail > succ:
            continue
        actions = sorted({(e.get("content") or {}).get("action") for e in eps
                          if (e.get("content") or {}).get("action")})
        claim = "目標『%s』では %s が成功しやすい（%d 成功/%d 失敗・%d エピソード）" % (
            goal[:40], "／".join(a[:30] for a in actions[:3]) or "当該手順",
            succ, fail, len(eps))
        candidates.append(prop_mod.make_proposal(
            "semantic", rationale=claim, scope=scope, target_level="L1",
            evidence_ids=sorted(eid for e in eps for eid in e.get("evidence_ids", [])),
            expected_effect="将来の類似目標での方策選択を助ける（候補）",
            side_effects="過度な一般化のリスク。適用範囲=%s に限定。" % scope,
            counterexamples="失敗 %d 件。反例条件は個別エピソード参照。" % fail,
            memory={"memory_id": "mem_sem_" + eps[0]["memory_id"][7:],
                    "type": "semantic", "scope": scope, "partition": partition,
                    "claim": claim, "level": "L1", "status": "candidate",
                    "confidence": 0.0, "provenance": eps[0].get("provenance"),
                    "created_at": as_of},
            occurred_at=as_of))
    return candidates


def _decay_candidates(memories, as_of):
    """古く・低想起・非保護の記憶に archive 候補を出す（自動削除しない・§7）。"""
    out = []
    for m in sorted(memories, key=lambda x: x.get("memory_id", "")):
        if m.get("status") not in ("candidate", "observed"):
            continue
        if learning.is_protected(m):
            continue
        if (m.get("derived") or {}).get("forgetting") == "exclude_from_search":
            out.append(prop_mod.make_proposal(
                "deprecation", rationale="低想起(retrievability<閾値)の非保護記憶を archive",
                scope=m.get("scope", "project"),
                evidence_ids=m.get("evidence_ids"),
                diff={"memory_id": m["memory_id"], "to_status": "archived"},
                expected_effect="検索ノイズ低減", occurred_at=as_of))
    return out


def _overfitting_anomalies(snapshot):
    """過学習・過強ハブの検出（自動改変せず報告のみ・§M/§7）。"""
    anomalies = []
    for m in snapshot.get("memories", []):
        n = m.get("success_count", 0) + m.get("failure_count", 0)
        if m.get("level") in ("L3", "L4", "L5") and n < 2:
            anomalies.append({"memory_id": m["memory_id"],
                              "issue": "高段階だが証拠サンプルが乏しい（過学習疑い）"})
    # ハブ: 入射 derived.strength 和が大きいノード。
    incoming = {}
    for e in snapshot.get("edges", []):
        incoming.setdefault(e.get("target"), 0.0)
        incoming[e["target"]] += (e.get("derived") or {}).get("strength", 0.0)
    for node, tot in sorted(incoming.items()):
        if tot > 3.0:
            anomalies.append({"node": node,
                              "issue": "過強ハブ（入射強度和=%.2f）。恒常性で派生縮小済み。" % tot})
    return anomalies


def consolidate(paths, scope=None, as_of=None, dry_run=True):
    """オフライン統合を実行して報告を返す。dry_run=True なら一切書き込まない。

    生成物は「候補（proposal）」まで。promotion（承認済み変更）は作らない。
    """
    snapshot = snap_mod.rebuild(paths, scope=scope, as_of=as_of)
    as_of = snapshot["as_of"]
    memories = snapshot["memories"]

    clusters = _episode_clusters(memories)
    semantic_cands = _hypothesize_semantics(clusters, as_of)
    decay_cands = _decay_candidates(memories, as_of)
    dedups = inhibition.dedup_memories(memories)
    conflicts = semantic_memory.detect_conflicts(
        {m["memory_id"]: m for m in memories})
    anomalies = _overfitting_anomalies(snapshot)

    candidates = semantic_cands + decay_cands
    written = []
    if not dry_run:
        for c in candidates:
            prop_mod.write_proposal(paths, c)
            written.append(c["proposal_id"])

    return {
        "dry_run": dry_run,
        "as_of": as_of,
        "scope": scope or "all",
        "n_memories": len(memories),
        "n_semantic_candidates": len(semantic_cands),
        "n_decay_candidates": len(decay_cands),
        "n_duplicate_pairs": len(dedups),
        "n_conflicts": len(conflicts),
        "conflicts": conflicts,
        "anomalies": anomalies,
        "candidates": [c["proposal_id"] for c in candidates],
        "written_proposals": written,
        "note": "候補のみ生成。本番昇格は executive の認可＋人間承認が必要（§8/§9）。",
    }
