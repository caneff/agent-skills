#!/usr/bin/env bash
# Test for #1415: `tests/all.sh --changed <base>` keeps the suites under the
# directories the diff touches plus `tests/`, widens to everything for a diff it
# cannot pin to a directory with suites, and the runner runs suites
# concurrently, reports them in order, marks `all.sh: serial` suites to run
# alone, and prints a failing suite's output in full. Every case runs the real
# tests/all.sh in a shadow repo of fake suites, so nothing here reads this one.
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
# The cases set these themselves; a caller's value would change what the inner
# tests/all.sh runs do.
unset TESTS_JOBS TESTS_CPU_BUDGET
root=$(git rev-parse --show-toplevel) || exit 1
shadow=$(mktemp -d) || { echo "FAIL: mktemp -d"; exit 1; }
trap 'rm -rf "$shadow"' EXIT
fail=0
check() { # <name> <0|1 condition status>
  if [ "$2" = 0 ]; then echo "ok   $1"; else echo "  FAIL $1"; fail=1; fi
}
has() { grep -qxF "$1" <<<"$out"; }
has_pass() { grep -qE "^PASS $1 \(" <<<"$out"; } # a PASS line ends in the suite's CPU time

# A fresh shadow: suites a/ and b/ (one each), tests/ (one), c/ with no suite.
# `base` is the commit before any case's change.
fresh() {
  rm -rf "$shadow/repo"; mkdir -p "$shadow/repo/tests" "$shadow/repo/a" "$shadow/repo/b" "$shadow/repo/c"
  cp "$root/tests/all.sh" "$shadow/repo/tests/all.sh"
  for f in a/a.test.sh b/b.test.sh tests/t.test.sh; do printf '#!/usr/bin/env bash\nexit 0\n' >"$shadow/repo/$f"; done
  echo c >"$shadow/repo/c/note.md"; echo r >"$shadow/repo/README.md"
  git -C "$shadow/repo" init -q
  git -C "$shadow/repo" config user.email owner@example.org
  git -C "$shadow/repo" config user.name owner
  git -C "$shadow/repo" add -A
  git -C "$shadow/repo" commit -qm base
  base=$(git -C "$shadow/repo" rev-parse HEAD)
}
change() { # <path>: commit a change to <path>
  mkdir -p "$(dirname "$shadow/repo/$1")"; echo "$RANDOM" >>"$shadow/repo/$1"
  git -C "$shadow/repo" add -A; git -C "$shadow/repo" commit -qm change
}
list() { out=$(cd "$shadow/repo" && bash tests/all.sh --list --changed "$base" 2>&1); rc=$?; }

fresh; change a/x.txt; list
check "a diff inside one directory lists that directory's suites" "$(has a/a.test.sh; echo $?)"
check "...and the repo-wide checks under tests/" "$(has tests/t.test.sh; echo $?)"
check "...and not another directory's suites" "$(has b/b.test.sh; echo $((1 - $?)))"

fresh; change a/x.txt; change b/y.txt; list
check "a diff in two directories lists both" "$(has a/a.test.sh && has b/b.test.sh; echo $?)"

fresh; change tests/all.sh; list
check "a diff touching tests/all.sh lists everything" "$(has a/a.test.sh && has b/b.test.sh && has tests/t.test.sh; echo $?)"

fresh; change README.md; list
check "a root file no suite directory owns lists everything" "$(has a/a.test.sh && has b/b.test.sh; echo $?)"

fresh; change c/note.md; list
check "a directory with no suites lists everything" "$(has a/a.test.sh && has b/b.test.sh; echo $?)"

fresh; list
check "an empty diff lists only the repo-wide checks" "$(has tests/t.test.sh && ! has a/a.test.sh; echo $?)"

fresh; change a/x.txt
out=$(cd "$shadow/repo" && bash tests/all.sh --list --changed no-such-ref 2>&1); rc=$?
check "an unreadable base exits 2 instead of selecting nothing" "$([ "$rc" = 2 ]; echo $?)"
out=$(cd "$shadow/repo" && bash tests/all.sh --changed no-such-ref 2>&1); rc=$?
check "...on a run too, which must not report 0 suites and exit 0" "$([ "$rc" = 2 ] && ! grep -q 'suites passed' <<<"$out"; echo $?)"

fresh; change a/x.txt
out=$(cd "$shadow/repo" && bash tests/all.sh --changed "$base" 2>&1); rc=$?
check "a --changed run passes and runs the narrowed set" "$([ "$rc" = 0 ] && has_pass a/a.test.sh && has_pass tests/t.test.sh && ! has_pass b/b.test.sh; echo $?)"
check "...and says which scope it chose" "$(has 'changed suites: a + tests'; echo $?)"

# Concurrency: two suites that each wait for the other's marker finish only if
# they run at the same time. The same pair under one job is the control that
# shows the fixture can fail.
rendezvous() { # <file> <my marker> <their marker>
  cat >"$1" <<FIXTURE
#!/usr/bin/env bash
# a mid-line mention of all.sh: serial must not make this suite serial
touch "$shadow/$2"
for _ in \$(seq 30); do [ -e "$shadow/$3" ] && exit 0; sleep 0.1; done
echo never-met
exit 1
FIXTURE
}
fresh; rendezvous "$shadow/repo/a/a.test.sh" mine theirs; rendezvous "$shadow/repo/b/b.test.sh" theirs mine
out=$(cd "$shadow/repo" && TESTS_JOBS=4 bash tests/all.sh 2>&1); rc=$?
check "two suites that need each other pass only because they ran concurrently" "$([ "$rc" = 0 ]; echo $?)"
rm -f "$shadow/mine" "$shadow/theirs"
out=$(cd "$shadow/repo" && TESTS_JOBS=1 bash tests/all.sh 2>&1); rc=$?
check "...and the same pair fails under one job (the fixture can go red)" "$([ "$rc" = 1 ] && has never-met; echo $?)"
rm -f "$shadow/mine" "$shadow/theirs"

# A serial suite never overlaps the concurrent ones.
fresh
printf '#!/usr/bin/env bash\ntouch "%s/busy"; sleep 1; rm -f "%s/busy"\n' "$shadow" "$shadow" >"$shadow/repo/a/a.test.sh"
printf '#!/usr/bin/env bash\n# all.sh: serial (test fixture)\n[ ! -e "%s/busy" ] || { echo overlapped; exit 1; }\n' "$shadow" >"$shadow/repo/b/b.test.sh"
out=$(cd "$shadow/repo" && TESTS_JOBS=4 bash tests/all.sh 2>&1); rc=$?
check "an 'all.sh: serial' suite runs alone after the concurrent ones" "$([ "$rc" = 0 ]; echo $?)"

# A failing suite stops new suites from starting.
fresh
printf '#!/usr/bin/env bash\nexit 1\n' >"$shadow/repo/a/a.test.sh"
printf '#!/usr/bin/env bash\ntouch "%s/later-ran"\n' "$shadow" >"$shadow/repo/b/b.test.sh"
rm -f "$shadow/later-ran"
out=$(cd "$shadow/repo" && TESTS_JOBS=1 bash tests/all.sh 2>&1); rc=$?
check "a failing suite stops the suites after it from starting" "$([ "$rc" = 1 ] && [ ! -e "$shadow/later-ran" ]; echo $?)"

# A failure prints that suite's output in full, in discovery order.
fresh
printf '#!/usr/bin/env bash\necho line-one; echo line-two; exit 1\n' >"$shadow/repo/a/a.test.sh"
out=$(cd "$shadow/repo" && bash tests/all.sh 2>&1); rc=$?
check "a failing suite fails the run and prints all of its output" "$([ "$rc" = 1 ] && has 'FAIL a/a.test.sh' && has line-one && has line-two; echo $?)"

# The CPU budget: a suite that burns CPU past it fails the run, naming both
# numbers. The burner counts its own process CPU time (a wall-clock loop would
# measure whatever the box gives it). `TESTS_CPU_BUDGET` only lowers a budget.
fresh
cat >"$shadow/repo/a/a.test.sh" <<'FIXTURE'
#!/usr/bin/env bash
python3 - <<'PY'
import time
t = time.process_time()
while time.process_time() - t < 2:
    pass
PY
FIXTURE
out=$(cd "$shadow/repo" && TESTS_CPU_BUDGET=1 bash tests/all.sh 2>&1); rc=$?
check "a suite over its CPU budget fails the run" "$([ "$rc" = 1 ] && has 'FAIL a/a.test.sh'; echo $?)"
check "...naming its CPU time and its budget" "$(grep -qE 'over its CPU budget: [0-9.]+s CPU against 1s' <<<"$out"; echo $?)"
out=$(cd "$shadow/repo" && bash tests/all.sh 2>&1); rc=$?
check "the same suite within the default budget passes, its CPU time on the PASS line" "$([ "$rc" = 0 ] && has_pass a/a.test.sh; echo $?)"

exit $fail
