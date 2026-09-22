#!/usr/bin/env bash
# Guards #1027: the verification pass counts `leftover` as a disposition and
# fails a leftover whose finding is high; the reviewer briefs point at
# implement's one severity mapping rather than restating it. Prose assertion
# over SKILL.md.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '### 6. The verification pass' '## Why separate axes' '### 5. Aggregate'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
verify="$(sed -n '/^### 6\. The verification pass$/,/^## Why separate axes$/p' "$skill" | flatten)"
spawn="$(sed -n '/^### 4\. Spawn/,/^### 5\. Aggregate$/p' "$skill" | flatten)"
whole="$(flatten <"$skill")"
[ -n "$verify" ] && [ -n "$spawn" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
check_in "§ 6" "$verify" '`leftover` counts as one'
check_in "§ 6" "$verify" 'a `leftover` whose finding is high'
check_in "§ 4" "$spawn" "Which rating counts as high is \`implement/SKILL.md\` § Review's severity mapping"
# Pointed at, never restated: the mapping's defining sentence lives in implement.
case "$whole" in *'A finding is high when'*)
  echo "FAIL: SKILL.md restates the severity mapping; point at implement's instead" >&2; fail=1 ;;
esac
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
