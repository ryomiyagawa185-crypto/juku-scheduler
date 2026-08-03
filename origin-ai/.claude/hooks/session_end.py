#!/usr/bin/env python3
"""SessionEnd フック。日次コストレポートを書き出す。

TODO(P2): drift-audit の軽量実行と、差分検出時の LINE 通知。
通知は外部送信なので external-send ゲートを通すこと（自分宛でも例外にしない）。
"""

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from origin_core import ROOT, pricing  # noqa: E402


def main() -> int:
    day = date.today().isoformat()
    trace_file = ROOT / "traces" / day / "trace.jsonl"
    if not trace_file.exists():
        return 0

    by_skill: dict[str, dict] = defaultdict(
        lambda: {
            "calls": 0,
            "cost_usd": 0.0,
            "input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 0,
            "blocked": 0,
        }
    )
    for line in trace_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        agg = by_skill[rec["skill_id"]]
        agg["calls"] += 1
        agg["cost_usd"] += rec.get("cost_usd", 0.0)
        agg["input_tokens"] += rec.get("input_tokens", 0)
        agg["cache_read_input_tokens"] += rec.get("cache_read_input_tokens", 0)
        agg["output_tokens"] += rec.get("output_tokens", 0)
        if rec.get("status") in {"blocked", "waiting_approval"}:
            agg["blocked"] += 1

    total_in = sum(v["input_tokens"] + v["cache_read_input_tokens"] for v in by_skill.values())
    cache_read = sum(v["cache_read_input_tokens"] for v in by_skill.values())
    report = {
        "date": day,
        "pricing_version": pricing.version(),
        "pricing_is_placeholder": pricing.is_placeholder(),
        "total_cost_usd": round(sum(v["cost_usd"] for v in by_skill.values()), 6),
        "cache_hit_ratio": round(cache_read / total_in, 4) if total_in else 0.0,
        "by_skill": {k: v for k, v in sorted(by_skill.items())},
    }

    out = ROOT / "costs" / f"{day}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
