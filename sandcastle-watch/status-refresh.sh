#!/usr/bin/env bash
# Keeps .sandcastle/logs/watch-status inside the segment's 180s freshness window
# for as long as the orchestrator lives, then deletes it so the bar clears.
# Usage: status-refresh.sh <combined-stdout-log> <repo-root>
# Launch once per run, alongside the run itself, with run_in_background.
#
# Format (settled):
#   healthy  🏰 3/20 · 101 102 104 · 0 PR
#   trouble  🏰 3/20 · 101 102 104 · 0 PR · 2✗ 103 105 · 1⚠ 104
# In-flight ids always show; failing ids follow their own marker. Only the
# trouble tail is lit — a clean run stays dim so it reads as background noise.
#
# Only DIGITS scraped out of the log ever reach the file (every id passes
# through `tr -cd`), so no agent-authored text is interpolated. That is what
# exempts this loop from the skill's no-shell-writes rule.
# Third arg "once" renders a single frame to stdout instead of looping — how you
# check the format against a finished run's log without an orchestrator alive.
L=$1
F="$2/.sandcastle/logs/watch-status"
ONCE=${3:-}

DIM=$'\033[2m'; RED=$'\033[31m'; YEL=$'\033[33m'; OFF=$'\033[0m'

# ids from marker lines, digits only: "  ✗ 105 (branch) ..." -> "105"
ids() { grep -oE "^  $1 #?[0-9]+" "$L" | grep -oE '[0-9]+' | sort -u | tr '\n' ' ' | sed 's/ $//'; }

frame() {
  it=$(grep -o '=== Iteration [0-9]*/[0-9]*' "$L" | tail -1 | tr -cd '0-9/')
  # work assignments since the last iteration header: "  [full] 104: title → branch"
  flight=$(awk '/=== Iteration /{buf=""} /^  \[[a-z]+\] [0-9]+:/{buf=buf $2" "} END{print buf}' \
    <(grep -E '=== Iteration |^  \[[a-z]+\] [0-9]+:' "$L") | tr -cd '0-9 ' | tr -s ' ' | sed 's/ $//')
  pr=$(grep -c '→ PR #' "$L")
  fx=$(ids '✗'); wn=$(ids '⚠')
  nfx=$(wc -w <<<"$fx"); nwn=$(wc -w <<<"$wn")

  line="${DIM}🏰 ${it:-?} · ${flight:-—} · ${pr} PR"
  [ "$nfx" -gt 0 ] && line="$line ${OFF}${RED}· ${nfx}✗ ${fx}${OFF}${DIM}"
  [ "$nwn" -gt 0 ] && line="$line ${OFF}${YEL}· ${nwn}⚠ ${wn}${OFF}${DIM}"
  printf '%s%s\n' "$line" "$OFF"
}

if [ "$ONCE" = once ]; then frame; exit 0; fi

while pgrep -f 'tsx \.sandcastle/main\.mts' >/dev/null; do
  frame > "$F"
  sleep 60
done
rm -f "$F"
