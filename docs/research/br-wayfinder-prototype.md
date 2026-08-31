# One wayfinder map, end to end on br

Findings for [Run one wayfinder map end to end on br](https://github.com/caneff/agent-skills/issues/469),
child of the tracker-migration map [#466](https://github.com/caneff/agent-skills/issues/466).

## What was run

Map #466 itself was mirrored into `br` 0.5.7 — an epic plus its ten real
tickets, their real types and statuses, and all eleven blocking edges — in a
throwaway git repo. The `policy.yaml` is the one verified in
[#474](https://github.com/caneff/agent-skills/issues/474), six statuses,
`status_groups.ready: [ready_agent]`.

Types and statuses came straight from the #474 mapping: `wayfinder:*` labels
became types (`research`, `prototype`, `grilling`, `task`), the map became an
epic, and every HITL ticket sat at `ready_human`.

Children got hierarchical ids under the epic: `brmap-pdx.1` … `brmap-pdx.10`,
in creation order. Parentage is readable from the id.

## Is `br ready` the frontier? No.

```
$ br ready
✨ No ready issues match the requested filters or configured ready status group
$ br ready --parent brmap-pdx
✨ No ready issues match the requested filters or configured ready status group
```

Every ticket on a wayfinder map is HITL, so every ticket sits `ready_human`,
and `ready_human` is not in the ready group. `br ready` is blind to a wayfinder
map by construction. This confirms
[#468](https://github.com/caneff/agent-skills/issues/468).

`dependency_count` is no help either — a child with no blocker still reports
`dependency_count: 1`, because the parent-child edge counts.

## The frontier query that works

Three calls: the blocked set, the candidate set, and a subtraction. `br list`
has no `--parent`, so the map's children are matched by id prefix.

```sh
MAP=brmap-pdx
br blocked --format json | jq -r '.issues[].id' > /tmp/blocked
br list -s ready_human -s ready_agent --unassigned \
       --sort created_at --reverse --format json \
  | jq -r --arg m "$MAP." '.issues[] | select(.id|startswith($m)) | "\(.id)\t\(.title)"' \
  | awk -F'\t' 'NR==FNR{b[$1];next} !($1 in b)' /tmp/blocked -
```

Run against the mirrored map it returned exactly the GitHub frontier —
#469, #471, #475, #476 — in map order.

It is also the **fast** side. Three `br` calls take 61 ms against local SQLite,
and they work offline. The same frontier from GitHub is one API call — the
`sub_issues` endpoint embeds `issue_dependencies_summary` — and takes 489 ms.
The pipeline costs shell written once, never latency.

Two traps in that pipeline, both load-bearing:

- **Sort by `created_at`, never by id.** Ids sort as text, so `.10` comes
  before `.3` and map order is lost.
- **`--sort created_at` is newest-first.** `--reverse` gives map order. The
  flag name reads backwards.

## Do `br dep add` edges express blocking the way the map needs? Yes.

`br blocked` lists open blockers only, and closing a blocker drops the
dependent out of the list. The epic itself appears in `br blocked` until its
children close, so the map advertises its own state:

```
[● P2] brmap-pdx: Move planning off GitHub issues onto br?
  Blocked by 5 open dependencies: [brmap-pdx.10, brmap-pdx.5, ...]
```

`br show <id>` prints **Dependents** as well as Dependencies — what this
ticket unblocks, which the GitHub issue page does not show.

## Does claiming work without an assignee field?

There is an assignee field, and `br update <id> --assignee <name>` claims a
ticket without touching its status. That is exactly wayfinder's claim.

`--claim` is the other verb: it sets `in_progress` **and** the assignee, and it
is the one the per-actor capacity cap guards. A bare `--assignee` claim is not
capped — three tickets were assigned to one actor in a row with no complaint.
The cap protects agent swarms, not wayfinder claims.

## What the human looks at instead of the GitHub UI

| want | command |
|---|---|
| map progress | `br epic status` → `Progress: 5/10 children closed (50%)` |
| what is takeable | the frontier query above |
| what is stuck, and why | `br blocked` |
| one ticket, with what it unblocks | `br show <id>` |
| the human's own queue | `br list -s ready_human` |

`br list --pretty` is **not** a tree — it prints a flat list with each ticket's
fields on branch characters, children not nested under the epic. No built-in
view renders the map as a hierarchy.

## The missing view is 16 lines of shell

Nothing in `br` shows a map whole, so this does. It runs in 109 ms and it is
the one thing a human opens instead of the GitHub issue page.

```sh
#!/usr/bin/env bash
# br-map <epic-id> — render a wayfinder map: children in map order, frontier marked.
set -euo pipefail
MAP="${1:?usage: br-map <epic-id>}"
blocked=$(br blocked --format json | jq -r '.issues[].id')
br epic status --json | jq -r --arg m "$MAP" '.[] | select(.epic.id==$m) | "\(.epic.id)  \(.epic.title)  —  \(.closed_children)/\(.total_children) closed"'
br list -s all --sort created_at --reverse --format json \
  | jq -r --arg m "$MAP." '.issues[] | select(.id|startswith($m)) | "\(.id)\t\(.status)\t\(.assignee // "-")\t\(.issue_type)\t\(.title)"' \
  | awk -F'\t' -v B="$blocked" '
      BEGIN { n=split(B,L,"\n"); for(i=1;i<=n;i++) b[L[i]]=1 }
      { mark = "."
        if ($2=="closed") mark="x"
        else if ($1 in b) mark="-"
        else if ($3=="-") mark=">"
        printf "  %s %-14s %-12s %-10s %s\n", mark, $1, $2, $4, $5 }'
echo "  legend: > frontier   - blocked   x closed   . claimed"
```

Output against the mirrored map:

```
brmap-pdx  Move planning off GitHub issues onto br?  —  4/10 closed
  x brmap-pdx.1    closed       research   Verify what br actually does
  x brmap-pdx.2    closed       task       Inventory every GitHub call site and what br would replace it with
  > brmap-pdx.3    ready_human  prototype  Run one wayfinder map end to end on br
  x brmap-pdx.4    closed       prototype  Two worktrees, one base: does br sync --merge hold?
  > brmap-pdx.5    ready_human  grilling   What happens to the 50 open GitHub issues?
  - brmap-pdx.6    ready_human  grilling   Which repos move, in what order?
  - brmap-pdx.7    ready_human  grilling   Go or no-go, and write the route
  x brmap-pdx.8    closed       grilling   Labels or statuses: how does the routing scheme port to br?
  > brmap-pdx.9    ready_human  grilling   How does br get installed and pinned?
  > brmap-pdx.10   ready_human  grilling   Ticket writes land in the primary checkout, which agents may not touch
  legend: > frontier   - blocked   x closed   . claimed
```

It subsumes the frontier query — the `>` rows **are** the frontier — so a
migration installs one script, `flow/bin/br-map`, not two. That install is code
and belongs to the go decision, not to this prototype.

## Defect: `br close --suggest-next` reports nothing

#468 recorded that `--suggest-next` names the newly-unblocked set. On 0.5.7 it
does not:

```
$ br close brmap-pdx.3 --suggest-next --json
{"closed":[{"id":"brmap-pdx.3", ...}],"unblocked":[]}
```

`brmap-pdx.6` was blocked by `brmap-pdx.3` alone, was `ready_agent`, and
dropped out of `br blocked` on that very close — yet `unblocked` was empty.
Reproduced twice: once for an epic child, once for two standalone tickets with
a single `blocks` edge and no parent. Treat `--suggest-next` as unavailable.

It costs little. With `br-map` below, a close is followed by one command that
shows the new frontier, so the dead flag saves a keystroke, not a step.

## Cost of the exercise

Charting the ten-ticket map took eleven `br create` calls and eleven
`br dep add` calls, all scriptable, no network. The same map on GitHub needs a
network round trip per call and a database-id lookup per dependency edge.
