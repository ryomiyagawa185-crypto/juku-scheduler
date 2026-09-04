"""P0 の最小ランナー。plan revision を読んで各ステップを実行する。

まだ LLM は呼ばない。呼ぶのは skills/<...>/scripts/run.py だけで、
stdin に inputs を渡し stdout から JSON を受け取る。
P0 の完了基準（手書きの plan で echo スキルが動く）はこれで満たす。

    python -m orchestrator.runner plans/echo.plan.json

意図的に実装していないもの（P2 以降で足す）:
- 推論層の呼び出しと再計画（plan_log への追記）
- 並列実行
- artifacts の atomic rename（下の _write_outputs は素朴な実装）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from origin_core import ROOT, hashing, pricing, registry, schema, tracing

from policy.approvals import ApprovalStore
from policy.budget import BudgetStore
from policy.store import connect

from . import middleware


def _idempotency_key(plan: dict, step: dict) -> str:
    return hashing.hash_value(
        {"plan_id": plan["plan_id"], "step_id": step["step_id"], "inputs": step.get("inputs", {})}
    )


def _already_done(conn, key: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM completed_steps WHERE idempotency_key = ?", (key,)
    ).fetchone()
    return row is not None


def _mark_done(conn, key: str, outputs_hash: str | None) -> None:
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR REPLACE INTO completed_steps (idempotency_key, completed_at, outputs_hash) "
            "VALUES (?, ?, ?)",
            (key, tracing.now_iso(), outputs_hash),
        )


def _order(steps: list[dict]) -> list[dict]:
    """depends_on を満たす順に並べる（循環があれば例外）。"""
    done: set[str] = set()
    remaining = list(steps)
    ordered: list[dict] = []
    while remaining:
        progressed = False
        for step in list(remaining):
            if all(d in done for d in step.get("depends_on", [])):
                ordered.append(step)
                done.add(step["step_id"])
                remaining.remove(step)
                progressed = True
        if not progressed:
            raise ValueError(f"依存が解決できません（循環の可能性）: {[s['step_id'] for s in remaining]}")
    return ordered


def _run_skill(entry: dict, inputs: dict, dry_run: bool) -> dict:
    script = ROOT / entry["path"] / "scripts" / "run.py"
    if not script.exists():
        raise FileNotFoundError(f"実行スクリプトがありません: {script}")
    payload = json.dumps({"inputs": inputs, "dry_run": dry_run}, ensure_ascii=False)
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"スキルが異常終了しました rc={proc.returncode}: {proc.stderr.strip()[:400]}")
    return json.loads(proc.stdout)


def run_plan(
    plan_path: str | Path,
    *,
    tracer: tracing.Tracer | None = None,
    state_path: str | Path | None = None,
) -> list[dict]:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    schema.validate(plan, "plan")

    if plan.get("review_required"):
        print("review_required: true — 人間の承認待ちのため実行しません", file=sys.stderr)
        return []

    entries = registry.load()
    tracer = tracer or tracing.Tracer()
    budget = BudgetStore(state_path)
    approvals = ApprovalStore(state_path)
    conn = connect(state_path)
    results: list[dict] = []

    for step in _order(plan["steps"]):
        started = time.monotonic()
        started_at = tracing.now_iso()
        entry = entries.get(step["skill_id"], {})
        key = _idempotency_key(plan, step)

        record = {
            "trace_id": tracing.new_trace_id(),
            "plan_id": plan["plan_id"],
            "plan_revision": plan["revision"],
            "step_id": step["step_id"],
            "skill_id": step["skill_id"],
            "skill_version": step.get("skill_version", entry.get("version", "0.0.0")),
            "model_id": step.get("model_id"),
            "prompt_hash": None,
            "pricing_version": pricing.version(),
            "input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": 0,
            "started_at": started_at,
            "ended_at": started_at,
            "status": "ok",
            "block_reason": None,
            "gates_triggered": list(step.get("gates_required", [])) + list(entry.get("gates", [])),
            "approval_ref": None,
            "data_class": entry.get("data_class", "pii"),
            "inputs_hash": hashing.hash_value(step.get("inputs", {})),
            "outputs_hash": None,
            "artifact_refs": list(step.get("expected_outputs", [])),
            "retry_count": 0,
            "error_class": None,
        }

        if _already_done(conn, key):
            record["status"] = "skipped_idempotent"
            tracer.write(record)
            results.append(record)
            continue

        decision = middleware.before_step(step, budget_store=budget, approval_store=approvals)
        record["approval_ref"] = decision.approval_ref

        if decision.status != "proceed":
            record["status"] = "blocked" if decision.status == "blocked" else "waiting_approval"
            record["block_reason"] = decision.reason or decision.gate
            record["ended_at"] = tracing.now_iso()
            tracer.write(record)
            results.append(record)
            print(f"[{step['step_id']}] {decision.message()}", file=sys.stderr)
            break  # 後続は依存している可能性が高いので止める

        try:
            output = _run_skill(entry, step.get("inputs", {}), decision.dry_run)
            record["outputs_hash"] = hashing.hash_value(output)
            record["status"] = "dry_run" if decision.dry_run else "ok"
            if step.get("budget_usd"):
                budget.spend(step["skill_id"], float(step["budget_usd"]))
                record["cost_usd"] = float(step["budget_usd"])
            if decision.approval_ref:
                approvals.consume(decision.approval_ref)
            if not decision.dry_run:
                _mark_done(conn, key, record["outputs_hash"])
        except Exception as e:  # noqa: BLE001
            record["status"] = "error"
            record["error_class"] = type(e).__name__
            record["block_reason"] = tracing.mask_exception(e, entry.get("secrets", []))[:200]
        finally:
            record["latency_ms"] = int((time.monotonic() - started) * 1000)
            record["ended_at"] = tracing.now_iso()
            tracer.write(record)
            results.append(record)

        if record["status"] == "error":
            break

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="plan revision を実行する")
    parser.add_argument("plan", help="plan JSON へのパス")
    args = parser.parse_args()
    results = run_plan(args.plan)
    for r in results:
        print(f"{r['step_id']:>4}  {r['status']:<18} {r.get('block_reason') or ''}")
    return 0 if all(r["status"] in {"ok", "dry_run", "skipped_idempotent"} for r in results) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
