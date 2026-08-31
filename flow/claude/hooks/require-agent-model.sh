#!/bin/bash
# Agent model guard (PreToolUse, Agent).
#
# Every Agent call should pass an explicit `model` — a bare call silently
# inherits the session's model, which is often the wrong tier for the work
# (an explore/lookup task doesn't need the session's top-tier model). This
# hook blocks an Agent call that has no `model` field, naming the tier
# rubric in the block message. A call with `model` set passes untouched. A
# fork (`subagent_type: "fork"`) always inherits the parent model by design
# and is exempt — it passes without `model`.

INPUT=$(cat)
tool=$(echo "$INPUT" | jq -r '.tool_name // ""')
[ "$tool" = "Agent" ] || exit 0

subagent_type=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // ""')
[ "$subagent_type" = "fork" ] && exit 0

model=$(echo "$INPUT" | jq -r '.tool_input.model // ""')
[ -n "$model" ] && exit 0

echo "BLOCKED: this Agent call has no 'model'. Pass one — explore/lookup work uses sonnet, review/diagnosis work uses opus. (subagent_type: \"fork\" is exempt: it always inherits the parent model.)" >&2
exit 2
