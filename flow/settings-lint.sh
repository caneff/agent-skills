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

command -v jq >/dev/null 2>&1 || { echo "settings-lint.sh: jq is not installed" >&2; exit 2; }

# One jq program reads the whole autoMode shape and prints a line per problem,
# so a jq failure is its own exit status and never reads as "no problem": a
# block of the wrong type is reported here, not passed over.
program='
  def lists: ["environment", "allow", "soft_deny", "hard_deny"];
  (if (.permissions | type) == "object" and (.permissions | has("autoMode"))
   then ["permissions.autoMode is never read; move the block to top-level autoMode"] else [] end)
  + (if has("autoMode") and (.autoMode | type) != "object"
     then ["autoMode must be an object, not " + (.autoMode | type)]
     elif has("autoMode") then
       [lists[] as $l | .autoMode as $m
        | if ($m | has($l) | not) then empty
          elif ($m[$l] | type) != "array" then "autoMode.\($l) must be an array, not \($m[$l] | type)"
          elif ($owned | index($l)) then empty
          elif ($m[$l] | index("$defaults") | not) then "autoMode.\($l) has no \"$defaults\", so it replaces the built-in \($l) rules"
          else empty end]
     else [] end)
  | .[]'
owned_json=$(printf '%s\n' "${OWNED_LISTS[@]}" | jq -R . | jq -s .)

status=0
problem() { echo "PROBLEM: $1: $2"; status=1; }
for file in "$@"; do
  if [ ! -r "$file" ]; then problem "$file" "cannot read"; continue; fi
  jq -e . "$file" >/dev/null 2>&1 || { problem "$file" "not valid JSON"; continue; }
  found=$(jq -r --argjson owned "$owned_json" "$program" "$file" 2>&1) ||
    { problem "$file" "jq could not read it: $found"; continue; }
  while IFS= read -r line; do [ -z "$line" ] || problem "$file" "$line"; done <<< "$found"
done
exit "$status"
