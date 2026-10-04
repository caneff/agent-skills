#!/bin/bash
# Teaching hook (PreToolUse, Bash): a process search usually comes just
# before a kill, so it answers with SHELL-SAFETY.md § Killing a process, once
# per session. Shared mechanics: teach-lib.sh.

# shellcheck source=teach-lib.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/teach-lib.sh"

if runs ps || runs pgrep || runs pidof; then
  teach SHELL-SAFETY.md "Killing a process" "a process search usually precedes a kill"
fi
teach_emit
