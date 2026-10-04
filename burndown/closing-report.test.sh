#!/usr/bin/env bash
# Guards #1401 (ADR 0004, ADR 0005): burndown/SKILL.md ends a run with one
# closing report carrying fixed, moved and friction-log counts and files no
# sweep ticket; controller friction goes to the friction log, not to a ticket;
# and the controller sends Chris only a contested or irreversible decision,
# restated in full, plus that report. Prose assertions no Python harness can
# make; the counts are tested in burndown/counts_test.py.
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

report="$(section 'The closing report')"
[ -n "$report" ] || { echo "FAIL: could not extract § The closing report from burndown/SKILL.md" >&2; exit 1; }
check_in "$report" 'one report to Chris, and no sweep ticket' '§ The closing report'
check_in "$report" 'two counts, **fixed** and **moved**' '§ The closing report'
check_in "$report" 'python3 burndown/counts.py counts <run-id> --repo <primary checkout>' '§ The closing report'
check_in "$report" 'friction-log count' '§ The closing report'
check_in "$report" 'review_ledger.py escapes --repo-dir <primary checkout>' '§ The closing report'
check_in "$report" 'keep the component if any escape is attributed, delete it otherwise' '§ The closing report'
check_in "$report" 'refused by number, never counted as zero' '§ The closing report'

friction="$(section 'The friction log')"
[ -n "$friction" ] || { echo "FAIL: could not extract § The friction log from burndown/SKILL.md" >&2; exit 1; }
check_in "$friction" 'one line appended to `docs/agents/friction-log.md`' '§ The friction log'
check_in "$friction" 'never a ticket of its own' '§ The friction log'
check_in "$friction" 'only on its second occurrence' '§ The friction log'

quiet="$(section 'What the controller says to Chris')"
[ -n "$quiet" ] || { echo "FAIL: could not extract § What the controller says to Chris from burndown/SKILL.md" >&2; exit 1; }
check_in "$quiet" 'a decision that is contested or cannot be undone' '§ What the controller says to Chris'
check_in "$quiet" 'restated in full' '§ What the controller says to Chris'
check_in "$quiet" 'the one closing report' '§ What the controller says to Chris'
check_in "$quiet" 'idle or stop notice and its "PR up" are never relayed' '§ What the controller says to Chris'

# The sweep is gone: no heading for it, no renderer, no leftover command.
if grep -qE '^## The sweep$|sweep\.py|runfile\.py leftover' "$skill"; then
  echo "FAIL: burndown/SKILL.md still describes the sweep or the leftover command" >&2; fail=1
fi
[ ! -e "$here/sweep.py" ] || { echo "FAIL: burndown/sweep.py still exists" >&2; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS burndown/closing-report.test.sh"
exit "$fail"
