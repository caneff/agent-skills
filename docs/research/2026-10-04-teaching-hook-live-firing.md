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

What this does not show: the other three hooks firing live (their process
contract is covered by their `*.test.sh`), and firing through the user
settings file itself, which takes effect only once the branch is merged.
