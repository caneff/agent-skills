---
name: skill-audit
description: "Audit ~/.agents/skills for model-invocable skills that cost context but go unused, so you can flip stale ones to `disable-model-invocation: true`."
disable-model-invocation: true
argument-hint: "[stale-days]"
---

Find skills whose `name`+`description` load into every context window (model-invocable)
but which are never actually used — prime candidates to flip to
`disable-model-invocation: true` (drops them from context, keeps `/slash`).

## Run

```bash
uv run --no-project python ~/.agents/skills/skill-audit/audit.py [stale-days]
```

`stale-days` defaults to 45. Prints a table of every skill under `~/.agents/skills`:
invoke type (model / slash-only), last-used date, age. Below the table it prints a
**numbered list** of the model-invocable skills unused past the threshold — the
stale candidates, nothing auto-decided.

## Flip the ones you pick

Staleness is a signal, not a verdict, so the report never flips anything on its own.
Read the numbered list, then re-run with the numbers you choose:

```bash
uv run --no-project python ~/.agents/skills/skill-audit/audit.py [stale-days] --flip 1,3
```

That adds `disable-model-invocation: true` to each picked skill's frontmatter (keeps
`/slash`, drops it from every context window). It is idempotent — a skill already
slash-only is left alone. The numbers come from the current report; pass the same
`stale-days` so they line up. Re-run without `--flip` to see the updated table.

## How it reads usage

Skill invocations log as `"skill":"<name>"` in Claude Code transcripts under
`~/.claude/projects/**/*.jsonl` — **including subagent logs nested two dirs deeper**,
which is why the scan recurses. Last-used = newest timestamp on any line naming the skill.
"NEVER" means no invocation in retained transcript history (logs get pruned, so treat
NEVER as "not lately", not "not ever").

## Which numbers to pick

Don't blanket-flip. Per candidate, ask: *would I want the model to auto-fire this?*
- **No — I'll call it by hand** (setup/convert/niche skills): pick its number.
- **Yes — broadly useful, just hasn't come up** (`diagnosing-bugs`,
  `resolving-merge-conflicts`, `read-the-damn-docs`): leave it. Unused ≠ useless.

Also leave anything the model *chains* — a skill another skill invokes by
name. Check the candidate's name against every other skill's body, not just
its own frontmatter: `implement`, `wayfinder`, and `ww` are the current
callers, but the roster changes as skills change, so grep for the name
rather than trusting a fixed list. `disable-model-invocation: true` blocks
that call, so flipping a chained skill breaks its caller even if the skill
itself looks unused.

Flipping = add one frontmatter line; no symlink or reinstall change needed.
