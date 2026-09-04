#!/bin/zsh
# validate-environment.zsh — Control Mac 環境の読取専用チェック（副作用なし）。
set -u
ok=0; warn=0
say() { print -r -- "$1"; }
check() { if eval "$2" >/dev/null 2>&1; then say "  OK   $1"; ok=$((ok+1)); else say "  WARN $1"; warn=$((warn+1)); fi }

say "== mac-neural-grid 環境チェック =="
say "-- 基本 --"
check "python3 が存在" "command -v python3"
check "Python 3.11+ " "python3 -c 'import sys;exit(0 if sys.version_info>=(3,11) else 1)'"
check "PyYAML 利用可" "python3 -c 'import yaml'"
check "sqlite3 モジュール" "python3 -c 'import sqlite3'"
say "-- macOS ツール（任意）--"
for t in ssh rsync sw_vers sysctl pmset caffeinate; do
  check "$t" "command -v $t"
done
say "-- AI/処理ツール（任意・ノード能力）--"
for t in claude ollama ffmpeg pdftotext tesseract brew; do
  check "$t" "command -v $t"
done
say ""
say "結果: OK=$ok WARN=$warn （WARN は degrade 可能・致命ではない）"
