#!/usr/bin/env bash
# Shared driver for the teaching-hook tests (teach-*.test.sh). Sourced, never
# run: the runner discovers only `*.test.sh`. Each test feeds a hook the
# PreToolUse JSON Claude Code sends and asserts on the additionalContext it
# prints, never on the hook's internals.
set -uo pipefail
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# The once-per-session record lands under $XDG_CACHE_HOME, so a test run never
# touches, or is fooled by, the real cache.
export XDG_CACHE_HOME="$tmp/cache"
fails=0

# context <hook> <session id> <command> -> the additionalContext printed, or
# nothing. RUN_CWD sets the session cwd the hook is told about (default $PWD);
# RUN_AGENT adds the agent_id a subagent's tool call carries.
# A non-zero exit or output that is not the PreToolUse shape is a failure of
# its own, reported here, so an empty answer always means the hook chose to
# say nothing.
context() {
  local hook=$1 session=$2 cmd=$3 out rc
  out=$(printf '%s' "$cmd" \
        | jq -Rs --arg s "$session" --arg cwd "${RUN_CWD:-$PWD}" --arg a "${RUN_AGENT:-}" \
            '{session_id:$s,cwd:$cwd,hook_event_name:"PreToolUse",tool_name:"Bash",tool_input:{command:.}}
             + (if $a == "" then {} else {agent_id:$a} end)' \
        | PATH="${STUB_PATH:-}${STUB_PATH:+:}$PATH" bash "$hook" 2>"$tmp/stderr")
  rc=$?
  if [ "$rc" != 0 ]; then
    echo "FAIL: $hook exited $rc on '$cmd': $(cat "$tmp/stderr")" >&2; fails=1; return
  fi
  [ -n "$out" ] || return 0
  printf '%s' "$out" | jq -er 'select(.hookSpecificOutput.hookEventName == "PreToolUse")
                               | .hookSpecificOutput.additionalContext' 2>/dev/null \
    || { echo "FAIL: $hook printed a non-PreToolUse answer on '$cmd': $out" >&2; fails=1; }
}

# expect_has <name> <context> <substring>...: every substring is present.
expect_has() {
  local name=$1 got=$2 want
  shift 2
  for want in "$@"; do
    if [[ "$got" != *"$want"* ]]; then
      echo "FAIL: $name — context lacks '$want'"; echo "  got: ${got:0:400}"; fails=1; return
    fi
  done
  echo "PASS: $name"
}

# expect_none <name> <context>: the hook said nothing.
expect_none() {
  if [ -n "$2" ]; then
    echo "FAIL: $1 — want no context, got: ${2:0:400}"; fails=1
  else
    echo "PASS: $1"
  fi
}

# copy_tree: a private copy of the hooks dir and its docs at $tmp/tree/claude,
# for a case that mutates a source doc or removes a file. The hooks find their
# docs and libs beside their own real path, so the copy reads the mutation.
copy_tree() {
  local src
  src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  mkdir -p "$tmp/tree/claude/hooks"
  cp "$src"/*.md "$tmp/tree/claude/"
  cp "$src"/hooks/*.sh "$tmp/tree/claude/hooks/"
}

finish() { [ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }; }
