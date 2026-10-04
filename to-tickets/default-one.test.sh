#!/usr/bin/env bash
# Guards #1402 (process redesign stage 2, docs/agents/process-redesign.md):
# planning makes one ticket by default. `to-tickets` slices only into pieces
# on disjoint files that can run at once and says why each slice exists;
# `to-spec` is for work that needs more than one session, else one ticket.
# Prose assertions over the two skills; no Python harness can make them.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tickets="$(tr '\n' ' ' <"$here/SKILL.md" | tr -s ' ')"
spec="$(tr '\n' ' ' <"$here/../to-spec/SKILL.md" | tr -s ' ')"
fail=0
need() { # <text> <needle> <where>
  case "$1" in *"$2"*) ;; *) echo "FAIL: $3 is missing: $2" >&2; fail=1 ;; esac
}
lack() { # <text> <needle> <where>
  case "$1" in *"$2"*) echo "FAIL: $3 must not contain: $2" >&2; fail=1 ;; esac
}
w=to-tickets/SKILL.md
need "$tickets" 'default output is **one** ticket' $w
need "$tickets" 'disjoint files' $w
need "$tickets" 'at the same time' $w
need "$tickets" 'why each slice exists' $w
need "$tickets" "under a day's agent work" $w
lack "$tickets" 'tracer-bullet tickets' $w
lack "$tickets" 'sized to fit in a single fresh context window' $w
w=to-spec/SKILL.md
need "$spec" 'more than one session' $w
need "$spec" 'single ticket' $w
[ "$fail" -eq 0 ] && echo "PASS to-tickets/default-one.test.sh"
exit "$fail"
