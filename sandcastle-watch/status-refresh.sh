#!/usr/bin/env bash
# Keeps .sandcastle/logs/watch-status inside the segment's 180s freshness window
# for as long as the orchestrator lives, then deletes it so the bar clears.
# Usage: status-refresh.sh <combined-stdout-log> <repo-root>
# Launch once per run, alongside the run itself, with run_in_background.
#
# Only NUMBERS from the log reach the file — iteration counter, PR count, real
# failure count. Nothing agent-authored is ever interpolated, so this loop is
# exempt from the skill's no-shell-writes rule that binds the tick digest.
L=$1
F="$2/.sandcastle/logs/watch-status"
while pgrep -f 'tsx \.sandcastle/main\.mts' >/dev/null; do
  it=$(grep -o '=== Iteration [0-9]*/[0-9]*' "$L" | tail -1 | tr -cd '0-9/')
  pr=$(grep -c 'PR #' "$L")
  fa=$(grep -cE '^  ✗' "$L")
  printf '🏰 iter %s · %s PRs · %s✗\n' "${it:-?}" "$pr" "$fa" > "$F"
  sleep 60
done
rm -f "$F"
