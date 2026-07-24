# -*- coding: utf-8 -*-
"""policy_engine — ポリシー評価とリスク分類（仕様 §15/§27）。ポリシーはコードと分離。

ジョブの executor/操作からリスク（read_only/reversible/high_risk）を分類し、機密ポリシー下では
外部ネットワーク・外部 AI API・非許可ノードを禁止する。high_risk は承認提示の材料を返す。
"""

from . import schemas

# executor → 既定リスク分類（§15）。
_EXECUTOR_RISK = {
    "checksum": "read_only", "document-summary": "reversible",
    "shell": "reversible", "python": "reversible", "ffmpeg": "reversible",
    "ocr": "reversible", "local-llm": "reversible", "claude-code": "reversible",
    "custom-script": "reversible", "external-api": "high_risk",
}
# 高リスクを示す操作語（argv/params に現れたら high_risk へ引き上げ・§15）。
_HIGH_RISK_TOKENS = ("rm", "rmdir", "mv", "chmod", "chown", "sudo", "launchctl",
                     "curl", "wget", "scp", "ssh", "brew", "installer", "defaults",
                     "diskutil", "pmset", "kill", "killall", "dd")


def classify_task_risk(task):
    risk = _EXECUTOR_RISK.get(task.get("executor"), "reversible")
    argv = (task.get("argv") or []) + list((task.get("params") or {}).get("args", []))
    tokens = {str(a).split("/")[-1] for a in argv}
    if tokens & set(_HIGH_RISK_TOKENS):
        risk = "high_risk"
    if task.get("executor") == "external-api":
        risk = "high_risk"
    return risk


def classify_job_risk(job_spec):
    risks = [classify_task_risk(t) for t in job_spec.get("tasks", [])]
    order = {"read_only": 0, "reversible": 1, "high_risk": 2}
    return max(risks, key=lambda r: order[r]) if risks else "read_only"


def validate_policy(policy):
    return schemas.validate(policy or {}, schemas.POLICY_SCHEMA)


def evaluate(job_spec, policy, nodes):
    """ジョブがポリシーに適合するか検査し {ok, violations, risk, requires_approval} を返す。"""
    policy = policy or {}
    violations = []
    for t in job_spec.get("tasks", []):
        if t.get("executor") == "external-api" and not policy.get("external_ai_api", False):
            violations.append("外部 AI API はポリシーで禁止（task type=%s）" % t.get("type"))
        needs_net = t.get("executor") in ("external-api", "claude-code")
        if needs_net and policy.get("external_network") is False:
            violations.append("外部ネットワークはポリシーで禁止（executor=%s）" % t.get("executor"))
    allowed = policy.get("allowed_nodes") or {}
    allow_labels = set(allowed.get("labels") or [])
    if allow_labels:
        for n in nodes:
            if not (allow_labels & set(n.get("labels") or [])):
                # 許可ラベルを持たないノードは選定対象外（scheduler 側 requirements で除外）。
                pass
    risk = classify_job_risk(job_spec)
    return {"ok": len(violations) == 0, "violations": violations, "risk": risk,
            "requires_approval": risk == "high_risk"}


def approval_prompt(job_spec, plan, policy):
    """high_risk 時に提示すべき事項をまとめる（§15）。実行はしない。"""
    tasks = job_spec.get("tasks", [])
    return {
        "risk": classify_job_risk(job_spec),
        "task_count": len(tasks),
        "executors": sorted({t.get("executor") for t in tasks}),
        "target_nodes": [a.get("node_id") for a in (plan or []) if a],
        "external_send": any(t.get("executor") == "external-api" for t in tasks),
        "reversible": classify_job_risk(job_spec) != "high_risk",
        "planned_commands": [t.get("argv") for t in tasks if t.get("argv")],
        "note": "high_risk は明示承認が必要（§15）。対象/件数/不可逆性/ロールバックを確認せよ。",
    }
