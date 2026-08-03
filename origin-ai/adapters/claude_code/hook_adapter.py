"""Claude Code 固有の接着剤。ランタイム依存はこのディレクトリだけに閉じる。

Hooks の仕様:
- stdin に JSON（tool_name, tool_input, session_id ほか）が来る
- PreToolUse は exit code 2 でツール実行をブロックし、stderr がモデルに返る
- exit code 0 は許可、それ以外の非ゼロは非ブロックのエラー扱い

判定そのものは policy/ にあり、ここは形の変換しかしない。
evaluate() を関数として切り出してあるのは、
tests/governance/test_policy_parity.py から直接呼ぶため。
"""

from __future__ import annotations

import json
import sys

from origin_core import registry

from policy import Decision, PolicyContext, decide

EXIT_ALLOW = 0
EXIT_BLOCK = 2


def evaluate(payload: dict, **kwargs) -> Decision:
    entry = None
    skill_id = payload.get("skill_id")
    if skill_id:
        try:
            entry = registry.get(skill_id)
        except registry.SkillNotFound:
            entry = None
    ctx = PolicyContext.from_tool_call(payload, entry)
    return decide(ctx, **kwargs)


def main(argv: list[str] | None = None) -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as e:  # noqa: BLE001 - 読めない入力は通さない
        print(f"policy: 入力を解釈できません ({type(e).__name__})", file=sys.stderr)
        return EXIT_BLOCK

    decision = evaluate(payload)
    if decision.blocked:
        print(f"policy: {decision.message()}", file=sys.stderr)
        return EXIT_BLOCK
    if decision.dry_run:
        print("policy: risk=high のため DRY_RUN で実行してください", file=sys.stderr)
    return EXIT_ALLOW


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
