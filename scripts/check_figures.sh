#!/bin/bash
# docs/figures/*.mmd(図の元データ)を機械検査し、検査済みの SVG を書き戻す。
#
#   scripts/check_figures.sh [図の名前(拡張子なし) ...]     # 省略時は docs/figures/ の全部
#
# 図の検査(fig.sh)は、mermaid の入った package.json が上位にある場所でしか動かない。そのため
# ~/Projects/claude/explainer-trial/docs/tc-docs/figures/ へ .mmd と .facts.json を複製して検査し、
# CLEAN のときだけ SVG を docs/figures/ に書き戻す。検査後に画像(look at it)を目で見て確認すること。
# 環境変数: EXPLAINER_TRIAL(既定 ~/Projects/claude/explainer-trial)
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$HERE/docs/figures"
EXPL="${EXPLAINER_TRIAL:-$HOME/Projects/claude/explainer-trial}"
WORK="$EXPL/docs/tc-docs/figures"
FIG="$HOME/.claude/skills/diagram-design/scripts/fig.sh"

[ -d "$EXPL" ] || { echo "中止: $EXPL がありません(EXPLAINER_TRIAL で指定できます)" >&2; exit 2; }
[ -x "$FIG" ] || [ -f "$FIG" ] || { echo "中止: $FIG がありません(diagram-design スキル)" >&2; exit 2; }
mkdir -p "$WORK"

names=("$@")
if [ ${#names[@]} -eq 0 ]; then
  for f in "$SRC"/*.mmd; do [ -e "$f" ] && names+=("$(basename "$f" .mmd)"); done
fi
[ ${#names[@]} -gt 0 ] || { echo "検査する図がありません($SRC/*.mmd)"; exit 0; }

status=0
for n in "${names[@]}"; do
  [ -f "$SRC/$n.mmd" ] || { echo "中止: $SRC/$n.mmd がありません" >&2; exit 2; }
  [ -f "$SRC/$n.facts.json" ] || { echo "中止: $SRC/$n.facts.json(事実シート)がありません" >&2; exit 2; }
  cp "$SRC/$n.mmd" "$SRC/$n.facts.json" "$WORK/"
  echo "== $n =="
  if out=$(bash "$FIG" "$WORK/$n.mmd" 2>&1); then rc=0; else rc=$?; fi
  echo "$out" | grep -E "✗|verdict|look at" || true
  if echo "$out" | grep -q "figure verdict: CLEAN"; then
    cp "$WORK/$n.svg" "$SRC/$n.svg"
    echo "  → $SRC/$n.svg を更新しました。上の 'look at' の画像を目で確認してください"
  else
    echo "  → 機械検査が通っていません。SVG は更新しません" >&2
    status=1
  fi
done
exit $status
