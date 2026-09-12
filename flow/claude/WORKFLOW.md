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

- **Auto-ship** (zero code files, no ticket): edit on `main`, commit, push,
  report. A fenced code block still gets its format check first (formatters
  read fences; `uv run ruff format --check <file>` or equivalent).
- **Code lane**: `implement-dispatch <n>` from `main` gives the ticket a
  workspace and a worker; `implement/SKILL.md` runs it at one of two tiers,
  set by the ticket's `documentation` label. **Light** (label present): the
  worker commits with `Closes #<n>` and pushes to the default branch, no PR,
  no reviewer. **Heavy** (no label): TDD → one round of `/code-review` +
  `/two-axis-code-review` → one verification pass → PR → I merge. Why: a
  doc-only diff is cheaper to revert than to review; code is not.
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
  the deletions and the churn, not the smallest diff.
- **"Do your research"** means online (Exa search / fetch), not the codebase.
  On an agent-workflow or tooling problem, survey prior art from primary
  sources first (GitHub search API, the tools' own repos and docs) before
  proposing a homegrown mechanism — we are not the first to hit it.
- **An automated reminder** ("prompt me when X") is one line in that repo's
  `AGENTS.md` — not a hook, not new tooling. Why: a hook or tool for a
  reminder is more to maintain than the reminder is worth.
- **Summarizing a source**: reword it; any verbatim phrase gets quotation
  marks.

## Personas

Humanizer is a plugin/hook, not this file: it governs *deliverable prose*
only. Facts and reasoning stay in the session's output style. Written
deliverables: match length to the task, no filler.
