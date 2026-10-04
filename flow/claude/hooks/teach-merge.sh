#!/bin/bash
# Teaching hook (PreToolUse, Bash): `gh pr view` and `gh pr checks` are the
# reads that come before a merge, so they answer with OPERATIONS.md § Merge
# preconditions, once per session. Shared mechanics: teach-lib.sh.

# Cheap exit before any parsing: most Bash calls are not a gh pr read.
input=$(cat)
case "$input" in *gh*pr*) ;; *) exit 0 ;; esac

# shellcheck source=teach-lib.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/teach-lib.sh" <<< "$input"

if runs gh pr view || runs gh pr checks; then
  teach OPERATIONS.md "Merge preconditions" "\`gh pr view\` and \`gh pr checks\` are the reads before a merge"
fi
teach_emit
