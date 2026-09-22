# The frontier: what a run may dispatch next

The **frontier** is the set of tickets a run may dispatch right now: open,
carrying the run's label, unclaimed, and not waiting on anything. Reading it
is `burndown/frontier.py` — `python3 burndown/frontier.py <owner/repo>
<label>`, or `frontier(repo, label)` in process — and it answers in four
buckets, not two.

```
unblocked   901 The closure resolver
blocked     903 The dispatch loop  (blocked by #901)
unresolved  907 Liveness  (no native dependencies and no `## Blocked by` section)
spec        885 Spec: the lane rebuilt  (a spec parent: dispatch with `implement-dispatch --spec 885 --slots <k>`)
```

**A bucket is a claim about what an entry is**, so an entry that fits no
existing bucket gets a bucket rather than the nearest wrong one. Silence is
`unresolved` for the same reason: it is the honest answer, not the
convenient one. That is the rule behind the fourth bucket below, and the
reason not to collapse it back into `unresolved` for tidiness.

A claimed ticket — one with an assignee, or the `in-progress` label — is in
no bucket at all. It is off the frontier because someone already has it.

**A non-dispatchable ticket is in no bucket either.** `implement-dispatch`
refuses some tickets on a label alone, whatever their blockers say, and a
ticket it will not take is not work this reader may offer. The set is
`NON_DISPATCHABLE_LABELS` in the reader; it holds `needs-info` — a ticket
waiting on grilling, not on another ticket. (`in-progress` is refused too,
and is handled above as a claim: an assignee says the same thing without a
label.)

The drop happens **before any bucket is decided**, so such a ticket's body
is never read. This is not the same posture as silence, and the difference
is the point: `unresolved` means "this ticket's blocking state could not be
determined, so a human must look", and that is the wrong question to ask
about a ticket no run may dispatch either way. Padding the bucket with items
a controller cannot act on trains them to skim it, which is the failure the
bucket was created to prevent.

## `spec` — dispatchable, by a different verb

A `spec`-labelled parent is **neither** of the above, which is why it has a
bucket of its own (#910).

It is not a drop: `implement-dispatch` refuses it in plain mode *while
naming the route that takes it* — `implement-dispatch --spec <n> --slots
<k>`, the nested run #897 landed. It is dispatchable work, and dropping it
hides real work from the only reader that surfaces it.

It is not `unresolved` either: nothing about its blocking state is in doubt,
and no human needs to look. What it needs is a different verb.

So the entry **names that verb**, with the ticket's own number filled in.
That is the point of the bucket rather than a decoration on it: a controller
reading the frontier can act on the line without opening another document.
An entry that said "this is a spec" and no more would have moved the problem
rather than answered it.

A claim outranks it. A spec parent that is assigned or `in-progress` is off
the frontier like any other claimed ticket — someone already has it, so
there is no route left to offer.

**`blocked` outranks `spec`, and the order is not arbitrary.** A spec parent
is dispatched by a different verb, but the frontier still checks its
prerequisites first: one with an open blocker — native edge or stated
section — reads `blocked`, not `spec`. Both would be true claims about the
entry, and that is exactly the trap. Only `spec` carries a dispatch verb,
and a controller copies a line like that; the cost of being wrong here is a
whole nested run over blocked work, against a controller seeing `blocked`
and having no line to copy, which is the correct experience for a ticket
that is not ready.

**An unreadable declaration stays `unresolved` too**, for the same reason a
blocked one stays `blocked`. Silence is the case that goes to `spec` — a
spec parent that never mentions blockers is off the frontier's blocking
question by its own nature. A ticket that *states* prerequisites this reader
cannot resolve has not been silent, and an unknown prerequisite is not a met
one. The route is offered only once the prerequisites are known and met.

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

  An inline line reaches to the end of that line and no further, and counts
  only in the **preamble** — the body above the first heading. The words
  must start the line: prose that says "this one is blocked by #7, we think"
  mid-sentence is not a declaration. Neither is anything indented four or
  more spaces (an indented code block) or starting with `>` (a blockquote):
  those lines are quotation everywhere, so they are not declarations and
  not part of a real section's answer either.
- **One declaration, or none.** Every visible section and every preamble
  inline line is a declaration. A ticket with more than one — two sections,
  two inline lines, or a section beside an inline line — is **ambiguous**,
  and ambiguous is unresolved: which one is the ticket's own cannot be told
  from the text, and a quoted copy of another ticket's blocker list looks
  the same as the real one. The reader never takes the first.
- **A fenced region is quoted, never declared.** Anything between ``` or ~~~
  fences is an example. A fence opens only at CommonMark's own bound — at
  most three spaces of indentation; four spaces or a tab is an indented code
  block, the same quotation the paragraph above already drops, not a fence
  (#999) — and closes CommonMark's way — on the same
  character, with a run at least as long as the opener, and nothing after it
  on the line — so a ```` fence goes on protecting a ``` line inside it,
  which is exactly how a ticket quotes this grammar: `/to-tickets` ships a fenced issue template
  containing a `## Blocked by` heading, and a ticket quoting this grammar
  carries one too. A ticket whose only `Blocked by` is inside a fence has
  stated nothing, so it is unresolved — reading the template's own
  `None — can start immediately.` as that ticket's answer is the
  false-ready dispatch this reader exists to stop.
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
