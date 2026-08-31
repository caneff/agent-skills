# GitHub call-site inventory, and what `br` would replace

Inventory for [#468](https://github.com/caneff/agent-skills/issues/468), child of the
tracker-migration map [#466](https://github.com/caneff/agent-skills/issues/466).
Companion to the capability research in `docs/research/br-capabilities.md`
(#467, on branch `research/br-capabilities`) and the routing decision in
[#474](https://github.com/caneff/agent-skills/issues/474).

**How this was produced.** A sweep of the whole repo for `gh issue`,
`gh api repos`, `gh pr`, `gh search issues`, and `githubIssues` — 71 matching
lines in 19 files. Every `br` replacement below was **run**, not read off the
help text: `br 0.5.7` against a throwaway workspace, with the
`status_groups.ready: [ready_agent]` policy from #474 in place. Where a claim
rests on `--help` alone, it says so.

**The ticket's known set of 11 files was short by 8.** The sweep adds
`extract-coding-standards/SKILL.md`, `flow/bin/pushpr`, `flow/claude/CLAUDE.md`,
`flow/claude/hooks/block-dangerous-git.sh` and its `.test.sh`,
`flow/vscode/settings.json`, `setup-matt-pocock-skills/issue-tracker-gitlab.md`,
and the companion doc `docs/research/br-capabilities.md`. Six of the eight touch
pull requests, not issues, and the map already rules PRs out of scope — so they
are listed and dismissed rather than costed.

## The table

### Issue call sites — in scope

| File | Operation | `br` replacement |
| --- | --- | --- |
| `docs/agents/issue-tracker.md` | The whole tracker contract for this repo: create, read, list, comment, label, close, parent, dependencies, type, frontier query, claim, resolve | Rewrite wholesale. Every line has a `br` equivalent except the frontier query (see below). ~35 lines of prose, one file. |
| `setup-matt-pocock-skills/issue-tracker-github.md` | The same contract, rendered into other people's repos by the installer | No rewrite needed. It stays the GitHub template. A `br` variant is a **new** file, not an edit — and whether one is offered at all is fog (#466). |
| `setup-matt-pocock-skills/issue-tracker-gitlab.md` | GitLab variant of the same contract | Untouched. |
| `setup-matt-pocock-skills/SKILL.md:40` | Explainer prose naming `gh issue create` as one of the tracker options | One-line edit, only if `br` becomes an offered option. |
| `burndown/SKILL.md:19` | `gh issue list --label ready-for-agent --state open` | `br ready` — and it gets *better*. Under the #474 policy, `br ready` already means "open, unblocked, not deferred, and `ready_agent`". The label filter and the unblocked check both disappear into the one command. Verified. |
| `implement/SKILL.md:26` | `gh issue edit <n> --remove-label ready-for-agent --add-label in-progress --add-assignee @me` | `br update <id> --claim` — one atomic call sets `assignee=actor` and `status=in_progress`. Three flags become one. |
| `implement/SKILL.md:31` | Put it back on failure: `--remove-label in-progress --add-label ready-for-agent` | `br update <id> --status ready_agent --assignee ""` (empty string clears the assignee — `--help`, not run). |
| `triage/AGENT-BRIEF.md:32` | Prose example naming `gh issue list --label needs-triage` | One-line edit. #474 deletes `needs-triage` outright — untriaged becomes plain `open` — so the example needs a new subject, not a translation. |
| `flow/bin/issue-counts` | One `gh issue list --json labels,blockedBy`, then jq tallies six frontier groups plus an "Other" bucket | Shrinks hard. `br count --by-status` returns the group counts directly; `br ready` gives "Ready now" without the `blockedBy` arithmetic. Both verified. The **"Other" bucket disappears entirely** — it exists to catch issues carrying no frontier label, and under #474 those are just `status: open`. |
| `flow/vscode/settings.json:37-69` | Eight `githubIssues.queries` kept label-for-label in sync with `issue-counts` | **No equivalent.** Accepted loss (#466). See below for what else goes with it. |
| `flow/claude/settings.json:12-14` | Permission allowlist: `Bash(gh issue *)`, `Bash(gh issue edit:*)`, `Bash(gh label *)` | Add `Bash(br *)`. Note the permission surface *changes shape*: `gh` writes over the network, `br` writes files in the repo (`.beads/*.db`, `issues.jsonl`), so a `br` allowlist entry grants local writes an equivalent `gh` entry never did. |
| `.github/workflows/clear-in-review.yml` | GitHub Action: on issue close, strip the `in-review` label | **Dies rather than ports.** The map already retires it — it is a janitor for a PR-era label no longer applied. |
| `setup-python-repo/templates/clear-in-review.yml` | The same workflow, shipped into other people's Python repos | Untouched. Those repos stay on GitHub. |

### GitHub call sites that are not issue call sites — out of scope

| File | Operation | Verdict |
| --- | --- | --- |
| `skills-safe-update/SKILL.md:92` | `gh api repos/<owner>/<repo>/git/trees/<branch>` — lists SKILL.md paths in a remote repo | Unaffected. Git trees, not issues. |
| `extract-coding-standards/SKILL.md:81-82` | Mines merged-PR review comments for conventions | Unaffected. PR data has no `br` counterpart and needs none — the PRs it reads are other people's, on GitHub. |
| `flow/bin/pushpr` | Creates the PR, and greps commit messages for `#<n>` to find issues a PR delivers but does not close | Unaffected **in practice**, but the coupling is worth naming: it is built end to end on `#[0-9]+` and `gh api repos/$target/issues/$n`. `br` ids are slugs (`br-<slug>-<hash>`), so none of that matches. It survives only because Gate 1 sends PRs to *other people's* repos, which stay on GitHub. On a `br` repo, `br orphans` ("issues referenced in commits but still open", per `br --help`) is the same idea natively. |
| `flow/claude/hooks/block-dangerous-git.sh`, `.test.sh` | Block `gh pr merge` | Unaffected. |
| `flow/claude/CLAUDE.md:4,82` | PR-handoff prose | Unaffected. |

## The "no equivalent" list — the real decisions

Four, and only one of them is new.

**1. The wayfinder frontier query has no single-command equivalent.** This is
the substantive finding, and it contradicts the obvious guess.

`br ready` is *not* the frontier. Under the #474 policy, `br ready` returned
only the `ready_agent` issue and skipped an `open`, unblocked, unassigned one —
verified directly. That is correct behaviour for the burndown queue and wrong
for wayfinder, whose frontier is "open, unblocked, unclaimed **children of this
map**".

Each of the three filters costs something:

- **Children of a map**: `br list` has no `--parent` or `--epic` filter (checked
  the full flag list). `br dep tree <epic>` prints only the epic — it walks
  dependencies, and the parent-child edge points the other way. `br epic status`
  knows the child *count* (`0/2 children closed`) but does not list them. What
  does work: `br create --parent <id>` mints **hierarchical ids** —
  `<map-id>.1`, `.2` — so a map's children are an id-prefix match. Verified.
  That is a string match on ids, where GitHub had a sub-issues endpoint.
- **Unblocked**: `br list --format json` reports `dependency_count`, which
  **counts the parent-child edge too** — a child with one parent and one blocker
  showed `dependency_count: 2`. So it is not a blocked test. The blocked set
  needs a second call, `br blocked`. Verified.
- **Unclaimed**: `br list --unassigned` works directly. Verified.

So the frontier becomes roughly `br list --status open --unassigned --format
json`, filtered to ids prefixed with the map id, minus the ids in `br blocked` —
two calls and a filter, against GitHub's one `gh issue list` plus an
`issue_dependencies_summary` field. Not a blocker; it is a rewrite of the one
query the whole wayfinder flow leans on, and it should be written once in the
tracker doc rather than rediscovered per session.

Two things go the *other* way and are worth banking:

- `br close <id> --suggest-next` returns the newly-unblocked issues from the
  close itself (verified: closing a blocker printed `Unblocked 1 issue(s)` and
  named it). GitHub needs a re-query. The wayfinder resolve step gets cheaper.
- A parent epic shows in `br blocked` as blocked by its own open children.
  Reads oddly, but it is exactly the "a map closes when its children do" rule,
  enforced by the tool instead of by prose.

**2. Claim without a status change is a different command.** `--claim` is
atomic and sets `status=in_progress` as well as the assignee. That is right for
`/implement`, and wrong for a wayfinder claim, which marks a ticket taken
without starting it. The plain `br update <id> --assignee <actor>` does the
narrow thing — verified. Two claim verbs where GitHub had one
`--add-assignee @me`.

**3. Server-side automation on issue events.** `clear-in-review.yml` fires on
GitHub's issue-closed event. `br` is a local binary with no daemon and no
hooks, so nothing fires on its own. Costs nothing here — the workflow is already
condemned — but it is the shape of the loss: any future "when an issue closes,
do X" wants a git hook or a skill step, not a workflow.

**4. The VS Code sidebar.** Accepted loss, already decided. Two details worth
recording rather than rediscovering:

- The loss is **larger than eight queries**. `issue-counts` names it in a
  comment — "Keep this list in sync with the vscode `githubIssues.queries` Other
  query" — so one label list is duplicated across a bash script and a JSON
  config, and both are hand-maintained. Moving to `br` deletes the duplication
  along with the sidebar, since `br count --by-status` derives the groups from
  status instead of restating a label list.
- `githubIssues.queries` interpolates `${owner}/${repository}`, so it is
  per-repo already. Nothing cross-repo is lost with it.

## What the sweep did not find

No `gh search issues` anywhere. No GitHub Projects usage. No GraphQL beyond the
`--json` fields `gh` fills in. No script outside `flow/bin/` reads issue state.
The blast radius is one contract doc, one bash script, one JSON config, two
skill files, two prose mentions, and a workflow that was already dying.

## Sizing, in one line

**Twelve issue call sites; four rewrites that matter** (`docs/agents/issue-tracker.md`,
`flow/bin/issue-counts`, `implement/SKILL.md`, `burndown/SKILL.md`), **three
one-line prose edits**, **two deletions**, and **one query that must be
redesigned rather than translated** — the wayfinder frontier. Two of the four
rewrites get *shorter* under `br`, not longer.
