# -*- coding: utf-8 -*-
"""inhibition — 抑制系（仕様 §K）。強化だけでなく抑制を必須要素として実装する。

【生物学的知見】皮質・基底核・海馬などで抑制性回路が競合を解消し、誤った連想や
不適切な自動反応を抑えると考えられている。
【計算論的抽象化】無関係情報・誤連想・外部文書内命令・危険自動化・過強ハブ・
一時的成功の過学習・重複記憶・古記憶・競合方策を、それぞれ別の抑制として扱う。
【実装上の近似】抑制性エッジ（inhibits/conflicts_with/contradicts/must_not_promote）
の照合と、決定的なパターン検出。抑制は「拒否」でなく「昇格・自動適用の遮断」。
"""

import re

from . import schemas

# 外部文書内に埋め込まれた「永続ルール化を迫る」命令の検出（prompt injection・§10）。
_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore (all |the )?(previous|prior|above) (instructions|prompt)"),
    re.compile(r"(?i)disregard (the )?(system|previous|safety)"),
    re.compile(r"(?i)from now on[, ].{0,40}(always|never|must)"),
    re.compile(r"(?i)save this (rule|instruction|as a rule|permanently)"),
    re.compile(r"(?i)update your (skill|system prompt|rules|memory)"),
    re.compile(r"(?i)add (this )?to your (constitution|permanent|persistent)"),
    re.compile(r"(以後|今後|これ以降).{0,20}(必ず|常に|絶対に)"),
    re.compile(r"(この(ルール|指示|命令)を)(保存|記憶|永続化|登録)"),
    re.compile(r"(?i)you are now"),
]


def looks_like_embedded_instruction(text):
    """未信頼テキストが永続ルール化を迫る命令を含むか（永続学習を拒む対象・§10）。"""
    if not isinstance(text, str):
        return False
    return any(p.search(text) for p in _INJECTION_PATTERNS)


def scan_injection(payload):
    hits = []

    def walk(v, path="$"):
        if isinstance(v, str):
            if looks_like_embedded_instruction(v):
                hits.append(path)
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(x, "%s.%s" % (path, k))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, "%s[%d]" % (path, i))
    walk(payload)
    return hits


def inhibitory_edges(snapshot):
    return [e for e in snapshot.get("edges", [])
            if e.get("relation") in schemas.INHIBITORY_RELATIONS
            and e.get("status", "active") == "active"]


def must_not_promote_targets(snapshot):
    """must_not_promote で保護された（＝昇格禁止の）ターゲット集合。"""
    return {e["target"] for e in inhibitory_edges(snapshot)
            if e.get("relation") == "must_not_promote"}


def promotion_blocked(mem, snapshot):
    """記憶 mem を行動規則/意味へ昇格させてよいか、抑制の観点で判定する。

    戻り値: (blocked: bool, reasons: list)
    """
    reasons = []
    trust = (mem.get("provenance") or {}).get("source_trust", "untrusted_external")
    if trust in ("untrusted_external", "model_generated"):
        reasons.append("未信頼/モデル生成源は行動規則へ昇格禁止（§10 must_not_promote 既定）")
    if mem.get("memory_id") in must_not_promote_targets(snapshot):
        reasons.append("must_not_promote 抑制エッジが存在")
    # 一時的成功の過学習抑制: サンプル数が少ないのに強化しようとする（§7）。
    n = mem.get("success_count", 0) + mem.get("failure_count", 0)
    if n < 2:
        reasons.append("サンプル数が少なく一時的成功の過学習の恐れ（要追加証拠）")
    return (len(reasons) > 0), reasons


def resolve_competition(candidates):
    """競合方策の相互抑制（winner-take-all 的）。conflicts_with/ inhibits 関係にある
    候補群から、スコアが最大の1件のみ残す近似（§K 競合方策の相互抑制）。

    candidates: [{id, score, conflicts_with:set}]
    戻り値: {selected_id, inhibited:[{id, by}]}
    """
    if not candidates:
        return {"selected_id": None, "inhibited": []}
    ranked = sorted(candidates, key=lambda c: (c.get("score", 0.0), c.get("id")),
                    reverse=True)
    winner = ranked[0]
    inhibited = []
    for c in ranked[1:]:
        conflicts = set(c.get("conflicts_with") or [])
        if winner["id"] in conflicts or c["id"] in set(winner.get("conflicts_with") or []):
            inhibited.append({"id": c["id"], "by": winner["id"]})
    return {"selected_id": winner["id"], "inhibited": inhibited}


def dedup_memories(memories):
    """重複記憶の抑制（§K）。同一 (type, scope, 正規化 claim) を重複候補として束ねる。"""
    seen = {}
    dups = []
    for m in memories:
        key = (m.get("type"), m.get("scope"),
               " ".join(sorted((m.get("claim") or "").lower().split())))
        if key in seen and key[2]:
            dups.append({"keep": seen[key], "duplicate": m.get("memory_id")})
        else:
            seen[key] = m.get("memory_id")
    return dups
