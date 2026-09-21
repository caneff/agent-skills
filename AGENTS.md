## Agent skills

### Issue tracker

Issues tracked in GitHub Issues via the `gh` CLI; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Six canonical roles, all mapped to their default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `backlog`, `wontfix`). See `docs/agents/triage-labels.md`.

### Include closure

None — no file in this repo is generated from another. Add a `**Directive**:` and a `**Generator**:` line here the day that stops being true. The grammar, and what a run does with it: `burndown/references/closure.md`.

### Skill frontmatter

`disable-model-invocation: true` means **not auto-invocable**: the skill runs
when someone types its command, never off model inference. It is the norm
here, not an exception — 53 of 79 `SKILL.md` files carry it, `implement`
among them — so it says nothing about whether a skill is live.

A **parked** skill is marked two ways and only these two: a `Parked: ` prefix
on its `description:`, and a `> **Parked**` banner under the frontmatter
saying what is retired and what will revive it. Both are prose. Unparking
removes both and touches no frontmatter key.

(2026-09-20, #899: a controller brief called the frontmatter key a parked
marker and told a worker to cut it from two skills. The worker checked before
cutting — the key predates the parking commit `207fee4`, which touched only
`description:` — and a grep treating it as a marker would have flagged 53
live skills. Anything claiming to detect parked state matches exactly the
parked files and no live skill; that property is the test.)

### Recurring defect classes

Three shapes have each been caught more than four times here since
2026-09-14, every one in code written to prevent the thing it failed at.
Check for them by name — a worker before reporting done, a review axis as
part of its brief:

1. **An absent or malformed answer read as a benign one.** Could this
   success have been produced by the thing not running at all?
2. **A stated fallback with no mechanism behind it.** A rule is not shipped
   until something can carry it out.
3. **A test that passes for a reason other than the one it claims.** When a
   mutation goes red, read the message and confirm it is your assertion.

The shapes, the checks and every instance: `docs/agents/defect-classes.md`.

### Section references

A `§ <Heading>` cross-reference in Markdown is checked by
`tests/check-section-references.py`. The grammar: `docs/agents/section-references.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## End-to-end seam

- **Seam**: `bash tests/all.sh`
- **Blind to**: anything a human reads rather than a test asserts: whether a model follows a skill's prose, whether a present `SKILL.md` instruction is also unambiguous, and the harness behaviours around them (a hook denying a step, a worker spinning on no-op tool calls, a pane closing before a question is answered, #925)

The gate runs the repo's shell and Python suites. The grammar and its reader: `implement-spec/references/closing-ticket.md`.
