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

# bash hands an async command /dev/null, so without the fd this silently differs
# from running the job unwrapped.
got=$(echo hello | "$job_run" --name reads-stdin --stdin -- cat 2>/dev/null)
[ "$got" = hello ] \
  && ok "--stdin passes the caller's stdin to the job" \
  || no "--stdin passes the caller's stdin to the job" "got=$got"

# Both drive a real background job-run and signal the wrapper itself.
start_bg() { # start_bg <name> ; echoes the job-run pid
  "$job_run" --name "$1" -- sh -c 'echo started; sleep 5' >/dev/null 2>&1 &
  echo $!
}
await() { # await <file> — up to ~3s for a file to appear
  local i; for i in $(seq 1 60); do [ -e "$1" ] && return 0; sleep 0.05; done; return 1
}

# Default: stdin is closed (/dev/null), so a reader sees EOF at once rather than
# waiting on a pipe that never closes (a 33-minute stall, #1698).
got=$( (sleep 30 | timeout 10 "$job_run" --name closed-stdin -- cat) 2>/dev/null); rc=$?
[ "$rc" = 0 ] && [ -z "$got" ] \
  && ok "by default the job's stdin is closed, so a reader sees EOF" \
  || no "by default the job's stdin is closed, so a reader sees EOF" "rc=$rc got=$got"

# Default wall-clock timeout, overridable; the kill is recorded as
# cause=timeout, rc=124.
started=$(date +%s)
"$job_run" --name slow --timeout 1 -- sleep 30 >/dev/null 2>&1; rc=$?
took=$(( $(date +%s) - started ))
[ "$rc" = 124 ] && grep -q '^rc=124$' "$jobs_dir/slow/exit" \
  && grep -q '^cause=timeout$' "$jobs_dir/slow/exit" && [ "$took" -lt 15 ] \
  && ok "--timeout kills a job past its limit and records cause=timeout rc=124" \
  || no "--timeout kills a job past its limit and records cause=timeout rc=124" \
     "rc=$rc took=$took $(cat "$jobs_dir/slow/exit" 2>&1)"

# The job writes its descendant's pid, so the check names this run's own process.
"$job_run" --name slow-tree --timeout 1 -- sh -c 'sleep 30 & echo $! > "$0"; wait' "$tmp/kid.pid" >/dev/null 2>&1
sleep 0.5
kid=$(cat "$tmp/kid.pid" 2>/dev/null)
if [ -n "$kid" ] && ! kill -0 "$kid" 2>/dev/null; then ok "a timeout kills the job's descendants too"
else no "a timeout kills the job's descendants too" "kid=$kid"; [ -n "$kid" ] && kill -9 "$kid" 2>/dev/null; fi

# A job that ignores TERM is killed after the grace, still recorded as a timeout.
started=$(date +%s)
JOB_RUN_KILL_GRACE=1 "$job_run" --name stubborn --timeout 1 -- sh -c 'trap "" TERM; for i in $(seq 60); do sleep 1; done' >/dev/null 2>&1; rc=$?
took=$(( $(date +%s) - started ))
[ "$rc" = 124 ] && grep -q '^cause=timeout$' "$jobs_dir/stubborn/exit" && [ "$took" -lt 15 ] \
  && ok "a job that ignores TERM is killed after the grace and recorded as a timeout" \
  || no "a job that ignores TERM is killed after the grace and recorded as a timeout" \
     "rc=$rc took=$took $(cat "$jobs_dir/stubborn/exit" 2>&1)"

# The default is 3600 s: a live run has a watchdog whose sleep is that long.
pid=$(start_bg dflt)
await "$jobs_dir/dflt/progress" && sleep 0.3
tree=$(pgrep -P "$pid" | xargs -r -n1 pgrep -a -P | tr '\n' ' ')
case "$tree" in *"sleep 3600"*) ok "a run with no --timeout has the 3600 s default limit" ;;
  *) no "a run with no --timeout has the 3600 s default limit" "children: $tree" ;; esac
kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null

# A job that ends in time leaves no watchdog: the unique limit names this run's.
lim=$((4000 + RANDOM % 1000))
"$job_run" --name fast --timeout "$lim" -- true >/dev/null 2>&1
grep -q '^cause=exit$' "$jobs_dir/fast/exit" && ! pgrep -fx "sleep $lim" >/dev/null \
  && ok "a job that ends in time records a normal exit and leaves no watchdog" \
  || no "a job that ends in time records a normal exit and leaves no watchdog" \
     "$(cat "$jobs_dir/fast/exit" 2>&1)"

# A wrapper SIGKILLed before the limit orphans its watchdog; at the limit it
# must not stamp a later same-name run as a timeout.
"$job_run" --name orphan --timeout 2 -- sleep 30 >/dev/null 2>&1 & opid=$!
await "$jobs_dir/orphan/pid" && sleep 0.3
kill -9 "$opid" 2>/dev/null; wait "$opid" 2>/dev/null
pkill -9 -P "$opid" 2>/dev/null
sleep 2.5
"$job_run" --name orphan --timeout 30 -- true >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q '^cause=exit$' "$jobs_dir/orphan/exit" \
  && ok "an orphaned watchdog does not mark a later run as a timeout" \
  || no "an orphaned watchdog does not mark a later run as a timeout" \
     "rc=$rc $(cat "$jobs_dir/orphan/exit" 2>&1)"
"$job_run" --name zero --timeout 0 -- true >/dev/null 2>&1
grep -q '^rc=0$' "$jobs_dir/zero/exit" \
  && ok "--timeout 0 means no limit" \
  || no "--timeout 0 means no limit"
JOB_RUN_TIMEOUT=1 "$job_run" --name envto -- sleep 30 >/dev/null 2>&1
grep -q '^cause=timeout$' "$jobs_dir/envto/exit" \
  && ok "JOB_RUN_TIMEOUT sets the default" \
  || no "JOB_RUN_TIMEOUT sets the default" "$(cat "$jobs_dir/envto/exit" 2>&1)"
for bad in abc -1 1.5 ""; do
  out=$("$job_run" --name badto --timeout "$bad" -- true 2>&1); rc=$?
  [ "$rc" = 1 ] && grep -q -- '--timeout' <<<"$out" \
    && ok "--timeout '$bad' is refused" || no "--timeout '$bad' is refused" "rc=$rc out=$out"
done
out=$("$job_run" --timeout 2>&1); rc=$?
[ "$rc" = 1 ] && ok "--timeout with no value errors" || no "--timeout with no value errors" "rc=$rc out=$out"

# A trailing `&` in a `sh -c` script makes the wrapper's direct child exit at
# once, so the wake fires before the work ends (#1901).
for shellcmd in "bash -c" "sh -c" "bash -lc"; do
  out=$("$job_run" --name trailing-amp -- $shellcmd 'sleep 5 &' 2>&1); rc=$?
  [ "$rc" = 1 ] && grep -q 'trailing &' <<<"$out" && [ ! -d "$jobs_dir/trailing-amp" ] \
    && ok "$shellcmd with a script ending in & is refused, creating no run" \
    || no "$shellcmd with a script ending in & is refused, creating no run" "rc=$rc out=$out"
done
out=$("$job_run" --name trailing-amp -- sh -c 'sleep 3 &' sh 2>&1); rc=$?
[ "$rc" = 1 ] && ok "a script followed by \$0 is still read" || no "a script followed by \$0 is still read" "rc=$rc"
out=$("$job_run" --name amp-data -- echo 'q=a&b&' 2>&1); rc=$?
[ "$rc" = 0 ] && [ "$out" = 'q=a&b&' ] \
  && ok "an & ending another program's argument is data, not refused" \
  || no "an & ending another program's argument is data, not refused" "rc=$rc out=$out"
"$job_run" --name amp-ok -- bash -c 'true &&
echo hi' >/dev/null 2>&1
grep -q '^rc=0$' "$jobs_dir/amp-ok/exit" \
  && ok "a && inside a script is not a trailing &" \
  || no "a && inside a script is not a trailing &"
"$job_run" --check -- bash -c 'echo x &&' >/dev/null 2>&1; rc1=$?
"$job_run" --check -- bash -c 'echo x &' >/dev/null 2>&1; rc2=$?
[ "$rc1" = 0 ] && [ "$rc2" = 1 ] && [ ! -d "$jobs_dir/amp-ok-check" ] \
  && ok "--check allows a script ending in && and refuses one ending in &" \
  || no "--check allows a script ending in && and refuses one ending in &" "rc1=$rc1 rc2=$rc2"

# A poll loop wrapped in a job re-creates the spin the no-poll rule bans: the
# wrapper only hides it from the session (#1705). Refused with exit 2 under
# --check (the hook's reading) and exit 1 on a real run, creating no run.
for script in \
  'until [ "$(gh run list --json status -q .[0].status)" = completed ]; do sleep 5; done' \
  'while ps aux | grep -q loop57.sh; do sleep 5; done' \
  'while true
do
  sleep 2
done' \
  'gh run rerun 1 && sleep 3 && gh run watch 1' \
  'sleep $n && gh run watch 1' \
  'while sleep 5; do gh run view 1; done' \
  'for i in $(seq 100); do gh run view 1 | grep -q completed && break; sleep 10; done' \
  'while true; do sleep 5; done &'; do
  out=$("$job_run" --name poll-loop --timeout 5 -- bash -c "$script" 2>&1); rc=$?
  [ "$rc" = 1 ] && grep -q 'pr_settle.py' <<<"$out" && grep -q 'gh run watch' <<<"$out" && [ ! -d "$jobs_dir/poll-loop" ] \
    && ok "a poll loop is refused naming pr_settle.py and gh run watch: ${script%%$'\n'*}" \
    || no "a poll loop is refused naming pr_settle.py and gh run watch: ${script%%$'\n'*}" "rc=$rc out=$out"
  "$job_run" --check -- bash -c "$script" >/dev/null 2>&1; rc=$?
  [ "$rc" = 2 ] && ok "--check answers a poll loop with exit 2: ${script%%$'\n'*}" \
    || no "--check answers a poll loop with exit 2: ${script%%$'\n'*}" "rc=$rc"
done
# A wrapper in front of the shell does not hide the loop from a direct call.
for pre in 'timeout 600' env nohup; do
  "$job_run" --check -- $pre bash -c 'until false; do sleep 5; done' >/dev/null 2>&1; rc=$?
  [ "$rc" = 2 ] && ok "--check reads a poll loop behind: $pre" || no "--check reads a poll loop behind: $pre" "rc=$rc"
done
# Waiting is not polling when the loop has no sleep, a plain sleep is a job, and
# a read loop that paces itself is not a condition poll. A sleep after the last
# loop, or the word while in a string, is not a loop that sleeps; one delayed
# gh pr checks is a check, not a poll.
for script in \
  'while [ "$n" -lt 3 ]; do n=$((n+1)); done; sleep 2' \
  'while getopts a: o; do :; done; sleep 1' \
  'echo "while we do this"; sleep 5' \
  'sleep 60; gh pr checks 5' \
  'sleep 2; echo done' \
  'for i in 1 2 3; do echo $i; sleep 1; done' \
  'while read -r x; do echo "$x"; sleep 1; done < /dev/null' \
  'while IFS= read -r x; do echo "$x"; sleep 1; done < /dev/null' \
  'while [ "$n" -lt 3 ]; do n=$((n+1)); done'; do
  "$job_run" --check -- bash -c "$script" >/dev/null 2>&1; rc=$?
  [ "$rc" = 0 ] && ok "--check allows: ${script%%$'\n'*}" || no "--check allows: ${script%%$'\n'*}" "rc=$rc"
done
"$job_run" --check -- sleep 1 >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && ok "a direct sleep command is not read as a poll loop" || no "a direct sleep command is not read as a poll loop" "rc=$rc"

# #1703: a `bash -c` job runs with pipefail, so a failing stage is not hidden by
# the stage after it, and the status names the stage.
"$job_run" --name pf -- bash -c 'false | cat' >/dev/null 2>&1; pf_rc=$?
[ "$pf_rc" = 1 ] && grep -q '^rc=1$' "$jobs_dir/pf/exit" \
  && ok "a failed first stage of a pipe is the job's exit" \
  || no "a failed first stage of a pipe is the job's exit" "rc=$pf_rc $(cat "$jobs_dir/pf/exit" 2>&1)"
line=$("$job_run" --status pf)
[[ "$line" == *"stage 1 of 2"* ]] \
  && ok "--status names the failing pipeline stage" \
  || no "--status names the failing pipeline stage" "$line"
grep -q 'pipeline stage 1 of 2' "$jobs_dir/pf/progress" \
  && ok "progress names the failing pipeline stage" \
  || no "progress names the failing pipeline stage" "$(cat "$jobs_dir/pf/progress")"

"$job_run" --name pf-last -- bash -c 'true | false' >/dev/null 2>&1
line=$("$job_run" --status pf-last)
[[ "$line" == finished*rc=1* && "$line" != *stage* ]] \
  && ok "a failing last stage is a plain failure, no stage named" \
  || no "a failing last stage is a plain failure, no stage named" "$line"

"$job_run" --name pf-stale -- bash -c 'false | cat; true' >/dev/null 2>&1; stale_rc=$?
line=$("$job_run" --status pf-stale)
[ "$stale_rc" = 0 ] && [[ "$line" != *stage* ]] \
  && ok "a tolerated pipe failure earlier in the script names no stage" \
  || no "a tolerated pipe failure earlier in the script names no stage" "rc=$stale_rc $line"

"$job_run" --name pf-sigpipe -- bash -c 'yes | head -1' >/dev/null 2>&1; sp_rc=$?
line=$("$job_run" --status pf-sigpipe)
[ "$sp_rc" = 141 ] && [[ "$line" == *"stopped by SIGPIPE"* && "$line" != *failed* ]] \
  && grep -q 'stopped by SIGPIPE' "$jobs_dir/pf-sigpipe/progress" && ! grep -q 'failed' "$jobs_dir/pf-sigpipe/progress" \
  && ok "a pipe closed early is reported as a SIGPIPE stop, not a failure" \
  || no "a pipe closed early is reported as a SIGPIPE stop, not a failure" "rc=$sp_rc $line $(cat "$jobs_dir/pf-sigpipe/progress")"

# The stage is named only when its code is the job's exit: a tolerated failure
# earlier, then a different exit, is a plain failure.
"$job_run" --name pf-other -- bash -c 'false | cat; exit 2' >/dev/null 2>&1
line=$("$job_run" --status pf-other)
[[ "$line" == finished*rc=2* && "$line" != *stage* ]] \
  && ok "a different exit code than the saved pipe stage names no stage" \
  || no "a different exit code than the saved pipe stage names no stage" "$line"

# A rerun under the same name starts with no saved pipe status.
"$job_run" --name pf-rerun -- bash -c 'false | cat' >/dev/null 2>&1
"$job_run" --name pf-rerun -- bash -c 'exit 1' >/dev/null 2>&1
line=$("$job_run" --status pf-rerun)
[[ "$line" == finished*rc=1* && "$line" != *stage* ]] \
  && ok "a rerun does not inherit the previous run's pipe stage" \
  || no "a rerun does not inherit the previous run's pipe stage" "$line"

# Forms the wrapper must still run as bash does, and still harden.
out=$("$job_run" --name pf-dd -- bash -c -- 'echo hi' 2>&1)
[ "$out" = hi ] && ok "options after -c are read, not run as the command" || no "options after -c are read, not run as the command" "$out"
out=$("$job_run" --name pf-e -- bash -c -e 'echo hi' 2>&1)
[ "$out" = hi ] && ok "a flag after -c is read, not run as the command" || no "a flag after -c is read, not run as the command" "$out"
for form in "timeout -k 5 60" "env -u X" "nice -n 1" "nice" "env -i"; do
  # shellcheck disable=SC2086
  "$job_run" --name pf-form -- $form bash -c 'false | cat' >/dev/null 2>&1
  [[ "$("$job_run" --status pf-form)" == *"stage 1 of 2"* ]] \
    && ok "pipefail applies behind: $form" || no "pipefail applies behind: $form" "$("$job_run" --status pf-form)"
done
out=$("$job_run" --name pf-i -- env -i bash -c 'false | cat' 2>&1)
[[ "$out" != *"No such file"* ]] \
  && ok "env -i leaves no error from the trap" || no "env -i leaves no error from the trap" "$out"
"$job_run" --name pf-oc -- bash -o errexit -c 'false | cat' >/dev/null 2>&1
[[ "$("$job_run" --status pf-oc)" == *"stage 1 of 2"* ]] \
  && ok "pipefail applies with -o <option> before -c" || no "pipefail applies with -o <option> before -c"
# One reader for the command: a trailing & is refused behind an env assignment too.
out=$(timeout 5 "$job_run" --name pf-amp -- env X=1 bash -c 'sleep 1 &' 2>&1); rc=$?
[ "$rc" = 1 ] && [[ "$out" == *"trailing &"* ]] \
  && ok "a trailing & is refused behind an env assignment" \
  || no "a trailing & is refused behind an env assignment" "rc=$rc out=$out"

# Only bash is touched: sh has no ERR trap, and a non-shell command is data.
out=$("$job_run" --name pf-sh -- sh -c 'echo ok' 2>&1)
[ "$out" = ok ] && ok "a non-bash shell runs unchanged" || no "a non-bash shell runs unchanged" "$out"
out=$("$job_run" --name pf-args -- bash -c 'echo "$0 $1"' a b 2>&1)
[ "$out" = "a b" ] && ok "arguments after the script keep their positions" || no "arguments after the script keep their positions" "$out"
out=$("$job_run" --name pf-env -- env X=1 bash -c 'false | cat; echo "x=$X"' 2>&1)
[[ "$out" == x=1 ]] && ok "an env prefix still reaches the shell" || no "an env prefix still reaches the shell" "$out"
"$job_run" --name pf-env2 -- env X=1 bash -c 'false | cat' >/dev/null 2>&1
[[ "$("$job_run" --status pf-env2)" == *"stage 1 of 2"* ]] \
  && ok "pipefail applies behind an env prefix" || no "pipefail applies behind an env prefix"

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"

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

pid=$(start_bg termed)
await "$jobs_dir/termed/progress" && sleep 0.2
kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
if await "$jobs_dir/termed/exit" && grep -q '^cause=TERM$' "$jobs_dir/termed/exit"; then
  ok "a SIGTERMed run records that cause"
else
  no "a SIGTERMed run records that cause" "$(cat "$jobs_dir/termed/exit" 2>&1)"
fi

# A job that ignores the forwarded signal and finishes on its own exited — the
# cause follows what the job returned, never what the wrapper was asked to do.
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

# The run directory's whole address is $HOME/.cache/agent-jobs/<name>, so a job
# launched from inside a checkout must leave that checkout clean.
scratch="$tmp/scratch-repo"; mkdir -p "$scratch"
git -C "$scratch" init -q
( cd "$scratch" && "$job_run" --name in-a-repo -- sh -c 'echo noise; echo more >&2' ) >/dev/null 2>&1
[ -d "$jobs_dir/in-a-repo" ] \
  && [ -z "$(git -C "$scratch" status --porcelain --untracked-files=all)" ] \
  && ok "a job launched inside a checkout leaves it clean" \
  || no "a job launched inside a checkout leaves it clean" \
       "$(git -C "$scratch" status --porcelain --untracked-files=all)"

# One line each, and an exit status a caller can branch on without parsing it:
# 0 finished, 10 alive, 11 killed, 12 no such run — the last three above the
# range bash and the script use for their own errors.
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

# The same name against a dead pid reuses the directory, and the previous run's
# exit record does not survive into the new run.
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

# Retention ages a run by the newest thing inside it, not the directory's own
# mtime: appending to progress never touches the directory, so a killed run that
# logged for weeks would otherwise be pruned first — exactly the record this is
# all for.
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

# Launched as a run_in_background Bash call so the harness wakes the session
# when the job ends. Never returns 10: a live run is waited on, not reported.
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

# --status still ignores what it always ignored: the refusals are --wait's own.
out=$("$job_run" --status clean --name whatever 2>&1); rc=$?
case "$rc|$out" in
  0\|finished\ clean*) ok "--status is unchanged by --name beside it" ;;
  *) no "--status is unchanged by --name beside it" "rc=$rc out=$out" ;;
esac

# A run directory with no pid and no exit record is a run mid-start, not a dead
# one: it is `starting` (10), so a --wait keeps waiting instead of ending on it.
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

# A reused name drops the previous run's pid and exit record together, so a
# reader of the new run never sees the old verdict once the new pid is down.
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

# The job-wake mod wakes a group once; it finds a run's group in this file.
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
