#!/usr/bin/env bash
# Guards #1027: a finding that is neither fixed nor high takes the fifth
# sidecar outcome, `leftover`, instead of a ticket of its own; `filed` is
# reserved for high findings; and implement/SKILL.md § Review states the one
# severity mapping the three reviewer vocabularies share, once, where the
# reviewer briefs point. Prose assertion over SKILL.md; the sidecar forms are
# checked against the fixture by dispositions_fixture_test.py.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '### Review' '### Before the PR'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
review="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
whole="$(flatten <"$skill")"
[ -n "$review" ] || { echo "FAIL: could not extract § Review" >&2; exit 1; }

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
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
