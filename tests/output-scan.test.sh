#!/usr/bin/env bash
# Regression test for #954: tests/all.sh judged every suite by exit status
# alone, captured its output into `out` and threw it away on success. A suite
# that printed real failures and exited 0 was counted PASS and its output was
# never shown — defect class 1 in docs/agents/defect-classes.md, sitting in the
# harness whose whole job is to answer "is this tree good".
#
# Both directions are witnessed here, because either one alone is a test that
# passes for a reason other than the one it claims (class 3 in the same doc):
# a suite that prints a failure line and exits 0 must fail the gate, and a
# suite that prints the same words while narrating an expected-red mutation
# check must not.
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
# exit status.
run_gate() { # <fixture name>
  local scratch
  scratch=$(mktemp -d) || return 99
  mkdir -p "$scratch/tests"
  cp "$root/tests/all.sh" "$scratch/tests/all.sh"
  cp "$root/tests/fixtures/output-scan/$1.sh" "$scratch/tests/fixture.test.sh"
  git -C "$scratch" init -q && git -C "$scratch" add -A || return 99
  ( cd "$scratch" && bash tests/all.sh 2>&1 )
  local rc=$?
  rm -rf "$scratch"
  return $rc
}

out=$(run_gate silent-failure); rc=$?
[ "$rc" = 99 ] && fail "could not build the scratch repo for silent-failure"
if [ "$rc" = 0 ]; then
  fail "gate passed a suite that printed a failure line and exited 0"$'\n'"$out"
fi
printf '%s\n' "$out" | grep -q 'tests/fixture.test.sh' \
  || fail "gate failed but never named the offending suite"$'\n'"$out"
printf '%s\n' "$out" | grep -q 'FAIL: config/app.yaml declares a port' \
  || fail "gate failed but never showed the line that matched"$'\n'"$out"

out=$(run_gate expected-red-narration); rc=$?
[ "$rc" = 99 ] && fail "could not build the scratch repo for expected-red-narration"
if [ "$rc" != 0 ]; then
  fail "gate rejected a passing suite for narrating an expected-red check"$'\n'"$out"
fi
printf '%s\n' "$out" | grep -q '^PASS tests/fixture.test.sh$' \
  || fail "gate exited 0 but did not report the narrating suite as PASS"$'\n'"$out"

echo "ALL PASS"
