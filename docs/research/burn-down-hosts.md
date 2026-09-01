# Which host runs the burn-down?

Ticket: [#485](https://github.com/caneff/agent-skills/issues/485)
Map: [#477](https://github.com/caneff/agent-skills/issues/477)
Extends the tool survey in [#478](https://github.com/caneff/agent-skills/issues/478) — it is not repeated here.

Every candidate scored on the six lines from #485, against **primary sources only**:
the tool's own repo (README and source), its official docs site, its own
changelog, and — for the local `claude` CLI — its own `--help` output and live
behaviour on this machine. No blog posts, no roundups. Where a source does not
say, this document says **not documented** and names what was checked.

---

## Bottom line

**Stay on Claude Code, and make the `claude agents` view the burn-down surface.**

It is the only candidate that clears requirement 1 and requirement 4 at the same
time while still being Claude Code, so the skills survive by construction. It is
also the only candidate whose deletion policy is documented to be liveness-aware
rather than age-aware — which is the exact bug (`land` sweeping a live reader's
worktree) that opened this map.

Requirement 2 is its one real defect and #478 already found the workaround.

Two strongest reasons against it are at the end.

**Half the shortlist is dead.** Vibe Kanban announced its own sunset, Crystal was
deprecated in favour of a different product, and uzi has not had a commit in
fifteen months. See [Maintenance signals](#maintenance-signals).

---

## Scoring table

Requirement 1 is a hard reject. Requirement 4 is the second killer.

| Candidate | 1. 4-5 repos, one view | 2. Workspace at launch | 3. Foreign tickets | 4. Batched merges | 5. Deletion policy | 6. Runs Claude Code | Land on `main`, no PR |
|---|---|---|---|---|---|---|---|
| **`claude agents` view** | **PASS** (verified live) | **FAIL** — on first write | PASS | PASS | PASS — liveness-aware | PASS — is Claude Code | Yes |
| **Claude Code desktop app** | **PASS** | **PASS** — automatic | not documented | PASS | PASS — liveness-aware | PASS — is Claude Code | Yes |
| **Stay on the CLI, fix in place** | **PASS** (via `claude agents`) | PASS for `-w` + subagents; FAIL for background | PASS | PASS | PASS — liveness-aware | PASS — is Claude Code | Yes |
| **Claude Squad** | **PASS to view, FAIL to launch** | PASS | PASS | PASS (never makes a PR) | FAIL — `remove -f`, no liveness | PASS | Yes |
| **Vibe Kanban** | **REJECT** | PASS | not documented | **FAIL** | FAIL — age-based sweep | PASS | not documented |
| **Crystal** | **REJECT** — deprecated | n/a | n/a | n/a | n/a | n/a | n/a |
| **uzi** | **REJECT** — repo-filtered | PASS | PASS | PASS (rebases into your branch) | FAIL — wipes everything | PASS | Yes |
| **container-use** | not documented (setup is per-repo) | PASS | PASS | PASS by composition | FAIL — "disposable by design" | PASS (via MCP) | Yes |
| **Conductor** | not documented | partially documented | not documented | **FAIL (likely)** | not documented | not documented | not documented |
| **Devin** | not documented | PASS | not documented | **FAIL** — inverts it | not documented | **FAIL** — own agent | not documented |
| **Jules** | **REJECT** — one repo per task | PASS | PASS — issue label | **FAIL** | not documented | **FAIL** — own agent | not documented |

### Who dies on requirement 1 (hard reject)

- **uzi** — proven from source. `GetActiveSessionsForRepo` filters on
  `state.GitRepo == currentRepo`, so `uzi ls` only ever shows the repo you are
  standing in. ([state.go](https://github.com/devflowinc/uzi/blob/main/pkg/state/state.go))
- **Crystal** — dead before it gets scored. Its own README: "Crystal (formerly a
  multi-session AI code assistant manager) **has been deprecated** … Deprecated:
  February 2026." ([README](https://github.com/stravu/crystal))
- **Vibe Kanban** — the docs describe navigating *between* projects, not a
  consolidated view: "You have several ways to switch projects… Click any project
  name in the sidebar to open it."
  ([projects](https://vibekanban.com/docs/cloud/projects.md)) No multi-project
  board is documented. It is also sunsetting.
- **Jules** — "Jules needs a repo and branch to work on," selected per task from
  a repo dropdown. ([running-tasks](https://jules.google/docs/running-tasks/))
  Whether the *task list* spans repos is not documented; the task unit certainly
  does not.

**Survives with a caveat:** Claude Squad clears the viewing half and fails the
launching half. See its section.

**Cannot be rejected or cleared:** Conductor, container-use, Devin — not
documented, see their sections.

### Who dies on requirement 4 (one big PR, never a click per ticket)

- **Devin** — and it inverts the requirement rather than merely missing it.
  Stacked PRs are "an ordered series of pull requests that make up one piece of
  work and land together, bottom-up," and a stack "contains between 2 and 100
  PRs." ([stacked-prs](https://docs.devin.ai/work-with-devin/stacked-prs.md))
  That turns *one* ticket into up to a hundred PRs.
- **Jules** — one task, one branch, one PR: "You can click Create branch to push
  the changes," then "open a PR from this branch in GitHub."
  ([running-tasks](https://jules.google/docs/running-tasks/)) No batching
  documented, and the changelog frames the PR button as the terminal step: "Jules
  will request to merge the newly published branch into main."
  ([changelog](https://jules.google/docs/changelog/))
- **Vibe Kanban** — PRs are created per workspace from the workspace's Git panel;
  batching several tasks into one PR is not documented.
  ([git-operations](https://vibekanban.com/docs/workspaces/git-operations.md))
- **Conductor** — likely, not proven. "Create a pull request with Command + Shift
  + P" is per workspace, and each workspace maps to one branch, which the docs
  call "the review and PR unit."
  ([workflow](https://conductor.build/docs/concepts/workflow),
  [workspaces-and-branches](https://conductor.build/docs/concepts/workspaces-and-branches))
  Batching is not documented either way.

The tools that **pass** requirement 4 nearly all pass it by *doing nothing* —
they hand you a branch and never open a PR, so batching N branches into one PR is
your business, unchanged. That is the correct shape for this loop.

---

## Per candidate

### `claude agents` view — recommended

**1. Multi-repo: PASS, and this is the strongest evidence in the survey.** The
docs say it outright: "By default the list shows every background session you've
started, **across all your projects**. A session working in one repository and
another in a different worktree both appear here, regardless of which directory
you opened agent view from."
([agent-view](https://code.claude.com/docs/en/agent-view)) The CLI corroborates
by negation — `claude agents --cwd <path>` is documented as "Show only background
sessions started **under** `<path>`", a filter that would be meaningless if the
default were already scoped (`claude agents --help`, v2.1.252).

Verified live rather than taken on faith: `claude agents --json` on this machine
returned seven sessions spanning **five distinct repositories** —
`src/drills`, `src/sudokupad-art`, `agent-skills`, `twitch-rules-scroller`, and
`sudokumaker-custom-constraints`. Requirement 1 is not a hope here; it is already
running.

**2. Workspace at launch: FAIL.** This is the one defect, and it confirms #478
exactly: "Every background session, whether started from agent view, `/bg`, or
`claude --bg`, **starts in your working directory**. Before editing files, Claude
moves the session into an isolated git worktree under `.claude/worktrees/`."
([agent-view](https://code.claude.com/docs/en/agent-view)) The move is mid-run, on
first write — the moment this map named as the bug.

#478's fix stands: point each row's directory at a worktree that already exists,
and there is nothing left to move. The docs support it — Claude skips the move
when "the session is already inside a linked git worktree." You can also target a
directory at dispatch with an `@<repo>` mention, or `cd` into a worktree and use
`claude --bg`.

**3. Foreign tickets: PASS, trivially.** There is no task store to fight. The
dispatch input is free text; a ticket is a number you paste and `gh` reads.

**4. Batched merges: PASS.** Nothing in the view creates a PR. Branches
accumulate; you merge as many as you like into one PR, or none.

**5. Deletion: PASS, and it is the best-documented policy of any candidate.**
Three separate guards, all liveness-aware:

- "While an agent is running, Claude Code holds a `git worktree lock` on its
  worktree so that concurrent cleanup can't remove it, and releases the lock when
  the agent finishes… the sweep leaves the worktree in place and `git worktree
  remove` refuses to remove it."
- The sweep "also releases a lock Claude Code set for a session whose process has
  exited, so a killed background session doesn't leave its worktree permanently
  locked. The sweep **never releases a lock you set yourself**."
- The sweep skips a worktree that "still holds work: changed or untracked files,
  or unpushed commits," and keeps any worktree without Claude Code's own marker.

([worktrees](https://code.claude.com/docs/en/worktrees)) Deletion from the view
itself preserves a worktree "when another running session is using it," and
`claude rm <id>` is documented as deleting "a background session, and its
worktree **when that is safe**" (`claude --help`, v2.1.252).

This is precisely the lock-for-the-whole-run, release-on-exit, honour-it-
unconditionally policy that #478 concluded was required. **The harness already
implements it.** The t294 failure was not a gap in this policy — it was `land`
deliberately running `git worktree unlock` to get around it, on an idleness
heuristic #478 correctly called an outlier.

**6. Runs Claude Code: PASS.** It is Claude Code.

**Land on `main` with no PR:** Yes. Nothing pushes or opens a PR on its own.

---

### Claude Code desktop app

**1. Multi-repo: PASS.** "Use the controls at the top of the sidebar to filter
sessions by status, **project**, or environment, and to **group sessions by
project**." ([desktop](https://code.claude.com/docs/en/desktop)) A per-project
filter and a group-by-project control both presuppose a sidebar holding more than
one project.

**2. Workspace at launch: PASS — the only local candidate that does this without
a workaround.** "For Git repositories, each session gets its own isolated copy of
your project using Git worktrees." The worktrees page is blunter: "In the desktop
app, **every new session gets its own worktree automatically**."
([worktrees](https://code.claude.com/docs/en/worktrees)) The CLI-vs-Desktop
comparison table lists session isolation as `--worktree` flag for the CLI versus
"Automatic worktrees" for Desktop.

**3. Foreign tickets: not documented.** Checked the desktop page in full and its
CLI-equivalence table; there is no GitHub-issue ingest for the Code tab. In
practice the prompt box takes free text, so a ticket number works the same way it
does in the CLI — but no documented issue integration exists to cite.

**4. Batched merges: PASS, with a pull in the other direction.** Nothing forces a
PR. But the app is clearly built around one-PR-per-session: it opens PRs, watches
CI, offers **Auto-fix** and **Auto-merge** ("Claude merges the PR once all checks
pass. The merge method is squash"), and can auto-archive a session when its PR
merges. Using it for batched merges means ignoring the feature it is proudest of.

**5. Deletion: PASS.** Same worktree engine and the same lock as the CLI, plus a
per-session archive icon, and — importantly — "Auto-archive **only applies to
local sessions that have finished running**." An explicit liveness condition.
There is also a documented approval gate: "Before archiving any session, Claude
asks you first. You see the approval card in **every** permission mode, including
Auto and Bypass permissions."

**6. Runs Claude Code: PASS.** "Desktop and CLI read the same configuration
files, so your setup carries over."

**Land on `main` with no PR:** Yes.

**Caveat that matters here:** Linux is a beta, distributed via apt/`.deb` for
Ubuntu and Debian ([desktop-linux](https://code.claude.com/docs/en/desktop-linux)),
which is the platform this workspace runs on. macOS and Windows are the first-
class targets.

---

### Stay on the Claude Code CLI and fix it in place

Scored as its own candidate, on the same six lines.

**1. PASS**, because `claude agents` *is* the CLI — see above. Five separate
terminals would fail this outright; the agents view is what rescues it.

**2. Split.** `claude --worktree|-w [name]` creates the worktree at launch
("Create a new git worktree for this session", `claude --help` v2.1.252), and a
subagent with `isolation: worktree` in frontmatter gets one at spawn. Background
sessions do not — see the agents-view entry. So the answer depends entirely on
which of the three creation paths a given session takes, which is #478's finding
restated.

**3. PASS. 4. PASS. 5. PASS. 6. PASS** — identical to the agents view.

**Land on `main` with no PR:** Yes; it is the current habit and nothing removes
it.

**What "fix it in place" actually costs.** Less than the map assumed. The
deletion policy the map wanted does not need building — it exists, documented,
lock-based. What survives as real work is: making background sessions eager
(#478's answer), and deleting `land`'s sweep, `require-worktree.sh`, and the
`settings.json` worktree allow-list that made the unsafe path approval-free.

---

### Claude Squad

The most interesting near-miss, and the verdict needed reading the source rather
than the README.

**1. Multi-repo: PASS to view, FAIL to launch.** Sessions are persisted globally,
each carrying its own `RepoPath` in a `GitWorktreeData` struct
([storage.go](https://github.com/smtg-ai/claude-squad/blob/main/session/storage.go)).
`LoadInstances()` deserialises **every** stored instance with no repo filter, and
`newHome` adds all of them to the list unconditionally
([app.go](https://github.com/smtg-ai/claude-squad/blob/main/app/app.go)). So one
`cs` window does show and attach to sessions across every repo.

But creating one is hard-wired to the process's own directory: both `new session`
handlers call `session.NewInstance(session.InstanceOptions{Title: "", Path: ".",
…})`. You can watch five repos from one window; you can only start work in the
repo you launched `cs` from.

**2. Workspace at launch: PASS.** A git worktree per instance, at creation.
README: "Each task gets its own isolated git workspace, so no conflicts."

**3. Foreign tickets: PASS.** A session is a free-text prompt (`N` — "Create a
new session with a prompt"). No task store.

**4. Batched merges: PASS, by omission.** `s` is documented as "Commit and push
branch to github," and the code path is `worktree.PushChanges(commitMsg, true)` —
it commits and pushes a branch and **never calls `gh pr create`**. N sessions
produce N branches and zero PRs; batching them is entirely yours.

**5. Deletion: FAIL.** `Cleanup()` and `Remove()` both run `git worktree remove
**-f**`, which overrides a lock by design, with no liveness check of any kind
([worktree_ops.go](https://github.com/smtg-ai/claude-squad/blob/main/session/git/worktree_ops.go)).
`CleanupWorktrees()` walks the shared worktree directory and removes everything
in it. Deletion is user-initiated (`D`) rather than swept on a timer, which is
better than `land`, but the force flag means pressing `D` on a live session's row
does exactly the t294 failure.

**6. Runs Claude Code: PASS.** "The default program is `claude`."

**Land on `main` with no PR:** Yes — it only ever gives you branches.

---

### Vibe Kanban — sunsetting

**Its own README carries the notice**: "**Vibe Kanban is sunsetting.**"
([README](https://github.com/BloopAI/vibe-kanban)) The first-party announcement:
"The project will continue as open source and community maintained," with remote
services (kanban issues, comments, projects, organisations) withdrawn after 30
days from 10 April 2026, and "local workspaces will continue to function."
([shutdown announcement](https://www.vibekanban.com/blog/shutdown))

The requirement-1 rejection above stands independently of the sunset.

**2. PASS** — "each workspace gives an agent a branch, a terminal, and a dev
server" (README). **3. not documented** — it has its own kanban issues; a GitHub
*issue* import (as opposed to the GitHub integration for PRs) is not documented
on the pages checked ([github-integration](https://vibekanban.com/docs/integrations/github-integration.md),
[issues](https://vibekanban.com/docs/cloud/issues.md)). **4. FAIL** — see above.
**6. PASS** — Claude Code is one of 10+ supported agents.

**5. Deletion: FAIL, and it is the same shape as `land`.** The README documents
an env var whose existence proves an automatic age-based sweep:
`DISABLE_WORKTREE_CLEANUP` — "Disable all git worktree cleanup including orphan
and **expired workspace cleanup**." Expiry is wall-clock, not occupancy. No
liveness guard is documented.

**Land on `main` with no PR:** not documented. The docs describe Merge as pulling
"the target branch INTO your working branch (the opposite direction of a PR
merge)" ([git-operations](https://vibekanban.com/docs/workspaces/git-operations.md)),
which is not the same operation.

---

### Crystal — deprecated

Not scored past requirement 1. From its own README: "**Crystal Is Now
Nimbalyst.** Crystal … has been deprecated and replaced by Nimbalyst. Deprecated:
February 2026." ([README](https://github.com/stravu/crystal))

Its successor **Nimbalyst** (https://nimbalyst.com/,
[Nimbalyst/nimbalyst](https://github.com/Nimbalyst/nimbalyst)) advertises "Git
worktree isolation for safer parallel AI coding sessions" and "Project-level
workspace management." It was not on the candidate list and is not scored here.
Its own README wording is project-level, which reads one-project-at-a-time, but
that is an inference and was not verified — if it is worth considering it needs
its own pass.

---

### uzi — unmaintained, and repo-scoped

**1. REJECT**, proven from source (above).

Worth recording anyway, because **it has the best batching primitive in the
survey**: `uzi checkpoint <agent> "<msg>"` "Makes a commit and rebases changes
from an agent's worktree into your current branch"
([README](https://github.com/devflowinc/uzi)). Run it N times and you have one
branch holding N finished tickets, which is requirement 4 stated as a command.
That idea is worth stealing even though the tool is not usable.

**2. PASS** (worktree per agent at spawn). **3. PASS** (free-text prompt).
**5. FAIL** — `uzi kill all`, and `uzi reset` "deletes all data in
`~/.local/share/uzi`"; no liveness guard documented. **6. PASS** (`--agents
claude:N`).

**Land on `main` with no PR:** Yes — `checkpoint` never opens one.

Last commit **4 June 2025**; only release `v0.0.2`, **3 June 2025**. Fifteen
months idle.

---

### container-use

**1. not documented.** The CLI reference describes `container-use list` only as
"List all environments and their status" with no statement of scope
([cli-reference](https://container-use.com/cli-reference)); the environment
workflow page likewise says "See all environments and their status" without
defining the boundary
([environment-workflow](https://container-use.com/environment-workflow)). What
*is* documented points toward per-repo: setup is `cd /path/to/repository && claude
mcp add container-use -- container-use stdio`, and each environment is "a fresh
container **in its own git branch**" of that repository
([README](https://github.com/dagger/container-use)). Branches live in one repo, so
a cross-repo list would have nothing to list. Treat this as probably-rejected but
unproven; it needs a hands-on check, not another doc read.

**2. PASS** — a fresh container and branch per environment, at creation.
**3. PASS** — the agent is prompted in free text. **6. PASS** — "an open-source
MCP server that works as a CLI tool with Claude Code," so Claude Code is the
agent. Note the skills still run, but inside a container, so any skill or hook
that shells out to the host changes shape.

**4. PASS by composition.** No batching feature is documented, but `container-use
merge` "Merge an environment's work into your current branch" and `apply` "Apply
an environment's changes as staged modifications" both land into *your* branch —
so N merges then one PR is available, the same trick as uzi's `checkpoint`.

**5. FAIL.** "Environments are **disposable by design**" and the docs
"recommend not hesitating to delete failed work"; `delete` takes an `--all`. No
safeguard for a running agent is documented anywhere in the CLI reference or the
workflow page.

**Land on `main` with no PR:** Yes — merge into your branch and push.

Marked "**stability: experimental**" in its own README, and it is "in early
development and actively evolving."

---

### Conductor — largely not documented

The thinnest evidence base of any candidate, and the one this document is least
able to judge. It is closed-source (Mac app), `https://conductor.build/docs/llms.txt`
returns 404, and the two concept pages that should answer these questions do not.

**1. not documented.** Checked the landing page, `/docs`,
`/docs/concepts/workspaces-and-branches`, `/docs/concepts/workflow`. None states
whether several repositories can be open at once or whether it is one repo per
window. Given requirement 1 is the hard reject, **Conductor cannot be advanced
without a hands-on trial** — and it is macOS-only, which this workspace is not.

**2. partially documented.** "Conductor creates these separate checkouts with Git
worktrees" ([workspaces-and-branches](https://conductor.build/docs/concepts/workspaces-and-branches)),
and "Each task gets its own workspace, branch, files, terminal, diff, and review
path" ([docs](https://conductor.build/docs)). Creation *timing* — at launch versus
mid-run — is not stated.

**3. not documented.** No GitHub-issue import found on any page checked.

**4. FAIL (likely).** "Create a pull request with Command + Shift + P," one
workspace to one branch, the branch being "the review and PR unit"
([workflow](https://conductor.build/docs/concepts/workflow)). A click per ticket
is exactly the shape the requirement rules out. Batching is not documented either
way.

**5. not documented.** Archiving exists — "Archive finished workspaces so your
sidebar stays focused… restore it from there, including its chat history" — but
deletion mechanics and any running-agent protection are not described.

**6. not documented.** The product is marketed around Claude Code, but no page
checked states that it invokes the `claude` CLI, which is what decides whether
skills survive.

**Land on `main` with no PR:** not documented.

---

### Devin — hosted, own agent

**6. FAIL, and this is decisive on its own.** Devin is Cognition's own agent. The
existing skills, `CLAUDE.md`, hooks and the whole planning pipeline do not
transfer. Everything downstream of "here is a ready ticket" would be rebuilt in
someone else's product.

**4. FAIL, by inversion.** See the requirement-4 section: stacked PRs turn one
piece of work into 2–100 PRs. This is the opposite of the requirement, not a
partial match.

**1. not documented.** Checked `docs.devin.ai` root and its `llms.txt` index; the
only multi-repo page found is about *indexing* repositories for Ask Devin
([index-repo](https://docs.devin.ai/onboard-devin/index-repo.md)), not about a
session list spanning repos.

**2. PASS** — each session runs in its own cloud workspace/VM
([environment](https://docs.devin.ai/onboard-devin/environment.md)).

**3. not documented.** Checked the GitHub integration page
([gh](https://docs.devin.ai/integrations/gh.md)); it covers installation and
permissions, and does not state whether an existing issue can be assigned to
Devin by label, assignment, or mention.

**5. not documented.** No workspace deletion policy or running-agent protection
found in the environment pages.

**Land on `main` with no PR:** not documented; every documented flow is
PR-shaped.

---

### Jules — hosted, own agent

**6. FAIL.** Google's own agent. It reads `AGENTS.md` — "Jules now automatically
looks for a file named AGENTS.md in the root of your repository"
([changelog](https://jules.google/docs/changelog/)) — but that is a context file,
not the Claude Code skill and hook machinery. The pipeline does not survive.

**1. REJECT.** "Jules needs a repo and branch to work on," chosen per task from a
repo selector ([running-tasks](https://jules.google/docs/running-tasks/)). Whether
the *task list* spans repos is **not documented** — checked
[tasks-repos](https://jules.google/docs/tasks-repos/), which says only that "Each
task runs in its own virtual machine and maintains its own logs, environment
setup, and code changes." The per-task unit is single-repo regardless.

**2. PASS** — a VM per task, at task start.

**3. PASS, and it is the only candidate with a documented, first-class answer:**
"You can start a task from a GitHub issue by applying the label `jules` (case
insensitive)." ([running-tasks](https://jules.google/docs/running-tasks/)) Worth
noting as the pattern to copy, whoever hosts.

**4. FAIL.** One task → Create branch → one PR. No batching documented.

**5. not documented.** VM cleanup after task completion is not described on the
pages checked.

**Land on `main` with no PR:** not documented. The changelog describes the PR
button as requesting "to merge the newly published branch into main," i.e. always
via a PR.

---

## Maintenance signals

From each project's own repo, via the GitHub API on 2026-09-01.

| Project | Latest release | Last push | Stars | Concentration | Status |
|---|---|---|---|---|---|
| Claude Squad | `v1.0.20`, 2026-08-20 | 2026-08-20 | 8,407 | two main contributors (116 / 87 commits) | **Healthy** |
| container-use | `v0.4.2`, **2025-08-19** | 2026-08-17 | 4,027 | spread across Dagger team (71 / 51 / 43) | Active commits, **no release in a year**; self-described experimental |
| Vibe Kanban | `v0.1.44`, 2026-04-24 | 2026-04-24 | 27,974 | one dominant author (878 vs 257) | **Sunsetting**; handed to community |
| Crystal | `v0.3.5`, 2026-02-26 | 2026-02-26 | 3,114 | effectively **one maintainer** (617 vs 29) | **Deprecated**, replaced by Nimbalyst |
| uzi | `v0.0.2`, **2025-06-03** | **2025-06-04** | 582 | effectively **one maintainer** (45 vs 16) | **Abandoned** — 15 months idle |
| Conductor | closed source | n/a | n/a | unknown | Cannot verify |
| Claude Code | CLI 2.1.252 in use here | n/a | n/a | Anthropic | Actively shipping |

Devin and Jules are hosted commercial products; release recency is not a
meaningful signal for them and their pricing was not investigated.

---

## What could not be determined

Recorded rather than guessed.

1. **Conductor, on nearly every line.** Its `llms.txt` 404s, it is closed source,
   and its two concept pages do not answer requirement 1, 3, 5, or 6. It cannot
   be cleared or rejected from documentation. It is also macOS-only.
2. **container-use's `list` scope.** Neither the CLI reference nor the workflow
   page states whether it is repo-scoped. The per-repo MCP setup and
   branch-per-environment model imply it is, but that is an inference.
3. **Devin's issue ingestion and direct-to-main.** The GitHub integration page
   covers install and permissions only.
4. **Whether the Jules dashboard lists tasks across repos.** Only the per-task
   repo selection is documented.
5. **The desktop app's handling of a ticket authored elsewhere.** No documented
   issue integration for the Code tab; free-text prompting is the assumed path
   but is not stated as a feature.
6. **Nimbalyst.** Crystal's successor was not on the candidate list and was not
   scored.
7. **Vibe Kanban post-sunset.** What the community-maintained edition keeps was
   promised as a roadmap "over the next few weeks" from April 2026; not checked.

---

## Recommendation, and the two strongest reasons against it

**Recommend: stay on Claude Code, with `claude agents` as the burn-down surface
and the desktop app as the upgrade path once its Linux build leaves beta.**

Nothing else clears requirement 1 and requirement 4 together. Of the eight named
alternatives: three are dead or dying (Crystal, uzi, Vibe Kanban), two are hosted
agents that discard the entire skill pipeline on requirement 6 (Devin, Jules),
one cannot be evaluated from its own documentation (Conductor), one is probably
repo-scoped and self-describes as experimental (container-use), and the last
(Claude Squad) is genuinely good but can only *launch* work in the repo you
started it from, and force-removes worktrees with no liveness check.

### Reason against it #1 — it is the status quo, and the status quo is what broke

Choosing this means no host arrives to do the work. Requirement 2 stays open for
the session kind the burn-down leans on hardest: background sessions still take
their worktree on first write, mid-run, which is the bug this map was opened to
kill. #478's workaround — pre-made worktrees behind each row — is a convention,
not an enforcement, and conventions are what failed three times.

Note the sharpest counter-argument, though, because it changes the size of the
remaining job: the deletion policy the map assumed had to be built **already
exists and is documented** — a lock held for the whole run, released on process
exit, honoured by the sweep and by `git worktree remove`. The t294 failure was
`land` deliberately unlocking to get past it. The fix there is deletion of our
own code, not construction.

### Reason against it #2 — a session list is not a ticket board

`claude agents` shows *sessions*, not *tickets*. Every rival that lost on
requirement 1 beat it on this: Vibe Kanban has a real board, Jules can be handed
a GitHub issue by label alone. Here, the mapping from a ready ticket to a running
session stays manual — you paste, you dispatch, you remember which row is which
issue. Across 4-5 repos and a batch of tickets, that bookkeeping is the thing
that will hurt, and this recommendation does nothing about it.

The escape route is the desktop app, which adds eager worktrees and closes
requirement 2 properly — but its Linux support is a beta apt/`.deb` build for
Ubuntu and Debian, and it pulls hard toward one-PR-per-session, the exact habit
requirement 4 exists to prevent.
