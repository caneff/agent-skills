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
# `--check` is job-run's own test, so the stub hands it to the real script.
real_jr="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../bin" && pwd)/job-run"
printf '#!/bin/bash\n[ "${1-}" = --check ] && exec /bin/bash "%s" "$@"\nexit 0\n' "$real_jr" > "$tmp/withjr/job-run"; chmod +x "$tmp/withjr/job-run"

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

got=$(fire withjr "$bg"); rc=${got%%|*}; body=${got#*|}
cmd=$(printf '%s' "$body" | jq -r '.hookSpecificOutput.updatedInput.command // ""' 2>/dev/null)
[ "$rc" = 0 ] && [[ "$cmd" == job-run\ * ]] && [[ "$cmd" == *"sleep 30; echo done"* ]] \
  && ok "a background Bash call comes back running under job-run" \
  || no "a background Bash call comes back running under job-run" "rc=$rc cmd=$cmd"
[ "$(printf '%s' "$body" | jq -r '.hookSpecificOutput.updatedInput.run_in_background' 2>/dev/null)" = true ] \
  && ok "the rewritten call is still a background call" \
  || no "the rewritten call is still a background call" "$body"

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

# On the reason field itself: $name came out of updatedInput.command, which is in
# the same body, so grepping the body would pass with no feedback at all.
printf '%s' "$body" | jq -e --arg n "$name" \
  '.hookSpecificOutput.permissionDecisionReason | test($n)' >/dev/null 2>&1 \
  && ok "the feedback names the run so its path is predictable" \
  || no "the feedback names the run so its path is predictable" "$body"

short='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"ab","tool_input":{"command":"ls -l","run_in_background":true}}'
sn=$(fire withjr "$short"); sn=$(printf '%s' "${sn#*|}" | jq -r '.hookSpecificOutput.updatedInput.command' | sed -n 's/.*--name \([^ ]*\).*/\1/p')
[ "$sn" = "ls-ab" ] \
  && ok "an id shorter than the slice still lands in the name" \
  || no "an id shorter than the slice still lands in the name" "$sn"

name_for() { # name_for <command> <description-json-fragment, e.g. ,"description":"x">
  local j
  j='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"command":'"$(printf '%s' "$1" | jq -Rs .)"$2',"run_in_background":true}}'
  fire withjr "$j" | sed 's/^[^|]*|//' | jq -r '.hookSpecificOutput.updatedInput.command' \
    | sed -n 's/.*--name \([^ ]*\).*/\1/p'
}
got=$(name_for 'cd /x && make test' ',"description":"Run the full test suite"')
[ "$got" = "Run-the-full-test-suite-IjKlMnOp" ] \
  && ok "the name is taken from the description when there is one" \
  || no "the name is taken from the description when there is one" "$got"
got=$(name_for 'mkdir -p /x' ',"description":""')
case "$got" in job-*) ok "an empty description with a shell-builtin or file-verb first word gets the neutral job- prefix" ;;
  *) no "an empty description with a shell-builtin or file-verb first word gets the neutral job- prefix" "$got" ;; esac
got=$(name_for 'mkdir -p /x' ',"description":"  /// "')
case "$got" in job-*) ok "a description with nothing to slug gets the neutral job- prefix for a builtin or file verb" ;;
  *) no "a description with nothing to slug gets the neutral job- prefix for a builtin or file verb" "$got" ;; esac
# The name sits unquoted in the rewritten command, so the whole command must
# still read as `job-run --name <one legal token> -- bash -c <original>`; a
# metacharacter that survived into the name would split or inject there.
meta_desc='Build $(rm -rf x) & `id`; "quoted" / path'
mj=$(jq -nc --arg d "$meta_desc" '{hook_event_name:"PreToolUse",tool_name:"Bash",tool_use_id:"toolu_01AbCdEfGhIjKlMnOp",tool_input:{command:"sleep 1",description:$d,run_in_background:true}}')
mc=$(fire withjr "$mj" | sed 's/^[^|]*|//' | jq -r '.hookSpecificOutput.updatedInput.command')
case "$mc" in
  "job-run --name "[A-Za-z0-9._-]*" -- bash -c 'sleep 1'") 
    tok=${mc#job-run --name }; tok=${tok%% -- bash -c *}
    case "$tok" in *[!A-Za-z0-9._-]*|"") no "a description with shell metacharacters yields a legal name" "$mc" ;;
      *) ok "a description with shell metacharacters yields a legal name" ;; esac ;;
  *) no "a description with shell metacharacters yields a legal name" "$mc" ;;
esac
got=$(name_for 'sleep 1' ',"description":"--- dashes   and   gaps ---"')
[ "$got" = "dashes-and-gaps-IjKlMnOp" ] \
  && ok "leading dashes are stripped and runs of separators squeezed to one dash" \
  || no "leading dashes are stripped and runs of separators squeezed to one dash" "$got"
got=$(name_for 'mkdir -p /x' ',"description":{"a":1}')
case "$got" in job-*) ok "a non-string description gets the neutral job- prefix for a builtin or file verb" ;;
  *) no "a non-string description gets the neutral job- prefix for a builtin or file verb" "$got" ;; esac
for verb in rm cd mkdir mv cp touch for while if '(cd' '{ cd'; do
  got=$(name_for "$verb -p /x" '')
  case "$got" in job-IjKlMnOp) ok "a leading $verb is never a job name" ;;
    *) no "a leading $verb is never a job name" "$got" ;; esac
done
got=$(name_for 'cd /x
make test' '')
[ "$got" = "job-IjKlMnOp" ] && ok "a multi-line command is named from its first line only" || no "a multi-line command is named from its first line only" "$got"
got=$(name_for 'make test' '')
[ "$got" = "make-IjKlMnOp" ] && ok "another first word still names the job" || no "another first word still names the job" "$got"
got=$(name_for 'sleep 1' ',"description":"A very long description that keeps going well past any sensible name length limit"')
slug=${got%-*}
[ "${#slug}" -le 40 ] && [ "${#slug}" -gt 24 ] \
  && ok "a long description is cut to 40 characters" \
  || no "a long description is cut to 40 characters" "$got"

extra='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"command":"sleep 30","description":"a long job","timeout":600000,"run_in_background":true}}'
got=$(fire withjr "$extra"); body2=${got#*|}
[ "$(printf '%s' "$body2" | jq -r '.hookSpecificOutput.updatedInput.description')" = "a long job" ] \
  && [ "$(printf '%s' "$body2" | jq -r '.hookSpecificOutput.updatedInput.timeout')" = 600000 ] \
  && ok "description and timeout survive the rewrite" \
  || no "description and timeout survive the rewrite" "$body2"

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
# A command is "already wrapped" only where a command can start. Merely naming
# the phrase, even in full, is an ordinary job and deserves its record.
mentions_wrapped() { # mentions_wrapped <expectation> <command>
  local want=$1 cmd=$2 body
  body=$(fire withjr "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Bash\",\"tool_use_id\":\"toolu_01AbCdEfGhIjKlMnOp\",\"tool_input\":{\"command\":$(printf '%s' "$cmd" | jq -Rs .),\"run_in_background\":true}}")
  body=${body#*|}
  local saw=skipped
  printf '%s' "$body" | jq -e '.hookSpecificOutput.updatedInput.command' >/dev/null 2>&1 && saw=wrapped
  [ "$saw" = "$want" ] && ok "$want: $cmd" || no "$want: $cmd" "saw $saw"
}
mentions_wrapped wrapped "grep -r job-run flow/bin"
mentions_wrapped wrapped "grep -r 'job-run --name ' flow/"
mentions_wrapped wrapped "echo 'use job-run --name x'"
mentions_wrapped skipped "job-run --name x -- true"
mentions_wrapped skipped "echo a; job-run --name x -- true"
# job-run refuses a trailing top-level & (#1901); wrapping one would fail the call.
mentions_wrapped skipped "sleep 5 &"
mentions_wrapped wrapped "true && true"
mentions_wrapped wrapped "echo 'q=a&b&'"
mentions_wrapped wrapped "echo x &&"
body=$(fire withjr '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01AbCdEfGhIjKlMnOp","tool_input":{"command":"sleep 5 &","run_in_background":true}}'); body=${body#*|}
printf '%s' "$body" | jq -e '.systemMessage | test("trailing &")' >/dev/null 2>&1 \
  && ok "a trailing & passes through and says why" \
  || no "a trailing & passes through and says why" "$body"
silent "a non-Bash tool call passes through untouched" withjr "$other"
passthrough "a command the wrapper cannot take passes through" withjr "$nocmd"
passthrough "job-run missing from PATH passes through" nojr "$bg"

got=$(fire nojr "$bg"); body=${got#*|}
printf '%s' "$body" | jq -e '.systemMessage | test("no.*record"; "i")' >/dev/null 2>&1 \
  && ok "job-run missing from PATH says no record will exist" \
  || no "job-run missing from PATH says no record will exist" "$body"
got=$(fire withjr "$nocmd"); body=${got#*|}
printf '%s' "$body" | jq -e '.systemMessage | test("no.*record"; "i")' >/dev/null 2>&1 \
  && ok "an unwrappable command says no record will exist" \
  || no "an unwrappable command says no record will exist" "$body"
# A poll loop is refused, not wrapped (#1705): the one case where this hook
# denies, because a loop inside job-run is the spin the no-poll rule bans.
for loop in 'until [ "$(gh run list -q .[0].status)" = completed ]; do sleep 5; done' \
            'gh run rerun 1 && sleep 3 && gh run watch 1' \
            'while true; do sleep 5; done &'; do
  pj=$(jq -nc --arg c "$loop" '{hook_event_name:"PreToolUse",tool_name:"Bash",tool_use_id:"toolu_01AbCdEfGhIjKlMnOp",tool_input:{command:$c,run_in_background:true}}')
  got=$(fire withjr "$pj"); rc=${got%%|*}; body=${got#*|}
  [ "$rc" = 0 ] \
    && [ "$(printf '%s' "$body" | jq -r '.hookSpecificOutput.permissionDecision' 2>/dev/null)" = deny ] \
    && printf '%s' "$body" | jq -e '.hookSpecificOutput.permissionDecisionReason | test("pr_settle.py") and test("gh run watch")' >/dev/null 2>&1 \
    && ! printf '%s' "$body" | jq -e '.hookSpecificOutput.updatedInput' >/dev/null 2>&1 \
    && ok "a poll loop is denied naming pr_settle.py and gh run watch: $loop" \
    || no "a poll loop is denied naming pr_settle.py and gh run watch: $loop" "rc=$rc body=$body"
done

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

# #1703: a call the hook wrapped gets job-run's pipefail and stage naming.
pipe_json='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_use_id":"toolu_01PipeFailXxYyZz","tool_input":{"command":"false | cat","run_in_background":true}}'
body=$(printf '%s' "$pipe_json" | PATH="$here/../../bin:$PATH" "$hook" 2>/dev/null)
rewritten=$(printf '%s' "$body" | jq -r '.hookSpecificOutput.updatedInput.command')
pipe_name=$(printf '%s' "$rewritten" | sed -n 's/.*--name \([^ ]*\).*/\1/p')
( export HOME="$tmp/pipe-home"; mkdir -p "$HOME"
  export PATH="$here/../../bin:$PATH"; eval "$rewritten" ) >/dev/null 2>&1
pipe_rc=$?
pipe_line=$(HOME="$tmp/pipe-home" PATH="$here/../../bin:$PATH" job-run --status "$pipe_name" 2>&1)
[ "$pipe_rc" = 1 ] && [[ "$pipe_line" == *"rc=1"*"pipeline stage 1 of 2"* ]] \
  && ok "a hook-wrapped call fails on a failed pipe stage and names the stage" \
  || no "a hook-wrapped call fails on a failed pipe stage and names the stage" "rc=$pipe_rc $pipe_line cmd=$rewritten"

# #1697: a rewritten background call sent beside Agent calls leaves those Agent
# calls with no auto-mode verdict, so the review wave starts the Codex pass as an
# explicit job-run call the hook leaves alone. The command under test is read
# out of implement/SKILL.md, so the skill text and the hook cannot drift apart.
skill="$here/../../../implement/SKILL.md"
codex_launch=$(awk '/^job-run --name codex-<n> -- /{on=1} on{print} on&&!/\\$/{exit}' "$skill" \
  | sed 's/<n>/1697/g; s/<default>/main/g; s/<[^>]*>/X/g')
codex_json=$(jq -nc --arg c "$codex_launch" \
  '{hook_event_name:"PreToolUse",tool_name:"Bash",tool_use_id:"toolu_01CodexLaunchXx",tool_input:{command:$c,run_in_background:true}}')
got=$(fire withjr "$codex_json"); rc=${got%%|*}; body=${got#*|}
[ -n "$codex_launch" ] && [[ "$codex_launch" == job-run\ --name\ codex-1697\ --\ python3\ *codex-gate-run.py* ]] \
  && ok "implement/SKILL.md gives the Codex launch as an explicit job-run call" \
  || no "implement/SKILL.md gives the Codex launch as an explicit job-run call" "launch=$codex_launch"
[ "$rc" = 0 ] && ! printf '%s' "$body" | grep -q updatedInput \
  && ok "the skill's Codex launch passes the hook with no updatedInput" \
  || no "the skill's Codex launch passes the hook with no updatedInput" "rc=$rc body=$body"
bare_codex=$(jq -nc '{hook_event_name:"PreToolUse",tool_name:"Bash",tool_use_id:"toolu_01CodexBareXxYy",tool_input:{command:"python3 ~/.agents/skills/implement/codex-gate-run.py --ticket 1 --body-file b --base origin/main",run_in_background:true}}')
got=$(fire withjr "$bare_codex"); body=${got#*|}
[[ "$(printf '%s' "$body" | jq -r '.hookSpecificOutput.updatedInput.command // ""')" == job-run\ --name\ *"codex-gate-run.py"* ]] \
  && ok "a bare background Codex call is still wrapped" \
  || no "a bare background Codex call is still wrapped" "$body"
# No doc may show the pass launched bare: every codex-gate-run.py command line in
# a Markdown file sits under a job-run line or inside a job-run call.
repo_root="$(cd "$here/../../.." && pwd)"
bare_docs=$(cd "$repo_root" && git ls-files '*.md' | grep -v '^docs/research/' \
  | xargs grep -n -B1 '^python3 .*codex-gate-run\.py' 2>/dev/null | grep -v -- '-job-run ' | grep 'codex-gate-run\.py')
[ -z "$bare_docs" ] \
  && ok "no doc shows the Codex pass launched as a bare background call" \
  || no "no doc shows the Codex pass launched as a bare background call" "$bare_docs"

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
