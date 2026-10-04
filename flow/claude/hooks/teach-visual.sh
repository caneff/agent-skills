#!/bin/bash
# Teaching hook (PreToolUse, Bash): the first `zed` call answers with
# VISUAL-INSPECTION.md § Showing me a file, the first `shot-scraper` call with
# § Reading a rendered page yourself, each once per session, so the calls
# after it follow the section. Shared mechanics: teach-lib.sh.

# shellcheck source=teach-lib.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/teach-lib.sh" 2>/dev/null || {
  printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "Teaching hook error: teach-lib.sh is missing beside teach-visual.sh, so it cannot teach."}}'
  exit 0
}

if runs zed; then
  teach VISUAL-INSPECTION.md "Showing me a file" "\`zed\` opens a file for Chris"
fi
if runs shot-scraper; then
  teach VISUAL-INSPECTION.md "Reading a rendered page yourself" "\`shot-scraper\` reads a rendered page"
fi
teach_emit
