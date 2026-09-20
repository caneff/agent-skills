# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments,parent,blockedBy,issueType --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body], parent: .parent.number, blockedBy: [.blockedBy.nodes[].number], issueType: .issueType.name}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Relationships (parent, dependencies, type)**: record these as first-class GitHub fields, not as body prose, so automation reads structured data via the `--json` fields above:
  - Sub-issue of a parent: `gh issue create ... --parent <#>` (or `gh issue edit <#> --parent <#>` / `--remove-parent`).
  - Dependencies: `gh issue create ... --blocked-by <#,#> --blocking <#>` (or `gh issue edit <#> --add-blocked-by <#>` / `--remove-blocked-by <#>`, plus the `--add-blocking` / `--remove-blocking` pair).
  - Type: `gh issue create ... --type <name>` — only a type the org defines. `gh` errors on an unknown name, and types are unavailable on user-account repos, so omit `--type` when none exist.
- **Close**: `gh issue close <number> --comment "..."`

Pass `--repo <owner>/<name>` on every `gh` call; read the pair once from `git remote -v`. Without it `gh issue view` can print nothing and exit 0 (worktrees, cwd outside the clone), and `gh api` paths need the pair anyway.

## Grilling gate on new tickets

When filing a ticket, route it to whoever acts on it next, using two questions.

**1. Does it need grilling** — an open design decision, a tradeoff, or a departure from a documented standard that should be stress-tested before any code is written?

- **Yes, tracked in a wayfinder map**: no `ready-for-*` label. The wayfinder flow owns it — it lives as a `wayfinder:grilling` child of the map and is handled there.
- **Yes, standalone** (not part of a wayfinder map): label it `needs-info`. It goes through `/grill-with-docs` before `/implement`.

**2. If it does not need grilling, can the AFK agent build it end to end?**

- **Yes** — fully specified, mechanical, no human judgment or hands needed (a boundary move, reusing an existing helper, a refactor): label it `ready-for-agent`. This is the default for tracer-bullet work.
- **No** — specified, but it needs a human touch (a delicate change, a taste call, credentials or secrets, something you want to write yourself): label it `ready-for-human`.

So `ready-for-human` is only for a specified ticket a human builds, and `needs-info` is for a standalone ticket that needs grilling first. `ready-for-agent` is only for work the agent can take unattended.

Never file a ticket label-less. A bare issue reads as *untriaged / unknown*, not as a signal to anyone — so every ticket leaves the gate with exactly one routing label: a `ready-*` label, `needs-info` when it needs grilling, a `wayfinder:*` label when a map owns it, or `backlog` when the work is real and its turn has not come. Wanting a human to grill it is `needs-info` and wanting a human to build it is `ready-for-human`, never the absence of a label. A ticket too unclear to route is `needs-info`, with the body saying what is unclear. `needs-triage` is never a gate label — it is only for issues outside people open.

A quick sanity check the implementer can do while building (read the code, confirm one behavior) is neither grilling nor a human touch — write the constraint into the ticket and still mark it `ready-for-agent`.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate). Where dependencies aren't available, state the relationship in the ticket body instead, in one of the three forms the frontier reader parses: a `## Blocked by` section (what `/to-tickets` emits), a `Blocked by: #<n>, #<n>` line at the top of the child body, or a `**Blocked by:** ...` line. In any of them, a blocker is a bare `#<n>` in this repo and "no blockers" is the literal word `None`. A ticket is unblocked when every blocker is closed. Full grammar: `~/.agents/skills/burndown/references/frontier.md`.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list) and split them three ways, not two — **unblocked** (no open blocker), **blocked** (`issue_dependencies_summary.blocked_by > 0`, or a `Blocked by` naming an open issue), and **unresolved** (no native dependencies *and* no `Blocked by` of any form). A ticket with an assignee is off the frontier whichever bucket it would land in. Take the first unblocked ticket in map order. **Silence is unresolved, never unblocked**: a ticket that states nothing about its blockers is resolved by hand before it is dispatched, because dispatching one whose prerequisite is still open costs a whole build. `python3 ~/.agents/skills/burndown/frontier.py <owner/repo> <label>` runs exactly this query.
- **Claim**: `gh issue edit <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
