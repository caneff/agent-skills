#!/usr/bin/env bash
# Lint a Claude Code settings file for the autoMode mistakes that fail silently
# (#1225). The classifier reads `autoMode` only at the top level of the user
# settings, so a block under `permissions` is dead, and a list written without
# "$defaults" replaces the built-in rules for that section instead of adding to
# them (https://code.claude.com/docs/en/auto-mode-config). Prints one line per
# problem; exit 1 on any, 2 on a bad call.
# Usage: settings-lint.sh <settings.json>...
set -uo pipefail
[ $# -gt 0 ] || { echo "usage: settings-lint.sh <settings.json>..." >&2; exit 2; }

# Lists spelled out on purpose, so they carry no "$defaults". soft_deny is
# written out in full since Chris dropped the Instruction Poisoning rule from
# it on 2026-10-04 (docs/research/2026-10-04-auto-mode-self-modification-denials.md).
OWNED_LISTS=(soft_deny)

status=0
problem() { echo "PROBLEM: $1: $2"; status=1; }
for file in "$@"; do
  if [ ! -r "$file" ]; then problem "$file" "cannot read"; continue; fi
  jq -e . "$file" >/dev/null 2>&1 || { problem "$file" "not valid JSON"; continue; }
  if jq -e '.permissions.autoMode' "$file" >/dev/null 2>&1; then
    problem "$file" "permissions.autoMode is never read; move the block to top-level autoMode"
  fi
  for list in environment allow soft_deny hard_deny; do
    case " ${OWNED_LISTS[*]} " in *" $list "*) continue ;; esac
    if jq -e --arg l "$list" '(.autoMode[$l] // null) | type == "array" and (index("$defaults") | not)' "$file" >/dev/null 2>&1; then
      problem "$file" "autoMode.$list has no \"\$defaults\", so it replaces the built-in $list rules"
    fi
  done
done
exit "$status"
