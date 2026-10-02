#!/bin/bash
# feature ブランチを dev → main の順に統合し、push して、WebUI を再起動する。
#
#   scripts/release_dev_main.sh <featureブランチ> "<mainのマージコミットメッセージ>"
#   scripts/release_dev_main.sh --dry-run <featureブランチ>     # 確認だけ(何も変更しない)
#
# 順序は CLAUDE.md の規則(feature → dev → main)どおり。dev は本番 tc-prod にチェックアウトされている
# ため、dev の更新は本番コードの更新になる。main の更新はユーザーの明示的な指示があるときだけ実行すること
# (このスクリプトを実行すること自体が、その指示)。
#
# 安全装置: 前提が 1 つでも崩れていれば何も変更せずに止まる。
#   - tc-prod が dev で、追跡ファイルに未コミット変更が無い
#   - dev が feature の祖先(fast-forward できる)
#   - ローカルの dev / main が origin と一致している
#   - main がどこにもチェックアウトされていない
#   - 再起動は、WebUI のキューに実行中・待機中のジョブが無いときだけ(--force-restart で上書き)
set -euo pipefail

PROD=/home/abem/Projects/tc-prod
REPO=/home/abem/Projects/tc
SERVICE=tc-webui.service
PORT=8501

DRY_RUN=0
FORCE_RESTART=0
NO_RESTART=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    --force-restart) FORCE_RESTART=1 ;;
    --no-restart) NO_RESTART=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) ARGS+=("$a") ;;
  esac
done

FEATURE="${ARGS[0]:-}"
MSG="${ARGS[1]:-}"
[ -n "$FEATURE" ] || { echo "使い方: $0 [--dry-run] [--no-restart] [--force-restart] <featureブランチ> \"<マージメッセージ>\"" >&2; exit 2; }
if [ "$DRY_RUN" -eq 0 ] && [ -z "$MSG" ]; then
  echo "main のマージコミットメッセージを第2引数で指定してください" >&2; exit 2
fi

g() { git -C "$PROD" "$@"; }
fail() { echo "中止: $*" >&2; exit 1; }
step() { echo; echo "== $* =="; }

step "前提の確認"
git -C "$PROD" rev-parse --git-dir >/dev/null 2>&1 || fail "$PROD が git リポジトリではありません"
g rev-parse --verify -q "refs/heads/$FEATURE" >/dev/null || fail "ブランチ $FEATURE がありません"
[ "$(g branch --show-current)" = "dev" ] || fail "tc-prod のブランチが dev ではありません($(g branch --show-current))"
[ -z "$(g status --porcelain --untracked-files=no)" ] || fail "tc-prod の追跡ファイルに未コミット変更があります"
g merge-base --is-ancestor dev "$FEATURE" || fail "dev が $FEATURE の祖先ではありません(fast-forward できません)。dev と feature が分岐しています"
[ "$(g rev-parse dev)" = "$(g rev-parse origin/dev)" ] || fail "ローカルの dev が origin/dev と一致しません(先に原因を確認してください)"
[ "$(g rev-parse main)" = "$(g rev-parse origin/main)" ] || fail "ローカルの main が origin/main と一致しません(先に原因を確認してください)"
if g worktree list --porcelain | grep -q "^branch refs/heads/main$"; then
  fail "main が別の worktree にチェックアウトされています"
fi
AHEAD=$(g rev-list --count "dev..$FEATURE")
echo "dev: $(g rev-parse --short dev)   $FEATURE: $(g rev-parse --short "$FEATURE")   (dev に取り込むコミット: ${AHEAD}件)"
echo "main: $(g rev-parse --short main)"

# WebUI のジョブ状態: ログ末尾の dispatch_next 行 / 実行中の状態遷移から判断する
LOG="$PROD/logs/transcription.log"
BUSY=0
if [ -f "$LOG" ]; then
  LAST_DISPATCH=$(grep "dispatch_next呼び出し" "$LOG" | tail -1 || true)
  if [ -n "$LAST_DISPATCH" ] && ! echo "$LAST_DISPATCH" | grep -q "current_item_id=None queued_count=0"; then
    BUSY=1
  fi
fi
if [ "$BUSY" -eq 1 ]; then
  echo "注意: WebUI にジョブが実行中または待機中の可能性があります(最終: ${LAST_DISPATCH:0:120})"
else
  echo "WebUI のキューは空です"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo
  echo "ドライラン: 前提はすべて満たしています。何も変更していません。"
  exit 0
fi

if [ "$NO_RESTART" -eq 0 ] && [ "$BUSY" -eq 1 ] && [ "$FORCE_RESTART" -eq 0 ]; then
  fail "ジョブがあるため再起動できません。終わるまで待つか、--no-restart(統合のみ)/ --force-restart(ジョブを失ってよい場合)を指定してください。何も変更していません"
fi

step "dev を fast-forward"
g merge --ff-only "$FEATURE"

step "main へ --no-ff で dev をマージ(一時 worktree)"
TMP=$(mktemp -d /tmp/main-merge.XXXXXX)
cleanup() { git -C "$REPO" worktree remove --force "$TMP" >/dev/null 2>&1 || true; rm -rf "$TMP"; git -C "$REPO" worktree prune || true; }
trap cleanup EXIT
rmdir "$TMP"
git -C "$REPO" worktree add "$TMP" main
git -C "$TMP" merge --no-ff dev -m "$MSG"
[ "$(git -C "$TMP" rev-parse 'main^{tree}')" = "$(git -C "$TMP" rev-parse 'dev^{tree}')" ] || fail "main と dev の内容(tree)が一致しません。push しません"

step "push (dev, main)"
git -C "$TMP" push origin dev main

step "同期の確認"
for b in dev main; do
  L=$(g rev-parse "$b"); R=$(g rev-parse "origin/$b")
  echo "$b: local=${L:0:7} origin=${R:0:7}"
  [ "$L" = "$R" ] || fail "$b が origin と一致しません"
done
echo "tree main==dev: yes"

if [ "$NO_RESTART" -eq 1 ]; then
  echo; echo "統合と push が完了しました(--no-restart のため WebUI は再起動していません。反映には再起動が必要です)"
  exit 0
fi

step "WebUI を再起動"
systemctl --user restart "$SERVICE"
for i in $(seq 1 30); do
  sleep 1
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 3 "http://localhost:$PORT/_stcore/health" || true)
  [ "$CODE" = "200" ] && break
done
[ "$CODE" = "200" ] || fail "再起動後のヘルスチェックが 200 になりません(HTTP $CODE)。systemctl --user status $SERVICE を確認してください"
echo "サービス: $(systemctl --user is-active "$SERVICE")   ヘルス: HTTP $CODE"

echo
echo "完了: dev=$(g rev-parse --short dev) main=$(g rev-parse --short main)"
