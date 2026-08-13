# Hard rules — never violate

- **NEVER run `ship`.** Merge is my gate. After I've looked, hand me the exact
  `! ship ...` line — always.
- **NEVER merge or fast-forward `main` onto a worktree branch.** It empties the
  PR the code lane is built around.
- **STOP and ask before** an *irreversible* deletion — an untracked or
  uncommitted file, or a history-rewriting git op — and before adding a
  dependency or changing a database schema. A *tracked* file removed in a commit
  is undoable (git history plus the PR diff I review), so delete it in place as
  part of the change — no ask needed. The bar is "can I undo it," not "is it a
  deletion."
- **Gate 1 — whose repo?** My repo → agent may open the PR. Anyone else's →
  push the branch, stop before the PR, hand me the PR command.
- **Gate 2 — code or decision?** Any code file touched → code lane (`/implement`
  → `pushpr` → I run `ship`). Zero code files → auto-ship docs/decisions to main.

The two gates are detailed under "How work lands"; the principle behind both is
**I see it before another human does.**

# Precedence — highest wins

On conflict, higher wins: (1) hard rules, (2) my live instruction, (3) safety/
verification defaults ("Done means verified", "STOP and ask"), (4) personas
(ponytail build-style, caveman/humanizer prose-style), (5) model defaults.
A persona never overrides a rule above it — it can't make you skip a check, cut
a required feature, or mangle deliverable prose.

# Done means verified

Never report work done without running the smallest check that would fail if it
broke — a test, a build, or re-reading the ask. Say what you checked.

# Communication

## Modes & their scope

Three personas may be active (set by plugins/hooks, not this file). Each governs
one thing, and none overrides a rule under Precedence.

- **Ponytail** — *build* style. Fewest lines that work; skip speculative code.
  Never at the cost of validation, error handling, security, or anything I asked
  for.
- **Caveman** — *talk* style. Terse phrasing for chat, explanation, my reasoning.
  Exempts code, commits, and PRs (write those normal).
- **Humanizer** — *deliverable prose* style. Full natural sentences for anything a
  reader judges for voice: essays, emails, marketing copy, blog posts, docs prose.

Caveman and Humanizer never overlap. Rule of thumb: text read for facts/function
or my reasoning → caveman OK; text a human judges for voice → normal prose, never
caveman.

## Written deliverables

Match length to what the task needs: cover the substance, don't pad with filler
sections, redundant summaries, or boilerplate. Length calibration, not caveman.

## Progress updates

Before your first tool call, say in one sentence what you're about to do. While
working, give a brief update only when you find something important or change
direction. When you finish, lead with the outcome: your first sentence answers
"what happened" or "what did you find," with supporting detail after it.

# Planning/build workflow (Matt Pocock skills)

I use the Matt Pocock skill pipeline for non-trivial work, in every project:
**`/wayfinder` (decide, grill out the fog) → `/to-spec` (crystallize the
conversation into a tracker spec) → `/to-tickets` (slice into tracer-bullet
tickets) → `/implement` (build each ticket).**

- Default to this flow for anything past a trivial edit. Don't shortcut
  straight to `/implement` unless I say so.
- Before kicking off `/implement` for the code pipeline, grill me on the task
  first if any of it is still fuzzy — unclear scope, unstated assumptions, open
  decisions. Skip the grilling only when the task is already crisp.
- An existing PRD doesn't replace `/to-spec` — if the conversation changed
  decisions, `/to-spec` captures the corrected ones.
- Skills live in `~/.agents/skills` (symlinked into `~/.claude/skills`).
- **Never a bare open issue.** Every open issue announces its state; a bare one
  is a signal to classify, not a gap to paper over with any label. Sort it:
  mid-pipeline → its `wayfinder:*`/stage label; a sliced spec → `spec` (its
  parent-reference status); a **spent parent** whose every child has merged →
  **close it, don't relabel**; genuinely untriaged → `needs-triage`; parked/
  someday → `backlog` (or close as not-planned). The bare state is the tell —
  read it, don't label over it.

# How work lands (every repo)

The two gates from the top of this file, in detail.

**Gate 1 — outward: whose repo?** The PR's base repo is the upstream parent for
a fork, else this repo. Owned by me (`gh api user` login) → agent may open the
PR. Owned by anyone else → agent pushes the branch but stops before the PR and
hands me the drafted title/body, the `gh pr create ...` line, and a compare
command; I review, I open it. `pushpr` enforces this itself, so it's safe for
the agent to run.

**Gate 2 — review: code or decision?** Only reached on my own repos. A **code
file** is anything executed, imported, or that changes runtime/tool behavior:
`.py/.ts/.js/.sh/.rs`, `settings.json`, hooks, CI config — and a `.md` that
defines a skill or agent (it changes behavior). **Docs** are ordinary `.md` and
plain prose. When a diff mixes both, it's code.
- **Decision docs** (`/wayfinder`, `/grilling`, `/to-spec`, `/to-tickets`
  output) or a single-file doc edit, touching **zero code files** →
  **auto-ship**: commit straight to main in the main checkout and push. No
  worktree, no PR, no `ship`. If *any* changed path is a code file, this lane
  does not apply — drop to the code lane. Auto-ship is the routine lane for
  docs/decisions — just do it; don't announce "auto-ship was used" in the
  report. Report *what* landed and where, not *which lane* carried it.
  **Fenced code makes a doc gate-relevant.** A `.md` carrying a code block is
  still docs, but formatters read it — `ruff format` checks Python fences in
  Markdown, so an unformatted snippet turns `main` red for every code run that
  follows, and auto-ship skips the gate that would have caught it. Before
  auto-shipping a doc with a fence, run the repo's format check on that file
  (`uv run ruff format --check <file>`, or the project's equivalent) and fix
  what it flags. No fence, no check.
- **Everything else** — `/implement`, multi-file doc changes, README rewrites,
  any diff touching a code file → **code lane**: always run it through
  `/implement` (worktree → TDD → commits → `/code-review` → `pushpr`) → I run
  `ship`. Don't hand-roll the worktree/pushpr steps; invoke `/implement` and let
  it drive. I read every code line before it merges.

`pushpr` and `ship` are my scripts in `~/.local/bin`. The agent may run `pushpr`
(the outward gate makes it self-limiting); it may never run `ship` (see hard
rules).

Worktree handling for the code lane:
- After `pushpr`, immediately `ExitWorktree` with `keep` — the worktree stays on
  disk (no confirm needed) and the session returns to repo root, so my later
  `ship` line runs clean. `ship` must run from repo root: my `!` commands run in
  the agent's cwd, and if the agent is still inside the worktree, ship's
  "remove the worktree first" guard sees itself, skips, and `gh --delete-branch`
  then dies on `'main' is already used by worktree`. Do the ExitWorktree
  silently — the reason is recorded here, no need to narrate it each time.
- If I ask "why don't I see any edits", the answer is "they're in the worktree"
  — not a reason to merge anything. Tests run in the worktree; my checkout sees
  the change when the PR ships, not before.
- A repo with no `origin` can't run the code lane. Say so and offer
  `gh repo create`; don't silently fall back to merging locally.

# Gotchas

- Subagents: fire-and-return work → no `name`, `run_in_background: false`.
  Named + background = persistent teammate that parks idle and returns nothing.
  Test one before fanning out.
- Subagent model: default `model: sonnet` for mechanical retrieval/
  characterization (grep sweeps, surveys, counts, structured reports — no
  judgment inside the agent). Keep Opus where the agent's own reasoning is
  the deliverable: adversarial bug-hunting, diagnosis, design synthesis,
  quality judgment.
- `.claude/worktrees/` must be gitignored. Untracked, it makes the main
  checkout read dirty, and `pushpr` then cuts a junk branch and commits the
  worktree back as a gitlink instead of pushing the worktree branch.
- `head`/`tail` are for looking, not measuring. `wc -l` / `grep -c` before
  treating file contents as a premise.

@RTK.md

# second-brain vault memory (auto-imported by the weekly retro)
@/home/caneff/src/second-brain-v2/Memory/RULES.md
@/home/caneff/src/second-brain-v2/Memory/SOUL.md
