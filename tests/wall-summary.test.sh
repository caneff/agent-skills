#!/usr/bin/env bash
# #1958: tests/all.sh prints wall seconds per suite (slowest first) and a total,
# and appends one summary record per run to $TESTS_RUN_DIR/runs.jsonl, keeping
# the last TESTS_RUN_KEEP. Each case builds a throwaway repo holding the working
# tree's tests/all.sh and a few fixture suites, so an uncommitted change is what
# gets tested. A record's status is pass, fail, or incomplete; a run killed
# before it finishes must leave `incomplete`, never a record that reads as a pass.
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
printf '#!/usr/bin/env bash\nsleep 1\n' >"$repo/tests/slow.test.sh"
printf '#!/usr/bin/env bash\nexit 0\n' >"$repo/tests/fast.test.sh"
. "$root/tests/fixture-identity.sh"
git -C "$repo" init -q && git -C "$repo" add -A && fixture_identity "$repo" "$scratch" \
  && git -C "$repo" commit -q -m fixture || { echo "FAIL: scratch repo"; exit 1; }
export TESTS_RUN_DIR=$runs

run() { (cd "$repo" && bash tests/all.sh "$@" 2>&1); }
field() { python3 -c 'import json,sys; r=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]; v=eval(sys.argv[2]); print(" ".join(map(str,v)) if isinstance(v,tuple) else v)' "$runs/runs.jsonl" "$1"; }

out=$(run); rc=$?
check "a full run passes" "$rc"
slow_line=$(grep -n 's wall.*tests/slow.test.sh\|tests/slow.test.sh.*s wall' <<<"$out" | head -1 | cut -d: -f1)
fast_line=$(grep -n 's wall.*tests/fast.test.sh\|tests/fast.test.sh.*s wall' <<<"$out" | head -1 | cut -d: -f1)
check "wall seconds are printed per suite, slowest first" "$([ -n "$slow_line" ] && [ -n "$fast_line" ] && [ "$slow_line" -lt "$fast_line" ]; echo $?)"
check "a total wall line is printed" "$(grep -qE '^total wall: [0-9.]+s' <<<"$out"; echo $?)"
check "PASS lines keep their shape" "$(grep -qE '^PASS tests/fast.test.sh \([0-9.]+s cpu\)$' <<<"$out"; echo $?)"
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
git -C "$repo" rm -qf tests/bad.test.sh

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
check "TESTS_RUN_DIR=off writes no record" "$([ ! -e "$runs/runs.jsonl" ]; echo $?)"

[ "$fail" = 0 ] && echo "ALL PASS"; exit "$fail"
