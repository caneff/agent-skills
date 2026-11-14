#!/usr/bin/env bash
# usage-segment.sh's cases (#609, #1753). The Python helpers' cases live in the
# `*_test.py` suites beside them.
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
seg="$dir/usage-segment.sh"
# Offsets sit ~30s past each minute boundary so the ~1s render drift between
# this `date +%s` and jq's `now` can't flip a floor (2d3h30m vs 2d3h29m).
s='{"rate_limits":{"five_hour":{"used_percentage":12.9,"resets_at":'"$(( $(date +%s) + 3*3600 + 10*60 + 30 ))"'},"seven_day":{"used_percentage":42.1,"resets_at":'"$(( $(date +%s) + 2*86400 + 3*3600 + 30*60 + 30 ))"'}}}'
check() { # name expected actual
  [ "$2" = "$3" ] || { echo "FAIL $1: expected [$2] got [$3]"; exit 1; }
}
check weekly  "42%"     "$(printf '%s' "$s" | "$seg" weekly)"
check session "12%"     "$(printf '%s' "$s" | "$seg" session)"
check wreset  "2d3h30m" "$(printf '%s' "$s" | "$seg" wreset)"
check breset  "3h10m"   "$(printf '%s' "$s" | "$seg" breset)"
check absent-field "" "$(printf '{}' | "$seg" weekly)"
check all "$(printf '42%%\t2d3h30m\t12%%\t3h10m')" "$(printf '%s' "$s" | "$seg" all)"
check all-absent "$(printf '\t\t\t')" "$(printf '{}' | "$seg" all)"
check unknown-mode "" "$(printf '%s' "$s" | "$seg" bogus)"
echo "ok"
