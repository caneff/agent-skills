#!/usr/bin/env bash
# Contract test for teach-process-kill.sh: a process search (`ps`, `pgrep`,
# `pidof`) answers with SHELL-SAFETY.md § Killing a process once per session.
# Also carries the cases for teach-lib.sh's own failure paths, which every
# teaching hook shares.
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
expect_has "extraction: pgrep in a new session" "$(context "$hook" s2 "pgrep -a python")" "${section[@]}"
expect_has "extraction: pidof after a cd" "$(context "$hook" s3 "cd /tmp && pidof node")" "${section[@]}"
# A subagent's call carries its parent's session id; it has its own once.
expect_has "extraction: a subagent of s1 is its own session" \
  "$(RUN_AGENT=a1 context "$hook" s1 "ps aux")" "${section[@]}"

# Shapes a process search takes before a kill.
expect_has "extraction: pgrep as an if condition" "$(context "$hook" k1 "if pgrep -f hunt; then echo up; fi")" "${section[@]}"
expect_has "extraction: ps in a brace group" "$(context "$hook" k2 "{ ps aux; }")" "${section[@]}"
expect_has "extraction: ps under sudo" "$(context "$hook" k3 "sudo ps -ef")" "${section[@]}"
expect_has "extraction: ps after a comment holding an apostrophe" "$(context "$hook" k4 "# don't kill yet
ps -eo pid,args")" "${section[@]}"

expect_none "unrelated command" "$(context "$hook" s4 "git status")"
expect_none "ps as an argument" "$(context "$hook" s4 "echo ps")"
# A separator inside quotes does not start a command.
expect_none "trigger in a grep pattern" "$(context "$hook" s4 "rg 'foo|pgrep -f' docs/")"
expect_none "trigger in a double-quoted pattern" "$(context "$hook" s4 'grep -n "x; ps -eo" SHELL-SAFETY.md')"
expect_none "trigger after a quoted separator" "$(context "$hook" s4 'git commit -m "stop it; ps aux"')"
expect_none "trigger in a comment" "$(context "$hook" s4 "ls # then ps aux")"
expect_none "trigger in a heredoc body" "$(context "$hook" s4 "cat > kill.sh <<'SH'
ps -eo pid,args
SH")"
# A word that only starts with a trigger is a different command.
expect_none "psql is not ps" "$(context "$hook" s4 "psql -c 'select 1'")"
expect_has "extraction: s4 still unspent after all that" "$(context "$hook" s4 "ps aux")" "${section[@]}"

# A renamed source heading must say so, never print nothing: empty output
# reads as "nothing to teach" (defect class 1).
copy_tree
sed -i 's/^## Killing a process$/## Stopping a process/' "$tmp/tree/claude/SHELL-SAFETY.md"
got=$(context "$tmp/tree/claude/hooks/teach-process-kill.sh" s5 "ps aux")
expect_has "renamed heading is reported, not silent" "$got" "no \"## Killing a process\" heading"

# The same for every other way the text can be missing.
printf '## Killing a process\n\n## Editing\n' > "$tmp/tree/claude/SHELL-SAFETY.md"
expect_has "empty section is reported" \
  "$(context "$tmp/tree/claude/hooks/teach-process-kill.sh" s6 "ps aux")" "has nothing under it"
rm "$tmp/tree/claude/SHELL-SAFETY.md"
expect_has "missing doc is reported" \
  "$(context "$tmp/tree/claude/hooks/teach-process-kill.sh" s7 "ps aux")" "cannot be read"
rm "$tmp/tree/claude/hooks/command-scan-lib.sh"
expect_has "missing lib is reported" \
  "$(context "$tmp/tree/claude/hooks/teach-process-kill.sh" s8 "ps aux")" "command-scan-lib.sh is missing"

finish
