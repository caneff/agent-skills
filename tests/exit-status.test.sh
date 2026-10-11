#!/usr/bin/env bash
# Regression test for #1524: when a suite exited non-zero, tests/all.sh printed
# `FAIL <label>` and the suite's output but never its exit status, so a suite
# that failed silently (drain's 2026-10-09 run: a bare `FAIL
# test-audit/audit-mjs.test.sh`) left nothing to diagnose.
#
# Each case builds a throwaway repo holding the working tree's tests/all.sh and
# one fixture suite from tests/fixtures/exit-status/, then reads the failure
# report. Every assertion is on a phrase that only the gate's note carries:
# the fixtures never print the words "status", "signal" or "no output", so a
# suite echoing them cannot satisfy a check (defect class 3,
# docs/agents/defect-classes.md).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
root=$PWD

fail() { echo "FAIL: $*"; exit 1; }

# Runs the gate over a one-suite repo (tests/gate-fixture.sh): prints the
# gate's output, returns its exit status, or 99 if the scratch repo could not
# be built.
. "$root/tests/gate-fixture.sh"
run_gate() { run_gate_fixture exit-status "$1"; }

gate_red() { # <fixture> -> sets $out, fails the test unless the gate exited 1
  out=$(run_gate "$1"); local rc=$?
  [ "$rc" = 99 ] && fail "could not build the scratch repo for $1"
  [ "$rc" = 1 ] || fail "gate exited $rc, not 1, on $1"$'\n'"$out"
  printf '%s\n' "$out" | grep -q '^FAIL tests/fixture.test.sh' \
    || fail "gate never named the suite ($1)"$'\n'"$out"
}

# A silent exit 3: the report names status 3 and says the output was empty.
gate_red silent-exit3
printf '%s\n' "$out" | grep -qE 'exited with status 3( |$|\()' \
  || fail "silent exit 3: the report never named the exit status"$'\n'"$out"
printf '%s\n' "$out" | grep -q 'printed no output' \
  || fail "silent exit 3: the report never said the output was empty"$'\n'"$out"
printf '%s\n' "$out" | grep -qi 'signal' \
  && fail "silent exit 3: the report named a signal for a plain exit"$'\n'"$out"

# An exit 255: no signal bears that number, so none is named (a plain exit code
# a suite chose, or ssh's, is not reported as a kill).
gate_red exit255
printf '%s\n' "$out" | grep -q 'exited with status 255' \
  || fail "exit 255: the report never named the exit status"$'\n'"$out"
printf '%s\n' "$out" | grep -qi 'signal' \
  && fail "exit 255: the report named a signal no signal bears"$'\n'"$out"

# A SIGKILL: status 137, the signal named, a kill told apart from an assertion.
gate_red killed
printf '%s\n' "$out" | grep -q 'exited with status 137, which reads as' \
  || fail "killed: the report never named status 137"$'\n'"$out"
printf '%s\n' "$out" | grep -qE 'signal 9 \(KILL\)' \
  || fail "killed: the report never named the signal"$'\n'"$out"
printf '%s\n' "$out" | grep -q 'printed no output' \
  || fail "killed: the report never said the output was empty"$'\n'"$out"

# A suite with output: the status is named, and it is not called output-less.
gate_red loud-exit1
printf '%s\n' "$out" | grep -q 'exited with status 1' \
  || fail "loud exit 1: the report never named the exit status"$'\n'"$out"
printf '%s\n' "$out" | grep -q 'assertion: expected 1, got 2' \
  || fail "loud exit 1: the suite's own output went missing"$'\n'"$out"
printf '%s\n' "$out" | grep -q 'printed no output' \
  && fail "loud exit 1: the report called an output-ful suite output-less"$'\n'"$out"

echo "ALL PASS"
