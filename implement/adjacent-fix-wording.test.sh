#!/usr/bin/env bash
# Guards #1025: a small round-1 finding in a file the worker already changes
# is fixed in the round rather than filed. implement/SKILL.md § Review must
# state the five-part shape, the 20-line budget and that the budget cannot be
# split across files; § Build must point its pre-existing-bug rule at that
# narrowing; the prose and sidecar forms of the disposition are stated once.
# Prose assertion over SKILL.md; no harness runs the prose.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

# A sed range whose end heading was renamed runs to EOF and would widen the
# slice; require each end heading so a rename fails here, not silently.
for h in '### Review' '### Before the PR'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
build="$(sed -n '/^### Build$/,/^### Review$/p' "$skill" | flatten)"
review="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
whole="$(flatten <"$skill")"
[ -n "$build" ] && [ -n "$review" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
# Stated once: the phrase appears exactly once in the whole file.
check_once() {
  local n
  n="$(grep -o -F -- "$1" <<<"$whole" | wc -l || true)"
  [ "$n" -eq 1 ] || { echo "FAIL: expected '$1' exactly once in SKILL.md, found $n" >&2; fail=1; }
}

check_in "§ Build" "$build" "§ Review's adjacent-fix rule"
check_in "§ Review" "$review" 'it sits in a file already in the diff'
check_in "§ Review" "$review" 'the fix is confined to one function'
check_in "§ Review" "$review" 'it changes under 20 lines, its test included'
check_in "§ Review" "$review" 'it adds no public seam'
check_in "§ Review" "$review" 'it touches no second file'
check_in "§ Review" "$review" 'The 20-line budget cannot be split across files'
check_in "§ Review" "$review" "The fix's own test file is part of the fix, not a second file"
check_in "§ Review" "$review" 'a fix touching any other second file is a change, not an adjacent fix'
check_in "§ Review" "$review" 'in a commit of its own'
check_in "§ Review" "$review" '`fixed (adjacent)`'
check_in "§ Review sidecar" "$review" '{"id": "<id>", "outcome": "fixed", "sha": "<sha>", "scope": "adjacent"}'
check_in "§ Review" "$review" 'multi-axis-code-review/SKILL.md` § 6'
check_once '`fixed (adjacent)`'
check_once '"scope": "adjacent"}'
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
