#!/usr/bin/env bash
#
# grok-review.sh — Grok CLI（@xai-official/grok）でこのリポジトリに質問・レビューを投げる
#
#   ./scripts/grok-review.sh                        既定のレビュー観点で実行
#   ./scripts/grok-review.sh "任意の質問"            質問を指定して実行
#   ./scripts/grok-review.sh --json "TODO を列挙"    JSON で受け取る
#   ./scripts/grok-review.sh --model grok-4.5 "..."  モデルを指定
#
# 読み取り専用で動かすため --permission-mode plan を既定にしている。
# 実際に編集させたい場合は対話モード（引数なしで `grok`）を使うこと。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_FORMAT="plain"
MODEL=""
PROMPT=""

usage() {
  sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --json)         OUTPUT_FORMAT="json"; shift ;;
    --model)        MODEL="${2:-}"; [ -n "$MODEL" ] || { echo "--model には値が必要です" >&2; exit 2; }; shift 2 ;;
    -h|--help)      usage 0 ;;
    --)             shift; PROMPT="$*"; break ;;
    -*)             echo "不明なオプション: $1" >&2; usage 2 ;;
    *)              PROMPT="$*"; break ;;
  esac
done

# --- Grok CLI の存在確認 ------------------------------------------------------
if ! command -v grok >/dev/null 2>&1; then
  cat >&2 <<'EOF'
grok コマンドが見つかりません。次のいずれかで導入してください。

  curl -fsSL https://x.ai/cli/install.sh | bash
  npm i -g @xai-official/grok

詳細は docs/grok-cli.md を参照。
EOF
  exit 127
fi

# --- 公式版かどうかの確認 -----------------------------------------------------
VERSION_LINE="$(grok --version 2>/dev/null || true)"
case "$VERSION_LINE" in
  grok\ *) : ;;
  *)
    echo "警告: 公式版 (@xai-official/grok) ではない可能性があります: ${VERSION_LINE:-取得不可}" >&2
    echo "      有志版 @vibe-kit/grok-cli と取り違えていないか docs/grok-cli.md §0 を確認してください。" >&2
    ;;
esac

# --- 認証確認 -----------------------------------------------------------------
if [ -z "${XAI_API_KEY:-}" ] && [ ! -f "${GROK_HOME:-$HOME/.grok}/auth.json" ]; then
  cat >&2 <<'EOF'
Grok CLI が未認証です。次のいずれかを実行してください。

  grok login                 ブラウザが使える端末
  grok login --device-code   ブラウザが無い端末 / SSH 越し
  export XAI_API_KEY="xai-..."   CI・ヘッドレス環境（https://console.x.ai で発行）
EOF
  exit 1
fi

# --- 既定のレビュー観点 -------------------------------------------------------
if [ -z "$PROMPT" ]; then
  PROMPT=$(cat <<'EOF'
このリポジトリ（塾の授業スケジューラ PWA）の現在の作業ツリーをレビューしてください。
AGENTS.md の規約に照らして、次の観点で問題があれば具体的な箇所とともに指摘してください。

1. index.html / manifest.webmanifest / アイコンに変更があるのに sw.js の CACHE 版数が
   上がっていないか（上がっていない場合は PWA が古いキャッシュを掴み続ける）
2. index.html に外部 URL 参照（CDN のスクリプト・フォント等）が混入していないか
   ※ 本来 0 件であること
3. API キー・スプレッドシート ID・生徒名や保護者連絡先などの機微情報が
   HTML やコミット対象ファイルに直接書かれていないか
4. HTML / JS の明らかな構文エラー・壊れたタグ・重複 ID

問題が無ければ「問題なし」と明記してください。推測で問題をでっち上げないこと。
EOF
)
fi

# --- 実行 ---------------------------------------------------------------------
set -- -p "$PROMPT" --output-format "$OUTPUT_FORMAT" --permission-mode plan --cwd "$REPO_ROOT"
[ -n "$MODEL" ] && set -- "$@" --model "$MODEL"

exec grok "$@"
