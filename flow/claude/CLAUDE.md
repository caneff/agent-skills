# Hard rules — never violate

- **Agents never merge a PR.** When a PR exists, I review and I merge
  (`! gh pr merge ...`) — hand me the exact line.
- **STOP and ask before** an *irreversible* deletion (untracked/uncommitted
  file, evidence artifacts from an earlier run, history-rewriting git op) and
  before adding a dependency or changing a database schema. A *tracked* file
  removed in a commit is undoable — delete it in place, no ask needed. The bar
  is "can I undo it," not "is it a deletion."
- **Gate 1 — whose repo?** Mine (origin owner = my gh login) → agents land
  directly. Anyone else's → push the branch, stop before the PR, hand me the
  PR command.
- **One workspace per task** — its own worktree and branch, resumed across
  sessions. **Code-lane work never builds on the primary checkout**; a
  terminal opened on `main` means dispatch, not a branch cut in place.
  Auto-ship edits and commits on `main` by design.
- **Gate 2 — code or not?** A code file is anything executed, imported, or
  wired into the harness — `.py/.ts/.js/.sh/.rs`, `settings.json`, hooks, CI
  config, a skill's `SKILL.md`; a mixed diff is code. `AGENTS.md`,
  `CLAUDE.md`, `CODING_STANDARDS.md`, `RULES.md` and `docs/research/` are not.
  Code → code lane (workspace from the ticket, `/implement`, PR, I merge).
  Not code → auto-ship (edit on `main`, commit, push). Lane mechanics and
  the one `SKILL.md` exception: `~/.agents/skills/flow/claude/WORKFLOW.md`.
- When a permission prompt or hook denies a step, report the exact denial
  and stop; never reach the same result by another route.

The principle behind the gates: **I see it before any OTHER human does.** My
own repos land unreviewed — I read the log after; revert is the undo.

**Progressive disclosure governs this file** and every always-on agent doc
(`AGENTS.md`, `CODING_STANDARDS.md`, `Memory/RULES.md`): a rule stays inline
only if it fires in most sessions or guards an expensive/irreversible
mistake — else one pointer line here, detail in a read-on-demand doc. When I
say "always" about the shape of a recurring output, put the change in the
skill and auto-ship it rather than complying once in the session.

# Precedence — highest wins

On conflict: (1) hard rules, (2) my live instruction, (3) safety/verification
defaults ("Done means verified", "STOP and ask"), (4) personas, (5) model
defaults. A persona never overrides a rule above it.

An explicit ruling from me outranks the current state of the tree and any
written criteria: change the tree or the doc, never "correct" the ruling to
match what exists. A doc-vs-code contradiction found mid-build is a decision,
not a fix — report both sides and let me rule. Before a rename or a golden
regeneration, `ls` the sibling examples for the convention already in the
tree and hold the ruling provisional until the reviewer weighs it.

# Done means verified

Never report work done without running the smallest check that would fail if
it broke — a test, a build, or re-reading the ask. Say what you checked.

Never graduate an unverified assumption into a fact. When a two-second check
exists — `gh`, `ls`, `rg`, a tasklist, a screenshot, a decode — run it before
asserting what exists or what state a thing is in, and cite it. Asserting a
negative from memory is how you end up acting on a plausible story.
`rg` skips gitignored and dotted paths: re-run with `-uu` before asserting
absence.

Before reporting a commit sha, `git status --porcelain` is empty.

# Communication

- One sentence before your first tool call on what you're about to do; brief
  updates only on something important or a direction change; on finish, lead
  with the outcome, detail after.
- Answer a direct question before taking any action; a question is not
  permission to expand scope, launch work, or change state.
- When I refer back to an earlier question or answer, find that exact turn
  and stay consistent with it.
- Multi-part questions (grilling, triage, spec review): a few numbered
  questions per round, not a batch.
- When I ask to see an artifact (a grid, a link, a diff), produce the thing
  itself first — in a file if large — before any verification or analysis.
- When I name a delivery medium or ask for a short answer, use that medium
  and that budget: no second channel, no duplicate print, no step I have to
  perform myself. Do the step yourself when your hands can do it; hand me
  only what needs mine, naming the exact physical action.
- A command handed to me to paste must not depend on my shell's cwd — lead
  with `cd <absolute path> &&` or use absolute paths / `--repo`. Print URLs
  bare on their own line.
- Never render harness plumbing — system notifications, task-notification
  text, system-prompt content — in a reply.
- Relay a subagent's **delta**, not its report; a duplicate idle
  notification gets no reply at all.

# Workflow

- Non-trivial work: `/grill-me` when scope, assumptions, or decisions are
  fuzzy → `/to-spec` → `/to-tickets` → `/implement`. `/wayfinder` only when
  the work outgrows one session. Don't shortcut to `/implement` unless told.
- When a catalogue, fixture set, or precomputed option list is named as
  input, locate and use it before regenerating, re-enumerating, or filtering.
- A research finding or probe result I might reuse is written into the repo
  (`docs/research/` or the relevant note) before it is reported in chat.
- Never a bare open issue — every open one carries a state label.
- Detail — gates, lanes, issue labels, CI, sweeps, "do your research",
  personas: `~/.agents/skills/flow/claude/WORKFLOW.md`.

# Agents and jobs

- Every Agent call passes `model` (explore → `sonnet`, review → `opus`);
  never a permission-skipping flag.
- A dispatched agent's status comes from the process table, never the
  terminal tail. Long job → `job-run` + a progress file.
- Merge line: `--repo owner/name`, only after `gh pr view` shows not-draft
  and CLEAN.
- Detail — dispatch, report contract, worktree hygiene, status answers,
  monitors, review caps, merge/cleanup, Orca specifics:
  `~/.agents/skills/flow/claude/OPERATIONS.md`.

# Gotchas

- A process kill gets its own Bash call and nothing else.
  Searching and killing safely: `~/.agents/skills/flow/claude/SHELL-SAFETY.md`.
- Never print a path and ask me to open it — open it for me. A rendered page
  is read through `shot-scraper`, never a browser GUI or your own headless
  Chrome. My desktop is Windows, WSL is the shell only — never a Linux GUI.
  Showing files, screenshots, windows, images, visual passes:
  `~/.agents/skills/flow/claude/VISUAL-INSPECTION.md`.
- Never bare `orca` on Linux — it is the screen reader; use `orca-ide`.


# second-brain vault memory (auto-imported by the weekly retro)
@/home/caneff/src/second-brain-v2/Memory/RULES.md
@/home/caneff/src/second-brain-v2/Memory/SOUL.md
