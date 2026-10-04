#!/usr/bin/env bash
# Guards #1086, as #1401 left it: a reachability bar, applied before a finding
# is fixed or moved — a finding whose failure cannot occur here is
# `disputed: unreachable — <why>`. The bar is stated once in
# implement/SKILL.md § Review; multi-axis-code-review points at it. Prose assertion — no harness runs
# the skill's own prose.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
maxis="$here/../multi-axis-code-review/SKILL.md"

flatten() { tr '\n' ' ' | tr -s ' '; }
review="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
merge="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
whole="$(flatten <"$skill")"
maxis_text="$(flatten <"$maxis")"
# A sed range whose end heading was renamed runs to EOF and would widen the
# slice; require each end heading so a rename fails here, not silently.
grep -q '^### Before the PR$' "$skill" && grep -q '^## Someone else' "$skill" ||
  { echo "FAIL: an end heading the section slices need was renamed" >&2; exit 1; }
[ -n "$review" ] && [ -n "$merge" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
check_in "§ Review" "$review" '**The reachability bar.**'
check_in "§ Review" "$review" 'applied before a finding is fixed or moved'
check_in "§ Review" "$review" 'this box (WSL, one user, shared 32 cores)'
check_in "§ Review" "$review" 'all SHA-1, all `caneff/*`'
check_in "§ Review" "$review" '`disputed: unreachable — <why>`'
check_in "§ Review" "$review" 'whatever its rating'
check_in "§ Review" "$review" 'a bare "unlikely" is not one'
check_in "multi-axis-code-review § 4" "$maxis_text" "§ Review's reachability bar"

n="$(grep -o -F -- '**The reachability bar.**' <<<"$whole" | wc -l || true)"
[ "$n" -eq 1 ] || { echo "FAIL: expected the bar's heading exactly once, found $n" >&2; fail=1; }
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
