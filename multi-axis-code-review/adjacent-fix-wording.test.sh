#!/usr/bin/env bash
# Guards #1025: the verification pass measures every adjacent fix against
# implement's adjacent-fix rule and fails by finding id on a breach, beside
# its missing-disposition failure; the spec axis does not report a change an
# adjacent disposition names as scope creep. Prose assertion over SKILL.md;
# check_adjacent_test.py exercises the check the brief names.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '### 6. The verification pass' '## Why separate axes'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
verify="$(sed -n '/^### 6\. The verification pass$/,/^## Why separate axes$/p' "$skill" | flatten)"
spec="$(grep -F '**Spec sub-agent prompt**' -A4 "$skill" | flatten)"
[ -n "$verify" ] && [ -n "$spec" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
check_in "§ 6" "$verify" 'a round-1 finding with no disposition'
check_in "§ 6" "$verify" 'every sidecar line with `"scope": "adjacent"`'
check_in "§ 6" "$verify" 'python3 ~/.agents/skills/multi-axis-code-review/check_adjacent.py'
check_in "§ 6" "$verify" 'one function and no public seam'
check_in "§ 6" "$verify" 'Fail the pass, naming the finding id'
check_in "§ 6" "$verify" "implement/SKILL.md\` § Review's adjacent-fix rule"
check_in "Spec brief" "$spec" 'except a change an adjacent disposition names (`fixed (adjacent)`)'
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
