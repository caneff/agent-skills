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
