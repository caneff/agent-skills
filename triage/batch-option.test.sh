#!/usr/bin/env bash
# Guards #1546: a triage round over several items opens by offering the batch
# option (apply every recommended route at once, ask only the contested ones),
# names which items it counts as contested and why, and still asks those one
# at a time. Prose assertions no Python harness can make.
# BASH_SOURCE rather than `git rev-parse --show-toplevel` (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }
fail=0

section() { # <heading> -> that section's text, to the next `## ` heading
  awk -v h="## $1" '$0 == h { on = 1; next } /^## / { on = 0 } on' "$skill" | flatten
}
check_in() { # <text> <needle> <where>
  case "$1" in *"$2"*) ;; *) echo "FAIL: $3 is missing: $2" >&2; fail=1 ;; esac
}

batch="$(section 'Offer the batch option')"
[ -n "$batch" ] || { echo "FAIL: could not extract § Offer the batch option from triage/SKILL.md" >&2; exit 1; }
w='§ Offer the batch option'
check_in "$batch" 'apply my recommended route to every item' "$w"
check_in "$batch" 'names each contested item and why' "$w"
check_in "$batch" 'one at a time, each with a recommendation' "$w"
check_in "$batch" 'except controversial' "$w"
check_in "$batch" 'ask only the contested ones' "$w"
check_in "$batch" 'Ask once per round' "$w"
check_in "$batch" 'Any other reply is the default' "$w"
check_in "$batch" 'never decided by the agent' "$w"
check_in "$batch" 'applied then, not before' "$w"
check_in "$batch" 'an item that needs grilling' "$w"
check_in "$batch" 'stands in for the sort' "$w"
check_in "$batch" 'a `wontfix` of an enhancement' "$w"

# The offer comes before the per-item work: its heading sits ahead of
# "Triage a specific issue or PR", and the large-list step points at it.
offer_line=$(grep -n '^## Offer the batch option$' "$skill" | cut -d: -f1 || true)
triage_line=$(grep -n '^## Triage a specific issue or PR$' "$skill" | cut -d: -f1 || true)
[ -n "$offer_line" ] || { echo "FAIL: heading '## Offer the batch option' is missing from triage/SKILL.md" >&2; exit 1; }
[ -n "$triage_line" ] || { echo "FAIL: heading '## Triage a specific issue or PR' is missing from triage/SKILL.md" >&2; exit 1; }
[ "$offer_line" -lt "$triage_line" ] ||
  { echo "FAIL: § Offer the batch option does not precede § Triage a specific issue or PR" >&2; fail=1; }
check_in "$(section 'Show what needs attention')" '§ Offer the batch option' '§ Show what needs attention'

[ "$fail" -eq 0 ] && echo "PASS triage/batch-option.test.sh"
exit "$fail"
