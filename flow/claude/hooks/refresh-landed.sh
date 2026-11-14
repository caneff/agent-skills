#!/usr/bin/env bash
# PostToolUse(Bash) hook: refresh the landed review page after a push.
#
# Contract: read the Bash tool-call JSON on stdin; if the command pushed
# anything, regenerate the landed page in the background. Otherwise do
# nothing. Always exit 0 — never block the turn.

set -u

# Resolve generate.py relative to this hook's real location (it is installed
# as a symlink into ~/.claude/hooks, so follow the symlink first) rather than
# hard-coding a path: repo_root/landed/generate.py, where repo_root is three
# levels up from flow/claude/hooks.
hook_path="$(readlink -f "$0")"
repo_root="$(cd "$(dirname "$hook_path")/../../.." && pwd)"

# The command that just ran (empty string if absent / jq missing).
cmd="$(jq -r '.tool_input.command // ""' 2>/dev/null)"

# Cheap pre-filter: bail unless this was a push. A stray match only costs a
# ~1s regen.
case "$cmd" in
  *push*) ;;
  *) exit 0 ;;
esac

# Any push: refresh the landed review page in the background (~1s, 0 tokens).
python3 "$repo_root/landed/generate.py" >/dev/null 2>&1 &

exit 0
