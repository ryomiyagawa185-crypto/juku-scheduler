#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brain.py — brain_architecture CLI の薄いラッパー（scripts/ を sys.path に載せて起動）。

使い方:
  python3 scripts/brain.py <command> [options]
  例: python3 scripts/brain.py --dir /path/to/mem init
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain_architecture.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
