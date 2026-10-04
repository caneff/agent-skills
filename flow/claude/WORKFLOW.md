# Workflow detail (read when landing work, touching issues, or choosing a lane)

Pointer target for `CLAUDE.md` § Hard rules. The one-line rules there are the
invariants; this file holds their exceptions and mechanics.

## Gate 1 — whose repo

Base repo = upstream parent for a fork, else this repo. Anyone else's repo →
hand me the drafted title/body, the `gh pr create ...` line, and a compare
command. The ownership-gated git hook, not prose, is what blocks pushes to
repos I don't own. Why: a push or PR to someone else's repo is seen by another
human before me, and cannot be taken back.

## Undoable or not

STOP and ask is for what cannot be undone: an untracked or uncommitted file,
evidence artifacts from an earlier run, a history-rewriting git op, a new
dependency, a database schema change. The bar is "can I undo it", not "is it
a deletion".

- A *tracked* file removed in a commit is undoable: delete it in place, no
  ask.
- A file a tool wrote and will write again (build output, caches,
  engine-generated stubs and configs such as a plugin's
  `.claude-plugin/types/` or `tsconfig.json`) is undoable: rerunning the tool
  is the undo, so `merge-cleanup --discard` deletes it without asking.
- Two things are not history rewrites, because neither can reach `main` and
  both are recoverable: resolving a conflict inside a rebase already under way
  (`git checkout --ours|--theirs <paths>`, `git rebase --continue|--abort`),
  and `git push --force-with-lease` to a worker's own `implement-*` branch,
  since `--lease` refuses if anyone else pushed and the branch is disposable
  by design.
- Any force-push to `main`, any `--force` without a lease, and any rebase or
  reset I did not already sanction: still ask.

## Gate 2 — the two lanes

**Code file** = anything executed, imported, or wired into the harness:
`.py/.ts/.js/.sh/.rs`, hooks, CI config, and a skill's
`SKILL.md` (its body changes what I do). A mixed diff is code.
**Not code** = `AGENTS.md`, `CLAUDE.md`, `CODING_STANDARDS.md`,
`Memory/RULES.md`, `settings.json` (Chris, 2026-10-03: never the code
lane on its own; a hook script it wires in is still code), and research notes
(`flow/claude/rules/research-notes.md` says which `docs/research/` scripts
count).

**One workspace per task**: its own worktree and branch, resumed across
sessions. A terminal opened on `main` means dispatch (`implement-dispatch
<n>`), not a branch cut in place. Auto-ship edits and commits on `main` by
design.

- **Auto-ship** (zero code files): edit on `main`, commit, push,
  report. A fenced code block still gets its format check first (formatters
  read fences; `uv run ruff format --check <file>` or equivalent).
- **Code lane**: TDD, reviews and a PR, run by `implement/SKILL.md` in a
  workspace. On my repos the controller merges the PR and runs
  `merge-cleanup`; I read it after via `/landed`. Why: code is cheaper to
  review than to revert, and the reviewers have already read it before the
  merge. One exception: a `ready-for-human` ticket's PR gets handed to me
  with the merge line, and I merge it. Why: I marked that work for my own
  hands, so I see it before it lands.
- My insight is after the fact: small honest commits, `/landed` or
  `git log -p`, revert if wrong.
- **The one `SKILL.md` edit that auto-ships**: `flow/claude/rules/skill-files.md`,
  which loads when a session opens a `SKILL.md`.

## Issue state

Every open issue announces its state: `wayfinder:*`/stage if mid-pipeline,
`spec` if a sliced spec, `backlog` if parked, and otherwise the routing role
its filer already knows (`ready-for-agent`, `ready-for-human`, `needs-info`).
`needs-triage` is only for an issue someone outside opened; an agent filing
a follow-up never uses it (`file-ticket/SKILL.md`). Why: an unlabelled issue
is invisible to every queue that picks work by label, and a `needs-triage`
one waits for a manual relabel before anyone can dispatch it. A spent parent (every child merged) gets closed, not relabeled. A
ticket labelled `needs-info` goes through `/grill-with-docs` before
`/implement` — never ad hoc questions in the terminal.

An agent files a ticket through `/file-ticket`, never a bare `gh issue
create`. Why: the skill writes the `## Blocked by` section the frontier
reader (`burndown/frontier.py`) parses; a body without one is `unresolved`
and never dispatched. 2026-09-20: ten tickets "filed from conversation" by
hand the day the section became required, and the next burn's controller
had to resolve all of them before it could dispatch.

## Before filing a ticket

Before any ticket is filed — a review follow-up, a controller observation, a
retro digest item — the open issues on the same file or component are
searched. When one exists, the item goes onto it as a comment
(`gh issue comment <n>`) instead of a new issue. Work under about two minutes
is done on the spot, never ticketed. Why: on 2026-10-04, 295 tickets had been
opened in 14 days against 271 closed, most of them one-paragraph items on a
component that already had an open ticket
(`docs/research/2026-10-04-agent-ticket-inflation.md`). The teaching hook
`hooks/teach-filing.sh` shows this section on the first `gh issue create` of
a session, and on every `gh issue create` lists the open issues its own title
search found.

## Pipeline notes

`/wayfinder` is for work that outgrows one session — a shared map of decision
tickets. `/grill-me` runs when scope, assumptions, or decisions are fuzzy, and
`/to-spec` only when the work needs more than one session. An existing PRD
doesn't replace `/to-spec` if decisions changed since. Why: a PRD written
before a decision changed builds the old decision.
Skills live in `~/.agents/skills` (symlinked into `~/.claude/skills`).

## Rulings and changes to the workflow

- Write each design or content ruling Chris makes into the repo's decisions
  doc when he makes it; a subagent that receives a ruling directly also
  relays it to its spawner. A ruling that supersedes a ticket's text is
  written onto the ticket before a reviewer is dispatched. Why: a ruling held
  only in chat or in one agent is lost at compaction and returns as a
  regression, and the reviewer fetches the ticket as its spec.
- My comment on a ticket sets the standard the diff is measured by; it does
  not hand the agent that fetched it a new task.
- Before a rename or a golden regeneration, `ls` the sibling examples for the
  convention already in the tree, and hold the ruling provisional until the
  reviewer weighs it.
- Before proposing a change to a workflow step or skill rule, find the
  commit or ticket that introduced the current behaviour and state the
  problem it solved; a proposal that undoes it says how that problem stays
  solved. Why: otherwise the change brings back the failure the step was
  written to prevent.

## Auto mode and harness work

Work that changes the harness itself is never dispatched into auto mode
workers. Harness work means `flow/claude/settings.json`, hooks, mods, plugins,
plugin load paths, and sessions driving other sessions. Chris runs it in a
session outside auto mode, where each risky step is one prompt he approves.
Why: the classifier exists to stop exactly this work, and its rules for it
(`Self-Modification`, `Auto-Mode Bypass`, `Instruction Poisoning`,
`Unauthorized Persistence`, and more) are must-name `soft_deny` rules that
no `autoMode.allow` entry clears. Spec #1365 under auto mode cost about a
dozen park-and-relay rounds in burn burn-skills-2026-10-03 (#1389 adds the
pre-dispatch check).

A denial report names the root-cause fix: the user-level settings or
`autoMode` entry that produces the denial, never a per-worktree or one-off
allow. `~/.claude/settings.json` is a symlink to this repo's
`flow/claude/settings.json`; writing the home path through a temp file and
`os.replace`/`mv` swaps the link for a copy (four times on 2026-10-04).

On any classifier denial, read the matched rule before proposing a fix:
`claude auto-mode config`, the rule named in the brackets, its section and
its `must name` clause. The fix options follow from that text, never from a
guess at the classifier. Detail and the six failed guesses it would have
saved: `docs/research/2026-10-04-auto-mode-self-modification-denials.md`
(#1388 makes this a required park step).

## CI

CI is local, not GitHub Actions: a repo's gate is `git config land.testcmd`,
and new repos get no workflow files. Why: the Actions budget ran out on
private repos.

## Requests with a fixed shape

- **A sweep** (cleanup, audit, rename) I asked for is thorough and ruthless —
  the deletions and the churn, not the smallest diff. Why: a timid sweep leaves
  the cruft it was asked to remove and needs a second pass.
- **A named catalogue, fixture set or precomputed option list** is located
  and used before anything is regenerated, re-enumerated or filtered.
- **"Do your research"** means online (Exa search / fetch), not the codebase.
  On an agent-workflow or tooling problem, survey prior art from primary
  sources first (GitHub search API, the tools' own repos and docs) before
  proposing a homegrown mechanism. Why: we are not the first to hit it, and
  the codebase cannot tell you what exists outside it.
- **A git-ignored scratch script that produces something that ships** (a
  published link, a sheet write, a frozen reference build): snapshot the
  script, its inputs and its exact rebuild command into `docs/research/`
  before reporting, and file the ticket that promotes it to tracked tooling.
  Why: scratch is the only copy, and a worktree cleanup or restart loses the
  way to regenerate it.
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
