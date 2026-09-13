# Workflow detail (read when landing work, touching issues, or choosing a lane)

Pointer target for `CLAUDE.md` § Workflow. The inline rules there are the
invariants; this file holds the mechanics.

## Gate 1 — whose repo

Base repo = upstream parent for a fork, else this repo. Anyone else's repo →
hand me the drafted title/body, the `gh pr create ...` line, and a compare
command. The ownership-gated git hook, not prose, is what blocks pushes to
repos I don't own. Why: a push or PR to someone else's repo is seen by another
human before me, and cannot be taken back.

## Gate 2 — the two lanes

**Code file** = anything executed, imported, or wired into the harness:
`.py/.ts/.js/.sh/.rs`, `settings.json`, hooks, CI config, and a skill's
`SKILL.md` (its body changes what I do). A mixed diff is code.
**Not code** = `AGENTS.md`, `CLAUDE.md`, `CODING_STANDARDS.md`,
`Memory/RULES.md`, research notes and the scripts under `docs/research/`
that nothing imports or runs.

- **Auto-ship** (zero code files): edit on `main`, commit, push,
  report. A fenced code block still gets its format check first (formatters
  read fences; `uv run ruff format --check <file>` or equivalent).
- **Code lane**: TDD, reviews and a PR I merge, run by `implement/SKILL.md`
  in a workspace. Why: code is cheaper to review than to revert.
- **A dispatched ticket** (`implement-dispatch <n>` from `main`) runs at its
  **tier** (`~/.agents/skills/CONTEXT.md`): heavy is the code lane; light, for a
  `documentation` label, lands like auto-ship but from its own workspace.
  Why: a doc-only diff is cheaper to revert than to review, and the workspace
  keeps the primary checkout from being built on.
- My insight is after the fact: small honest commits, `/landed` or
  `git log -p`, revert if wrong.
- **The one `SKILL.md` edit that auto-ships**: a change that only alters the
  shape of a recurring report I said "always" about (a burndown verdict
  table, a report format). Anything else in a skill is code lane. Why: a
  skill body changes what every later session does.

## Issue state

Every open issue announces its state: `wayfinder:*`/stage if mid-pipeline,
`spec` if a sliced spec, `needs-triage` if genuinely untriaged, `backlog` if
parked. Why: an unlabelled issue is invisible to every queue that picks work
by label. A spent parent (every child merged) gets closed, not relabeled. A
ticket labelled `needs-info` goes through `/grill-with-docs` before
`/implement` — never ad hoc questions in the terminal.

## Pipeline notes

`/wayfinder` is for work that outgrows one session — a shared map of decision
tickets. Everyday non-trivial work: `/grill-me` when scope, assumptions, or
decisions are fuzzy → `/to-spec` → `/to-tickets` (tracer-bullet slices) →
`/implement`. An existing PRD doesn't replace `/to-spec` if decisions changed
since. Why: a PRD written before a decision changed builds the old decision.
Skills live in `~/.agents/skills` (symlinked into `~/.claude/skills`).

## CI

CI is local, not GitHub Actions: a repo's gate is `git config land.testcmd`,
and new repos get no workflow files. Why: the Actions budget ran out on
private repos.

## Requests with a fixed shape

- **A sweep** (cleanup, audit, rename) I asked for is thorough and ruthless —
  the deletions and the churn, not the smallest diff. Why: a timid sweep leaves
  the cruft it was asked to remove and needs a second pass.
- **"Do your research"** means online (Exa search / fetch), not the codebase.
  On an agent-workflow or tooling problem, survey prior art from primary
  sources first (GitHub search API, the tools' own repos and docs) before
  proposing a homegrown mechanism. Why: we are not the first to hit it, and
  the codebase cannot tell you what exists outside it.
- **An automated reminder** ("prompt me when X") is one line in that repo's
  `AGENTS.md` — not a hook, not new tooling. Why: a hook or tool for a
  reminder is more to maintain than the reminder is worth.
- **Summarizing a source**: reword it; any verbatim phrase gets quotation
  marks. Why: unmarked verbatim text passes someone else's words off as mine.

## Personas

Humanizer is a plugin/hook, not this file: it governs *deliverable prose*
only. Facts and reasoning stay in the session's output style — why: a
humanized fact is harder to check than a plain one. Written deliverables:
match length to the task, no filler.
