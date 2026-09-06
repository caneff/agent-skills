# Issue tracker: GitLab

Issues and specs for this repo live as GitLab issues. Use the [`glab`](https://gitlab.com/gitlab-org/cli) CLI for all operations.

## Conventions

- **Create an issue**: `glab issue create --title "..." --description "..."`. Use a heredoc for multi-line descriptions. Pass `--description -` to open an editor.
- **Read an issue**: `glab issue view <number> --comments`. Use `-F json` for machine-readable output.
- **List issues**: `glab issue list -F json` with appropriate `--label` filters.
- **Comment on an issue**: `glab issue note <number> --message "..."`. GitLab calls comments "notes".
- **Apply / remove labels**: `glab issue update <number> --label "..."` / `--unlabel "..."`. Multiple labels can be comma-separated or by repeating the flag.
- **Relationships (parent, dependencies, type)**: GitLab has no `gh`-style structured fields for these on the free tier — record them the same way the Wayfinding operations below do:
  - Sub-issue of a parent: Premium/Ultimate epics can hold it as a native child; on the free tier put `Part of #<parent>` at the top of the description instead.
  - Dependencies: the native blocking link via the `/blocked_by #<n>` quick action (Premium/Ultimate), or a `Blocked by: #<n>, #<n>` line where unavailable.
  - Type: GitLab's built-in issue Type field (Issue/Incident/Task) — set at creation in the web UI or via `glab api`; `glab issue create` has no `--type` flag, so omit it from the CLI command and set it after creation when it matters.
- **Close**: `glab issue close <number>`. `glab issue close` does not accept a closing comment, so post the explanation first with `glab issue note <number> --message "..."`, then close.
- **Merge requests**: GitLab calls PRs "merge requests". Use `glab mr create`, `glab mr view`, `glab mr note`, etc. — the same shape as `gh pr ...` with `mr` in place of `pr` and `note`/`--message` in place of `comment`/`--body`.

Infer the repo from `git remote -v` — `glab` does this automatically when run inside a clone.

## Grilling gate on new tickets

When filing a ticket, route it to whoever acts on it next, using two questions.

**1. Does it need grilling** — an open design decision, a tradeoff, or a departure from a documented standard that should be stress-tested before any code is written?

- **Yes, tracked in a wayfinder map**: no `ready-for-*` label. The wayfinder flow owns it — it lives as a `wayfinder:grilling` child of the map and is handled there.
- **Yes, standalone** (not part of a wayfinder map): label it `ready-for-human`. A human grills the decision, then implements.

**2. If it does not need grilling, can the AFK agent build it end to end?**

- **Yes** — fully specified, mechanical, no human judgment or hands needed (a boundary move, reusing an existing helper, a refactor): label it `ready-for-agent`. This is the default for tracer-bullet work.
- **No** — specified, but it needs a human touch (a delicate change, a taste call, credentials or secrets, something you want to write yourself): label it `ready-for-human`.

So `ready-for-human` covers both a standalone grilling ticket and any specified ticket a human should build. `ready-for-agent` is only for work the agent can take unattended.

Never file a ticket label-less. A bare issue reads as *untriaged / unknown*, not as a signal to anyone — so every ticket leaves the gate with exactly one routing label: a `ready-*` label, a `wayfinder:*` label when a map owns it, or `backlog` when the work is real and its turn has not come. Wanting a human to see or grill it is `ready-for-human`, never the absence of a label.

A quick sanity check the implementer can do while building (read the code, confirm one behavior) is neither grilling nor a human touch — write the constraint into the ticket and still mark it `ready-for-agent`.

## Merge requests as a triage surface

**MRs as a request surface: no.** _(Set to `yes` if this repo treats external merge requests as feature requests; `/triage` reads this flag.)_

When set to `yes`, MRs run through the same labels and states as issues, using the `glab mr` equivalents:

- **Read an MR**: `glab mr view <number> --comments` and `glab mr diff <number>` for the diff.
- **List external MRs for triage**: `glab mr list -F json`, then keep only MRs whose author is not a project member/owner (a contributor's MR, not a maintainer's in-flight work).
- **Comment / label / close**: `glab mr note`, `glab mr update --label`/`--unlabel`, `glab mr close`.

Unlike GitHub, GitLab numbers issues and MRs separately, so `#42` is unambiguous once you know which surface the maintainer means.

## When a skill says "publish to the issue tracker"

Create a GitLab issue.

## When a skill says "fetch the relevant ticket"

Run `glab issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `glab issue create --label wayfinder:map`. (On GitLab tiers with native epics, an epic may hold the map instead; a labelled issue works everywhere.)
- **Child ticket**: an issue carrying `Part of #<map>` at the top of its description and labels `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitLab's **native blocking link** — the canonical, UI-visible representation. Add it with the `/blocked_by #<n>` quick action, posted as a note (`glab issue note <child> --message "/blocked_by #<blocker>"`). Native blocking links are a Premium/Ultimate feature; on the free tier (or where unavailable) fall back to a `Blocked by: #<n>, #<n>` line at the top of the description. A ticket is unblocked when every blocker is closed.
- **Frontier query**: `glab issue list -F json` scoped to the map's children, drop any with an open blocker — a native `blocked_by` link to an open issue (`glab api projects/:id/issues/:iid/links`), or an open issue in the `Blocked by` line — or an assignee; first in map order wins.
- **Claim**: `glab issue update <n> --assignee @me` — the session's first write.
- **Resolve**: `glab issue note <n> --message "<answer>"`, then `glab issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
