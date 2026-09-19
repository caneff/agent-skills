# The frontier: what a run may dispatch next

The **frontier** is the set of tickets a run may dispatch right now: open,
carrying the run's label, unclaimed, and not waiting on anything. Reading it
is `burndown/frontier.py` — `python3 burndown/frontier.py <owner/repo>
<label>`, or `frontier(repo, label)` in process — and it answers in three
buckets, not two.

```
unblocked   901 The closure resolver
blocked     903 The dispatch loop  (blocked by #901)
unresolved  907 Liveness  (no native dependencies and no `## Blocked by` section)
```

A claimed ticket — one with an assignee, or the `in-progress` label — is in
no bucket at all. It is off the frontier because someone already has it.

## Three sources, in order

**1. The tracker's native dependencies, where it has them.** On GitHub that
is `issue_dependencies_summary.blocked_by`, which counts **open blockers
only** and so is the live gate: nonzero is blocked, zero is unblocked. This
is the canonical path — the edges are queryable, the UI shows them, and
closing a blocker moves the count without anyone editing prose. Set them with
`gh issue edit <n> --add-blocked-by <#>` (see `docs/agents/issue-tracker.md`).

`total_blocked_by` counts every blocker, open or closed. A ticket whose
`total_blocked_by` is zero has **no native edges at all** — that is silence,
not an answer, and the reader falls through to the section. Where native
edges exist they win: they are live, and the section is prose someone typed
once.

**2. A stated `Blocked by`**, for a repo whose tickets carry the
relationship as prose. The reader parses the grammar below and nothing else.

**3. Nothing at all** — no native edges and no section. That ticket is
**unresolved**: not blocked, and emphatically not unblocked. It is reported
as unresolved and **never dispatched** on the assumption that silence means
clear. Reading a missing section as unblocked is the expensive failure — it
puts a worker on a ticket whose prerequisite is still open, and the cost is a
whole build. A controller resolves an unresolved ticket once, by hand, before
the wave: read it, then either add native edges or write the section.

Evidence: on `sudokumaker-custom-constraints` (#781) the repo had no native
links, the edges lived in `## Blocked by` sections, and **8 of 21**
`ready-for-agent` tickets had no such section at all.

## The `## Blocked by` grammar

This is what `/to-tickets` emits and what the fallback reader parses. Nothing
outside it is read as an edge.

- **Three written forms**, because the tree already writes three, and a
  ticket written to one of the repo's own templates must not read as silence:
  - a **section** under an ATX heading whose text is exactly `Blocked by` —
    `## Blocked by` canonically, any level, any case, optional trailing
    colon. It runs to the next heading of any level, or to the end of the
    body. This is what `/to-tickets` emits.
  - an **inline line** — `Blocked by: #7, #8` at the top of the body, the
    form `docs/agents/issue-tracker.md` gives `/wayfinder` children.
  - a **bold inline line** — `**Blocked by:** ...`, from `/to-tickets`'s
    local ticket template. The markers are not part of the answer, whichever
    side of them the colon sits on.

  An inline line reaches to the end of that line and no further. The words
  must start the line: prose that says "this one is blocked by #7, we think"
  mid-sentence is not a declaration. Where a ticket carries both a section
  and an inline line, the section wins.
- **A blocker** is a bare `#NNN` reference to an issue in the same repo,
  anywhere in the section — one per list item is the house form. A ticket is
  blocked when any referenced issue is open, and unblocked when every one of
  them is closed.
- **No blockers** is the literal word `None`, optionally with a list marker
  and a trailing clause: `None — can start immediately.` That is a statement,
  and it reads as unblocked.
- **Anything else is unresolved.** An empty section, or an inline line
  with nothing after it, states nothing. Prose
  naming no `#NNN` ("the database work, probably") states nothing this
  grammar can read. A cross-repo `owner/repo#NNN` is outside the grammar —
  the reader will not read its tail as a local `#NNN`, because gating a
  ticket on an unrelated local issue is worse than admitting it cannot tell.
- **A blocker whose state cannot be read** — a number that names nothing in
  this repo, or a `gh` call that fails — is unresolved too. A blocker that
  cannot be found is not a closed blocker.

## Why it is not just a regex at the call site

A skill cannot say "take the frontier" and mean a query that does not exist.
The one wave computed by hand on #781 meant fetching all 21 bodies and
regex-parsing them in the controller's own context, with no place for the
third answer to live. The reader exists so that the third answer — *I cannot
tell* — has a name, a bucket, and a test.
