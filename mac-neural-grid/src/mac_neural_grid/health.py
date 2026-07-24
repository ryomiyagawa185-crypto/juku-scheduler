# -*- coding: utf-8 -*-
"""health — ノード健全性による割当ゲート（仕様 §18/§19/§31）。

Mac が高温・バッテリー低下・スリープ直前の場合は新規ジョブを割り当てない。取得できない値は
「阻害しない（null 扱い）」として保守的に扱いつつ、明確な悪条件のみ割当を止める。
"""


def resource_pressure(capabilities):
    """0..1 の資源圧。CPU/メモリ負荷が高いほど大きい（scheduler が減点に使う）。"""
    load = (capabilities or {}).get("current_load") or {}
    cpu = _num(load.get("cpu_percent"), 0.0) / 100.0
    mem = _num(load.get("memory_percent"), 0.0) / 100.0
    jobs = _num(load.get("active_jobs"), 0.0)
    return min(1.0, 0.5 * cpu + 0.3 * mem + 0.2 * min(1.0, jobs / 4.0))


def assignable(node, policy=None):
    """新規割当可否と理由を返す（§18）。悪条件なら (False, reasons)。"""
    policy = policy or {}
    cap = node.get("capabilities") or {}
    reasons = []
    if not node.get("enabled", True):
        reasons.append("ノードが disabled")
    if node.get("trust") == "untrusted":
        reasons.append("trust=untrusted のノードには割当てない")
    thermal = (cap.get("thermal_state") or "").lower()
    if thermal in ("critical", "serious", "hot"):
        reasons.append("高温（thermal=%s）" % thermal)
    batt = cap.get("battery_percent")
    power = (cap.get("power_source") or "").lower()
    min_batt = policy.get("min_battery_percent")
    if power == "battery" and batt is not None and batt < 20:
        reasons.append("バッテリー低下(%s%%)かつ電源未接続" % batt)
    if min_batt is not None and batt is not None and batt < min_batt:
        reasons.append("ポリシー最低バッテリー(%s%%)未満(%s%%)" % (min_batt, batt))
    if policy.get("require_power") and power and power != "ac":
        reasons.append("ポリシーで電源接続必須だが power=%s" % power)
    load = cap.get("current_load") or {}
    if _num(load.get("cpu_percent"), 0) >= 95:
        reasons.append("CPU 逼迫(>=95%)")
    return (len(reasons) == 0, reasons)


def _num(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
