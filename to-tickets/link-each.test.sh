#!/usr/bin/env bash
# Guards #1254 (sweep item C2 of #867): to-tickets step 5 links each ticket to
# its parent right after publishing it. Publishing all first and linking after
# leaves a crash window in which the parent has no children, step 1's
# sub-issue guard reads it as unsliced, and a re-run publishes a duplicate set.
# A prose assertion over the skill, scoped to the publish bullet.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bullet="$(grep -F 'A real issue tracker (GitHub, Linear' "$here/SKILL.md" | tr -s ' ')"
[ -n "$bullet" ] || { echo "FAIL: could not find the real-tracker publish bullet in to-tickets/SKILL.md" >&2; exit 1; }
fail=0
for want in 'immediately after publishing it, before the next one' 'a re-run stops at step 1'; do
  case "$bullet" in
    *"$want"*) ;;
    *) echo "FAIL: the publish bullet is missing: $want" >&2; fail=1 ;;
  esac
done
[ "$fail" -eq 0 ] && echo "PASS to-tickets/link-each.test.sh"
exit "$fail"
