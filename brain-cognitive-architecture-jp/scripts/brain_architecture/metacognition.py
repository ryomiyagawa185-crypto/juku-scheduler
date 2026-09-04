# -*- coding: utf-8 -*-
"""metacognition — メタ認知層（仕様 §L）。

【生物学的知見】前頭前野などが「自分が知っているか」の感覚（確信度・既知感）を
モニタし、想起の成否や不確実性を評価すると考えられている。
【計算論的抽象化】知っている/知らない・推論/事実・予測/実測を区別し、自己評価の
信頼性を低く扱い、必要なら追加調査を選ぶ。「見つからない」と「存在しない」を分ける。
【実装上の近似】記憶の status/confidence/出典/有効期限から知識状態を決定的に分類し、
較正誤差（Brier）を計算する。self-report は較正の証拠として弱く扱う。
"""

from . import schemas
from . import validation


def classify_memory(mem, as_of=None):
    """記憶1件の知識状態を返す（§L の7状態）。"""
    status = mem.get("status")
    if status in ("deprecated", "archived", "rejected", "purged"):
        return "outdated"
    if (mem.get("derived") or {}).get("in_conflict"):
        return "conflicted"
    # 有効期限切れ = outdated（時間変化する知識・§E）。
    ra = mem.get("review_after")
    if ra and as_of and str(ra) < str(as_of):
        return "outdated"
    trust = (mem.get("provenance") or {}).get("source_trust")
    verified = mem.get("last_verified_at") is not None
    if verified and mem.get("confidence", 0) >= 0.7:
        return "known_verified"
    if trust in ("model_generated", "user_inferred") and not verified:
        return "inferred"        # 推論と事実を区別（§L）
    return "known_unverified"


def classify(retrieval_result, as_of=None):
    """retrieval 結果からトップ記憶の知識状態を統合分類する。

    retrieval の knowledge_state（unknown/not_retrieved 等）を尊重しつつ、
    トップ記憶があれば classify_memory で上書き精緻化する。
    """
    base = retrieval_result.get("knowledge_state", "unknown")
    results = retrieval_result.get("results") or []
    if not results:
        return base   # unknown（存在しない）と not_retrieved（見つからない）を保つ
    top = results[0]
    if top.get("in_conflict"):
        return "conflicted"
    conf = top.get("confidence", 0.0)
    if conf >= 0.7:
        return "known_verified"
    return "known_unverified"


def should_investigate(knowledge_state, confidence=0.0, risk=0.0):
    """追加調査すべきか（§L）。不明/未想起/矛盾、または高リスク×低確信なら True。"""
    if knowledge_state in ("unknown", "not_retrieved", "conflicted", "outdated"):
        return True
    if risk >= 0.6 and confidence < 0.7:
        return True
    return False


def calibration_error(records):
    """予測の較正誤差を返す（§19 calibration_error）。

    records: [{confidence: 0..1, correct: bool}]
    戻り値: {brier, reliability_gap, n}
      brier = mean((confidence - outcome)^2)
      reliability_gap = |mean(confidence) - accuracy|
    """
    recs = [r for r in records if isinstance(r.get("confidence"), (int, float))]
    n = len(recs)
    if n == 0:
        return {"brier": None, "reliability_gap": None, "n": 0}
    brier = sum((float(r["confidence"]) - (1.0 if r.get("correct") else 0.0)) ** 2
                for r in recs) / n
    mean_conf = sum(float(r["confidence"]) for r in recs) / n
    accuracy = sum(1.0 for r in recs if r.get("correct")) / n
    return {"brier": round(brier, 4),
            "reliability_gap": round(abs(mean_conf - accuracy), 4),
            "n": n, "mean_confidence": round(mean_conf, 4),
            "accuracy": round(accuracy, 4)}


def epistemic_report(snapshot, as_of=None):
    """snapshot 全体の知識状態分布を返す（説明可能性・自己点検用）。"""
    as_of = as_of or snapshot.get("as_of")
    dist = {s: 0 for s in schemas.KNOWLEDGE_STATES}
    for m in snapshot.get("memories", []):
        st = classify_memory(m, as_of)
        dist[st] = dist.get(st, 0) + 1
    return {"as_of": as_of, "distribution": dist,
            "note": "self-report は較正証拠として弱く扱う。verified を優先。"}
