#!/usr/bin/env bash
# Guards #1204: both places that start a Codex run — § The merge step 3 in
# SKILL.md and the Codex lane's preflight — run codex-usage-gate.py and say
# what each exit status means. A prose assertion: nothing runs the skill's
# own prose. The script's behavior is tested in codex_usage_gate_test.py.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0
check_in() { # <file> <needle> — fixed-string, case-insensitive
  grep -qiF -- "$2" "$1" || { echo "FAIL $(basename "$1"): missing: $2"; fail=1; }
}
for f in "$here/SKILL.md" "$here/codex-lane.md"; do
  check_in "$f" 'codex-usage-gate.py'
  check_in "$f" 'exit 10 (at or above 80%)'
  check_in "$f" 'exit 20 (capped)'
  check_in "$f" 'exit 30 (no fresh'
done
check_in "$here/SKILL.md" 'no refused duration row'
check_in "$here/SKILL.md" 'comment `Codex pass skipped: <why>` on the PR'
[ -x "$here/codex-usage-gate.py" ] || { echo "FAIL codex-usage-gate.py is not executable"; fail=1; }
[ "$fail" -eq 0 ] && echo ok
exit "$fail"
