#!/usr/bin/env bash
# Guards #1027: a finding that is neither fixed nor high takes the fifth
# sidecar outcome, `leftover`, instead of a ticket of its own; `filed` is
# reserved for high findings; and implement/SKILL.md § Review states the one
# severity mapping the three reviewer vocabularies share, once, where the
# reviewer briefs point. Prose assertion over SKILL.md; the sidecar forms are
# checked against the fixture by dispositions_fixture_test.py.
# Also guards #1033: a worker with no run file under it files one per-PR
# sweep ticket for its own leftover lines instead of one per finding
# (§ The PR), and a burn controller folds one it finds on the frontier
# rather than leaving it beside the run's own sweep (checked against
# `burndown/sweep-ticket.test.sh`'s own § The sweep extraction).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '### Review' '### Before the PR' '### The PR' '### The merge'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
review="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
the_pr="$(sed -n '/^### The PR$/,/^### The merge$/p' "$skill" | flatten)"
whole="$(flatten <"$skill")"
[ -n "$review" ] || { echo "FAIL: could not extract § Review" >&2; exit 1; }
[ -n "$the_pr" ] || { echo "FAIL: could not extract § The PR" >&2; exit 1; }

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
check_once() {
  local n
  n="$(grep -o -F -- "$1" <<<"$whole" | wc -l || true)"
  [ "$n" -eq 1 ] || { echo "FAIL: expected '$1' exactly once in SKILL.md, found $n" >&2; fail=1; }
}

check_in "§ Review" "$review" '**The severity mapping.**'
check_in "§ Review" "$review" 'A finding is high when it is a Codex `[high]` or a correctness `CONFIRMED`.'
check_in "§ Review" "$review" 'Codex medium and low, correctness `PLAUSIBLE`, and standards `hard` and `judgement` are not high'
check_in "§ Review" "$review" 'five outcomes: `fixed`, `disputed`, `filed`, `handed-back` and `leftover`'
check_in "§ Review" "$review" '`filed` is reserved for a high finding'
check_in "§ Review" "$review" 'A finding that is not high and not fixed in the round takes `leftover`'
check_in "§ Review sidecar" "$review" '{"id": "<id>", "outcome": "leftover", "file": "<path>", "title": "<short title>", "severity": "<the reviewer'"'"'s severity word>", "text": "<one line of the finding>"}'
check_once '**The severity mapping.**'
check_once 'A finding is high when'

# #1033: § Review points a no-run-file worker at § The PR for the filing
# itself, and defines "no run file" as dispatched directly, never through
# burndown's loop.
check_in "§ Review" "$review" 'a worker with **no'
check_in "§ Review" "$review" 'dispatched directly through `/implement`, never'
check_in "§ Review" "$review" "through \`burndown\`'s loop"

# #1033: § The PR states the per-PR sweep's title, its label, the
# zero-leftovers case, and the burn-controller fold.
check_in "§ The PR" "$the_pr" 'Sweep: leftovers from PR #<n>'
check_in "§ The PR" "$the_pr" 'labelled `ready-for-agent`'
check_in "§ The PR" "$the_pr" 'None: file nothing'
check_in "§ The PR" "$the_pr" 'folds it into its own'

# Codex gate finding 2 on PR #1094: a crash after /file-ticket here is the
# same recovery hazard #1030 already solved for the burn sweep — search by
# the deterministic title first, update on a hit, file only on a miss.
check_in "§ The PR" "$the_pr" 'check first, the same idempotent search'
check_in "§ The PR" "$the_pr" 'Sweep: leftovers from PR #<n> in:title'

[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
