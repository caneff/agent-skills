#!/bin/bash
# Teaching hook (SessionStart, matcher compact): a compaction drops the
# sections the teaching hooks showed from the context, so this forgets the
# session's record of them, its subagents' included, and the next trigger
# shows its section again. Any other start (startup, resume, clear) keeps the
# record: a resumed or cleared session gets a new id or keeps its context.
# Shared mechanics: teach-lib.sh.

# shellcheck source=teach-lib.sh
TEACH_EVENT=SessionStart
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/teach-lib.sh" 2>/dev/null || {
  printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "Teaching hook error: teach-lib.sh is missing beside teach-reset.sh, so it cannot teach."}}'
  exit 0
}

[ "$TEACH_SOURCE" = compact ] || exit 0
while IFS= read -r record; do rm -f -- "$record"; done < <(session_records)
exit 0
