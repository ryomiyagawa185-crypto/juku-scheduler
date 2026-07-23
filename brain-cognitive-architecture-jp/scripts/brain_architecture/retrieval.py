# -*- coding: utf-8 -*-
"""retrieval — パターン補完（部分手掛かり検索）と誤補完の抑制（仕様 §D/§5）。

【生物学的知見】海馬は部分手掛かりから連想的にエピソードを補完すると考えられる
（パターン補完）。一方で似て非なる記憶の混同（誤補完）はパターン分離で防がれる。
【計算論的抽象化】手掛かりと記憶の重なりで想起候補を出すが、閾値未満なら「補完
しない」＝でっち上げない。スコープ/パーティション越えの想起は遮断する（§5）。
【実装上の近似】決定的なトークン重なり＋confidence＋retrievability の合成スコア。
"""

from . import schemas
from . import attention as attn

MIN_MATCH = 0.12          # これ未満は誤補完として抑制（confabulation 防止）
MIN_RETRIEVABILITY = 0.05


def scope_allowed(mem, query_scope, query_partition=None):
    """記憶が現在の文脈に適用可能か（狭いスコープ優先・パーティション隔離・§5）。

    - パーティション（顧客/組織/ユーザ等の instance）が設定された記憶は、
      パーティション一致時のみ想起可能（顧客間漏洩を遮断）。
    - スコープ level は「等しいか広い」記憶のみ下位文脈へ generalize する
      （project 固有を global へ、一回限りを恒久へ、勝手に広げない）。
    """
    part = mem.get("partition")
    if part not in (None, "") and part != query_partition:
        return False
    mb = schemas.SCOPE_BREADTH.get(mem.get("scope"), 2)
    qb = schemas.SCOPE_BREADTH.get(query_scope, 2)
    return mb >= qb


def retrieve(snapshot, cue, query_scope="project", query_partition=None,
             limit=8, include_suppressed=False):
    """手掛かり cue に対する想起結果を返す。

    cue: {keywords, text, goal} のいずれか。
    戻り値: {results, suppressed, knowledge_state, considered}
    """
    cue_tok = attn._tokens(_cue_text(cue))
    memories = snapshot.get("memories", [])
    in_scope = [m for m in memories if scope_allowed(m, query_scope, query_partition)]

    scored, suppressed = [], []
    for m in in_scope:
        if m.get("status") not in schemas.RETRIEVABLE_STATUS:
            continue
        mem_tok = attn._tokens(_mem_text(m))
        sim = attn._overlap(cue_tok, mem_tok) if cue_tok else 0.0
        retr = (m.get("derived") or {}).get("retrievability", 0.0)
        forgetting = (m.get("derived") or {}).get("forgetting", "none")
        conf = m.get("confidence", 0.0)
        s = round(0.5 * sim + 0.3 * conf + 0.2 * retr, 4)
        rec = {"memory_id": m["memory_id"], "type": m.get("type"),
               "claim": m.get("claim"), "scope": m.get("scope"),
               "similarity": round(sim, 4), "confidence": conf,
               "retrievability": retr, "score": s,
               "in_conflict": (m.get("derived") or {}).get("in_conflict", False)}
        # 忘却で検索対象外 / 想起容易性が下限未満 → 抑制（誤補完・古記憶の想起抑制・§7）。
        if forgetting == "exclude_from_search" or retr < MIN_RETRIEVABILITY:
            suppressed.append({**rec, "reason": "forgotten/low-retrievability"})
            continue
        if sim < MIN_MATCH:
            suppressed.append({**rec, "reason": "below-match-threshold(誤補完抑制)"})
            continue
        scored.append(rec)

    scored.sort(key=lambda r: (r["score"], r["memory_id"]), reverse=True)
    results = scored[:limit]

    # 「見つからない」と「存在しない」を区別（§L）。
    if results:
        conflicted = any(r["in_conflict"] for r in results)
        knowledge_state = "conflicted" if conflicted else _state_of(results[0])
    elif in_scope:
        knowledge_state = "not_retrieved"   # 記憶はあるが手掛かりに合致しない
    else:
        knowledge_state = "unknown"         # 当該スコープに記憶が存在しない
    out = {"results": results, "knowledge_state": knowledge_state,
           "considered": len(in_scope)}
    if include_suppressed:
        out["suppressed"] = suppressed
    return out


def _state_of(rec):
    if rec["confidence"] >= 0.7:
        return "known_verified"
    return "known_unverified"


def _cue_text(cue):
    if isinstance(cue, str):
        return cue
    parts = [cue.get("text", ""), cue.get("goal", "")]
    parts += list(cue.get("keywords", []) or [])
    return " ".join(str(p) for p in parts)


def _mem_text(m):
    return " ".join(str(x) for x in [m.get("claim", ""), m.get("content") or ""])
