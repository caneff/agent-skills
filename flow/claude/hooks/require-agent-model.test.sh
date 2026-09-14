#!/usr/bin/env bash
# Contract test for require-agent-model.sh: synthetic PreToolUse JSON on
# stdin -> exit 0 (allow) or exit 2 + message on stderr (block).
# Run: bash flow/claude/hooks/require-agent-model.test.sh
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/require-agent-model.sh"
fails=0

# run <name> <expected-exit> <json> [<substring stderr must contain>]
run() {
  local name=$1 want=$2 json=$3 needle=${4:-}
  local out rc
  out=$(printf '%s' "$json" | "$hook" 2>&1)
  rc=$?
  if [ "$rc" != "$want" ]; then
    echo "FAIL: $name — want exit $want, got $rc"; echo "  out: $out"; fails=1; return
  fi
  if [ -n "$needle" ] && [[ "$out" != *"$needle"* ]]; then
    echo "FAIL: $name — stderr missing '$needle'"; echo "  out: $out"; fails=1; return
  fi
  echo "PASS: $name"
}

run "Agent call without model is blocked, names rubric" 2 \
  '{"tool_name":"Agent","tool_input":{"description":"explore code"}}' \
  "explore/lookup"

run "Agent call with model set proceeds" 0 \
  '{"tool_name":"Agent","tool_input":{"description":"explore code","model":"sonnet"}}'

run "fork call without model proceeds" 0 \
  '{"tool_name":"Agent","tool_input":{"description":"fork self","subagent_type":"fork"}}'

run "non-Agent tool call is untouched" 0 \
  '{"tool_name":"Bash","tool_input":{"command":"ls"}}'

run "Explore with opus is blocked" 2 \
  '{"tool_name":"Agent","tool_input":{"description":"explore code","subagent_type":"Explore","model":"opus"}}' \
  "sonnet or haiku"

run "Explore with sonnet proceeds" 0 \
  '{"tool_name":"Agent","tool_input":{"description":"explore code","subagent_type":"Explore","model":"sonnet"}}'

run "Explore with haiku proceeds" 0 \
  '{"tool_name":"Agent","tool_input":{"description":"explore code","subagent_type":"Explore","model":"haiku"}}'

run "Explore with no model is blocked, names Explore rule" 2 \
  '{"tool_name":"Agent","tool_input":{"description":"explore code","subagent_type":"Explore"}}' \
  "sonnet or haiku"

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
