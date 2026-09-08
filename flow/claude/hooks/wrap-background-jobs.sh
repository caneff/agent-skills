#!/bin/bash
# Background job recorder (PreToolUse, Bash).
#
# A plain `run_in_background` Bash job that is SIGKILLed says nothing on the way
# down, and the only account of it was the process's own stdout, which died with
# it. This hook rewrites such a call to run under `job-run`, so the job leaves a
# directory on disk holding what it printed and how it ended, whether or not it
# survives. Read it back with `job-run --status <name>`.
#
# The name is derived from the call — the first word of the command plus a slice
# of the tool_use_id — so it is stable for that call and unique across calls. The
# caller learns it from the rewritten command, which the background task's own
# completion notice echoes back verbatim; it is repeated in
# permissionDecisionReason rather than in systemMessage, because a warning banner
# on every background job would be noise, and nothing here is a warning.
#
# It degrades, it never blocks. A call it cannot wrap — no command, or `job-run`
# not on PATH — passes through unchanged *and* says so, because the one failure
# worse than no record is an agent believing in a record that was never written.
# An already-wrapped command passes through silently: that record exists.
#
# Every path exits 0. A bookkeeping hook must never be the reason a real command
# does not run, so its own failure is never the tool call's.
#
# Two limits of the wrapping, by design: the job body runs in a fresh `bash -c`,
# so shell functions and aliases the session had defined are not in scope, and
# job-run's tee is line-oriented, so binary output on stdout is not preserved.
# Neither is what a background job wants; a job that needs either should write
# its own file and be run unwrapped.
#
# Ordering: hooks on one matcher each see the original input, their rewrites do
# not chain, and exactly one `updatedInput` survives at random — measured in
# docs/research/run-in-background-reaches-pretooluse.md. `rtk hook claude` also
# rewrites background calls, so registration must leave one producer of
# `updatedInput` for them; see flow/claude/settings.json.
set -u

INPUT=$(cat 2>/dev/null) || exit 0
command -v jq >/dev/null 2>&1 || exit 0

field() { printf '%s' "$INPUT" | jq -r "$1" 2>/dev/null || true; }

IFS=$'\t' read -r tool background id <<<"$(field '
  [ .tool_name // "", (.tool_input.run_in_background // false | tostring),
    .tool_use_id // "" ] | @tsv')"
[ "$tool" = Bash ] || exit 0
[ "$background" = true ] || exit 0

cmd=$(field '.tool_input.command // ""')

# Already under job-run: a record exists, so wrapping again would only risk
# nesting, and warning about a missing record would be a lie. Anchored, not a
# substring — a command that merely mentions job-run (`grep job-run flow/bin/*`)
# is an ordinary job and deserves its record.
case "$cmd" in "job-run "*|*"job-run --name "*) exit 0 ;; esac

skip() { # skip <why> — pass the call through, and say a record will not exist
  jq -nc --arg m "job-run: $1, so this background job runs unwrapped and will leave no record. \`job-run --status\` will not find it." \
    '{systemMessage:$m}'
  exit 0
}

[ -n "$cmd" ] || skip "this call carries no command to wrap"
command -v job-run >/dev/null 2>&1 || skip "job-run is not on PATH (run flow/install.sh)"

# <first word, slugged> - <tail of the tool_use_id>. The id makes concurrent
# runs of the same command distinct, so the wrapper's name-collision refusal
# can never turn into a failed tool call.
slug=$(printf '%s' "${cmd%%[ 	;|&]*}" | tr -c 'A-Za-z0-9' '-' | cut -c1-24)
slug=$(printf '%s' "$slug" | sed 's/-*$//'); slug=${slug:-job}
# With no tool_use_id there is no stable key, and uniqueness has to win: two
# concurrent jobs sharing a name would hit job-run's live-name refusal and fail
# the very tool call this hook promises never to fail.
[ -n "$id" ] || id="$$$RANDOM"
[ ${#id} -gt 8 ] && id=${id: -8}
name="$slug-$(printf '%s' "$id" | tr -c 'A-Za-z0-9' '-')"

# The rewrite edits the original tool_input rather than replacing it, so a
# description or a timeout the caller set survives the wrapping.
out=$(printf '%s' "$INPUT" | jq -c --arg n "$name" --arg c "$cmd" '
  { hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecisionReason: "job-run: recording as \($n); read it with `job-run --status \($n)`",
      updatedInput: (.tool_input + {
        command: ("job-run --name \($n) -- bash -c " + ($c | @sh)),
        run_in_background: true
      }) } }' 2>/dev/null)
# A rewrite that could not be built is a pass-through that says so, never a
# silent one — silence is the hole this hook exists to close.
[ -n "$out" ] || skip "the rewrite could not be built for this call"
printf '%s\n' "$out"
exit 0
