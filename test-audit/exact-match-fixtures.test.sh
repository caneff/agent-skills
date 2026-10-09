#!/usr/bin/env bash
# Pins what both pass-one scanners report on the exact-match-smell fixtures
# (#1488): the four pytest smells, the two vitest ones, and the near-miss
# negatives beside each, which must stay unreported. Line numbers are the
# fixtures' own, so edit a fixture and this file together.
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
[ -d node_modules ] || npm ci --silent

fail=0
check() { # <label> <expected> <actual>
  if [ "$2" != "$3" ]; then
    printf 'FAIL %s\n--- expected\n%s\n--- actual\n%s\n' "$1" "$2" "$3" >&2
    fail=1
  fi
}

py=fixtures/test_exact_match_smells.py
check "audit.py on $py" "$py:13: dead assertion in an expect-exception block
$py:28: lost test (duplicate name)
$py:36: lost test (uncollected class)
$py:52: broad exception expectation
$py:66: non-strict xfail" "$(python3 audit.py "$py" 2>/dev/null | sort -t: -k2,2n)"

js=fixtures/vitest_exact_match_smells.test.js
check "audit.mjs on $js" "$js:13: lost test (duplicate name)
$js:29: broad exception expectation" "$(node audit.mjs "$js" 2>/dev/null | sort -t: -k2,2n)"

# Both scanners gate on the duplicate-name case and nothing else new. A copy of
# each fixture outside fixtures/ must fail the gate on that one finding.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/.git"
cp "$py" "$tmp/test_exact.py"
cp "$js" "$tmp/exact.test.js"
check "audit.py --gate" "$tmp/test_exact.py:28: lost test (duplicate name)" \
  "$(python3 audit.py --gate "$tmp" 2>/dev/null || true)"
check "audit.mjs --gate" "$tmp/exact.test.js:13: lost test (duplicate name)" \
  "$(node audit.mjs --gate "$tmp" 2>/dev/null || true)"
python3 audit.py --gate "$tmp" >/dev/null 2>&1 && { echo "FAIL audit.py --gate exited 0" >&2; fail=1; }
node audit.mjs --gate "$tmp" >/dev/null 2>&1 && { echo "FAIL audit.mjs --gate exited 0" >&2; fail=1; }

# ...while the fixtures directory itself stays exempt, and says what it hid.
python3 audit.py --gate fixtures >/dev/null 2>"$tmp/py.err" || { echo "FAIL audit.py --gate fixtures failed" >&2; fail=1; }
grep -q '1 duplicate-name finding(s) suppressed under fixtures/' "$tmp/py.err" ||
  { echo "FAIL audit.py gate hid a fixtures duplicate without saying so" >&2; fail=1; }
node audit.mjs --gate fixtures >/dev/null 2>"$tmp/js.err" || { echo "FAIL audit.mjs --gate fixtures failed" >&2; fail=1; }
grep -q '1 duplicate-name finding(s) suppressed under fixtures/' "$tmp/js.err" ||
  { echo "FAIL audit.mjs gate hid a fixtures duplicate without saying so" >&2; fail=1; }

[ "$fail" -eq 0 ] && echo ok
exit "$fail"
