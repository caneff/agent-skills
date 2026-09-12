# Shell safety (read before a search you will assert from, or a process kill)

Pointer target for `CLAUDE.md` § Gotchas.

## Searching

- `rg`, not `grep -r`. It skips gitignored *and* dotted paths by default, so
  a zero-hit result is not evidence of absence — re-run with `-uu` before
  asserting a thing does not exist. `.agents/skills` ignores installed skill
  dirs (its `.gitignore` names them), `twitch-rules-scroller` ignores
  `e2e-artifacts/`, and `.github/` is dotted everywhere.
- `head`/`tail` are for looking, not measuring — `wc -l`/`grep -c` before
  treating file contents as a premise. Why: a truncated view reads as the
  whole file.

## Killing a process

A kill gets its own Bash call and nothing else. Never `pkill -f`/`pgrep -f`
in a command line that names the target anywhere else — a heredoc writing the
script, or a relaunch after the kill, both match and kill your shell (exit
143/144). Default: kill by PID from a separate
`ps -eo pid,args --no-headers | grep '[p]attern'` listing. Bracketing
(`'zb[.]py hunt'`) only stops the pattern matching itself — second line of
defence, not the rule. Why: the kill takes out the shell running the rest
of the step. When the shell dies mid-compound-command the later
steps never ran: a file you "just wrote" may still hold its old contents, so
re-read it before debugging what it does.

## Editing

Prefer a surgical edit over rewriting the whole file when the result is the
same. Why: a whole-file rewrite costs output tokens and time, and can drop
a line nobody meant to touch.
