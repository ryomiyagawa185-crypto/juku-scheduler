#!/bin/zsh
# bootstrap-node.zsh — リモート Mac をノード登録する *前* の読取専用チェック（§8）。
#
# 使い方:  ./bootstrap-node.zsh <user> <host>
# この時点では SSH 実行しない（--connect 指定時のみ、明示同意として host 鍵確認つきで疎通確認）。
# StrictHostKeyChecking=no は使わない。鍵生成・known_hosts 変更・リモート実行は行わない。
set -u

user="${1:-}"; host="${2:-}"; mode="${3:-}"
if [[ -z "$user" || -z "$host" ]]; then
  print -r -- "usage: bootstrap-node.zsh <user> <host> [--connect]"; exit 2
fi

print -r -- "== ノード登録前チェック: ${user}@${host} =="
print -r -- "-- ローカル前提 --"
command -v ssh >/dev/null 2>&1 && print -r -- "  OK   ssh クライアントあり" || print -r -- "  WARN ssh なし"
print -r -- "-- known_hosts の状態（変更しない・確認のみ）--"
if ssh-keygen -F "$host" >/dev/null 2>&1; then
  print -r -- "  OK   $host は known_hosts に登録済み（host 鍵確認済み）"
else
  print -r -- "  NOTE $host は未登録。初回接続時に host 鍵を目視確認し accept-new で固定すること。"
fi

print -r -- ""
print -r -- "次の手順（承認が必要な操作は手動で）:"
print -r -- "  1) 鍵認証を用意（鍵生成はこのスクリプトでは行わない）。"
print -r -- "  2) 初回 SSH で host 鍵を確認し known_hosts に固定（StrictHostKeyChecking=accept-new）。"
print -r -- "  3) mac-neural-grid node add --host $host --user $user --transport ssh"
print -r -- "  4) host 鍵確認後: mac-neural-grid node trust <node_id> --level medium|high"
print -r -- "  5) mac-neural-grid node inspect <node_id>  （能力台帳を収集）"

if [[ "$mode" == "--connect" ]]; then
  print -r -- ""
  print -r -- "-- 疎通確認（明示同意・StrictHostKeyChecking=accept-new・読取のみ）--"
  ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=10 \
      "${user}@${host}" "uname -a; sw_vers -productVersion 2>/dev/null" \
    && print -r -- "  OK   疎通成功" || print -r -- "  WARN 疎通失敗（鍵/ネットワーク/host を確認）"
fi
