#!/usr/bin/env bash
# Contract test for job-run, against a redirected HOME under mktemp, so no real
# run directory is touched. Asserts only on observable artifacts — the files a
# run leaves behind, the printed status line, and the exit status — never on the
# script's internals. Jobs are short; the two cases that need a live process to
# signal, and the one that waits out the drain, are the suite's slow part.
# Run: bash flow/bin/job-run.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
job_run="$here/job-run"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
export HOME="$tmp/home"; mkdir -p "$HOME"
jobs_dir="$HOME/.cache/agent-jobs"
fails=0
ok() { echo "PASS $1"; }
no() { echo "FAIL $1"; [ $# -gt 1 ] && printf '  %s\n' "$2"; fails=1; }

"$job_run" --name hello -- sh -c 'echo out; echo err >&2' >/dev/null 2>&1
[ -d "$jobs_dir/hello" ] && ok "a run creates its directory" || no "a run creates its directory"
grep -q 'echo out' "$jobs_dir/hello/cmd" \
  && ok "cmd records the command as invoked" \
  || no "cmd records the command as invoked" "$(cat "$jobs_dir/hello/cmd" 2>&1)"

out=$("$job_run" --name passthrough -- sh -c 'echo out; echo err >&2' 2>&1)
[ "$out" = "out
err" ] \
  && ok "the job's own output still reaches the caller" \
  || no "the job's own output still reaches the caller" "out=$out"

prog="$jobs_dir/hello/progress"
grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z out$' "$prog" \
  && ok "stdout lands in progress, timestamped" \
  || no "stdout lands in progress, timestamped" "$(cat "$prog" 2>&1)"
grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z err$' "$prog" \
  && ok "stderr lands in progress, timestamped" \
  || no "stderr lands in progress, timestamped" "$(cat "$prog" 2>&1)"

# The job-wake mod finds a session's own jobs by this file, so a run started
# outside any session leaves it empty rather than absent.
CLAUDE_CODE_SESSION_ID=sess-1 "$job_run" --name owned -- true >/dev/null 2>&1
[ "$(cat "$jobs_dir/owned/session" 2>&1)" = "sess-1" ] \
  && ok "session records the launching session's id" \
  || no "session records the launching session's id" "$(cat "$jobs_dir/owned/session" 2>&1)"
env -u CLAUDE_CODE_SESSION_ID "$job_run" --name owned -- true >/dev/null 2>&1
[ -e "$jobs_dir/owned/session" ] && [ -z "$(cat "$jobs_dir/owned/session")" ] \
  && ok "a rerun outside a session empties the previous run's session" \
  || no "a rerun outside a session empties the previous run's session" "$(cat "$jobs_dir/owned/session" 2>&1)"

mkdir -p "$jobs_dir/order"; echo "old line" > "$jobs_dir/order/progress"; echo "old-sess" > "$jobs_dir/order/session"
CLAUDE_CODE_SESSION_ID=sess-2 "$job_run" --name order -- sh -c '
  d="$HOME/.cache/agent-jobs/order"
  printf "pid=%s session=%s progress=%s\n" "$(cat "$d/pid")" "$(cat "$d/session")" "$(grep -c "old line" "$d/progress")"' > "$tmp/order.out" 2>&1
grep -qE '^pid=[0-9]+ session=sess-2 progress=0$' "$tmp/order.out" \
  && ok "the job sees its own session and an emptied progress" \
  || no "the job sees its own session and an emptied progress" "$(cat "$tmp/order.out")"

rm -rf "$jobs_dir"
out=$("$job_run" -- true 2>&1); rc=$?
[ "$rc" != 0 ] && [ ! -d "$jobs_dir" ] \
  && ok "a missing --name errors and creates no run directory" \
  || no "a missing --name errors and creates no run directory" "rc=$rc out=$out"

# `shift 2` on one remaining argument fails silently, and without this guard the
# arg loop spins forever on a typo.
for flag in --name --status; do
  out=$(timeout 5 "$job_run" "$flag" 2>&1); rc=$?
  [ "$rc" != 0 ] && [ "$rc" != 124 ] \
    && ok "$flag with no value errors instead of hanging" \
    || no "$flag with no value errors instead of hanging" "rc=$rc out=$out"
done

"$job_run" --name clean -- true >/dev/null 2>&1
grep -q '^rc=0$' "$jobs_dir/clean/exit" \
  && ok "a clean exit records rc=0" \
  || no "a clean exit records rc=0" "$(cat "$jobs_dir/clean/exit" 2>&1)"

"$job_run" --name failed -- sh -c 'exit 7' >/dev/null 2>&1; caller_rc=$?
grep -q '^rc=7$' "$jobs_dir/failed/exit" \
  && ok "a non-zero exit records that code" \
  || no "a non-zero exit records that code" "$(cat "$jobs_dir/failed/exit" 2>&1)"
[ "$caller_rc" = 7 ] \
  && ok "job-run returns the job's own exit status to its caller" \
  || no "job-run returns the job's own exit status to its caller" "got $caller_rc"

# Enough lines that a slow per-line timestamp would let the drain cut the tail
# off both streams in silence.
lines=$("$job_run" --name chatty -- sh -c 'seq 1 20000' 2>/dev/null | wc -l)
[ "$lines" = 20000 ] && [ "$(wc -l < "$jobs_dir/chatty/progress")" = 20000 ] \
  && ok "20000 lines reach both the caller and progress" \
  || no "20000 lines reach both the caller and progress" \
       "caller=$lines progress=$(wc -l < "$jobs_dir/chatty/progress")"

got=$(echo hello | "$job_run" --name reads-stdin -- cat 2>/dev/null)
[ "$got" = hello ] \
  && ok "the caller's stdin reaches the job" \
  || no "the caller's stdin reaches the job" "got=$got"

# A job whose child outlives it makes the wrapper write the one progress line it
# does not write from inside the tee; under a non-UTC TZ that line must still be
# UTC, or it lands hours out of order in its own file.
TZ=Asia/Tokyo "$job_run" --name tz -- sh -c 'sleep 9 & echo first' >/dev/null 2>&1
notice=$(grep -c 'outlived the job' "$jobs_dir/tz/progress")
stamp=$(sed -n '$s/ .*//p' "$jobs_dir/tz/progress")
skew=$(( $(date -u +%s) - $(date -u -d "$stamp" +%s 2>/dev/null || echo 0) ))
[ "$notice" = 1 ] && [ "$skew" -ge -120 ] && [ "$skew" -le 120 ] \
  && ok "the cut-short notice is stamped in UTC like every line above it" \
  || no "the cut-short notice is stamped in UTC like every line above it" \
       "skew=${skew}s $(cat "$jobs_dir/tz/progress")"

"$job_run" --name missing-tool -- sh -c 'notarealtool --x' >/dev/null 2>&1; rc=$?
[ "$rc" = 127 ] && grep -q '^rc=127$' "$jobs_dir/missing-tool/exit" \
  && ok "command-not-found records rc=127, not success" \
  || no "command-not-found records rc=127, not success" \
       "rc=$rc $(cat "$jobs_dir/missing-tool/exit" 2>&1)"

escape="$tmp/escaped"
out=$("$job_run" --name "../../../../${escape#/}" -- sh -c 'echo pwned' 2>&1); rc=$?
[ "$rc" != 0 ] && [ ! -e "$escape" ] \
  && ok "a --name that climbs out of the jobs dir is refused" \
  || no "a --name that climbs out of the jobs dir is refused" "rc=$rc out=$out"
# Refused as a bad name, not merely reported as an unknown run — the difference
# is whether the path was ever built.
out=$("$job_run" --status "../../etc" 2>&1); rc=$?
[ "$rc" != 0 ] && [[ "$out" == *"may hold only"* ]] \
  && ok "--status refuses the same shape" \
  || no "--status refuses the same shape" "rc=$rc out=$out"

# Both drive a real background job-run and signal the wrapper itself.
start_bg() { # start_bg <name> ; echoes the job-run pid
  "$job_run" --name "$1" -- sh -c 'echo started; sleep 5' >/dev/null 2>&1 &
  echo $!
}
await() { # await <file> — up to ~3s for a file to appear
  local i; for i in $(seq 1 60); do [ -e "$1" ] && return 0; sleep 0.05; done; return 1
}

pid=$(start_bg termed)
await "$jobs_dir/termed/progress" && sleep 0.2
kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
if await "$jobs_dir/termed/exit" && grep -q '^cause=TERM$' "$jobs_dir/termed/exit"; then
  ok "a SIGTERMed run records that cause"
else
  no "a SIGTERMed run records that cause" "$(cat "$jobs_dir/termed/exit" 2>&1)"
fi

"$job_run" --name outlives -- bash -c 'trap "" TERM; sleep 1; exit 5' >/dev/null 2>&1 &
pid=$!
await "$jobs_dir/outlives/pid" && sleep 0.3
kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
if await "$jobs_dir/outlives/exit" && grep -q '^cause=exit$' "$jobs_dir/outlives/exit" \
   && grep -q '^rc=5$' "$jobs_dir/outlives/exit"; then
  ok "a job that outlives a forwarded TERM records its own exit, not a termination"
else
  no "a job that outlives a forwarded TERM records its own exit, not a termination" \
     "$(cat "$jobs_dir/outlives/exit" 2>&1)"
fi

pid=$(start_bg killed)
await "$jobs_dir/killed/progress" && sleep 0.2
kill -9 "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
# Longer than the wrapper's bounded drain, so this asserts absence rather than
# merely outrunning a record that was on its way.
sleep 3.5
[ ! -e "$jobs_dir/killed/exit" ] \
  && ok "a kill -9ed run leaves no exit file" \
  || no "a kill -9ed run leaves no exit file" "$(cat "$jobs_dir/killed/exit" 2>&1)"
pkill -9 -P "$pid" 2>/dev/null

"$job_run" --name appends -- sh -c 'echo tee-line; echo own-line >> "$JOB_PROGRESS"' >/dev/null 2>&1
prog="$jobs_dir/appends/progress"
grep -q 'tee-line' "$prog" && grep -q 'own-line' "$prog" \
  && ok "a job appends its own lines beside the tee'd output" \
  || no "a job appends its own lines beside the tee'd output" "$(cat "$prog" 2>&1)"

scratch="$tmp/scratch-repo"; mkdir -p "$scratch"
git -C "$scratch" init -q
( cd "$scratch" && "$job_run" --name in-a-repo -- sh -c 'echo noise; echo more >&2' ) >/dev/null 2>&1
[ -d "$jobs_dir/in-a-repo" ] \
  && [ -z "$(git -C "$scratch" status --porcelain --untracked-files=all)" ] \
  && ok "a job launched inside a checkout leaves it clean" \
  || no "a job launched inside a checkout leaves it clean" \
       "$(git -C "$scratch" status --porcelain --untracked-files=all)"

status_of() { # status_of <name> ; prints "<rc>|<line>"
  local out rc
  out=$("$job_run" --status "$1" 2>&1); rc=$?
  printf '%s|%s' "$rc" "$out"
}

got=$(status_of nobody-ran-this)
case "$got" in
  12\|unknown*"no run"*) ok "an unknown name reports no such run, exit 12" ;;
  *) no "an unknown name reports no such run, exit 12" "$got" ;;
esac

got=$(status_of clean)
case "$got" in
  0\|finished*rc=0*cause=exit*) ok "a finished job reports its return code, exit 0" ;;
  *) no "a finished job reports its return code, exit 0" "$got" ;;
esac

got=$(status_of failed)
case "$got" in
  0\|finished*rc=7*) ok "a failed job reports rc=7" ;;
  *) no "a failed job reports rc=7" "$got" ;;
esac

got=$(status_of termed)
case "$got" in
  0\|finished*cause=TERM*) ok "a SIGTERMed job reports finished with that cause, not killed" ;;
  *) no "a SIGTERMed job reports finished with that cause, not killed" "$got" ;;
esac

got=$(status_of killed)
case "$got" in
  11\|killed*"last progress"*started*) ok "a kill -9ed job reports killed with its last progress line, exit 11" ;;
  *) no "a kill -9ed job reports killed with its last progress line, exit 11" "$got" ;;
esac
case "$got" in
  *[0-9]-[0-9][0-9]-[0-9][0-9]T*Z*) ok "the killed line carries the last progress timestamp" ;;
  *) no "the killed line carries the last progress timestamp" "$got" ;;
esac

pid=$(start_bg still-going)
await "$jobs_dir/still-going/progress" && sleep 0.2
got=$(status_of still-going)
case "$got" in
  10\|alive*) ok "a running job reports alive, exit 10" ;;
  *) no "a running job reports alive, exit 10" "$got" ;;
esac
kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null

oneline=1
for n in nobody-ran-this clean failed termed killed still-going; do
  lines=$("$job_run" --status "$n" 2>&1 | wc -l)
  [ "$lines" = 1 ] || { oneline=0; no "--status $n prints exactly one line" "$lines lines"; }
done
[ "$oneline" = 1 ] && ok "every --status answer is one line"

pid=$(start_bg held)
await "$jobs_dir/held/progress" && sleep 0.2
before=$(cat "$jobs_dir/held/progress")
out=$("$job_run" --name held -- echo second 2>&1); rc=$?
[ "$rc" != 0 ] && [[ "$out" == *held* ]] && [[ "$out" == *"$pid"* ]] \
  && ok "a name held by a live pid refuses, naming the live run" \
  || no "a name held by a live pid refuses, naming the live run" "rc=$rc out=$out"
[ "$(cat "$jobs_dir/held/progress")" = "$before" ] \
  && ok "a refusal leaves the existing run's files untouched" \
  || no "a refusal leaves the existing run's files untouched" "$(cat "$jobs_dir/held/progress")"
kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
await "$jobs_dir/held/exit"

"$job_run" --name held -- sh -c 'echo rerun; sleep 0.1' >/dev/null 2>&1
grep -q 'rerun' "$jobs_dir/held/progress" \
  && ok "the same name against a dead pid reuses the directory" \
  || no "the same name against a dead pid reuses the directory" "$(cat "$jobs_dir/held/progress")"
grep -q '^cause=exit$' "$jobs_dir/held/exit" \
  && ok "a reused directory does not carry the previous run's exit file" \
  || no "a reused directory does not carry the previous run's exit file" "$(cat "$jobs_dir/held/exit")"

age() { # age <name> <days> — a finished run whose files are <days> old
  mkdir -p "$jobs_dir/$1"
  printf 'rc=0\ncause=exit\nended=old\n' > "$jobs_dir/$1/exit"
  printf 'old\n' > "$jobs_dir/$1/progress"
  printf '999999\n' > "$jobs_dir/$1/pid"
  touch -d "$2 days ago" "$jobs_dir/$1"/* "$jobs_dir/$1"
}
age ancient 15
age recent 13
"$job_run" --name trigger-prune -- true >/dev/null 2>&1
[ ! -d "$jobs_dir/ancient" ] \
  && ok "a run directory older than 14 days is pruned on start" \
  || no "a run directory older than 14 days is pruned on start"
[ -d "$jobs_dir/recent" ] \
  && ok "a run directory newer than 14 days is kept" \
  || no "a run directory newer than 14 days is kept"

mkdir -p "$jobs_dir/long-runner"
printf '999999\n' > "$jobs_dir/long-runner/pid"
printf 'old\n' > "$jobs_dir/long-runner/progress"
touch -d "1 day ago" "$jobs_dir/long-runner/progress"
touch -d "40 days ago" "$jobs_dir/long-runner"
"$job_run" --name trigger-prune-3 -- true >/dev/null 2>&1
[ -d "$jobs_dir/long-runner" ] \
  && ok "a run whose progress is recent survives an old directory mtime" \
  || no "a run whose progress is recent survives an old directory mtime"

pid=$(start_bg old-but-live)
await "$jobs_dir/old-but-live/progress" && sleep 0.2
touch -d "60 days ago" "$jobs_dir/old-but-live"
"$job_run" --name trigger-prune-2 -- true >/dev/null 2>&1
[ -d "$jobs_dir/old-but-live" ] \
  && ok "a live run is never pruned regardless of age" \
  || no "a live run is never pruned regardless of age"
kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null

# A prune that cannot remove a directory must not stop the job it was launched
# alongside, and must not leak its own noise into the caller's output — the job's
# stdout is what the caller reads. A read-only run directory makes rm -rf fail.
age stubborn 20
chmod 500 "$jobs_dir/stubborn"
out=$("$job_run" --name survives-a-prune-failure -- echo ran 2>&1); rc=$?
chmod 700 "$jobs_dir/stubborn"
[ "$rc" = 0 ] && grep -q 'ran' "$jobs_dir/survives-a-prune-failure/progress" \
  && ok "a prune failure does not stop the job" \
  || no "a prune failure does not stop the job" "rc=$rc out=$out"
[ "$out" = "ran" ] \
  && ok "a prune failure does not leak into the caller's output" \
  || no "a prune failure does not leak into the caller's output" "out=$out"
[ -d "$jobs_dir/stubborn" ] \
  && ok "a directory prune could not remove is left alone" \
  || no "a directory prune could not remove is left alone"

"$job_run" --name waited -- sh -c 'echo going; sleep 2' >/dev/null 2>&1 &
wpid=$!
await "$jobs_dir/waited/pid"
t0=$(date +%s)
out=$("$job_run" --wait waited 2>&1); rc=$?
t1=$(date +%s)
case "$rc|$out" in
  0\|finished\ waited\ rc=0*) ok "--wait prints the finished line and exits 0" ;;
  *) no "--wait prints the finished line and exits 0" "rc=$rc out=$out" ;;
esac
[ -e "$jobs_dir/waited/exit" ] && [ $((t1 - t0)) -ge 1 ] \
  && ok "--wait returns only after the run's exit record exists" \
  || no "--wait returns only after the run's exit record exists" \
       "elapsed=$((t1 - t0))s exit-file=$([ -e "$jobs_dir/waited/exit" ] && echo yes || echo no)"
[ "$out" = "$("$job_run" --status waited)" ] \
  && ok "--wait prints exactly the line --status prints" \
  || no "--wait prints exactly the line --status prints" "$out"
wait "$wpid" 2>/dev/null

out=$(timeout 2 "$job_run" --wait clean 2>&1); rc=$?
case "$rc|$out" in
  0\|finished\ clean*) ok "--wait on a finished run returns at once" ;;
  *) no "--wait on a finished run returns at once" "rc=$rc out=$out" ;;
esac

out=$(timeout 2 "$job_run" --wait failed 2>&1); rc=$?
case "$rc|$out" in
  0\|finished\ failed\ rc=7*) ok "--wait reports a failed job's rc in the line, exit 0" ;;
  *) no "--wait reports a failed job's rc in the line, exit 0" "rc=$rc out=$out" ;;
esac

pid=$(start_bg waitkilled)
await "$jobs_dir/waitkilled/progress" && sleep 0.2
kids=$(pgrep -P "$pid")   # the job's own children, taken before the wrapper dies
( sleep 0.5; kill -9 "$pid" 2>/dev/null ) &
out=$(timeout 15 "$job_run" --wait waitkilled 2>&1); rc=$?
case "$rc|$out" in
  11\|killed\ waitkilled*) ok "--wait on a SIGKILLed run says killed, exit 11" ;;
  *) no "--wait on a SIGKILLed run says killed, exit 11" "rc=$rc out=$out" ;;
esac
wait "$pid" 2>/dev/null
for k in $kids; do pkill -9 -P "$k" 2>/dev/null; kill -9 "$k" 2>/dev/null; done

out=$(timeout 2 "$job_run" --wait nosuch 2>&1); rc=$?
case "$rc|$out" in
  12\|unknown\ nosuch*) ok "--wait on an unknown name exits 12 at once" ;;
  *) no "--wait on an unknown name exits 12 at once" "rc=$rc out=$out" ;;
esac
out=$("$job_run" --wait ../x 2>&1); rc=$?
[ "$rc" != 0 ] && [[ "$out" == *"may hold only"* ]] \
  && ok "--wait refuses a traversal name via check_name" \
  || no "--wait refuses a traversal name via check_name" "rc=$rc out=$out"

pid=$(start_bg waitterm)
await "$jobs_dir/waitterm/progress" && sleep 0.2
"$job_run" --wait waitterm >"$tmp/term.out" 2>&1 &
wp=$!
sleep 0.5
t0=$(date +%s%N)
kill -TERM "$wp" 2>/dev/null; wait "$wp" 2>/dev/null; rc=$?
ms=$(( ($(date +%s%N) - t0) / 1000000 ))
# Well under the 3 s poll interval: a signal handled only when a foreground
# sleep returns would take up to that long.
[ "$rc" = 13 ] && ! grep -q '^finished' "$tmp/term.out" && [ "$ms" -lt 1000 ] \
  && ok "a TERMed --wait exits 13 promptly and does not say finished" \
  || no "a TERMed --wait exits 13 promptly and does not say finished" \
       "rc=$rc elapsed=${ms}ms out=$(cat "$tmp/term.out")"
kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null

refuse() { # refuse <expected message part> <args...>
  local want="$1" out rc; shift
  out=$(timeout 5 "$job_run" "$@" 2>&1); rc=$?
  [ "$rc" = 1 ] && [[ "$out" == *"$want"* ]] \
    && ok "'$*' is refused: $want" \
    || no "'$*' is refused: $want" "rc=$rc out=$out"
}
refuse "--wait cannot be combined with --status" --wait a --status b
refuse "--wait cannot be combined with --name" --wait a --name b
refuse "--wait cannot be combined with --name" --name b --wait a
refuse "--wait cannot be combined with a command" --wait a -- true
refuse "--wait needs a value" --wait

out=$("$job_run" --status clean --name whatever 2>&1); rc=$?
case "$rc|$out" in
  0\|finished\ clean*) ok "--status is unchanged by --name beside it" ;;
  *) no "--status is unchanged by --name beside it" "rc=$rc out=$out" ;;
esac

mkdir -p "$jobs_dir/midstart"
got=$(status_of midstart)
case "$got" in
  10\|starting*) ok "a run directory with no pid and no exit reads starting, exit 10" ;;
  *) no "a run directory with no pid and no exit reads starting, exit 10" "$got" ;;
esac
timeout 4 "$job_run" --wait midstart >/dev/null 2>&1; rc=$?
[ "$rc" = 124 ] \
  && ok "--wait keeps waiting on a run mid-start" \
  || no "--wait keeps waiting on a run mid-start" "rc=$rc"
rmdir "$jobs_dir/midstart"

"$job_run" --name reuse -- sh -c 'exit 4' >/dev/null 2>&1
"$job_run" --name reuse -- sh -c 'sleep 1' >/dev/null 2>&1 &
rpid=$!
await "$jobs_dir/reuse/pid"; sleep 0.2
got=$(status_of reuse)
case "$got" in
  10\|alive*) ok "a reused name reports the new run alive, not the previous verdict" ;;
  *) no "a reused name reports the new run alive, not the previous verdict" "$got" ;;
esac
wait "$rpid" 2>/dev/null

[ ! -e "$jobs_dir/nosuch" ] \
  && ok "--wait creates no run directory" \
  || no "--wait creates no run directory"

"$job_run" --name g1 --group shard -- true >/dev/null 2>&1
[ "$(cat "$jobs_dir/g1/group" 2>&1)" = "shard" ] \
  && ok "group records the run's group name" \
  || no "group records the run's group name" "$(cat "$jobs_dir/g1/group" 2>&1)"
"$job_run" --name g1 -- true >/dev/null 2>&1
[ ! -e "$jobs_dir/g1/group" ] \
  && ok "a rerun without --group drops the previous run's group" \
  || no "a rerun without --group drops the previous run's group" "$(cat "$jobs_dir/g1/group" 2>&1)"
"$job_run" --name g2 -- true >/dev/null 2>&1
[ ! -e "$jobs_dir/g2/group" ] \
  && ok "a run with no --group leaves no group file" \
  || no "a run with no --group leaves no group file"
refuse "--group may hold only" --name g3 --group ../x -- true
refuse "--group needs a value" --group
refuse "--group may not be empty" --name g3 --group "" -- true
refuse "--group cannot be combined with --status" --status a --group b
refuse "--group cannot be combined with --wait" --wait a --group b
[ ! -e "$jobs_dir/g3" ] \
  && ok "a refused --group creates no run directory" \
  || no "a refused --group creates no run directory"

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
