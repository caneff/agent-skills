#!/usr/bin/env bash
# Guards the discovery rules in tests/all.sh: every suite below is found by
# one of the three rules, not by a name the runner special-cases. Asserts on
# `all.sh --list` rather than a full run — the list IS the seam (#609).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

listed=$(bash tests/all.sh --list) || { echo "FAIL: all.sh --list exited non-zero"; exit 1; }

fail=0
for label in \
  "test-audit/audit-mjs.test.sh" \
  "skills-sync/skills-sync.test.sh" \
  "flow/ccstatusline-table/statusline.test.sh" \
  "all-audits/driver_test.py" \
  "crap-audit/audit_test.py" \
  "mutation-audit/audit.py --selfcheck"
do
  grep -qxF "$label" <<<"$listed" || { echo "FAIL: $label not discovered"; fail=1; }
done

bash tests/all.sh --bogus >/dev/null 2>&1; [ $? = 2 ] || { echo "FAIL: unknown flag did not exit 2"; fail=1; }

[ "$fail" = 0 ] || { echo "--- discovered ---"; printf '%s\n' "$listed"; exit 1; }
echo "ok"
