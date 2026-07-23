# -*- coding: utf-8 -*-
"""learning — 学習原則・忘却・可塑性・昇格ゲート（仕様 §7/§8）。

比喩ではなく実際のアルゴリズム:
  - derive_confidence: trust を事前とする Beta 事後平均（ベイズ的更新）。
    自己申告のみ・未信頼源は上限で抑える。反証で減衰。
  - retrievability: 経過時間の指数減衰（LTD/忘却の近似）。ただし安全記憶・重大失敗・
    明示ユーザー方針は減衰で消さない（§7）。
  - learning_rate: メタ可塑性。高リスク領域・不安定・高失敗率で学習率を下げる。
  - homeostatic_scale: 恒常性可塑性。派生 weight のみ縮小し raw は不可侵。
  - promotion_gate: L0..L5 の昇格条件（§8）。未信頼/モデル生成は行動規則へ昇格不可。
"""

import math

from . import schemas
from . import validation


# ---------- ベイズ的信頼度更新（§7）----------

def derive_confidence(mem):
    """success/failure と source_trust から Beta 事後平均で confidence を導出。"""
    trust = (mem.get("provenance") or {}).get("source_trust", "untrusted_external")
    tw = schemas.TRUST_WEIGHT.get(trust, 0.2)
    s = max(0, int(mem.get("success_count", 0)))
    f = max(0, int(mem.get("failure_count", 0)))
    a0 = 1.0 + 2.0 * tw
    b0 = 1.0 + 2.0 * (1.0 - tw)
    mean = (a0 + s) / (a0 + b0 + s + f)
    counter = len(mem.get("counterevidence_ids", []))
    if counter:
        mean *= 1.0 / (1.0 + 0.5 * counter)   # 反証で減衰
    verified = mem.get("last_verified_at") is not None
    if not verified and trust in ("untrusted_external", "model_generated", "user_inferred"):
        mean = min(mean, 0.5)                  # 未検証×未信頼は高信頼にしない（§10）
    return round(_clamp(mean), 4)


def bayesian_update(prior_confidence, evidence_reliability, observed_success,
                    scope_match=True, sample_size=1):
    """事前信念を証拠で更新する（固定加点でなく重み付き平均）。

    更新幅は evidence_reliability・scope_match・sample_size で調整（§7）。
    """
    prior = _clamp(prior_confidence)
    rel = _clamp(evidence_reliability)
    target = 1.0 if observed_success else 0.0
    lr = rel * (1.0 if scope_match else 0.3) * (1.0 - math.exp(-sample_size / 3.0))
    return round(_clamp(prior + lr * (target - prior)), 4)


# ---------- 忘却・記憶固定化（§7）----------

def _days_between(a, b):
    da, db = validation.parse_dt(a), validation.parse_dt(b)
    if da is None or db is None:
        return 0.0
    da, db = validation._to_naive(da), validation._to_naive(db)
    return max(0.0, (db - da).total_seconds() / 86400.0)


def is_protected(mem):
    """単純な時間減衰では消さない記憶（§7）: 安全記憶・重大失敗・明示ユーザー方針・憲法。"""
    trust = (mem.get("provenance") or {}).get("source_trust")
    if mem.get("level") == "L5":
        return True
    if trust in ("system_policy", "user_explicit"):
        return True
    if mem.get("type") == "inhibitory":
        return True
    if mem.get("failure_count", 0) > 0 or mem.get("counterevidence_ids"):
        return True  # 重大失敗の記憶は保持
    return False


def retrievability(mem, as_of):
    """想起容易性（0..1）。固定化された記憶ほど半減期が長い。保護記憶は下限が高い。"""
    last = mem.get("last_used_at") or mem.get("created_at")
    age = _days_between(last, as_of)
    status = mem.get("status")
    tau = 90.0 if status in ("verified", "active") else 14.0
    r = math.exp(-age / tau)
    if is_protected(mem):
        r = max(r, 0.5)   # 保護記憶は忘却で検索対象外にしない
    return round(_clamp(r), 4)


def forgetting_action(mem, as_of, retrievability_floor=0.05):
    """忘却の種別を返す（削除だけでない・§7）。派生の想起抑制であり raw は消さない。

    戻り値: none | suppress_recall | lower_confidence | exclude_from_search
    """
    if is_protected(mem):
        return "none"
    r = retrievability(mem, as_of)
    if r < retrievability_floor:
        return "exclude_from_search"
    if r < 0.2:
        return "suppress_recall"
    return "none"


# ---------- メタ可塑性（学習率の調整・§7）----------

def learning_rate(domain_risk=0.0, stability=0.5, failure_rate=0.0, base=0.3):
    """高リスク領域・不安定・高失敗率では学習率を下げる（§7 メタ可塑性）。"""
    lr = base * (1.0 - 0.6 * _clamp(domain_risk)) * (0.4 + 0.6 * _clamp(stability))
    lr *= (1.0 - 0.5 * _clamp(failure_rate))
    if domain_risk >= 0.8:
        lr *= 0.3   # 高リスク領域は特に慎重に
    return round(_clamp(lr, 0.02, 0.5), 4)


# ---------- 恒常性可塑性（派生のみ縮小・raw 不可侵・§7）----------

def homeostatic_scale(edges, cap=3.0):
    """各ターゲットノードの入射 derived.strength 和が cap を超えたら派生 weight を縮小。

    raw（観測事実）は決して書き換えない。derived.weight のみ設定する。
    """
    incoming = {}
    for e in edges:
        d = e.get("derived") or {}
        st = float(d.get("strength", 0.0) or 0.0)
        incoming.setdefault(e.get("target"), 0.0)
        incoming[e["target"]] += st
    for e in edges:
        d = e.setdefault("derived", {})
        st = float(d.get("strength", 0.0) or 0.0)
        total = incoming.get(e.get("target"), 0.0)
        scale = 1.0 if total <= cap else (cap / total)
        d["weight"] = round(st * scale, 4)  # 派生のみ。raw は不可侵。
    return edges


# ---------- 昇格ゲート L0..L5（§8）----------

_LEVEL_NEXT = {"L0": "L1", "L1": "L2", "L2": "L3", "L3": "L4", "L4": "L5"}


def promotion_gate(mem, target_level, evidence):
    """target_level への昇格条件を検査し (ok, reasons) を返す。

    evidence: {
      source_recorded, sensitive_removed, event_valid,
      independent_evidence_count, user_confirmed, decisive_test,
      independent_verification, counterevidence_checked, scope_fixed,
      confidence_threshold_met, reproduced_conditions, failure_conditions_known,
      rollback_available, regression_passed, human_approval, security_reviewed,
      diff_present, versioned
    }
    """
    reasons = []
    cur = mem.get("level", "L0")
    if schemas.LEVEL_ORDER.get(target_level, -1) != schemas.LEVEL_ORDER.get(cur, -1) + 1:
        reasons.append("段階的昇格のみ許可（現在 %s → %s は不可）" % (cur, target_level))
        return False, reasons

    trust = (mem.get("provenance") or {}).get("source_trust", "untrusted_external")
    ev = evidence or {}

    def need(cond, msg):
        if not cond:
            reasons.append(msg)

    if target_level == "L1":
        need(ev.get("event_valid"), "L1: イベント形式が妥当でない")
        need(ev.get("source_recorded"), "L1: 出典が記録されていない")
        need(ev.get("sensitive_removed", True), "L1: 機密情報が除去されていない")
    elif target_level == "L2":
        ok = (ev.get("independent_evidence_count", 0) >= 2 or
              ev.get("user_confirmed") or ev.get("decisive_test"))
        need(ok, "L2: 複数独立証拠/明示ユーザー確認/決定的テストのいずれも無い")
    elif target_level == "L3":
        need(ev.get("independent_verification"), "L3: 独立検証がない")
        need(ev.get("counterevidence_checked"), "L3: 反証確認をしていない")
        need(ev.get("scope_fixed"), "L3: 適用範囲が未確定")
        need(ev.get("confidence_threshold_met"), "L3: 信頼度閾値を通過していない")
    elif target_level == "L4":
        need(ev.get("reproduced_conditions", 0) >= 2, "L4: 複数条件下の再現が不足")
        need(ev.get("failure_conditions_known"), "L4: 失敗条件が未知")
        need(ev.get("rollback_available"), "L4: ロールバック不可")
        need(ev.get("regression_passed"), "L4: 回帰試験を通過していない")
        if trust not in schemas.TRUST_PROMOTABLE_TO_RULE:
            reasons.append("L4: 未信頼/モデル生成源は行動規則へ昇格不可（§10）")
    elif target_level == "L5":
        need(ev.get("human_approval"), "L5: 人間の明示承認がない")
        need(ev.get("security_reviewed"), "L5: セキュリティ審査がない")
        need(ev.get("diff_present"), "L5: 変更差分がない")
        need(ev.get("versioned"), "L5: バージョン管理がない")
        need(ev.get("regression_passed"), "L5: 回帰試験を通過していない")
        need(ev.get("rollback_available"), "L5: ロールバック未作成")
        if trust not in schemas.TRUST_PROMOTABLE_TO_RULE:
            reasons.append("L5: 未信頼/モデル生成源は憲法規則へ昇格不可（§10）")
    else:
        reasons.append("未知の target_level: %s" % target_level)

    return (len(reasons) == 0), reasons


def _clamp(x, lo=0.0, hi=1.0):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return lo
    if math.isnan(x):
        return lo
    return max(lo, min(hi, x))
