# -*- coding: utf-8 -*-
"""proposals — 自己改変候補の台帳（仕様 §8/§9）。仮説であり、自動では本番に入らない。

consolidate（オフライン統合）や learning が候補を生成し、ここに append する。
昇格（promote）は executive の認可 ＋ 人間承認を経てのみ event log に反映される。
台帳は proposals/OPEN.md（人が読む）＋ proposals/<id>.json（機械可読）。
"""

import hashlib

from . import secure_io
from . import event_store
from . import validation


def make_proposal(ptype, rationale, scope="project", target_level=None,
                  evidence_ids=None, diff=None, expected_effect=None,
                  side_effects=None, counterexamples=None, memory=None,
                  checklist=None, occurred_at=None):
    """§9 の必須項目（理由・根拠・diff・期待効果・副作用・反例・検証）を持つ候補を作る。"""
    created_at = occurred_at or event_store.now_iso()
    body = {"type": ptype, "rationale": rationale, "scope": scope,
            "target_level": target_level, "diff": diff, "memory": memory}
    pid = "prop_" + hashlib.sha1(
        event_store.content_hash(body).encode("utf-8")).hexdigest()[:16]
    return {
        "proposal_id": pid,
        "type": ptype,
        "status": "open",
        "scope": scope,
        "target_level": target_level,
        "rationale": rationale,
        "evidence_ids": sorted(evidence_ids or []),
        "diff": diff,
        "memory": memory,
        "expected_effect": expected_effect,
        "side_effects": side_effects,
        "counterexamples": counterexamples,
        # §9 の自己改変手順チェックリスト（既定は未達）。
        "checklist": checklist or {
            "reason": bool(rationale), "evidence": bool(evidence_ids),
            "diff": diff is not None, "expected_effect": bool(expected_effect),
            "side_effects": bool(side_effects), "counterexamples": bool(counterexamples),
            "regression_test": False, "security_test": False, "sandbox_run": False,
            "human_approval": False, "canary": False, "rollback_prepared": False,
        },
        "created_at": created_at,
        "approved_by": None,
    }


def write_proposal(paths, proposal):
    from . import schemas
    errors = validation.validate_schema(proposal, schemas.PROPOSAL_SCHEMA)
    if errors:
        raise ValueError("proposal schema 違反: %s" % "; ".join(errors))
    secure_io.makedirs(paths["proposals"])
    path = _proposal_path(paths, proposal["proposal_id"])
    secure_io.atomic_write_json(path, proposal)
    line = "- `%s` [%s] %s — %s" % (
        proposal["proposal_id"], proposal["status"], proposal["type"],
        (proposal.get("rationale") or "")[:80])
    secure_io.upsert_line_prepend(paths["proposals_open"],
                                  proposal["proposal_id"], line)
    return path


def _proposal_path(paths, pid):
    import os
    # path traversal 対策: id は英数と _ のみ許容。
    if not all(c.isalnum() or c == "_" for c in pid):
        raise ValueError("不正な proposal_id: %r" % pid)
    return os.path.join(paths["proposals"], pid + ".json")


def load_proposal(paths, pid):
    return secure_io.read_json(_proposal_path(paths, pid))


def list_proposals(paths, status=None):
    import os
    out = []
    d = paths["proposals"]
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            p = secure_io.read_json(os.path.join(d, fn))
            if isinstance(p, dict) and (status is None or p.get("status") == status):
                out.append(p)
    return out


def set_status(paths, pid, status, approver=None):
    from . import schemas
    p = load_proposal(paths, pid)
    if p is None:
        return None
    if status not in schemas.PROPOSAL_STATUS:
        raise ValueError("不正な proposal status: %s" % status)
    p["status"] = status
    if approver:
        p["approved_by"] = approver
        p.setdefault("checklist", {})["human_approval"] = True
    write_proposal(paths, p)
    return p
