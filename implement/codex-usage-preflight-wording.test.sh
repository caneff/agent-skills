#!/usr/bin/env bash
# Guards #1204: both places that start a Codex run — § The Codex pass in
# SKILL.md and the Codex lane's preflight — run codex-usage-gate.py and say
# what each exit status means. A prose assertion: nothing runs the skill's
# own prose. #1358 adds the size skip (exit 40) and its forcing label, which
# the triage-labels doc names. The script's behavior is tested in
# codex_usage_gate_test.py. #1359 replaces the 80% warn (exit 10) with the
# 70% reserve ceiling, an exit 20 with its own skip reason.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0
check_in() { # <file> <needle> — fixed-string, case-insensitive
  grep -qiF -- "$2" "$1" || { echo "FAIL $(basename "$1"): missing: $2"; fail=1; }
}
# The ceiling and size threshold the prose quotes are the gate's own constants, so a retune that
# leaves the prose behind goes red here.
ceiling=$(sed -n 's/^RESERVE_PERCENT = \([0-9][0-9]*\)$/\1/p' "$here/codex-usage-gate.py")
[ -n "$ceiling" ] || { echo "FAIL codex-usage-gate.py: no RESERVE_PERCENT"; fail=1; }
threshold=$(sed -n 's/^SIZE_THRESHOLD = \([0-9][0-9]*\)$/\1/p' "$here/codex-usage-gate.py")
[ -n "$threshold" ] || { echo "FAIL codex-usage-gate.py: no SIZE_THRESHOLD"; fail=1; }
check_not_in() { # <file> <needle> — fixed-string, case-insensitive
  ! grep -qiF -- "$2" "$1" || { echo "FAIL $(basename "$1"): still says: $2"; fail=1; }
}
for f in "$here/SKILL.md" "$here/codex-lane.md"; do
  check_in "$f" 'codex-usage-gate.py'
  check_not_in "$f" 'exit 10'
  check_not_in "$f" 'at or above 80%'
  check_in "$f" 'reserve ceiling'
  check_in "$f" 'exit 20 (capped)'
  check_in "$f" 'exit 30 (no fresh'
done
check_in "$here/SKILL.md" 'name the printed line in the PR body'
check_in "$here/SKILL.md" 'launch nothing'
check_in "$here/SKILL.md" 'An unreadable cache is exit 30'
check_in "$here/SKILL.md" 'no `codex@openai-codex` entry'
check_in "$here/SKILL.md" '--base origin/<default> --tickets <n>...'
check_in "$here/SKILL.md" 'Exit 40 (under the size threshold)'
check_in "$here/SKILL.md" "\`Codex pass skipped: under size threshold (<churn> < ${threshold})\` in the PR body"
check_in "$here/SKILL.md" "churn is under ${threshold} lines"
check_in "$here/SKILL.md" '`--skip-reason size`'
check_in "$here/SKILL.md" '`needs-codex` label'
check_in "$here/SKILL.md" "the reserve ceiling, ${ceiling}%"
check_in "$here/codex-lane.md" "the ${ceiling}% reserve ceiling"
check_in "$here/codex-audit.md" "the reserve above ${ceiling} %"
check_in "$here/SKILL.md" '`--skip-reason ceiling`'
check_in "$here/../docs/agents/triage-labels.md" 'reserve ceiling'
check_in "$here/../docs/agents/triage-labels.md" '`needs-codex`'
check_in "$here/codex-lane.md" 'before the build and again before each review'
check_in "$here/codex-lane.md" 'start no Codex run'
check_in "$here/codex-lane.md" 'never headroom'
[ -x "$here/codex-usage-gate.py" ] || { echo "FAIL codex-usage-gate.py is not executable"; fail=1; }
[ "$fail" -eq 0 ] && echo ok
exit "$fail"
