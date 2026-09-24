#!/usr/bin/env bash
# Guards #1148: a worker's turn ends mid-lane only on a message to its
# controller — a question, a job declaration, or "PR up". #1095's worker
# committed, ran the gate and ended its turn with a summary to no one; the
# controller found it ten minutes later only because Chris asked. The rule
# sits in implement/SKILL.md § Control. A prose assertion, not a behavioral
# test — the hook that backs it is tested in
# flow/claude/hooks/worker-stop-alert.test.sh, the sweep's `stalled` verdict
# in burndown/loop_test.py.
# Resolving via BASH_SOURCE sidesteps a caller's leaked GIT_DIR (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

# Both range addresses must exist, or sed widens the range to EOF and every
# check below reads "somewhere in SKILL.md".
for heading in '^## Control$' '^## Light tier$'; do
  grep -q "$heading" "$skill" || { echo "FAIL: implement/SKILL.md has no heading matching $heading" >&2; exit 1; }
done
section="$(sed -n '/^## Control$/,/^## Light tier$/p' "$skill" | tr '\n' ' ' | tr -s ' ')"
[ -n "$section" ] || { echo "FAIL: could not extract § Control" >&2; exit 1; }

fail=0
check() {
  case "$section" in
    *"$1"*) ;;
    *) echo "FAIL: implement/SKILL.md § Control is missing: $1" >&2; fail=1 ;;
  esac
}

check 'Your turn ends mid-lane only on a message to the controller'
check 'a question, a job declaration, or "PR up"'
check 'A summary in your own pane reaches no one'
check '#1095'
check '`stalled`'

if [ "$fail" -eq 0 ]; then echo "PASS implement/turn-end-wording.test.sh"; else exit 1; fi
