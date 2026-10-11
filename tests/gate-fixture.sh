# Sourced by the suites that run tests/all.sh over one fixture suite.
# run_gate_fixture <fixtures dir under tests/fixtures> <fixture name>: builds a
# throwaway repo holding the working tree's tests/all.sh (not HEAD's, so an
# uncommitted fix is what gets tested) and the fixture as its only suite, runs
# the gate there and prints its output. Returns the gate's exit status, or 99
# if the scratch repo could not be built. Every setup step is checked: an
# unbuilt scratch repo yields a gate run over no suites at all, which exits 0
# and would surface as the wrong failure — the same "absent answer read as a
# benign one" these suites exist to catch. One cleanup path, so a setup failure
# does not leak the temp directory either. The caller's cwd is inside the repo.
run_gate_fixture() {
  local root scratch rc
  root=$(git rev-parse --show-toplevel) || return 99
  scratch=$(mktemp -d) || return 99
  rc=99
  if mkdir -p "$scratch/tests" \
    && cp "$root/tests/all.sh" "$scratch/tests/all.sh" \
    && cp "$root/tests/fixtures/$1/$2.sh" "$scratch/tests/fixture.test.sh" \
    && git -C "$scratch" init -q \
    && git -C "$scratch" add -A; then
    ( cd "$scratch" && bash tests/all.sh 2>&1 )
    rc=$?
  fi
  rm -rf "$scratch"
  return $rc
}
