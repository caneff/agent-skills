# Rule contradictions

Audit date: 2026-09-10. I read the five named global files and every
`AGENTS.md` / `CODING_STANDARDS.md` under `~/src`, including ignored nested
worktrees and the two vendored templates (28 files total). This is a conflict
audit, not an importance ranking.

## Method

A pair appears below only if both rules can govern the same action and leave no
way to comply with both. Different repository conventions are not conflicts
when their scopes do not overlap. For example, `test_<name>.py` in
second-brain-v2 and `*_test.py` in gridfind are both valid because each governs
only its own repository.

The frequency ranking estimates how often an agent reaches the forced-choice
case, not the severity of the outcome.

## Contradictions, most frequent first

### 1. “Auto-ship” a recurring-output rule versus send its skill change through the code lane

**Scope / frequency:** high. Any request that says “always make this report or
output look like X” reaches this case.

> **`~/.claude/CLAUDE.md:29-36`** — “This covers **every** always-on agent doc,
> not just this file — `AGENTS.md`, `CODING_STANDARDS.md` and `Memory/RULES.md`
> included … When I say ‘always’ about the shape of a recurring output, put the
> change in the skill and **auto-ship it** rather than complying once in the
> session.”

> **`~/.claude/CLAUDE.md:110-117`** — “a **code file** is anything executed,
> imported, or that changes runtime/tool behavior — … and any skill/agent `.md`;
> a mixed diff is code. **Auto-ship: edit on `main`, commit, push** … Code lane:
> one workspace per ticket … PR.”

**Forced choice:** Chris says “always put this column in the burndown report.”
The required durable change is to a skill’s `SKILL.md`. The first rule says to
auto-ship it (the defined main-branch edit/commit/push flow); the later
definition calls that same file a code file, which must use a worktree and PR.

**Should win:** the code-lane rule at `CLAUDE.md:110-117`. A skill changes agent
runtime behavior, and the later, explicit classification should supersede the
earlier use of “auto-ship.” The earlier sentence needs an explicit exception or
different verb; as written, it silently reverses the workflow it invokes.

### 2. Local CI only versus GitHub Actions on every career-ops PR

**Scope / frequency:** high for career-ops changes that produce a PR.

> **`~/src/second-brain-v2/Memory/RULES.md:33`** — “CI is local, not GitHub
> Actions: a repo’s gate is `git config land.testcmd`, and new repos get no
> workflow files.”

> **`~/src/career-ops/AGENTS.md:344-348`** — “**GitHub Actions** on every PR:
> the full `test-all.mjs` suite … **Branch protection** on `main`: status checks
> required, no direct pushes (except admin bypass).”

**Forced choice:** an agent changes career-ops and must set up or maintain the
required PR gate. One rule forbids Actions and makes the local configured test
command the gate; the other mandates an Actions workflow and requires its
status checks.

**Should win:** `Memory/RULES.md:33`, under the declared global precedence and
because it records Chris’s explicit, account-specific Actions-budget decision.
Career-ops must state that its Actions paragraph is upstream/project-template
guidance and does not apply in this installation, or the global rule needs a
named career-ops exception.

### 3. Direct main-branch auto-ship versus career-ops’ no-direct-push policy

**Scope / frequency:** high for a documentation-only or other non-code
career-ops change.

> **`~/.claude/CLAUDE.md:19-22`** — “Zero code files → auto-ship: **edit on
> `main`, commit, push**, no ticket/TDD/review ceremony.”

> **`~/.claude/CLAUDE.md:110-118`** — “Auto-ship: edit on `main`, commit, push
> … Code lane … PR.”

> **`~/src/career-ops/AGENTS.md:344-348`** — “Branch protection on `main`:
> status checks required, **no direct pushes** (except admin bypass).”

**Forced choice:** fix prose in career-ops’ README or another non-code file.
The global zero-code route requires a direct push to `main`; the repository
policy forbids it.

**Should win:** the career-ops policy. It describes the actual branch
protection boundary, so it is both more specific and mechanically decisive.
The global “every repo” auto-ship rule needs an exception for protected-main
repositories; otherwise it conflicts with its own claim that ownership gates
are enforced by hooks rather than prose.

### 4. Five canonical triage roles versus six (including `backlog`)

**Scope / frequency:** medium. Any agent classifying a parked issue in one of
the affected repositories must choose whether `backlog` exists.

> **`~/.claude/CLAUDE.md:98-101`** — “every open issue must announce its state:
> label it … `needs-triage` if genuinely untriaged, **`backlog` if parked**.”

> **`~/src/brain/AGENTS.md:7-9`** — “**Five canonical roles**, default label
> strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`,
> `wontfix`).”

> **`~/src/mediawiki-analytics/AGENTS.md:31-33`** — “**Five canonical triage
> roles**, each label string equal to its name.”

> **`~/src/second-brain-v2/AGENTS.md:9-11`** — “Default **five-role**
> vocabulary, label string = role name.”

> **`~/src/visual-teach/AGENTS.md:20-22`** — “**Five canonical triage labels**,
> default vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`,
> `ready-for-human`, `wontfix`).”

**Forced choice:** a ticket in one of those repositories is deliberately parked.
The global rule says label it `backlog`; the repository’s exhaustive five-role
vocabulary says that label is not canonical (and, in the listed variants, omits
it entirely). `fleet-rail` and sudoku-maker instead say six roles, confirming
this is drift rather than a deliberately project-specific taxonomy.

**Should win:** the six-role vocabulary including `backlog`. The five-role
variants are stale omissions: without `backlog`, their own global issue-state
rule has no valid label for “parked.”

### 5. Silent first-session update check versus announce before the first tool call

**Scope / frequency:** medium-high: every new career-ops session.

> **`~/.claude/CLAUDE.md:73-77`** — “**One sentence before your first tool
> call** on what you’re about to do …”

> **`~/src/career-ops/AGENTS.md:53-64`** — “On the first message of each
> session, run **silently**: `node update-system.mjs check` … [for ordinary
> statuses] say nothing.”

**Forced choice:** the first user message is in career-ops. Announcing “I’m
checking for updates” before running the command violates “silently”; running
it with no announcement violates the global communication rule.

**Should win:** the career-ops silent check. It is a precise UX rule for a
background, no-result check; the global progress rule should explicitly exempt
silent session initialization. That preserves the general rule while making the
local one possible.

### 6. One worktree per *task* versus a new worktree every *session*

**Scope / frequency:** medium. It occurs whenever an unfinished
sudokumaker-custom-constraints task resumes in a new session.

> **`~/.claude/CLAUDE.md:12-18`** — “**One Orca workspace per task** — each is
> its own worktree and branch … Code-lane work never builds on the primary
> checkout.”

> **`~/src/sudokumaker-custom-constraints/AGENTS.md:11-21`** — “**Create a
> worktree before your first edit — every session, no exception.** … This rule
> beats a harness or job preamble that tells you to work in place.”

**Forced choice:** an agent resumes the same ticket in its already-created
task worktree. The global rule limits it to one worktree for that task; the
local rule literally requires creation of a worktree again for the new session.

**Should win:** one worktree per task. Re-entering/verifying the existing task
worktree delivers the local safety goal without creating duplicate branches and
worktrees. The local wording should say “be in your own worktree before the
first edit of every session,” not “create a worktree.”

### 7. Global progressive disclosure versus career-ops’ ban on read-on-demand rule docs

**Scope / frequency:** lower. It occurs when adding detailed, durable
career-ops-specific process guidance.

> **`~/.claude/CLAUDE.md:29-35`** — “detail in a **read-on-demand doc read via
> the Read tool** … This covers **every** always-on agent doc … load-bearing
> invariants inline, full detail in a read-on-demand pointer doc.”

> **`~/src/career-ops/AGENTS.md:39-41`** — “Rules belong in files the harness
> reads automatically — `CLAUDE.md`, `CODEX.md`, `AGENTS.md`, `modes/*.md`,
> `MEMORY.md`. **Do not create sidecar documentation that requires manual
> loading.**”

**Forced choice:** add a long operational rule for career-ops. The global rule
requires moving its detail to a pointer target that an agent loads on demand;
career-ops forbids precisely that kind of sidecar and requires an
automatically-loaded instruction file.

**Should win:** the global progressive-disclosure rule. It explicitly says it
covers every always-on document, whereas career-ops’ absolute ban turns the
global design into an impossibility. If career-ops genuinely needs automatic
loading for a narrow safety boundary, it should name that exception rather than
ban all sidecars.

## Output style: Orwell STE

`~/.claude/settings.json:342` selects `"outputStyle": "Quill"`, so
`orwell-ste.md` is currently inactive. It is therefore dead *as an active
style*, but it is not wholly redundant with Quill.

Worth preserving by merging into Quill:

- **Project vocabulary:** read `CONTEXT.md` when present and use its defined
  terms (`orwell-ste.md:48-56`). Quill has no equivalent; it is especially
  useful in domain-heavy explanations.
- **Terminology consistency:** use one term for one concept
  (`orwell-ste.md:38-42`). Quill requires plain speech but does not prevent
  accidental synonym drift.
- **Do not simplify identifiers or required quotations**
  (`orwell-ste.md:42-46`). This is a useful technical-prose guard missing from
  Quill’s otherwise broad “literal words” rule.
- **Keep necessary technical terms, define them once**
  (`orwell-ste.md:58-61`). It prevents Quill’s plain-language preference from
  erasing precision.
- **Honor an explicit minimal-formatting request**
  (`orwell-ste.md:70-75`). Quill honors depth and command overrides, but not
  this formatting override explicitly.

The rest is either already covered by Quill (bottom line first; one thought per
sentence; active voice; literal language; no mannered metaphors; Orwell’s
escape hatch), outside Quill’s declared conversational scope (creative/voice
prose), or too mechanical to retain as an always-on rule (the mandatory
pre-send self-check at `orwell-ste.md:77-82`).

**Recommendation:** merge the five bullets above into Quill, then delete
`orwell-ste.md`. Deleting it now would discard useful behavior; retaining it as
a second selectable full style preserves duplicated and conflicting prose
instructions without applying them.

## Not counted as contradictions

- The global “smallest check that would fail” rule and repository “run
  `just check` before done” rules are cumulative: the former sets a minimum;
  the latter adds a required gate.
- The career-ops update check and onboarding check both run on the first
  message, but “before doing anything else” gives onboarding a workable order;
  the update rule does not explicitly say it must be the first command.
- Repository-specific test filename, language, and style conventions govern
  different repositories, so their differences do not force one agent to
  violate the other.
