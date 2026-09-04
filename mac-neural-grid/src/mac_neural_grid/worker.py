# -*- coding: utf-8 -*-
"""worker — ノード上で1タスクを実行する Worker Agent（仕様 §6/§16/§17/§29）。

`python -m mac_neural_grid.worker --envelope <path>` として（localhost では subprocess、
将来は SSH 経由で）起動される。責務:
  - 受信 envelope を未信頼入力として検証（schema・payload_hash・expires_at・protocol）。
  - 専用作業ディレクトリ input/ work/ output/ logs/ を用意（§16）。
  - executor を実行し、result.json / manifest.json を原子的に書く。
  - タイムアウト・中断に対応し、一時データを安全に扱う。
返り値（プロセス終了コード）: 成功 0 / 失敗 1 / 検証拒否 2。
"""

import argparse
import json
import os
import sys

from . import security, schemas
from .database import now_iso
from .executor import ExecContext, run_executor


def _validate_envelope(env):
    errors = schemas.validate(env, schemas.ENVELOPE_SCHEMA)
    if errors:
        return "envelope schema 違反: %s" % "; ".join(errors)
    if env.get("protocol_version") != "mng/1":
        return "protocol_version 不一致: %r" % env.get("protocol_version")
    payload = env.get("payload") or {}
    if not security.verify_payload_hash(payload, env.get("payload_hash")):
        return "payload_hash 不一致（改竄/破損の疑い）"
    if now_iso() > str(env.get("expires_at", "")):
        return "EXPIRED"
    return None


def run_envelope(env, dirs=None):
    """envelope を実行し result dict を返す（in-process 版・テスト用）。"""
    err = _validate_envelope(env)
    payload = env.get("payload") or {}
    task_spec = payload.get("task_spec") or {}
    work_base = env.get("work_base") or payload.get("work_base")
    dirs = dirs or {k: security.safe_join(work_base, k)
                    for k in ("input", "work", "output", "logs")}
    for d in dirs.values():
        security.makedirs(d)
    if err == "EXPIRED":
        return _finalize(env, dirs, {"status": "quarantined", "exit_code": None,
                                     "failure_class": "policy_denied", "artifacts": [],
                                     "stdout_excerpt": "", "stderr_excerpt": "期限切れ envelope",
                                     "duration_s": 0.0})
    if err:
        return _finalize(env, dirs, {"status": "failed", "exit_code": None,
                                     "failure_class": "invalid_input", "artifacts": [],
                                     "stdout_excerpt": "", "stderr_excerpt": err,
                                     "duration_s": 0.0})
    ctx = ExecContext(dirs, payload.get("node") or {"node_id": env.get("node_id")},
                      payload.get("limits") or env.get("resource_limits"),
                      payload.get("capabilities"), payload.get("policy"))
    result = run_executor(task_spec.get("executor"), ctx, task_spec)
    return _finalize(env, dirs, result)


def _finalize(env, dirs, result):
    result["task_id"] = env.get("task_id")
    result["node_id"] = env.get("node_id")
    # manifest（envelope メタ + 成果物 checksum。payload/秘密は残さない）。
    manifest = {"protocol_version": env.get("protocol_version"),
                "job_id": env.get("job_id"), "task_id": env.get("task_id"),
                "attempt_id": env.get("attempt_id"), "node_id": env.get("node_id"),
                "created_at": env.get("created_at"), "finalized_at": now_iso(),
                "artifacts": [{"name": a["name"], "checksum": a["checksum"],
                               "size_bytes": a["size_bytes"]}
                              for a in result.get("artifacts", [])]}
    base = os.path.dirname(dirs["output"])
    security.atomic_write_json(security.safe_join(base, "manifest.json"), manifest)
    dest = env.get("result_destination") or security.safe_join(base, "result.json")
    security.atomic_write_json(dest, security.redact_obj(result))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(prog="mac_neural_grid.worker")
    p.add_argument("--envelope", required=True)
    args = p.parse_args(argv)
    try:
        with open(args.envelope, encoding="utf-8") as f:
            env = json.load(f)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": "envelope 読込失敗: %s" % exc}))
        return 2
    result = run_envelope(env)
    print(json.dumps({"task_id": result.get("task_id"), "status": result.get("status"),
                      "failure_class": result.get("failure_class"),
                      "n_artifacts": len(result.get("artifacts", []))}, ensure_ascii=False))
    return 0 if result.get("status") == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
