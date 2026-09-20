#!/usr/bin/env bash
# Regression test for #954: tests/all.sh judged every suite by exit status
# alone, so a suite that printed real failures and exited 0 was counted PASS
# and its captured output was thrown away unread. Why that set of signature
# words, anchored where it is: the block above `failure_signature` in
# tests/all.sh.
#
# Every word in the set is witnessed in both directions, because one direction
# alone is a test that passes for a reason other than the one it claims
# (defect class 3, docs/agents/defect-classes.md). One positive fixture per
# word, never one fixture printing all three: the gate greps with `-m1`, so a
# combined fixture would keep matching on the first word and deleting either
# of the others from the set would go unnoticed.
#
# Each case builds a throwaway repo holding the working tree's tests/all.sh
# (not HEAD's, so an uncommitted fix is what gets tested) and one fixture
# suite, then runs the gate there. The fixtures live under
# tests/fixtures/output-scan/ named `*.sh`, never `*.test.sh`: this repo's own
# gate discovers suites by glob over tracked files, and a fixture that means to
# fail would be discovered and run for real.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
root=$PWD

fail() { echo "FAIL: $*"; exit 1; }

# Runs the gate over a one-suite repo. Prints the gate's output; returns its
# exit status, or 99 if the scratch repo could not be built. Every setup step
# is checked: an unbuilt scratch repo yields a gate run over no suites at all,
# which exits 0 and would surface as the wrong failure — the same "absent
# answer read as a benign one" this suite exists to catch. One cleanup path,
# so a setup failure does not leak the temp directory either.
run_gate() { # <fixture name>
  local scratch rc
  scratch=$(mktemp -d) || return 99
  rc=99
  if mkdir -p "$scratch/tests" \
    && cp "$root/tests/all.sh" "$scratch/tests/all.sh" \
    && cp "$root/tests/fixtures/output-scan/$1.sh" "$scratch/tests/fixture.test.sh" \
    && git -C "$scratch" init -q \
    && git -C "$scratch" add -A; then
    ( cd "$scratch" && bash tests/all.sh 2>&1 )
    rc=$?
  fi
  rm -rf "$scratch"
  return $rc
}

# Direction 1: a column-0 signature word with exit 0 must fail the gate, which
# must name both the suite and the line that matched.
#
# The third column is whether the report must also carry the logging remedy.
# It is checked in both directions on purpose: asserting only that the remedy
# appears for the logging case would pass just as well if the gate printed it
# on every failure, and an unconditional remedy points away from a real
# failure on a genuine `FAIL:` catch. `remedy_marker` is a phrase from the
# note alone — no fixture prints it — so the assertion cannot be satisfied by
# the suite's own output being echoed back.
remedy_marker='looks like a logging record'

while IFS='|' read -r fixture signature remedy; do
  out=$(run_gate "$fixture"); rc=$?
  [ "$rc" = 99 ] && fail "could not build the scratch repo for $fixture"
  if [ "$rc" = 0 ]; then
    fail "gate passed a suite that printed a failure line and exited 0 ($fixture)"$'\n'"$out"
  fi
  printf '%s\n' "$out" | grep -q 'tests/fixture.test.sh' \
    || fail "gate failed but never named the offending suite ($fixture)"$'\n'"$out"
  printf '%s\n' "$out" | grep -q "$signature" \
    || fail "gate failed but never showed the line that matched ($fixture)"$'\n'"$out"
  if [ "$remedy" = yes ]; then
    printf '%s\n' "$out" | grep -q "$remedy_marker" \
      || fail "gate failed on a logging-shaped line without naming the way out ($fixture)"$'\n'"$out"
  else
    printf '%s\n' "$out" | grep -q "$remedy_marker" \
      && fail "gate offered the logging remedy on a line that is not a logging record ($fixture)"$'\n'"$out"
  fi
done <<'CASES'
silent-failure|FAIL: config/app.yaml declares a port|no
silent-traceback|Traceback (most recent call last):|no
silent-error|ERROR:root:manifest checksum did not match|yes
CASES

# Direction 2: the same three words, mid-line where a quoted child failure
# lands, must leave a passing suite passing. Only the column-0 anchor
# separates this case from the three above.
out=$(run_gate expected-red-narration); rc=$?
[ "$rc" = 99 ] && fail "could not build the scratch repo for expected-red-narration"
if [ "$rc" != 0 ]; then
  fail "gate rejected a passing suite for narrating an expected-red check"$'\n'"$out"
fi
printf '%s\n' "$out" | grep -q '^PASS tests/fixture.test.sh$' \
  || fail "gate exited 0 but did not report the narrating suite as PASS"$'\n'"$out"

echo "ALL PASS"
