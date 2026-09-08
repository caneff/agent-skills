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

# --- a run leaves a directory holding what it ran and what it printed --------
"$job_run" --name hello -- sh -c 'echo out; echo err >&2' >/dev/null 2>&1
[ -d "$jobs_dir/hello" ] && ok "a run creates its directory" || no "a run creates its directory"
grep -q 'echo out' "$jobs_dir/hello/cmd" \
  && ok "cmd records the command as invoked" \
  || no "cmd records the command as invoked" "$(cat "$jobs_dir/hello/cmd" 2>&1)"

# A wrapped job has to look like the unwrapped one to whatever reads its output.
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

# --- a missing --name is an error and creates nothing ------------------------
rm -rf "$jobs_dir"
out=$("$job_run" -- true 2>&1); rc=$?
[ "$rc" != 0 ] && [ ! -d "$jobs_dir" ] \
  && ok "a missing --name errors and creates no run directory" \
  || no "a missing --name errors and creates no run directory" "rc=$rc out=$out"

# --- a flag with no value is an error, not a hang ----------------------------
# `shift 2` on one remaining argument fails silently, and without this guard the
# arg loop spins forever on a typo.
for flag in --name --status; do
  out=$(timeout 5 "$job_run" "$flag" 2>&1); rc=$?
  [ "$rc" != 0 ] && [ "$rc" != 124 ] \
    && ok "$flag with no value errors instead of hanging" \
    || no "$flag with no value errors instead of hanging" "rc=$rc out=$out"
done

# --- observed exits ----------------------------------------------------------
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

# --- a chatty job loses nothing, to the caller or to the record --------------
# A per-line `date` fork once held the tee to about a thousand lines a second,
# slow enough that the drain below cut the tail off both streams in silence.
lines=$("$job_run" --name chatty -- sh -c 'seq 1 20000' 2>/dev/null | wc -l)
[ "$lines" = 20000 ] && [ "$(wc -l < "$jobs_dir/chatty/progress")" = 20000 ] \
  && ok "20000 lines reach both the caller and progress" \
  || no "20000 lines reach both the caller and progress" \
       "caller=$lines progress=$(wc -l < "$jobs_dir/chatty/progress")"

# --- the caller's stdin reaches the job --------------------------------------
# bash hands an async command /dev/null, so without the fd this silently differs
# from running the job unwrapped.
got=$(echo hello | "$job_run" --name reads-stdin -- cat 2>/dev/null)
[ "$got" = hello ] \
  && ok "the caller's stdin reaches the job" \
  || no "the caller's stdin reaches the job" "got=$got"

# --- every progress timestamp is UTC, including the ones the wrapper writes ---
# A job whose child outlives it makes the wrapper write the one progress line it
# does not write from inside the tee. Under a non-UTC TZ that line used to be
# local time wearing a Z, landing hours out of order in its own file.
TZ=Asia/Tokyo "$job_run" --name tz -- sh -c 'sleep 9 & echo first' >/dev/null 2>&1
notice=$(grep -c 'outlived the job' "$jobs_dir/tz/progress")
stamp=$(sed -n '$s/ .*//p' "$jobs_dir/tz/progress")
skew=$(( $(date -u +%s) - $(date -u -d "$stamp" +%s 2>/dev/null || echo 0) ))
[ "$notice" = 1 ] && [ "$skew" -ge -120 ] && [ "$skew" -le 120 ] \
  && ok "the cut-short notice is stamped in UTC like every line above it" \
  || no "the cut-short notice is stamped in UTC like every line above it" \
       "skew=${skew}s $(cat "$jobs_dir/tz/progress")"

# --- a job that never ran is not a clean success -----------------------------
"$job_run" --name missing-tool -- sh -c 'notarealtool --x' >/dev/null 2>&1; rc=$?
[ "$rc" = 127 ] && grep -q '^rc=127$' "$jobs_dir/missing-tool/exit" \
  && ok "command-not-found records rc=127, not success" \
  || no "command-not-found records rc=127, not success" \
       "rc=$rc $(cat "$jobs_dir/missing-tool/exit" 2>&1)"

# --- a run name is one directory under the jobs dir, never a way out of it ---
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

# --- a SIGTERMed run records the cause; a SIGKILLed one records nothing ------
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

# --- the job can append its own lines through the exported variable ----------
"$job_run" --name appends -- sh -c 'echo tee-line; echo own-line >> "$JOB_PROGRESS"' >/dev/null 2>&1
prog="$jobs_dir/appends/progress"
grep -q 'tee-line' "$prog" && grep -q 'own-line' "$prog" \
  && ok "a job appends its own lines beside the tee'd output" \
  || no "a job appends its own lines beside the tee'd output" "$(cat "$prog" 2>&1)"

# --- nothing is written inside the repo the job runs in ----------------------
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

# --- --status: alive, finished, killed, unknown ------------------------------
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

# --- lifecycle: name collision -----------------------------------------------
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

# --- lifecycle: 14-day prune -------------------------------------------------
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

# A live run is never pruned, however old its files are.
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

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
