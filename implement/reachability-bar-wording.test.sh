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
check_in "§ Review" "$review" 'applied before severity'
check_in "§ Review" "$review" 'the worker in round 1, the controller at merge'
check_in "§ Review" "$review" 'disputed rather than fixed'
check_in "§ Review" "$review" 'this box (WSL, one user, shared 32 cores)'
check_in "§ Review" "$review" 'all SHA-1, all `caneff/*`'
check_in "§ Review" "$review" '`disputed: unreachable — <why>`'
check_in "§ Review" "$review" 'whatever Codex'"'"'s severity word'
check_in "§ Review" "$review" 'never becomes a `leftover` sidecar line'
check_in "§ The merge" "$merge" "§ Review's reachability bar"
check_in "multi-axis-code-review § 4" "$maxis_text" "§ Review's reachability bar"

# The verification brief fails an unreachable dispute whose why names no
# environment fact (Codex gate H1 on PR #1135).
check_in "multi-axis-code-review § 6" "$maxis_text" 'on any of four things:'
check_in "multi-axis-code-review § 6" "$maxis_text" 'a `disputed: unreachable — <why>` disposition whose why does not name how the environment'
check_in "multi-axis-code-review § 6" "$maxis_text" 'rules the failure out'

n="$(grep -o -F -- '**The reachability bar.**' <<<"$whole" | wc -l || true)"
[ "$n" -eq 1 ] || { echo "FAIL: expected the bar's heading exactly once, found $n" >&2; fail=1; }
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
