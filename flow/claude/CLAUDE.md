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
- **One Orca workspace per task** — each is its own worktree and branch. Make
  it from the `+` on the project row, or let `/implement` make it from `main`.
- **Code-lane work never builds on the primary checkout.** Agents never share
  a tree, so nothing guards it; a terminal opened on `main` means you meant
  it, and for code-lane work what it means is dispatch, not a branch cut in
  place. Auto-ship (Gate 2, zero code files) edits and commits on `main` by
  design.
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
gets a pointer. This covers **every** always-on agent doc, not just this file
— `AGENTS.md`, `CODING_STANDARDS.md` and `Memory/RULES.md` included: load-bearing
invariants inline, full detail in a read-on-demand pointer doc. When I say
"always" about the shape of a recurring output, put the change in the skill and
auto-ship it rather than complying once in the session.

# Precedence — highest wins

On conflict: (1) hard rules, (2) my live instruction, (3) safety/verification
defaults ("Done means verified", "STOP and ask"), (4) personas
(caveman/humanizer prose-style), (5) model defaults. A persona
never overrides a rule above it — can't skip a check, cut a required feature,
or mangle deliverable prose.

An explicit ruling from me outranks the current state of the tree and any
written criteria: change the tree or the doc, never "correct" the ruling to
match what exists. A doc-vs-code contradiction found mid-build is a decision,
not a fix — report both sides and let me rule. Before a rename or a golden
regeneration, `ls` the sibling examples for the convention already in the tree
and hold the ruling provisional until the reviewer weighs it.

# Done means verified

Never report work done without running the smallest check that would fail if
it broke — a test, a build, or re-reading the ask. Say what you checked.

Never graduate an unverified assumption into a fact. When a two-second check
exists — `gh`, `ls`, `grep`, a tasklist, a screenshot, a decode — run it before
asserting what exists or what state a thing is in, and cite it. Asserting a
negative from memory is how you end up acting on a plausible story.

# Communication

## Modes & their scope

Two personas may be active (plugins/hooks, not this file), none overriding
Precedence: Caveman = *talk* style (exempts code/commits/PRs), Humanizer =
*deliverable prose* style. Never overlap —
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
A teammate or subagent idle notification that repeats a report you already
relayed gets **no reply at all** — not "nothing new", not "already relayed".
The one-sentence confirmation above is for a report that adds nothing, not for
a literal duplicate.

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
drives TDD → `/code-review` + `/two-axis-code-review` → commit with
`Closes #<n>` → PR. My insight is after the fact: small honest commits,
`/landed` or `git log -p`, revert if wrong.

# Gotchas

- **Never `ORCA terminal wait`** — stale server-side waiters make it fail with
  `waiter_exists` and the replace flag doesn't attach. Use `orca-wait
  --terminal <handle> --for exit|tui-idle [--timeout-ms N]` (script in
  `~/.local/bin`, polls `terminal show`, no server waiter; exit 0 = met,
  2 = timeout).
- **Every Agent call passes `model`** — the session is Fable and a bare call
  inherits it. Explore/lookup → `sonnet`, review/diagnosis → `opus`. Rubric:
  `~/.agents/skills/flow/claude/subagent-tiers.md`.
- **A dispatched agent's status comes from the process table, never the
  terminal tail** — a cached screen with unchanged text is not evidence of
  work. Check children (`ps --ppid`), HEAD, `ls-remote`, `gh pr list`. Detail:
  `~/.agents/skills/flow/claude/agent-status.md`.
- **Long background job? run it under `job-run --name <n> -- <cmd>`** — its
  output and exit survive a kill, and `job-run --status <n>` answers alive /
  finished / killed. Details in `job-run --help`.
- **Never bare `orca` on Linux** — it resolves to the GNOME screen reader and
  starts speech. Use `orca-ide`, or `$ORCA_CLI_COMMAND` where Orca exports it.
- Orca does not clean up after a merge — run `merge-cleanup --repo <primary
  checkout> <branch>` (`--help` for PR/URL and `--sweep`), or worktrees pile up.
- `head`/`tail` are for looking, not measuring — use `wc -l`/`grep -c` before
  treating file contents as a premise.
- Shell searches use `rg`, not `grep -r`. It skips gitignored *and* dotted
  paths by default, so a zero-hit result is not evidence of absence — re-run
  with `-uu` before asserting a thing does not exist. `.agents/skills` ignores
  three live skill dirs (`computer-use/`, `orca-cli/`, `orchestration/`),
  `twitch-rules-scroller` ignores `e2e-artifacts/`, and `.github/` is dotted
  everywhere.
- To show me a file, open it in Orca's editor: `orca-ide file open <path>
  [--worktree <selector>]` (`file diff`, `file open-changed` likewise). Never
  print a path and ask me to open it. A **rendered** artifact — an HTML page, a
  report, a lineup — goes to Orca's browser instead, and so does any page I
  need to *look at* myself: `orca-ide tab create --url
  file://wsl.localhost/Ubuntu-24.04/<abs path>`, then `tab switch --page <id>`
  and `screenshot`. Three traps: the UNC form is not optional — the GUI is the
  Windows build, so a Linux `file:///home/...` loads as `ERR_FILE_NOT_FOUND` and
  only `tab list --json` shows it in `loadError`; `screenshot` shoots the
  *active* tab, and handing it `--page` answers `runtime_unavailable`, so `tab
  switch` first; and `eval` wants an **expression**, so wrap statements in an
  IIFE and reach elements through `document.getElementById` (a bare `sort` is
  not a global). Never stand up an http server, headless Chrome or a screenshot
  MCP to read a local page. The rest of the group (`goto`, `eval`, `click`,
  `check`) is in the `orca-cli` skill — load it rather than guessing at command
  names, which are top-level and not under a `browser` subcommand. **Load it on
  my own intent, with you having named nothing**: its own triggers are all
  phrases *you* say, so it never fires when I am the one who needs to look at
  something, and that gap is what sends me building an http server instead. The
  same goes for `computer-use` and `orchestration`. Fix the gap here and not in
  those three skills' own files — they are `orca skills install` output,
  gitignored, and regenerated on the next install.
- Never `pkill -f`/`pgrep -f` in a command line that names the target anywhere
  else — a heredoc writing the script, or a relaunch after the kill, both match
  and kill your shell (exit 143/144). A kill gets its own Bash call and nothing
  else; killing by PID from a separate `ps -eo pid,args --no-headers | grep
  '[p]attern'` listing is the default. Bracketing (`'zb[.]py hunt'`) only stops
  the pattern matching itself, so it is the second line of defence, not the
  rule. When the shell dies mid-compound-command the later steps never ran — a
  file you "just wrote" may still hold its old contents, so re-read it before
  debugging what it does.
- Prefer a surgical edit over rewriting the whole file when the result is the
  same — whole-file rewrites waste output tokens and time.
- When summarizing a source, reword it; any verbatim phrase gets quotation
  marks.
- Dense image (chart, screenshot, board photo): crop and enlarge the region
  of interest before answering — don't squint at the full frame. Pillow and
  OpenCV are installed for bare `python3` (`import PIL, cv2`).


# second-brain vault memory (auto-imported by the weekly retro)
@/home/caneff/src/second-brain-v2/Memory/RULES.md
@/home/caneff/src/second-brain-v2/Memory/SOUL.md
