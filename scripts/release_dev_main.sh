#!/bin/bash
# feature ブランチを dev → main の順に統合し、push して、WebUI を再起動する。
#
#   scripts/release_dev_main.sh <featureブランチ> "<mainのマージコミットメッセージ>"
#   scripts/release_dev_main.sh --dry-run <featureブランチ>     # 確認だけ(何も変更しない)
#   オプション: --no-restart(統合と push だけ) / --force-restart(ジョブがあっても再起動)
#
# 順序は CLAUDE.md の規則(feature → dev → main)どおり。dev は本番 tc-prod にチェックアウトされている
# ため、dev の更新は本番コードの更新になる。main の更新はユーザーの明示的な指示があるときだけ実行すること
# (このスクリプトを実行すること自体が、その指示)。
#
# 手順(本番を動かすのは最後):
#   1. 前提の確認(origin を fetch して最新と比べる)。1 つでも崩れていれば何も変更せずに止まる
#   2. 一時 worktree で main に feature を --no-ff でマージし、内容(tree)が feature と一致することを確認
#   3. origin へ dev と main を --atomic で push(拒否されれば、ここで止まる。本番もローカルの main も未変更)
#   4. push が成功したあとで、本番 dev を fast-forward し、ローカルの main を進める
#   5. WebUI を再起動してヘルスチェック(ジョブがあれば、手順 2 より前に止まる)
#
# 止まる前提:
#   - tc-prod が dev で、追跡ファイルに未コミット変更が無い
#   - ローカルの dev / main が origin(fetch 直後)と一致し、dev と main の内容(tree)が同じ
#   - dev が feature の祖先で、取り込むコミットがある
#   - main がどこにもチェックアウトされていない
#   - WebUI のジョブ(ダウンロード中・待機中・処理中)が無い。ログの状態遷移と、WebUI 配下の
#     yt-dlp / ffmpeg / nemotron のプロセスから判断する。確認できなければ「ある」とみなす
#
# 環境変数(テスト用): TC_PROD, TC_LOG, TC_SERVICE(空なら再起動しない), TC_SYSTEMCTL, TC_PORT
set -euo pipefail

PROD="${TC_PROD:-/home/abem/Projects/tc-prod}"
SERVICE="${TC_SERVICE-tc-webui.service}"
SYSTEMCTL="${TC_SYSTEMCTL:-systemctl --user}"
PORT="${TC_PORT:-8501}"
LOG="${TC_LOG:-$PROD/logs/transcription.log}"

DRY_RUN=0
FORCE_RESTART=0
NO_RESTART=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    --force-restart) FORCE_RESTART=1 ;;
    --no-restart) NO_RESTART=1 ;;
    -h|--help) awk 'NR>1 && /^#/ {print substr($0,3); next} NR>1 {exit}' "$0"; exit 0 ;;
    --*) echo "不明なオプション: $a (--help を参照)" >&2; exit 2 ;;
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
WANT_RESTART=1
{ [ "$NO_RESTART" -eq 1 ] || [ -z "$SERVICE" ]; } && WANT_RESTART=0

# ---- WebUI にジョブがあるかの判定 ------------------------------------------------------------
# 戻り値: 標準出力に "IDLE" か "BUSY: <理由>"。確認できないときは BUSY(安全側)。
detect_busy() {
  # (1) WebUI 配下で動いている取得・変換・推論のプロセス(ログに現れないもの)
  if [ -n "$SERVICE" ]; then
    if [ "$($SYSTEMCTL is-active "$SERVICE" 2>/dev/null || true)" = "active" ]; then
      local main_pid
      main_pid=$($SYSTEMCTL show -p MainPID --value "$SERVICE" 2>/dev/null || echo 0)
      if [ "${main_pid:-0}" -gt 0 ] 2>/dev/null; then
        local pids="$main_pid" frontier="$main_pid" next p
        while [ -n "$frontier" ]; do
          next=""
          for p in $frontier; do next="$next $(pgrep -P "$p" 2>/dev/null | tr '\n' ' ')"; done
          frontier=$(echo "$next" | xargs 2>/dev/null || true)
          pids="$pids $frontier"
        done
        for p in $pids; do
          local cmd
          cmd=$(ps -o args= -p "$p" 2>/dev/null || true)
          if echo "$cmd" | grep -qE "yt-dlp|ffmpeg|nemotron_infer"; then
            echo "BUSY: WebUI 配下で取得・変換・推論のプロセスが動いています(pid $p: ${cmd:0:80})"
            return 0
          fi
        done
      fi
    fi
  fi

  # (2) ログの状態遷移: サービスの起動以降で、終了(DONE / FAILED)していない項目があるか
  if [ ! -f "$LOG" ]; then
    if [ -n "$SERVICE" ]; then
      echo "BUSY: ログ($LOG)が無く、ジョブの状態を確認できません"
    else
      echo "IDLE"
    fi
    return 0
  fi
  local since="1970-01-01 00:00:00"
  if [ -n "$SERVICE" ]; then
    local ts
    ts=$($SYSTEMCTL show -p ActiveEnterTimestamp --value "$SERVICE" 2>/dev/null || true)
    if [ -n "$ts" ]; then
      since=$(date -d "$ts" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "$since")
    fi
  fi
  python3 - "$LOG" "$since" <<'PY'
import re, sys, time
from datetime import datetime

log, since = sys.argv[1], sys.argv[2]
ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
tr_re = re.compile(r"状態遷移 item_id=(\d+) (?:\(新規\)|\w+)->(\w+)")
# item_id はブラウザセッションごとに 1 から採番されるため、別セッションの項目と衝突する。
# item_id で最後の状態を上書きすると、別セッションの終了(DONE / FAILED)が、処理中の項目を隠してしまう。
# そこで、項目の作成(`(新規)->...`)と終了(`->DONE` / `->FAILED`)の回数を item_id ごとに数え、
# 作成が終了を上回っている(=終了していない項目がある)かで判断する。
open_count = {}
last_dispatch = None
with open(log, encoding="utf-8", errors="replace") as f:
    for line in f:
        m = ts_re.match(line)
        if not m or m.group(1) < since:
            continue
        t = tr_re.search(line)
        if t:
            item_id, to_state = t.group(1), t.group(2)
            if "(新規)->" in line:
                open_count[item_id] = open_count.get(item_id, 0) + 1
            elif to_state in ("DONE", "FAILED"):
                # ログの窓の外(ローテーションなど)で作られた項目の終了は、他の項目の開始を打ち消さない
                open_count[item_id] = max(open_count.get(item_id, 0) - 1, 0)
        if "dispatch_next呼び出し" in line:
            last_dispatch = (m.group(1), line)
busy = {i: c for i, c in open_count.items() if c > 0}
if busy:
    i, c = sorted(busy.items())[0]
    total = sum(busy.values())
    print(f"BUSY: ジョブが終了していません(item_id={i} など{total}件。ログに開始があり終了が無い)")
    sys.exit(0)
if last_dispatch:
    when, line = last_dispatch
    fresh = (datetime.now() - datetime.strptime(when, "%Y-%m-%d %H:%M:%S")).total_seconds() < 120
    if fresh and "current_item_id=None queued_count=0" not in line:
        print("BUSY: 直近 2 分以内のログで、処理中または待機中のジョブがあります")
        sys.exit(0)
print("IDLE")
PY
}

# ---- 前提の確認(何も変更しない) -------------------------------------------------------------
step "前提の確認"
git -C "$PROD" rev-parse --git-dir >/dev/null 2>&1 || fail "$PROD が git リポジトリではありません"
g rev-parse --verify -q "refs/heads/$FEATURE" >/dev/null || fail "ブランチ $FEATURE がありません"
[ "$(g branch --show-current)" = "dev" ] || fail "tc-prod のブランチが dev ではありません($(g branch --show-current))"
[ -z "$(g status --porcelain --untracked-files=no)" ] || fail "tc-prod の追跡ファイルに未コミット変更があります"
echo "origin を fetch します"
g fetch --quiet origin dev main || fail "origin の fetch に失敗しました(ネットワークまたは認証)。何も変更していません"
[ "$(g rev-parse dev)" = "$(g rev-parse origin/dev)" ] || fail "ローカルの dev が origin/dev と一致しません(origin が先に進んでいる可能性)。原因を確認してください。何も変更していません"
[ "$(g rev-parse main)" = "$(g rev-parse origin/main)" ] || fail "ローカルの main が origin/main と一致しません。原因を確認してください。何も変更していません"
[ "$(g rev-parse 'dev^{tree}')" = "$(g rev-parse 'main^{tree}')" ] || fail "dev と main の内容(tree)が一致しません。どちらかが単独で更新されています。原因を確認してください。何も変更していません"
g merge-base --is-ancestor dev "$FEATURE" || fail "dev が $FEATURE の祖先ではありません(fast-forward できません)。dev と feature が分岐しています"
if g worktree list --porcelain | grep -q "^branch refs/heads/main$"; then
  fail "main がどこかの worktree にチェックアウトされています"
fi
AHEAD=$(g rev-list --count "dev..$FEATURE")
[ "$AHEAD" -gt 0 ] || fail "dev に取り込むコミットがありません($FEATURE は dev と同じです)"
FEATURE_SHA=$(g rev-parse "$FEATURE^{commit}")
echo "dev: $(g rev-parse --short dev)   $FEATURE: ${FEATURE_SHA:0:7}   (dev に取り込むコミット: ${AHEAD}件)"
echo "main: $(g rev-parse --short main)"

BUSY_RESULT=$(detect_busy)
BUSY=0
case "$BUSY_RESULT" in
  BUSY*) BUSY=1; echo "注意: ${BUSY_RESULT}" ;;
  *) echo "WebUI のジョブはありません" ;;
esac

if [ "$DRY_RUN" -eq 1 ]; then
  echo
  echo "ドライラン: 前提はすべて満たしています(origin を fetch して確認済み)。何も変更していません。"
  if [ "$WANT_RESTART" -eq 1 ] && [ "$BUSY" -eq 1 ] && [ "$FORCE_RESTART" -eq 0 ]; then
    echo "ただし、このままの実行は WebUI のジョブがあるため止まります(--no-restart か --force-restart を指定してください)。"
  fi
  exit 0
fi
if [ "$WANT_RESTART" -eq 1 ] && [ "$BUSY" -eq 1 ] && [ "$FORCE_RESTART" -eq 0 ]; then
  fail "WebUI にジョブがあるため再起動できません(${BUSY_RESULT#BUSY: })。終わるまで待つか、--no-restart(統合のみ)/ --force-restart(ジョブを失ってよい場合)を指定してください。何も変更していません"
fi

# ---- main へのマージ(一時 worktree。本番の dev はまだ動かさない) ------------------------------
step "main へ --no-ff で $FEATURE をマージ(一時 worktree)"
TMP=$(mktemp -d /tmp/release-dev-main.XXXXXX)
cleanup() {
  g worktree remove --force "$TMP/wt" >/dev/null 2>&1 || true
  rm -rf "$TMP"
  g worktree prune >/dev/null 2>&1 || true
}
trap cleanup EXIT
g worktree add --quiet --detach "$TMP/wt" main
if ! git -C "$TMP/wt" merge --no-ff "$FEATURE_SHA" -m "$MSG" >/dev/null 2>&1; then
  git -C "$TMP/wt" merge --abort >/dev/null 2>&1 || true
  fail "main への $FEATURE のマージが競合しました。何も変更していません"
fi
MERGED=$(git -C "$TMP/wt" rev-parse HEAD)
[ "$(git -C "$TMP/wt" rev-parse "$MERGED^{tree}")" = "$(g rev-parse "$FEATURE_SHA^{tree}")" ] \
  || fail "マージ後の main と $FEATURE の内容(tree)が一致しません。push しません。何も変更していません"
echo "マージコミット: ${MERGED:0:7}"

# ---- origin へ push(ここが失敗しても、本番もローカルの main も未変更) ---------------------------
step "origin へ push (dev と main を --atomic で)"
if ! git -C "$TMP/wt" push --atomic origin "$FEATURE_SHA:refs/heads/dev" "$MERGED:refs/heads/main"; then
  fail "origin が push を拒否しました。本番 dev・ローカルの main・origin は変更していません。fetch して原因(origin が先に進んだ等)を確認してください"
fi

# ---- push が成功したあとで、本番とローカルを追従させる ---------------------------------------
step "本番 dev とローカルの main を更新"
if ! g merge --ff-only "$FEATURE_SHA"; then
  echo "origin は更新済みですが、本番 dev の fast-forward に失敗しました。次を実行してください:" >&2
  echo "  git -C $PROD merge --ff-only origin/dev" >&2
  fail "本番 dev が未更新です"
fi
if ! g branch -f main "$MERGED"; then
  echo "origin は更新済みですが、ローカルの main の更新に失敗しました。次を実行してください:" >&2
  echo "  git -C $PROD fetch origin && git -C $PROD branch -f main origin/main" >&2
  fail "ローカルの main が未更新です"
fi

step "同期の確認"
for b in dev main; do
  L=$(g rev-parse "$b"); R=$(g rev-parse "origin/$b")
  echo "$b: local=${L:0:7} origin=${R:0:7}"
  [ "$L" = "$R" ] || fail "$b が origin と一致しません"
done
[ "$(g rev-parse 'dev^{tree}')" = "$(g rev-parse 'main^{tree}')" ] || fail "main と dev の内容(tree)が一致しません"
echo "tree main==dev: yes"

if [ "$WANT_RESTART" -eq 0 ]; then
  echo; echo "統合と push が完了しました(再起動はしていません。WebUI に反映するには再起動が必要です)"
  exit 0
fi

step "WebUI を再起動"
$SYSTEMCTL restart "$SERVICE"
CODE=000
for _ in $(seq 1 30); do
  sleep 1
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 3 "http://localhost:$PORT/_stcore/health" || true)
  [ "$CODE" = "200" ] && break
done
[ "$CODE" = "200" ] || fail "再起動後のヘルスチェックが 200 になりません(HTTP $CODE)。$SYSTEMCTL status $SERVICE を確認してください(統合と push は完了しています)"
echo "サービス: $($SYSTEMCTL is-active "$SERVICE")   ヘルス: HTTP $CODE"

echo
echo "完了: dev=$(g rev-parse --short dev) main=$(g rev-parse --short main)"
