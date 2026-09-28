#!/usr/bin/env bash
# Guards #1188: § The merge step 2 blocks a heavy PR whose dispositions
# sidecar is missing or empty, and § Before the PR step 5 says the gate
# refuses it. Prose assertion over implement/SKILL.md.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }
fail=0
check_in() { # <section text> <label> <needle>
  case "$1" in *"$3"*) ;; *) echo "FAIL: $2 is missing: $3" >&2; fail=1 ;; esac
}
merge="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
before="$(sed -n '/^### Before the PR$/,/^### The PR$/p' "$skill" | flatten)"
[ -n "$merge" ] && [ -n "$before" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

check_in "$merge" "§ The merge" 'a heavy PR with no verification pass (#1188)'
check_in "$merge" "§ The merge" 'test -s ~/.cache/agent-reviews/<repo>/dispositions-<n>.jsonl'
check_in "$merge" "§ The merge" 'or the merge waits and the worker is sent back to § Review step 2'
check_in "$before" "§ Before the PR" 'when `dispositions-<n>.jsonl` is missing or empty (#1188)'
check_in "$before" "§ Before the PR" '"PR up" waits until it has'
[ "$fail" = 0 ] && echo "ALL PASS" || exit 1
