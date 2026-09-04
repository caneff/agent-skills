#!/usr/bin/env bash
# Compliant ccstatusline usage segments.
#
# Renders weekly/session percentages and 5h/weekly reset countdowns from the
# session JSON that Claude Code pipes to a ccstatusline custom-command on stdin
# (the `rate_limits.*` block, present for Pro/Max). No credential read, no
# /api/oauth/usage call — that path violates Anthropic's "ordinary use of
# native applications only" credential clause. This reads only what the
# official client already handed us.
#
# Usage: usage-segment.sh weekly|session|wreset|breset   (session JSON on stdin)
# Empty output when the field is absent (non-subscriber, or older Claude Code).
set -uo pipefail

# ponytail: jq does the epoch math via its `now` builtin — no shell `date`.
compact_countdown='(. - now) as $s | if $s <= 0 then "0m" else
  ($s/86400|floor)        as $d |
  (($s%86400)/3600|floor) as $h |
  (($s%3600)/60|floor)    as $m |
  ([ (if $d>0 then "\($d)d" else "" end),
     (if $h>0 then "\($h)h" else "" end),
     (if $m>0 then "\($m)m" else "" end) ] | join("")) as $o
  | if $o=="" then "0m" else $o end end'

in=$(cat)
case "${1:-}" in
  weekly)  jq -rj "(.rate_limits.seven_day.used_percentage // empty) | \"\(floor)%\"" <<<"$in" ;;
  session) jq -rj "(.rate_limits.five_hour.used_percentage  // empty) | \"\(floor)%\"" <<<"$in" ;;
  wreset)  jq -rj "(.rate_limits.seven_day.resets_at // empty) | $compact_countdown" <<<"$in" ;;
  breset)  jq -rj "(.rate_limits.five_hour.resets_at // empty) | $compact_countdown" <<<"$in" ;;
  --selftest)
    # Offsets sit ~30s past each minute boundary so the ~1s render drift between
    # this `date +%s` and jq's `now` can't flip a floor (2d3h30m vs 2d3h29m).
    s='{"rate_limits":{"five_hour":{"used_percentage":12.9,"resets_at":'"$(( $(date +%s) + 3*3600 + 10*60 + 30 ))"'},"seven_day":{"used_percentage":42.1,"resets_at":'"$(( $(date +%s) + 2*86400 + 3*3600 + 30*60 + 30 ))"'}}}'
    [ "$(printf '%s' "$s" | "$0" weekly)"  = "42%" ] || { echo "FAIL weekly: $(printf '%s' "$s" | "$0" weekly)"; exit 1; }
    [ "$(printf '%s' "$s" | "$0" session)" = "12%" ] || { echo "FAIL session"; exit 1; }
    [ "$(printf '%s' "$s" | "$0" wreset)"  = "2d3h30m" ] || { echo "FAIL wreset: $(printf '%s' "$s" | "$0" wreset)"; exit 1; }
    [ "$(printf '%s' "$s" | "$0" breset)"  = "3h10m" ]   || { echo "FAIL breset: $(printf '%s' "$s" | "$0" breset)"; exit 1; }
    [ -z "$(printf '{}' | "$0" weekly)" ]            || { echo "FAIL absent-field not blank"; exit 1; }
    echo "ok" ;;
  *) exit 0 ;;
esac
