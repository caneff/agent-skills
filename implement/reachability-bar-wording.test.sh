#!/usr/bin/env bash
# Guards #1086: the severity mapping carries a reachability bar, applied
# before severity — a finding whose failure cannot occur here is
# `disputed: unreachable — <why>`, never filed and never a sidecar line
# (burn-2026-09-22-0636 filed seven tickets from second and third passes;
# four were closed on sight as unreachable). The bar is stated once in
# implement/SKILL.md § Review; § The merge and multi-axis-code-review point
# at it. Prose assertion — no harness runs the skill's own prose.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
maxis="$here/../multi-axis-code-review/SKILL.md"

flatten() { tr '\n' ' ' | tr -s ' '; }
review="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
merge="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
whole="$(flatten <"$skill")"
maxis_text="$(flatten <"$maxis")"
[ -n "$review" ] && [ -n "$merge" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
check_in "§ Review" "$review" '**The reachability bar.**'
check_in "§ Review" "$review" 'applied before severity'
check_in "§ Review" "$review" 'this box (WSL, one user, shared 32 cores)'
check_in "§ Review" "$review" 'all SHA-1, all `caneff/*`'
check_in "§ Review" "$review" '`disputed: unreachable — <why>`'
check_in "§ Review" "$review" 'whatever Codex'"'"'s severity word'
check_in "§ Review" "$review" 'not a sidecar line'
check_in "§ The merge" "$merge" "§ Review's reachability bar"
check_in "multi-axis-code-review § 4" "$maxis_text" "§ Review's reachability bar"

n="$(grep -o -F -- '**The reachability bar.**' <<<"$whole" | wc -l || true)"
[ "$n" -eq 1 ] || { echo "FAIL: expected the bar's heading exactly once, found $n" >&2; fail=1; }
exit "$fail"
