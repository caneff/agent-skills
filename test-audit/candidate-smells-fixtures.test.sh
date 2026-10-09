#!/usr/bin/env bash
# Pins what both pass-one scanners report on the candidate-smell fixtures
# (#1489): private-API access, a stub that is also asserted called, and a
# vacuous loop assertion, each beside its nearest negatives, which must stay
# unreported. Line numbers are the fixtures' own, so edit a fixture and this
# file together.
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

py=fixtures/test_candidate_smells.py
check "audit.py on $py" "$py:10: private-API access
$py:32: private-API access
$py:57: stub asserted called
$py:65: stub asserted called
$py:91: vacuous loop assertion" "$(python3 audit.py "$py" 2>/dev/null | sort -t: -k2,2n)"

ts=fixtures/vitest_candidate_smells.test.ts
check "audit.mjs on $ts" "$ts:20: private-API access
$ts:25: private-API access
$ts:31: private-API access
$ts:49: stub asserted called
$ts:55: stub asserted called
$ts:77: vacuous loop assertion
$ts:84: vacuous loop assertion" "$(node audit.mjs "$ts" 2>/dev/null | sort -t: -k2,2n)"

# All three are report-only: a copy of each fixture outside fixtures/ must pass
# the gate, which fails only on an assertion-free or duplicate-named test.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/.git"
cp "$py" "$tmp/test_candidates.py"
cp "$ts" "$tmp/candidates.test.ts"
python3 audit.py --gate "$tmp" >/dev/null 2>&1 || { echo "FAIL audit.py --gate gated a report-only smell" >&2; fail=1; }
node audit.mjs --gate "$tmp" >/dev/null 2>&1 || { echo "FAIL audit.mjs --gate gated a report-only smell" >&2; fail=1; }

[ "$fail" -eq 0 ] && echo ok
exit "$fail"
