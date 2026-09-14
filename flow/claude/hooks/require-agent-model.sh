#!/bin/bash
# Agent model guard (PreToolUse, Agent).
#
# Every Agent call should pass an explicit `model` — a bare call silently
# inherits the session's model, which is often the wrong tier for the work
# (an explore/lookup task doesn't need the session's top-tier model). This
# hook blocks an Agent call that has no `model` field, naming the tier
# rubric in the block message. A fork (`subagent_type: "fork"`) always
# inherits the parent model by design and is exempt — it passes without
# `model`. `subagent_type: "Explore"` is read-only search by definition, so
# it has a second, tighter gate: only `model: sonnet` or `model: haiku`
# pass, everything else (including opus, fable, or no model) is blocked.
# Every other Agent call just needs `model` set to some value.

INPUT=$(cat)
tool=$(echo "$INPUT" | jq -r '.tool_name // ""')
[ "$tool" = "Agent" ] || exit 0

subagent_type=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // ""')
[ "$subagent_type" = "fork" ] && exit 0

model=$(echo "$INPUT" | jq -r '.tool_input.model // ""')

if [ "$subagent_type" = "Explore" ]; then
  case "$model" in
    sonnet|haiku) exit 0 ;;
    *)
      echo "BLOCKED: Explore is a read-only search agent — pass model: sonnet or haiku, never opus or fable." >&2
      exit 2
      ;;
  esac
fi

[ -n "$model" ] && exit 0

echo "BLOCKED: this Agent call has no 'model'. Pass one — explore/lookup work uses sonnet, review/diagnosis work uses opus. (subagent_type: \"fork\" is exempt: it always inherits the parent model.)" >&2
exit 2
