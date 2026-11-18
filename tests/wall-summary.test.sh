#!/usr/bin/env bash
# #1958: tests/all.sh prints wall seconds per suite (slowest first) and a total,
# and appends one summary record per run (fields: tests/run_summary.py). Each
# case builds a throwaway repo holding the working tree's tests/all.sh and a few
# fixture suites, so an uncommitted change is what gets tested.
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
unset TESTS_JOBS TESTS_CPU_BUDGET TESTS_RUN_KEEP
root=$(git rev-parse --show-toplevel) || exit 1
scratch=$(mktemp -d) || exit 1
trap 'rm -rf "$scratch"' EXIT
fail=0
check() { if [ "$2" = 0 ]; then echo "ok   $1"; else echo "  FAIL $1"; fail=1; fi; }

repo=$scratch/repo; runs=$scratch/runs
mkdir -p "$repo/tests" "$runs"
cp "$root/tests/all.sh" "$repo/tests/all.sh"
printf '#!/usr/bin/env bash\nsleep 1\n' >"$repo/tests/a-slow.test.sh"
printf '#!/usr/bin/env bash\nexit 0\n' >"$repo/tests/z-fast.test.sh"
. "$root/tests/fixture-identity.sh"
git -C "$repo" init -q && git -C "$repo" add -A && fixture_identity "$repo" "$scratch" \
  && git -C "$repo" commit -q -m fixture || { echo "FAIL: scratch repo"; exit 1; }
export TESTS_RUN_DIR=$runs

run() { (cd "$repo" && bash tests/all.sh "$@" 2>&1); }
field() { python3 -c 'import json,sys; r=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]; v=eval(sys.argv[2]); print(" ".join(map(str,v)) if isinstance(v,tuple) else v)' "$runs/runs.jsonl" "$1"; }

out=$(run); rc=$?
check "a full run passes" "$rc"
slow_line=$(grep -n 's wall.*tests/a-slow.test.sh\|tests/a-slow.test.sh.*s wall' <<<"$out" | head -1 | cut -d: -f1)
fast_line=$(grep -n 's wall.*tests/z-fast.test.sh\|tests/z-fast.test.sh.*s wall' <<<"$out" | head -1 | cut -d: -f1)
check "wall seconds are printed per suite, slowest first" "$([ -n "$slow_line" ] && [ -n "$fast_line" ] && [ "$slow_line" -lt "$fast_line" ]; echo $?)"
check "the verdict line stays last, after the wall table" "$([ "$(tail -1 <<<"$out")" = "2 suites passed" ]; echo $?)"
check "a total wall line is printed" "$(grep -qE '^total wall: [0-9.]+s' <<<"$out"; echo $?)"
check "PASS lines keep their shape" "$(grep -qE '^PASS tests/z-fast.test.sh \([0-9.]+s cpu\)$' <<<"$out"; echo $?)"
check "one record: pass, full, 2 selected" "$([ "$(field 'len(r), r[-1]["status"], r[-1]["mode"], r[-1]["selected"]')" = "1 pass full 2" ]; echo $?)"
check "the record carries the 1-minute load and per-suite wall and cpu" "$([ "$(field 'type(r[-1]["load1"]).__name__, sorted(r[-1]["suites"][0])')" = "float ['cpu', 'label', 'verdict', 'wall']" ]; echo $?)"

out=$(run --changed HEAD); rc=$?
check "a narrowed run passes" "$rc"
check "its record says narrowed and how many suites it selected" "$([ "$(field 'r[-1]["mode"], r[-1]["selected"]')" = "narrowed 2" ]; echo $?)"

TESTS_RUN_KEEP=2 run >/dev/null; TESTS_RUN_KEEP=2 run >/dev/null
check "only the last N records are kept" "$([ "$(field 'len(r)')" = 2 ]; echo $?)"

printf '#!/usr/bin/env bash\necho "FAIL: broken"\nexit 1\n' >"$repo/tests/bad.test.sh"
git -C "$repo" add -A
out=$(run); rc=$?
check "a failing run fails" "$([ "$rc" != 0 ]; echo $?)"
check "its record is fail and names the failing suite" "$([ "$(field 'r[-1]["status"], [s["label"] for s in r[-1]["suites"] if s["verdict"]=="fail"]')" = "fail ['tests/bad.test.sh']" ]; echo $?)"
check "on a failure the wall table comes before the FAIL report" "$([ "$(grep -n '^total wall' <<<"$out" | cut -d: -f1)" -lt "$(grep -n '^FAIL tests/bad' <<<"$out" | cut -d: -f1)" ]; echo $?)"
git -C "$repo" rm -qf tests/bad.test.sh

# A gate exit before any suite ran still leaves a fail record (#1958 "fails part-way").
TESTS_JOBS=x run >/dev/null; rc=$?
check "a bad TESTS_JOBS exits 2" "$([ "$rc" = 2 ]; echo $?)"
check "...and leaves a fail record, not nothing" "$([ "$(field 'r[-1]["status"], r[-1]["suites"]')" = "fail []" ]; echo $?)"
TESTS_RUN_KEEP=zero run >/dev/null; rc=$?
check "a malformed TESTS_RUN_KEEP is refused, not defaulted" "$([ "$rc" = 2 ]; echo $?)"

# A damaged line in the file never stops recording.
printf '{broken\n' >>"$runs/runs.jsonl"
run >/dev/null
check "a damaged line is skipped and the next record still lands" "$([ "$(field 'r[-1]["status"]')" = pass ] && ! grep -q '{broken' "$runs/runs.jsonl"; echo $?)"

# Suites the run starts get a scratch TESTS_RUN_DIR (C5): a nested all.sh must not write here.
printf '#!/usr/bin/env bash\nprintf "%%s" "$TESTS_RUN_DIR" >"$0.seen"\n' >"$repo/tests/env.test.sh"
git -C "$repo" add -A; run >/dev/null
seen=$(cat "$repo/tests/env.test.sh.seen" 2>/dev/null)
check "a suite sees a TESTS_RUN_DIR other than the real one" "$([ -n "$seen" ] && [ "$seen" != "$runs" ]; echo $?)"
rm -f "$repo/tests/env.test.sh.seen"; git -C "$repo" rm -qf tests/env.test.sh

# Default directory: used only where the reader sits beside the script.
home=$scratch/home; mkdir -p "$home"
( cd "$repo" && unset TESTS_RUN_DIR && HOME=$home bash tests/all.sh >/dev/null 2>&1 )
check "no reader beside the script: nothing is written under HOME" "$([ ! -e "$home/.cache/test-runs" ]; echo $?)"
cp "$root/tests/run_summary.py" "$repo/tests/run_summary.py"; git -C "$repo" add -A
( cd "$repo" && unset TESTS_RUN_DIR && HOME=$home bash tests/all.sh >/dev/null 2>&1 )
check "reader beside the script: the default directory gets the record" "$([ -s "$home/.cache/test-runs/runs.jsonl" ]; echo $?)"
git -C "$repo" rm -qf tests/run_summary.py

# A hang that expires by itself: nothing here kills any process but the runner.
printf '#!/usr/bin/env bash\nsleep 6\n' >"$repo/tests/hang.test.sh"
git -C "$repo" add -A
for sig in KILL TERM; do
  ( cd "$repo" && exec bash tests/all.sh >/dev/null 2>&1 ) &
  pid=$!
  sleep 2
  kill -"$sig" "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  check "a run killed by $sig mid-way leaves an incomplete record" "$([ "$(field 'r[-1]["status"]')" = incomplete ]; echo $?)"
done

rm -rf "$runs"; mkdir "$runs"; git -C "$repo" rm -qf tests/hang.test.sh
TESTS_RUN_DIR=off run >/dev/null
check "TESTS_RUN_DIR=off writes no record, here or in a directory named off" "$([ ! -e "$runs/runs.jsonl" ] && [ ! -e "$repo/off" ]; echo $?)"

[ "$fail" = 0 ] && echo "ALL PASS"; exit "$fail"
