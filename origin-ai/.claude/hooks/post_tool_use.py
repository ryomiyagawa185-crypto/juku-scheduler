#!/usr/bin/env python3
"""PostToolUse フック。

P1 の範囲では、対話セッション中のツール呼び出しを最小限のトレースとして残す。
実測トークンはツール呼び出し単位では取れないため 0 のままにし、
model_id と prompt_hash を null にして「LLM 呼び出しではない」ことを明示する。

TODO(P2): セッションの usage を集計して costs/ に日次で書き出す。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from origin_core import hashing, pricing, tracing  # noqa: E402


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0  # PostToolUse で失敗しても実行済みの操作は取り消せない。黙って抜ける

    tool_input = payload.get("tool_input", {}) or {}
    now = tracing.now_iso()
    record = {
        "trace_id": tracing.new_trace_id(),
        "plan_id": payload.get("session_id") or "interactive",
        "plan_revision": 1,
        "step_id": payload.get("tool_name", "unknown"),
        "skill_id": f"tool.{str(payload.get('tool_name', 'unknown')).lower()}",
        "skill_version": "0.0.0",
        "model_id": None,
        "prompt_hash": None,
        "pricing_version": pricing.version(),
        "input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "latency_ms": 0,
        "started_at": now,
        "ended_at": now,
        "status": "ok",
        "block_reason": None,
        "gates_triggered": [],
        "approval_ref": None,
        "data_class": "internal",
        "inputs_hash": hashing.hash_value(tool_input),
        "outputs_hash": None,
        "artifact_refs": [],
        "retry_count": 0,
        "error_class": None,
    }
    try:
        tracing.Tracer().write(record)
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
