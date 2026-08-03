#!/usr/bin/env python3
"""PreToolUse フック。判定は policy/ にあり、ここは呼ぶだけ。

このファイルにルールを書かないこと。書いた瞬間、そのルールは
対話セッションでしか効かなくなり、バッチ実行に穴が開く。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapters.claude_code.hook_adapter import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
