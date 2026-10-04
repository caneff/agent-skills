#!/usr/bin/env bash
# Contract test for teach-process-kill.sh: a process search (`ps`, `pgrep`,
# `pidof`) answers with SHELL-SAFETY.md § Killing a process once per session.
# Run: bash flow/claude/hooks/teach-process-kill.test.sh
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=teach-testlib.sh
. "$here/teach-testlib.sh"
hook="$here/teach-process-kill.sh"

# The extraction assertion: a sentence from the section body, read off the
# doc's own text, plus the heading the context names as its source.
section=(" § Killing a process" "A kill gets its own Bash call and nothing else.")

got=$(context "$hook" s1 "ps -eo pid,args --no-headers | grep '[z]b[.]py'")
expect_has "extraction: ps returns § Killing a process" "$got" "${section[@]}"
expect_none "second process search in the same session" "$(context "$hook" s1 "pgrep -a python")"
expect_has "pgrep in a new session" "$(context "$hook" s2 "pgrep -a python")" "${section[@]}"
expect_has "pidof after a cd" "$(context "$hook" s3 "cd /tmp && pidof node")" "${section[@]}"

expect_none "unrelated command" "$(context "$hook" s4 "git status")"
expect_none "ps as an argument" "$(context "$hook" s4 "echo ps")"
expect_none "trigger in a grep pattern" "$(context "$hook" s4 "rg 'pgrep -f' docs/")"
expect_none "trigger in a double-quoted pattern" "$(context "$hook" s4 'grep -n "ps -eo" SHELL-SAFETY.md')"
# A separator inside quotes does not start a command.
expect_none "trigger after a quoted separator" "$(context "$hook" s4 'git commit -m "stop it; ps aux"')"
expect_none "trigger in a heredoc body" "$(context "$hook" s4 "cat > kill.sh <<'SH'
ps -eo pid,args
SH")"
# A word that only starts with a trigger is a different command.
expect_none "psql is not ps" "$(context "$hook" s4 "psql -c 'select 1'")"
expect_has "s4 still unspent after all that" "$(context "$hook" s4 "ps aux")" "${section[@]}"

# A renamed source heading must say so, never print nothing: empty output
# reads as "nothing to teach" (defect class 1).
copy_tree
sed -i 's/^## Killing a process$/## Stopping a process/' "$tmp/tree/claude/SHELL-SAFETY.md"
got=$(context "$tmp/tree/claude/hooks/teach-process-kill.sh" s5 "ps aux")
expect_has "renamed heading is reported, not silent" "$got" "Killing a process" "not found"

finish
