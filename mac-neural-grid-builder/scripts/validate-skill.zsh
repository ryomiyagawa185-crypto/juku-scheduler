#!/bin/zsh
# validate-skill.zsh — mac-neural-grid CLI の健全性を検査する（副作用なし）。
#
# 使い方:  ./validate-skill.zsh [/path/to/mac-neural-grid]
# 既定は本スキルから見た隣接プロジェクト（../mac-neural-grid）。SKILL 構造・py 構文・
# pytest・localhost の doctor/verify を実行する。リモート/外部送信は一切しない。
set -u
here="${0:A:h}"
proj="${1:-${here}/../../mac-neural-grid}"
proj="${proj:A}"
print -r -- "== validate-skill: $proj =="

fail=0
[[ -f "$proj/pyproject.toml" ]] && print -r -- "  OK   pyproject.toml" || { print -r -- "  FAIL pyproject.toml 無し"; fail=1; }
[[ -d "$proj/src/mac_neural_grid" ]] && print -r -- "  OK   src/mac_neural_grid" || { print -r -- "  FAIL パッケージ無し"; fail=1; }

print -r -- "-- Python 構文 --"
if python3 -m py_compile "$proj"/src/mac_neural_grid/*.py 2>/dev/null; then
  print -r -- "  OK   py_compile"
else
  print -r -- "  FAIL py_compile"; fail=1
fi

print -r -- "-- pytest --"
if command -v pytest >/dev/null 2>&1; then
  ( cd "$proj" && pytest -q ) && print -r -- "  OK   pytest" || { print -r -- "  FAIL pytest"; fail=1; }
else
  print -r -- "  WARN pytest 未導入（スキップ）"
fi

print -r -- "-- localhost 疎通（doctor/verify・無副作用に近い）--"
tmp="$(mktemp -d)"
MNG_HOME="$tmp" PYTHONPATH="$proj/src" python3 -m mac_neural_grid --json doctor >/dev/null 2>&1 \
  && print -r -- "  OK   doctor" || { print -r -- "  FAIL doctor"; fail=1; }
MNG_HOME="$tmp" PYTHONPATH="$proj/src" python3 -m mac_neural_grid --json verify >/dev/null 2>&1 \
  && print -r -- "  OK   verify" || print -r -- "  WARN verify"
rm -rf "$tmp"

print -r -- ""
[[ $fail -eq 0 ]] && print -r -- "PASS" || { print -r -- "FAIL"; exit 1 }
