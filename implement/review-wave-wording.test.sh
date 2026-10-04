#!/usr/bin/env bash
# Guards #1401 (ADR 0004, ADR 0005): implement/SKILL.md § Review is one wave
# and one fix round with three dispositions, the worker writes them, and the
# first ablation (the standards axis off on a small PR) names its gate, its
# ledger record and its decision rule. The leftover outcome, the size bar, the
# verification pass and the per-PR sweep are gone from the whole skill.
# Prose assertion — no harness runs the skill's own prose; the mechanical
# check the prose points at is tested in fix_check_test.py, and the fixture
# the sidecar forms are bound to in dispositions_fixture_test.py.
# Resolving via BASH_SOURCE sidesteps a caller's leaked GIT_DIR (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

grep -qx '### Review' "$skill" && grep -qx '#### The Codex pass' "$skill" ||
  { echo "FAIL: a § Review heading the slice needs was renamed" >&2; exit 1; }
review="$(sed -n '/^### Review$/,/^#### The Codex pass$/p' "$skill" | flatten)"
whole="$(flatten <"$skill")"
[ -n "$review" ] || { echo "FAIL: could not extract § Review" >&2; exit 1; }

fail=0
check_in() { case "$1" in *"$2"*) ;; *) echo "FAIL: implement/SKILL.md $3 is missing: $2" >&2; fail=1 ;; esac; }
check_absent() { case "$1" in *"$2"*) echo "FAIL: implement/SKILL.md still has: $2" >&2; fail=1 ;; *) ;; esac; }

# One wave, one fix round, the seam as the convergence check.
check_in "$review" 'One review wave, one fix round, then the seam' '§ Review'
check_in "$review" 'There is no re-review: the seam is the convergence check.' '§ Review'
check_in "$review" 'run `bash tests/all.sh`' '§ Review'

# Three outcomes, no size bar.
check_in "$review" 'exactly one disposition, one of three outcomes' '§ Review'
check_in "$review" 'No size bar, no "adjacent" test, no leftover' '§ Review'
check_in "$review" '{"id": "<id>", "outcome": "fixed", "sha": "<sha>"}' '§ Review'
check_in "$review" '{"id": "<id>", "outcome": "moved", "ticket": <n>}' '§ Review'
check_in "$review" '{"id": "<id>", "outcome": "disputed", "reason": "<why>"}' '§ Review'
check_in "$review" 'it goes onto the open ticket for its component' '§ Review'
check_in "$review" 'the disposition names that ticket' '§ Review'
check_in "$review" 'Write the file even when every reviewer found nothing' '§ Review'
check_in "$review" 'You write' '§ Review'

# The first ablation: its gate, its record, its rule.
check_in "$review" '**The first ablation** (#1401, ADR 0005)' '§ Review'
check_in "$review" 'codex-usage-gate.py --size --base origin/<default> --tickets <n>...' '§ Review'
check_in "$review" 'an unmeasured PR is not a small one' '§ Review'
check_in "$review" '--type standards --skip-reason ablation' '§ Review'
check_in "$review" 'keep the standards axis on small PRs if the ledger'"'"'s escape measure attributes any escape to a skipped run' '§ Review'
check_in "$review" 'The ablation runs for three burns' '§ Review'

# Gone from the whole skill.
for gone in '`leftover` outcome' 'adjacent-fix rule' 'verification pass' 'per-PR sweep' 'sweep ticket' 'handed-back' '`filed`' 'blocking kinds' 'severity mapping'; do
  check_absent "$whole" "$gone"
done
# The PR body keeps its last-reviewed-sha section, now naming the wave's commit.
check_in "$whole" '**Last reviewed sha** — the commit the wave read' '§ The PR'

[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
