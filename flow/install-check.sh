#!/usr/bin/env bash
# Check that the live ~/.claude matches this repo (#1224): settings.json is the
# link install.sh makes, every installed hook is linked to its repo file, and
# every repo hook is registered in settings.json or named in
# hooks-manifest.sh as unregistered by design. Prints one line per problem and
# exits 1 on any; exit 0 means all of it holds.
# Usage: install-check.sh [--home <dir>] [--flow <dir>]
set -uo pipefail
flow="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
home="$HOME"
while [ $# -gt 0 ]; do
  case "$1" in
    --home) home="${2:?--home needs a dir}"; shift 2 ;;
    --flow) flow="${2:?--flow needs a dir}"; shift 2 ;;
    *) echo "usage: install-check.sh [--home <dir>] [--flow <dir>]" >&2; exit 2 ;;
  esac
done
# shellcheck source=hooks-manifest.sh
. "$flow/hooks-manifest.sh" || { echo "cannot read $flow/hooks-manifest.sh" >&2; exit 2; }
settings="$flow/claude/settings.json"
problems=0
problem() { echo "PROBLEM: $*"; problems=$((problems + 1)); }

# A link counts only when it resolves to the repo file; a plain file is the
# #1412 drift, where repo edits stopped reaching live sessions.
linked_to() { # <live path> <repo file>
  [ -L "$1" ] && [ "$(readlink -f "$1")" = "$(readlink -f "$2")" ]
}

live_settings="$home/.claude/settings.json"
if [ -L "$live_settings" ]; then
  linked_to "$live_settings" "$settings" ||
    problem "$live_settings is a link to $(readlink -f "$live_settings"), not $settings"
elif [ -e "$live_settings" ]; then
  problem "$live_settings is a regular file, not a link to $settings: repo edits never reach live sessions and live edits never reach the repo. Merge its live-only entries into the repo copy, then re-run install.sh"
else
  problem "$live_settings is missing: run flow/install.sh"
fi

for h in "${LINKED_HOOKS[@]}"; do
  linked_to "$home/.claude/hooks/$h" "$flow/claude/hooks/$h" ||
    problem "$h is not linked: $home/.claude/hooks/$h should link to $flow/claude/hooks/$h (run flow/install.sh)"
done

# A misplaced autoMode block or a list missing "$defaults" is silent damage.
lint_out=$(bash "$(dirname "${BASH_SOURCE[0]}")/settings-lint.sh" "$settings") || {
  while IFS= read -r line; do problem "${line#PROBLEM: }"; done <<< "$lint_out"
}

commands=$(jq -r '[.. | objects | select(has("command")) | .command] | .[]' "$settings") ||
  { echo "cannot read hook commands from $settings" >&2; exit 2; }
in_array() { local x=$1; shift; for e in "$@"; do [ "$e" = "$x" ] && return 0; done; return 1; }
for path in "$flow"/claude/hooks/*.sh; do
  h=$(basename "$path")
  case "$h" in *.test.sh | *-lib.sh | *testlib.sh) continue ;; esac
  line=$(printf '%s\n' "$commands" | grep -F "/$h" | head -n1)
  if [ -z "$line" ]; then
    in_array "$h" "${UNREGISTERED_BY_DESIGN[@]}" ||
      problem "$h is not registered in $settings and is not listed in UNREGISTERED_BY_DESIGN"
  elif [[ "$line" == *"/.claude/hooks/$h"* ]] && ! in_array "$h" "${LINKED_HOOKS[@]}"; then
    problem "$h is registered under ~/.claude/hooks but is not in LINKED_HOOKS, so install.sh never links it"
  fi
done

[ "$problems" = 0 ] && echo "install check: ok"
[ "$problems" = 0 ]
