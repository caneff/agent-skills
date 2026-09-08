#!/usr/bin/env bash
# Contract test for wrap-background-jobs.sh: synthetic PreToolUse JSON on stdin
# -> exit code and emitted JSON out. Nothing live is touched; `job-run` is a
# stub on a scratch PATH, so the job-run-absent branch is reachable too.
# Run: bash flow/claude/hooks/wrap-background-jobs.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/wrap-background-jobs.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fails=0
ok() { echo "PASS $1"; }
no() { echo "FAIL $1"; [ $# -gt 1 ] && printf '  %s\n' "$2"; fails=1; }

# Two PATHs: one where job-run exists, one where it does not.
mkdir -p "$tmp/withjr" "$tmp/nojr"
for t in cat jq tr cut sed; do
  p=$(command -v "$t") && { ln -sf "$p" "$tmp/withjr/$t"; ln -sf "$p" "$tmp/nojr/$t"; }
done
printf '#!/usr/bin/env bash\nexit 0\n' > "$tmp/withjr/job-run"; chmod +x "$tmp/withjr/job-run"

fire() { # fire <path-dir> <json> ; prints "<rc>|<stdout>"
  local out rc
  out=$(printf '%s' "$2" | PATH="$tmp/$1" "$hook" 2>/dev/null); rc=$?
  printf '%s|%s' "$rc" "$out"
}
bg='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"command":"sleep 30; echo done","run_in_background":true}}'
fg='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"command":"echo hi","run_in_background":false}}'
noflag='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"command":"echo hi"}}'
wrapped='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"command":"job-run --name mine -- sleep 30","run_in_background":true}}'
other='{"hook_event_name":"PreToolUse","tool_name":"Read","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"file_path":"/tmp/x","run_in_background":true}}'
nocmd='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"run_in_background":true}}'

# --- a background Bash call comes back wrapped -------------------------------
got=$(fire withjr "$bg"); rc=${got%%|*}; body=${got#*|}
cmd=$(printf '%s' "$body" | jq -r '.hookSpecificOutput.updatedInput.command // ""' 2>/dev/null)
[ "$rc" = 0 ] && [[ "$cmd" == job-run\ * ]] && [[ "$cmd" == *"sleep 30; echo done"* ]] \
  && ok "a background Bash call comes back running under job-run" \
  || no "a background Bash call comes back running under job-run" "rc=$rc cmd=$cmd"
[ "$(printf '%s' "$body" | jq -r '.hookSpecificOutput.updatedInput.run_in_background' 2>/dev/null)" = true ] \
  && ok "the rewritten call is still a background call" \
  || no "the rewritten call is still a background call" "$body"

# --- the run name is derived from the call and stable for it -----------------
name=$(printf '%s' "$cmd" | sed -n 's/.*--name \([^ ]*\).*/\1/p')
again=$(fire withjr "$bg"); again=${again#*|}
name2=$(printf '%s' "$again" | jq -r '.hookSpecificOutput.updatedInput.command' | sed -n 's/.*--name \([^ ]*\).*/\1/p')
[ -n "$name" ] && [ "$name" = "$name2" ] \
  && ok "the generated run name is stable for that call" \
  || no "the generated run name is stable for that call" "$name vs $name2"
different=$(fire withjr "${bg/toolu_01AbCdEfGhIjKlMnOp/toolu_01ZzYyXxWwVvUuTtSs}"); different=${different#*|}
name3=$(printf '%s' "$different" | jq -r '.hookSpecificOutput.updatedInput.command' | sed -n 's/.*--name \([^ ]*\).*/\1/p')
[ "$name" != "$name3" ] \
  && ok "a different call gets a different run name" \
  || no "a different call gets a different run name" "both $name"

# With no tool_use_id there is no stable key, so uniqueness wins: two such calls
# must not share a run directory and trip job-run's live-name refusal.
noid='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"sleep 30; echo done","run_in_background":true}}'
n1=$(fire withjr "$noid"); n1=$(printf '%s' "${n1#*|}" | jq -r '.hookSpecificOutput.updatedInput.command' | sed -n 's/.*--name \([^ ]*\).*/\1/p')
n2=$(fire withjr "$noid"); n2=$(printf '%s' "${n2#*|}" | jq -r '.hookSpecificOutput.updatedInput.command' | sed -n 's/.*--name \([^ ]*\).*/\1/p')
[ -n "$n1" ] && [ "$n1" != "$n2" ] \
  && ok "a call with no tool_use_id still gets a distinct run name" \
  || no "a call with no tool_use_id still gets a distinct run name" "$n1 vs $n2"

# --- the hook tells the caller where the record is ---------------------------
printf '%s' "$body" | grep -q "$name" \
  && ok "the feedback names the run so its path is predictable" \
  || no "the feedback names the run so its path is predictable" "$body"

# --- pass-through cases ------------------------------------------------------
# A call the hook has no business touching says nothing at all.
silent() { # silent <name> <path-dir> <json>
  local got rc body
  got=$(fire "$2" "$3"); rc=${got%%|*}; body=${got#*|}
  [ "$rc" = 0 ] && [ -z "$body" ] && ok "$1" || no "$1" "rc=$rc body=$body"
}
# A call it wanted to wrap and could not passes through, but is not silent —
# see the systemMessage assertions below.
passthrough() { # passthrough <name> <path-dir> <json>
  local got rc body
  got=$(fire "$2" "$3"); rc=${got%%|*}; body=${got#*|}
  [ "$rc" = 0 ] && ! printf '%s' "$body" | grep -q updatedInput \
    && ok "$1" || no "$1" "rc=$rc body=$body"
}
silent "a foreground Bash call passes through untouched" withjr "$fg"
silent "a Bash call with no run_in_background field passes through untouched" withjr "$noflag"
silent "a command already running under job-run passes through untouched" withjr "$wrapped"
mentions='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"command":"grep -r job-run flow/bin","run_in_background":true}}'
got=$(fire withjr "$mentions"); body=${got#*|}
printf '%s' "$body" | jq -e '.hookSpecificOutput.updatedInput.command' >/dev/null 2>&1 \
  && ok "a command that merely mentions job-run is still wrapped" \
  || no "a command that merely mentions job-run is still wrapped" "$body"
silent "a non-Bash tool call passes through untouched" withjr "$other"
passthrough "a command the wrapper cannot take passes through" withjr "$nocmd"
passthrough "job-run missing from PATH passes through" nojr "$bg"

# --- and says so, where a record was expected and will not exist -------------
got=$(fire nojr "$bg"); body=${got#*|}
printf '%s' "$body" | jq -e '.systemMessage | test("no.*record"; "i")' >/dev/null 2>&1 \
  && ok "job-run missing from PATH says no record will exist" \
  || no "job-run missing from PATH says no record will exist" "$body"
got=$(fire withjr "$nocmd"); body=${got#*|}
printf '%s' "$body" | jq -e '.systemMessage | test("no.*record"; "i")' >/dev/null 2>&1 \
  && ok "an unwrappable command says no record will exist" \
  || no "an unwrappable command says no record will exist" "$body"
# An already-wrapped command keeps its record, so warning about one would lie.
got=$(fire withjr "$wrapped"); body=${got#*|}
printf '%s' "$body" | grep -qi 'no record' \
  && no "an already-wrapped command is not warned about" "$body" \
  || ok "an already-wrapped command is not warned about"

# --- no input shape blocks, and the hook's own failure is never the tool's ---
blocked=0
for j in "$bg" "$fg" "$noflag" "$wrapped" "$other" "$nocmd" \
         '' 'not json at all' '{}' '{"tool_name":"Bash"}' \
         '{"tool_name":"Bash","tool_input":{"command":null,"run_in_background":true}}'; do
  for p in withjr nojr; do
    got=$(fire "$p" "$j"); rc=${got%%|*}; body=${got#*|}
    [ "$rc" = 0 ] || { no "no input shape produces a non-zero exit" "path=$p rc=$rc json=$j"; blocked=1; }
    printf '%s' "$body" | grep -q '"permissionDecision"' \
      && { no "no input shape produces a block" "path=$p json=$j body=$body"; blocked=1; }
  done
done
[ "$blocked" = 0 ] && ok "no input shape blocks, errors, or fails the tool call"

# --- end to end, through the real job-run ------------------------------------
# The unit cases above stub job-run, so nothing so far proves the rewritten
# command actually survives a shell and leaves the record it promises. This runs
# it, with a command carrying nested quotes and a non-zero exit.
real='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01EndToEndZzYyXx","tool_input":{"command":"echo '"'"'quoted \"x\"'"'"'; echo err >&2; exit 3","run_in_background":true}}'
body=$(printf '%s' "$real" | PATH="$here/../../bin:$PATH" "$hook" 2>/dev/null)
rewritten=$(printf '%s' "$body" | jq -r '.hookSpecificOutput.updatedInput.command')
run_name=$(printf '%s' "$rewritten" | sed -n 's/.*--name \([^ ]*\).*/\1/p')
( export HOME="$tmp/e2e-home"; mkdir -p "$HOME"
  export PATH="$here/../../bin:$PATH"; eval "$rewritten" ) >/dev/null 2>&1
e2e_rc=$?
e2e_dir="$tmp/e2e-home/.cache/agent-jobs/$run_name"
[ "$e2e_rc" = 3 ] \
  && grep -q 'quoted "x"' "$e2e_dir/progress" 2>/dev/null \
  && grep -q 'err' "$e2e_dir/progress" 2>/dev/null \
  && grep -q '^rc=3$' "$e2e_dir/exit" 2>/dev/null \
  && ok "the rewritten command runs, keeps its quoting, and leaves a record" \
  || no "the rewritten command runs, keeps its quoting, and leaves a record" \
       "rc=$e2e_rc cmd=$rewritten $(cat "$e2e_dir/progress" "$e2e_dir/exit" 2>&1)"
line=$(HOME="$tmp/e2e-home" PATH="$here/../../bin:$PATH" job-run --status "$run_name" 2>&1)
case "$line" in finished*rc=3*) ok "--status reads back the record the hook set up" ;;
  *) no "--status reads back the record the hook set up" "$line" ;;
esac

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
