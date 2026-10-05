# Teaching hook: one live firing (#1412)

2026-10-04, Claude Code 2.1.289. Shows that a teaching hook's PreToolUse
`additionalContext` reaches a real session and that the model reads it.

## Run

From the `implement-1412` worktree, with only that worktree's
`teach-process-kill.sh` wired (`--setting-sources project`, so no user
SessionStart hook ran) and a private `XDG_CACHE_HOME`:

```
claude -p --model haiku --setting-sources project --settings <file wiring teach-process-kill.sh> \
  --allowedTools Bash --output-format stream-json --verbose \
  "Run exactly this Bash command once: ps -eo pid,comm --no-headers | head -3 . Then reply with the first sentence of any reference text that arrived with the tool result, verbatim, or say none arrived."
```

## Result

- Session `50908723-936f-4579-ac4d-63b5ae1569d4`. Its transcript
  (`~/.claude/projects/-home-caneff--agents-skills--claude-worktrees-implement-1412/50908723-936f-4579-ac4d-63b5ae1569d4.jsonl`)
  holds one `hook_success` attachment for `PreToolUse:Bash` (line 23) and one
  `hook_additional_context` attachment (line 24) whose content opens
  `Reference text from .../flow/claude/SHELL-SAFETY.md § Killing a process`.
- The model's final reply was the section's first sentence, verbatim:
  "A kill gets its own Bash call and nothing else."

## Second run: all four hooks (after round-1 fixes)

Same setup with all four `teach-*.sh` wired, one Bash call per trigger:
`ps -eo pid,comm --no-headers | head -2`, `shot-scraper --version`,
`gh pr view 1 --repo caneff/agent-skills --json number`, and
`gh issue create --repo caneff/agent-skills --title 'teach-lib: probe' --help`
(`--help` fires the hook without filing anything). `zed` was left out: it
opens a window on Chris's desktop.

- Session `9c119c36-c321-4984-88cc-68f38eafb079`. Its transcript holds four
  `hook_additional_context` attachments (lines 25, 34, 40, 46), one per
  command: SHELL-SAFETY § Killing a process, VISUAL-INSPECTION § Reading a
  rendered page yourself, OPERATIONS § Merge preconditions, and WORKFLOW
  § Before filing a ticket. The last one ends with its search result: "No
  open issue's title in caneff/agent-skills matches `teach-lib` (...; titles
  only, not bodies)."
- The model's final reply listed all four "Reference text from" lines.

What this does not show: `teach-visual.sh`'s `zed` branch firing live (its
process contract is covered by `teach-visual.test.sh`), and firing through
the user settings file itself. That file, `~/.claude/settings.json`, was a
symlink to `flow/claude/settings.json` when this work started and was a
regular file, drifted from the repo copy, by the end of the same day; until
it is a link again, merging this branch does not wire the hooks into live
sessions (round-1 finding C1).

## Through the live user settings (#1413, 2026-10-04)

`~/.claude/settings.json` is a link to `flow/claude/settings.json` again, so
the caveat above no longer holds. Checked with the user settings loaded, not
`--setting-sources project`: from a scratch directory, `claude -p --model
claude-haiku-4-5-20251001 --allowedTools='Bash(ps:*)'` was asked to run
`ps -o pid= -p 1` twice. The session's transcript
(`2d6eb335-9713-463a-9d60-712ef5a42702.jsonl`) holds one
`hook_additional_context` attachment, after the first call, carrying
SHELL-SAFETY.md § Killing a process, and none after the second; the cache
record for that session lists the section once. The stream-json output does
not carry `additionalContext`, so read the transcript, not the stream.

## What #1417 changed in block-dangerous-git.sh

Moving the scanner into `command-scan-lib.sh` changed the guard on purpose in
two ways, named here because the spec said the blocking guards stay as they
are: the guard blocks every Bash command when the lib is missing (fail
closed), and the scanner drops unquoted `#` comments and reads byte by byte.
The comment rule closed a bypass (an apostrophe in a comment opening a quote
that hid a later `gh pr merge`), and the spec-level review of #1409 found it
opened one (`a\ #x`, an escaped blank read as a word break). #1413 fixed that
and two older scanner gaps (`<<<` and a `<<` shift read as heredoc openers),
each with a guard test in `block-dangerous-git.test.sh`.

## When the same call is denied (#1423, 2026-10-04)

Question (finding C9 of #1413's review): `teach_emit` spends a section when it
prints it, so does PreToolUse `additionalContext` still reach the model when
the same Bash call is then denied? Claude Code 2.1.289, `claude -p --model
claude-haiku-4-5-20251001 --setting-sources project`, a private
`XDG_CACHE_HOME`, `teach-process-kill.sh` wired, asked to run
`ps -o pid= -p 1` once:

| Denial | Session | Tool result | `hook_additional_context` (transcript line 23) | Model's reply |
|---|---|---|---|---|
| a second PreToolUse hook beside it exits 2 | `72c7da7a-c771-44ce-a212-194f717c6ed1` | `PreToolUse:Bash hook error: ... denied by a parallel hook` | present, SHELL-SAFETY § Killing a process | quoted its first sentence, said the command was denied |
| no `--allowedTools`, so the permission prompt denies | `6d7bebcb-fcb5-413e-a7f0-b0c9f30b89a5` | `This command requires approval` | present, same section | quoted its first sentence, said the command was denied |
| `--permission-mode auto` | `e35e5bd5-f425-470d-911c-b4251151c3d3` | `This command requires approval` | present, same section | quoted its first sentence, said the command was denied |

All three transcripts are under
`~/.claude/projects/-tmp-claude-1000-probe/<session>.jsonl`; the cache record
of each run lists the section once.

Ruling: a denial does not drop the context, so the record stays on PreToolUse
and `teach_emit` is unchanged. The auto-mode run ended in the same
"requires approval" denial as the permission prompt, headless; an interactive
auto-mode classifier denial of a call the classifier judges unsafe was not
separately produced, and is inferred to behave the same since it decides after
PreToolUse.
