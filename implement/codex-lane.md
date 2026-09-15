# The Codex lane

Swap the build engine from Claude to Codex to spend someone else's quota. The
ceremony around it does not change: same claim, same workspace, same addenda,
same pre-report gate, same merge (`implement/SKILL.md` § The merge). Only who
writes the code moves.

**Opt-in, never inferred.** `--codex` on the invocation, or the owner saying in
so many words that Claude quota is short. A build that reaches for this on its
own has decided the owner's billing for them.

## Preflight

```
codex login status
```

Not `Logged in` — stop and hand the owner `! codex login`. Everything below
runs through the `codex@openai-codex` plugin, which drives the local Codex CLI
under the owner's own auth; there is no second runtime to configure.

Load the plugin's `gpt-5-4-prompting` skill before writing the brief. A prompt
shaped for Claude is not shaped for Codex, and the handoff is one shot.

## The build

Two doors, matching `implement/SKILL.md` § Build:

- **Inline in this workspace** — `/codex:rescue`, one call, carrying the brief
  below. Read the result, not the codebase.
- **No dispatched door yet** — `implement-dispatch` has no `--codex` flag.
  Dispatch normally and build under the inline door from inside the
  workspace. A dispatched Codex door is #688's to decide.

The brief carries what neither engine can infer:

- The ticket body **verbatim** — its acceptance criteria and its named seams
  under test. A pointer to an issue URL is not a brief for an agent that will
  not go fetch it.
- The repo's gate, read from `git config land.testcmd`, and the instruction to
  run it green before finishing.
- `implement/SKILL.md` § Build's TDD rules: failing test first per criterion, no implementation
  ahead of a red test, no scope beyond the ticket.
- Commit to this branch with `Closes #<n>` in the final commit body. Do not
  push, do not open a PR.

**Do not read the codebase yourself, before or after.** That reading is the
entire cost this lane exists to avoid; a "quick look" at the diff spends what
the delegation saved. The owner's `git log -p` is the cheap review of last
resort.

## The reviews

`/multi-axis-code-review`'s three axes are Claude passes and cost Claude
quota. In this lane they swap for:

1. `/codex:review` — correctness on the working diff.
2. `/codex:adversarial-review` — the skeptical pass. Hand it the ticket body
   again; without it there is no spec axis, only taste.

   Both carry `disable-model-invocation: true` (#814): the SlashCommand tool
   never reaches either for a dispatched worker. Invoke the plugin's own
   script instead of the slash command, for each — same commands, and the
   same injection-safety and `--wait` rationale, as `implement/SKILL.md`'s
   Review step:

   ```
   body_file=<absolute path you wrote the ticket body to>
   plugin_root=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['plugins']['codex@openai-codex'][0]['installPath'])" ~/.claude/plugins/installed_plugins.json)
   node "$plugin_root/scripts/codex-companion.mjs" review --wait --base origin/<default>
   node "$plugin_root/scripts/codex-companion.mjs" adversarial-review --wait --base origin/<default> -- "$(cat "$body_file")"
   ```

The one-round-plus-verification cap and the pre-report gate in
`implement/SKILL.md` § Review and § Before the PR: both bind unchanged. So does the
disclosure: the PR body names the reviews that actually ran and says the diff
was written by Codex, not Claude. A reader who assumes a Claude review
happened is reading a claim nobody made.

## When quota runs out mid-run

`/codex:transfer` converts this session into a resumable Codex thread and
returns a `codex resume <session-id>` line. Hand that line to the owner and
stop — it is a handoff, not a delegation, and this skill's driver does not
survive it.
