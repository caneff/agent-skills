#!/bin/bash
# Teaching hook (PreToolUse, Bash): the first `zed` call, or the first call of
# an image opener (`wslview` and its kin, #1531), answers with
# VISUAL-INSPECTION.md § Showing me a file, the first `shot-scraper` call with
# § Reading a rendered page yourself, each once per session, so the calls
# after it follow the section. Shared mechanics: teach-lib.sh.

# shellcheck source=teach-lib.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/teach-lib.sh" 2>/dev/null || {
  printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "Teaching hook error: teach-lib.sh is missing beside teach-visual.sh, so it cannot teach."}}'
  exit 0
}

# The openers that put a file or an image in front of Chris; one section, one
# key, so the first of them in a session spends it for all.
for opener in zed wslview xdg-open explorer.exe eog feh mspaint.exe; do
  if runs "$opener"; then
    teach VISUAL-INSPECTION.md "Showing me a file" "\`$opener\` opens a file for Chris"
    break
  fi
done
if runs shot-scraper; then
  teach VISUAL-INSPECTION.md "Reading a rendered page yourself" "\`shot-scraper\` reads a rendered page"
fi
teach_emit
