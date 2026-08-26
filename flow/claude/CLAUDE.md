# Hard rules — never violate

- **NEVER run `ship`.** Merge is my gate. After I've looked, hand me the exact
  `! ship ...` line — always.
- **NEVER merge or fast-forward `main` onto a worktree branch.** It empties the
  PR the code lane is built around.
- **STOP and ask before** an *irreversible* deletion (untracked/uncommitted
  file, history-rewriting git op) and before adding a dependency or changing a
  database schema. A *tracked* file removed in a commit is undoable — delete it
  in place, no ask needed. The bar is "can I undo it," not "is it a deletion."
- **Gate 1 — whose repo?** My repo → agent may open the PR. Anyone else's →
  push the branch, stop before the PR, hand me the PR command.
- **Gate 2 — code or decision?** Any code file touched → code lane (`/implement`
  → `pushpr` → I run `ship`). Zero code files → auto-ship docs/decisions to main.
- Code-lane mechanics (worktree, `pushpr`, `ship`) live in `/implement`.

Gates detailed under "How work lands"; the principle behind both: **I see it
before another human does.**

**Progressive disclosure governs this file:** pointer inline, detail in a
read-on-demand doc read via the Read tool. A rule stays inline only if it
fires in most sessions or guards an expensive/irreversible mistake — else it
gets a pointer.

# Precedence — highest wins

On conflict: (1) hard rules, (2) my live instruction, (3) safety/verification
defaults ("Done means verified", "STOP and ask"), (4) personas (ponytail
build-style, caveman/humanizer prose-style), (5) model defaults. A persona
never overrides a rule above it — can't skip a check, cut a required feature,
or mangle deliverable prose.

# Done means verified

Never report work done without running the smallest check that would fail if
it broke — a test, a build, or re-reading the ask. Say what you checked.

# Communication

## Modes & their scope

Three personas may be active (plugins/hooks, not this file), none overriding
Precedence: Ponytail = *build* style, Caveman = *talk* style (exempts
code/commits/PRs), Humanizer = *deliverable prose* style. Never overlap —
facts/reasoning gets caveman; voice-judged text gets normal prose. Written
deliverables: match length to the task, no filler — calibration, not caveman.

## Progress updates

One sentence before your first tool call on what you're about to do; brief
updates only on something important or a direction change; on finish, lead
with the outcome, detail after.

# Planning/build workflow (Matt Pocock skills)

Pipeline for non-trivial work: **`/wayfinder` (grill out the fog) →
`/to-spec` → `/to-tickets` (tracer-bullet slices) → `/implement`.** Default to
it past a trivial edit; don't shortcut to `/implement` unless told to. Grill
first if scope/assumptions/decisions are fuzzy — skip only when already crisp.
An existing PRD doesn't replace `/to-spec` if decisions changed since. Skills
live in `~/.agents/skills` (symlinked into `~/.claude/skills`).

**Never a bare open issue** — every open issue must announce its state: label
it `wayfinder:*`/stage if mid-pipeline, `spec` if a sliced spec, `needs-triage`
if genuinely untriaged, `backlog` if parked. A spent parent (every child
merged) gets closed, not relabeled.

# How work lands (every repo)

**Gate 1 detail:** base repo = upstream parent for a fork, else this repo.
Anyone else's repo → hand me the drafted title/body, `gh pr create ...` line,
and a compare command; `pushpr` enforces this itself.

**Gate 2 detail:** a **code file** is anything executed, imported, or that
changes runtime/tool behavior — `.py/.ts/.js/.sh/.rs`, `settings.json`, hooks,
CI config, and any skill/agent `.md`; a mixed diff is code. Auto-ship: commit
to main, push, report what landed — except a fenced code block still needs
its format check run first (formatters read fences; `uv run ruff format
--check <file>` or equivalent). Code lane: `/implement` drives worktree → TDD
→ `/code-review` → `pushpr`; I read every code line before it merges.

# Gotchas

- **Every Agent call passes `model`** — the session is Fable and a bare call
  inherits it. Explore/lookup → `sonnet`, review/diagnosis → `opus`. Rubric:
  `~/.agents/skills/flow/claude/subagent-tiers.md`.
- `.claude/worktrees/` must be gitignored — untracked, `pushpr` cuts a junk
  branch and commits the worktree back as a gitlink instead of pushing it.
- `head`/`tail` are for looking, not measuring — use `wc -l`/`grep -c` before
  treating file contents as a premise.

@RTK.md

# second-brain vault memory (auto-imported by the weekly retro)
@/home/caneff/src/second-brain-v2/Memory/RULES.md
@/home/caneff/src/second-brain-v2/Memory/SOUL.md
