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
# Usage: usage-segment.sh weekly|session|wreset|breset|all   (session JSON on stdin)
# Empty output when the field is absent (non-subscriber, or older Claude Code).
# `all` prints all four fields tab-separated on one line, in the order
# weekly, wreset, session, breset, each blank when absent — one jq pass, one
# process spawn, instead of a caller running the four single-field modes.
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

# `all`'s null-safe versions of the percentage/countdown filters above: each
# takes the raw field value (which may be `null` when absent) instead of a
# pre-filtered `// empty`, since a generator producing nothing would drop that
# field out of the joined array entirely.
all_filter='
def pct: if . == null then "" else "\(floor)%" end;
def cd: if . == null then "" else ('"$compact_countdown"') end;
[ (.rate_limits.seven_day.used_percentage | pct),
  (.rate_limits.seven_day.resets_at       | cd),
  (.rate_limits.five_hour.used_percentage | pct),
  (.rate_limits.five_hour.resets_at       | cd)
] | join("\t")
'

in=$(cat)
case "${1:-}" in
  weekly)  jq -rj "(.rate_limits.seven_day.used_percentage // empty) | \"\(floor)%\"" <<<"$in" ;;
  session) jq -rj "(.rate_limits.five_hour.used_percentage  // empty) | \"\(floor)%\"" <<<"$in" ;;
  wreset)  jq -rj "(.rate_limits.seven_day.resets_at // empty) | $compact_countdown" <<<"$in" ;;
  breset)  jq -rj "(.rate_limits.five_hour.resets_at // empty) | $compact_countdown" <<<"$in" ;;
  all)     jq -rj "$all_filter" <<<"$in" ;;
  --selftest)
    # Offsets sit ~30s past each minute boundary so the ~1s render drift between
    # this `date +%s` and jq's `now` can't flip a floor (2d3h30m vs 2d3h29m).
    s='{"rate_limits":{"five_hour":{"used_percentage":12.9,"resets_at":'"$(( $(date +%s) + 3*3600 + 10*60 + 30 ))"'},"seven_day":{"used_percentage":42.1,"resets_at":'"$(( $(date +%s) + 2*86400 + 3*3600 + 30*60 + 30 ))"'}}}'
    [ "$(printf '%s' "$s" | "$0" weekly)"  = "42%" ] || { echo "FAIL weekly: $(printf '%s' "$s" | "$0" weekly)"; exit 1; }
    [ "$(printf '%s' "$s" | "$0" session)" = "12%" ] || { echo "FAIL session"; exit 1; }
    [ "$(printf '%s' "$s" | "$0" wreset)"  = "2d3h30m" ] || { echo "FAIL wreset: $(printf '%s' "$s" | "$0" wreset)"; exit 1; }
    [ "$(printf '%s' "$s" | "$0" breset)"  = "3h10m" ]   || { echo "FAIL breset: $(printf '%s' "$s" | "$0" breset)"; exit 1; }
    [ -z "$(printf '{}' | "$0" weekly)" ]            || { echo "FAIL absent-field not blank"; exit 1; }
    exp_all=$(printf '42%%\t2d3h30m\t12%%\t3h10m')
    got_all=$(printf '%s' "$s" | "$0" all)
    [ "$got_all" = "$exp_all" ] || { echo "FAIL all: $got_all"; exit 1; }
    exp_blank=$(printf '\t\t\t')
    got_blank=$(printf '{}' | "$0" all)
    [ "$got_blank" = "$exp_blank" ] || { echo "FAIL all-absent: $got_blank"; exit 1; }
    echo "ok" ;;
  *) exit 0 ;;
esac
