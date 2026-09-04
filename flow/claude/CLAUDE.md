# Hard rules — never violate

- **Agents never merge a PR.** When a PR exists, I review and I merge
  (`! gh pr merge ...`) — hand me the exact line.
- **STOP and ask before** an *irreversible* deletion (untracked/uncommitted
  file, history-rewriting git op) and before adding a dependency or changing a
  database schema. A *tracked* file removed in a commit is undoable — delete it
  in place, no ask needed. The bar is "can I undo it," not "is it a deletion."
- **Gate 1 — whose repo?** Mine (origin owner = my gh login) → agents land
  directly. Anyone else's → push the branch, stop before the PR, hand me the
  PR command.
- **One Orca workspace per task** — each is its own worktree and branch, made
  from the `+` on the project row. Agents never share a tree, so nothing
  guards the primary checkout; a terminal opened on `main` means you meant it.
- **Gate 2 — code or decision?** Code file touched on my repo → code lane: a
  workspace made from the ticket, `/implement` inside it, PR at the end, and I
  merge. Zero code files → auto-ship: edit on `main`, commit, push, no
  ticket/TDD/review ceremony.
- Code-lane mechanics live in `/implement`.

Gates detailed under "How work lands"; the principle behind both: **I see it
before any OTHER human does.** My own repos land unreviewed — I read the log
after; revert is the undo.

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

## Subagent relay

Relay the **delta**, not the report. When a subagent finishes, say only what it
added that you had not already said; if it confirms what you told me, that is
one sentence. Never answer a question and delegate the same question — pick one.

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
and a compare command. The ownership-gated git hook, not prose, is what blocks
pushes to repos I don't own.

**Gate 2 detail:** a **code file** is anything executed, imported, or that
changes runtime/tool behavior — `.py/.ts/.js/.sh/.rs`, `settings.json`, hooks,
CI config, and any skill/agent `.md`; a mixed diff is code. Auto-ship: edit on
`main`, commit, push, report — except a fenced code block still needs its
format check run first (formatters read fences; `uv run ruff format --check
<file>` or equivalent). Code lane: one workspace per ticket, then `/implement`
drives TDD → `/code-review` → commit with `Closes #<n>` → PR. My insight is
after the fact: small honest commits, `/landed` or `git log -p`, revert if
wrong.

# Gotchas

- **Never `ORCA terminal wait`** — stale server-side waiters make it fail with
  `waiter_exists` and the replace flag doesn't attach. Use `orca-wait
  --terminal <handle> --for exit|tui-idle [--timeout-ms N]` (script in
  `~/.local/bin`, polls `terminal show`, no server waiter; exit 0 = met,
  2 = timeout).
- **Every Agent call passes `model`** — the session is Fable and a bare call
  inherits it. Explore/lookup → `sonnet`, review/diagnosis → `opus`. Rubric:
  `~/.agents/skills/flow/claude/subagent-tiers.md`.
- **Never bare `orca` on Linux** — it resolves to the GNOME screen reader and
  starts speech. Use `orca-ide`, or `$ORCA_CLI_COMMAND` where Orca exports it.
- Orca does not clean up after a merge — `orca-ide worktree rm` the workspace
  yourself, or merged branches pile up in the sidebar.
- `head`/`tail` are for looking, not measuring — use `wc -l`/`grep -c` before
  treating file contents as a premise.
- Prefer a surgical edit over rewriting the whole file when the result is the
  same — whole-file rewrites waste output tokens and time.
- When summarizing a source, reword it; any verbatim phrase gets quotation
  marks.
- Dense image (chart, screenshot, board photo): crop and enlarge the region
  of interest before answering — don't squint at the full frame. Pillow and
  OpenCV are installed for bare `python3` (`import PIL, cv2`).

@RTK.md

<!-- retro flag: the memory rule about staying quiet when `ship` fails after a
push is stale — `ship` was deleted for the land lane (issues #461–#465). -->
# second-brain vault memory (auto-imported by the weekly retro)
@/home/caneff/src/second-brain-v2/Memory/RULES.md
@/home/caneff/src/second-brain-v2/Memory/SOUL.md
