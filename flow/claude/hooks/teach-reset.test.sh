#!/usr/bin/env bash
# Contract test for teach-reset.sh: SessionStart after a compaction forgets
# which sections the session (and its subagents) were shown, so the next
# trigger shows its section again; the compacted context no longer holds it.
# Run: bash flow/claude/hooks/teach-reset.test.sh
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=teach-testlib.sh
. "$here/teach-testlib.sh"
kill_hook="$here/teach-process-kill.sh"
section=(" § Killing a process" "A kill gets its own Bash call and nothing else.")

reset() { # <session id> <source>
  jq -n --arg s "$1" --arg src "$2" '{session_id:$s,hook_event_name:"SessionStart",source:$src}' \
    | bash "$here/teach-reset.sh"
}

context "$kill_hook" s1 "ps aux" >/dev/null
RUN_AGENT=a1 context "$kill_hook" s1 "ps aux" >/dev/null
context "$kill_hook" s2 "ps aux" >/dev/null
reset s1 compact; rc=$?
[ "$rc" = 0 ] && echo "PASS: reset exits 0" || { echo "FAIL: reset exited $rc"; fails=1; }
expect_has "extraction: shown again after compaction" "$(context "$kill_hook" s1 "ps aux")" "${section[@]}"
expect_has "extraction: subagent shown again after compaction" "$(RUN_AGENT=a1 context "$kill_hook" s1 "ps aux")" "${section[@]}"
expect_none "another session keeps its record" "$(context "$kill_hook" s2 "ps aux")"

# Only a compaction forgets: a resume keeps the context that holds the text.
reset s2 resume
expect_none "a resume keeps the record" "$(context "$kill_hook" s2 "ps aux")"

finish
