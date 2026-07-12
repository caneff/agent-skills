---
name: skill-audit
description: Audit ~/.agents/skills for model-invocable skills that cost context but go unused, so you can flip stale ones to `disable-model-invocation: true`. Slash-only.
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
invoke type (model / slash-only), last-used date, age. Model-invocable skills unused
past the threshold are flagged `<-- FLIP` and listed at the bottom.

## How it reads usage

Skill invocations log as `"skill":"<name>"` in Claude Code transcripts under
`~/.claude/projects/**/*.jsonl` — **including subagent logs nested two dirs deeper**,
which is why the scan recurses. Last-used = newest timestamp on any line naming the skill.
"NEVER" means no invocation in retained transcript history (logs get pruned, so treat
NEVER as "not lately", not "not ever").

## Acting on results

Don't blanket-flip. Per candidate, ask: *would I want the model to auto-fire this?*
- **No — I'll call it by hand** (setup/convert/niche skills): flip it. Add
  `disable-model-invocation: true` to its frontmatter.
- **Yes — broadly useful, just hasn't come up** (`uv`, `diagnosing-bugs`,
  `resolving-merge-conflicts`, `read-the-damn-docs`): keep model-invocable. Unused ≠ useless.

Flipping = add one frontmatter line; no symlink or reinstall change needed.
