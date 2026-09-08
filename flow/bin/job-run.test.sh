#!/usr/bin/env bash
# Contract test for job-run, against a redirected HOME under mktemp, so no real
# run directory is touched. Asserts only on observable artifacts — the files a
# run leaves behind, the printed status line, and the exit status — never on the
# script's internals. Every job it drives is sub-second.
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

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
