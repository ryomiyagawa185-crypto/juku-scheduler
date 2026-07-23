#!/bin/zsh
# inspect-node.zsh — ノード能力を JSON で標準出力に出す（仕様 §7）。読取専用。
#
# リモート Mac 上（SSH 経由）でも実行できる純 zsh + BSD ツール実装。macOS を主対象とし、
# 取得できない項目は null にする（環境を固定仮定しない・graceful degradation）。
# 秘密値は一切出力しない。副作用なし。
set -u

json_escape() { print -r -- "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
val_or_null() { [[ -n "${1:-}" ]] && print -r -- "\"$(json_escape "$1")\"" || print -n "null"; }
num_or_null() { [[ "${1:-}" == <-> ]] && print -n "$1" || print -n "null"; }

os_version=""; arch=""; cpu=""; cores=""; mem_gb=""; free_gb=""
power=""; batt=""; thermal=""

if [[ "$(uname)" == "Darwin" ]]; then
  os_version="macOS $(sw_vers -productVersion 2>/dev/null)"
  arch="$(uname -m)"
  cpu="$(sysctl -n machdep.cpu.brand_string 2>/dev/null)"
  cores="$(sysctl -n hw.ncpu 2>/dev/null)"
  membytes="$(sysctl -n hw.memsize 2>/dev/null)"
  [[ -n "$membytes" ]] && mem_gb="$(( membytes / 1073741824 ))"
  free_gb="$(df -g / 2>/dev/null | awk 'NR==2{print $4}')"
  # 電源・バッテリー・温度（pmset）。ノート以外は電源のみ。
  pm="$(pmset -g batt 2>/dev/null)"
  print -r -- "$pm" | grep -q "AC Power" && power="AC" || { print -r -- "$pm" | grep -q "Battery Power" && power="battery"; }
  batt="$(print -r -- "$pm" | grep -oE '[0-9]+%' | head -1 | tr -d '%')"
  thermal="$(pmset -g therm 2>/dev/null | grep -oE 'CPU_Speed_Limit *= *[0-9]+' | grep -oE '[0-9]+$')"
  [[ -n "$thermal" && "$thermal" -lt 100 ]] && thermal="throttled" || thermal="nominal"
else
  os_version="$(uname -sr)"
  arch="$(uname -m)"
  cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null)"
fi

# ツール検出（allowlist 的・存在有無のみ）。
tool_json=""
for t in claude ollama ffmpeg pdftotext tesseract python3 brew git rsync sips caffeinate qlmanage; do
  key="$t"; [[ "$t" == "claude" ]] && key="claude_code"
  if command -v "$t" >/dev/null 2>&1; then v=true; else v=false; fi
  tool_json="${tool_json:+$tool_json,}\"$key\": $v"
done

# ローカルモデル（ollama があれば列挙・名前のみ）。
models_json=""
if command -v ollama >/dev/null 2>&1; then
  while IFS= read -r m; do
    [[ -z "$m" ]] && continue
    models_json="${models_json:+$models_json,}\"$(json_escape "$m")\""
  done < <(ollama list 2>/dev/null | awk 'NR>1{print $1}')
fi

node_id="${1:-$(hostname -s 2>/dev/null || hostname)}"
collected_at="$(date -u +%Y-%m-%dT%H:%M:%S 2>/dev/null)"

cat <<JSON
{
  "node_id": $(val_or_null "$node_id"),
  "collected_at": $(val_or_null "$collected_at"),
  "os_version": $(val_or_null "$os_version"),
  "architecture": $(val_or_null "$arch"),
  "cpu": $(val_or_null "$cpu"),
  "cpu_cores": $(num_or_null "$cores"),
  "memory_gb": $(num_or_null "$mem_gb"),
  "free_disk_gb": $(num_or_null "$free_gb"),
  "gpu": $( [[ "$arch" == "arm64" && "$(uname)" == "Darwin" ]] && print -n '"Apple Neural Engine (arm64)"' || print -n null ),
  "power_source": $(val_or_null "$power"),
  "battery_percent": $(num_or_null "$batt"),
  "thermal_state": $(val_or_null "$thermal"),
  "tools": { $tool_json },
  "models": [ $models_json ]
}
JSON
