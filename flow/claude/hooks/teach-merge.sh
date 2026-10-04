#!/bin/bash
# Teaching hook (PreToolUse, Bash): `gh pr view` and `gh pr checks` are the
# reads that come before a merge, so they answer with OPERATIONS.md § Merge
# preconditions, once per session. Shared mechanics: teach-lib.sh.

# shellcheck source=teach-lib.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/teach-lib.sh"

if runs gh pr view || runs gh pr checks; then
  teach OPERATIONS.md "Merge preconditions" "\`gh pr view\` and \`gh pr checks\` are the reads before a merge"
fi
teach_emit
