#!/usr/bin/env bash
#
# Indeed への投稿を、ローカルの Claude Code に依頼する。
#
# リモートセッション（claude.ai・GitHub連携）にはブラウザ操作のMCPが繋がっていないため、
# 投稿は claude-in-chrome MCP が使えるローカル環境で行う。
# このスクリプトは、最新の求人票から依頼文を組み立てて Claude Code を起動する。
#
# 使い方（Mac のターミナルで）:
#   ./recruitment/indeed/post_to_indeed.sh 17
#   ./recruitment/indeed/post_to_indeed.sh 17 --dry-run
#   ./recruitment/indeed/post_to_indeed.sh 14 --live 17 11    # 掲載中の求人と重複しないか検査
#
set -euo pipefail

usage() {
  cat <<'USAGE'
使い方: ./recruitment/indeed/post_to_indeed.sh <求人番号> [--dry-run] [--live <掲載中の番号>...]

例:
  ./recruitment/indeed/post_to_indeed.sh 17              # 農工大（W1で出す本命）
  ./recruitment/indeed/post_to_indeed.sh 11 --live 17    # 17を掲載中の状態で11を追加（W2）
  ./recruitment/indeed/post_to_indeed.sh 14 --live 17 11 # さらに14を追加（W3）
  ./recruitment/indeed/post_to_indeed.sh 17 --dry-run    # 依頼文を表示するだけ

--live に掲載中の求人番号を渡すと、重複判定を受けないかを事前に検査します。
掲載の順番と同時掲載のルールは recruitment/indeed/00_運用戦略_数学英語採用.md を参照。
USAGE
}

NUMBER=""
DRY_RUN="no"
LIVE=()
MODE=""

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN="yes"; MODE="" ;;
    --live)    MODE="live" ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [[ "$MODE" == "live" ]]; then
        LIVE+=("$arg")
      elif [[ -z "$NUMBER" ]]; then
        NUMBER="$arg"
      else
        echo "!!  解釈できない引数です: $arg" >&2
        usage >&2
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$NUMBER" ]]; then
  usage
  exit 1
fi

# リポジトリ直下へ移動する（どこから叩かれてもいいように）
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
INDEED_DIR="recruitment/indeed"

echo "==> リポジトリ: $ROOT"

# --- 1. 最新を取り込む -------------------------------------------------------
if git rev-parse --git-dir >/dev/null 2>&1; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  echo "==> ブランチ: $BRANCH"
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "!!  未コミットの変更があります。pull は行いません。"
    git status --short
  else
    echo "==> git pull を実行します"
    git pull --ff-only origin "$BRANCH" || echo "!!  pull できませんでした。ローカルの内容で続行します。"
  fi
fi

# --- 2. 貼り付け用テキストを最新化する ---------------------------------------
echo "==> 貼り付け用テキストを生成します"
python3 "$INDEED_DIR/to_plaintext.py" "$NUMBER"

# --- 3. 同時掲載の重複を検査する ---------------------------------------------
echo
if (( ${#LIVE[@]} > 0 )); then
  echo "==> 同時掲載の検査（掲載中: ${LIVE[*]} ＋ 今回: $NUMBER）"
  set +e
  python3 "$INDEED_DIR/check_similarity.py" --live "$NUMBER" "${LIVE[@]}" --top 3
  CHECK_STATUS=$?
  set -e
  if (( CHECK_STATUS == 1 )); then
    echo
    echo "!!  危険域の組み合わせがあります。このまま出すと重複判定を受けます。"
    echo "    別の求人に差し替えるか、本文を書き分けてください。"
    exit 1
  elif (( CHECK_STATUS != 0 )); then
    echo
    echo "!!  検査を実行できませんでした（番号の指定を確認してください）。"
    exit 1
  fi
else
  echo "==> 同時掲載の検査はスキップしました"
  echo "    掲載中の求人がある場合は --live で番号を渡すと検査します"
  echo "    例: ./recruitment/indeed/post_to_indeed.sh $NUMBER --live 17 11"
fi

# --- 4. 依頼文を組み立てる ---------------------------------------------------
WORK="$(mktemp -d)"
BRIEFING="$WORK/indeed_briefing_$NUMBER.md"
python3 "$INDEED_DIR/make_briefing.py" "$NUMBER" --out "$BRIEFING"

# 本文をクリップボードへ（手作業に切り替えたくなった時のため）
PADDED="$(printf '%02d' "$((10#$NUMBER))")"
BODY="$(find "$INDEED_DIR/plaintext" -name "${PADDED}_*.txt" | head -1 || true)"
if [[ -n "$BODY" ]] && command -v pbcopy >/dev/null 2>&1; then
  pbcopy < "$BODY"
  echo "==> 仕事内容の本文をクリップボードにコピーしました"
  echo "    $BODY"
fi

if [[ "$DRY_RUN" == "yes" ]]; then
  echo
  echo "===================== 依頼文 ====================="
  cat "$BRIEFING"
  echo "=================================================="
  echo
  echo "（--dry-run のため Claude Code は起動しませんでした）"
  echo "依頼文: $BRIEFING"
  exit 0
fi

# --- 5. Claude Code を起動する -----------------------------------------------
if ! command -v claude >/dev/null 2>&1; then
  cat <<EOF

!!  claude コマンドが見つかりません。

    依頼文はここにあります:
      $BRIEFING

    Claude Code を起動して、このファイルの中身を貼り付けてください。
EOF
  exit 1
fi

echo
echo "==> Claude Code を起動します。ブラウザ操作の許可を求められたら承認してください。"
echo

claude "$(cat "$BRIEFING")"
