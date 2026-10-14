# Post-sweep grilling workflow

`all-audits/SKILL.md` points here after the sweep reports its index — the
sweep continues straight into this, the grill's own walk of every report it
produced, without being asked and without the user naming one to start.

## Check the ignore-file path, in both modes

Before the offer below, and so before the first DROP is written, look for
rejections kept anywhere in the audited repo other than `.audit-ignore.md` —
a `docs/audit-ignores.md`, an `audit-ignore` section in another file. The
driver reads only the one path in `IGNORE-FILE.md` § Location, so an entry
anywhere else never reaches an audit's prompt and its finding comes back in
this sweep as fresh. If you find one, ask the user about it now, in the same
message as the offer, with a recommendation, whichever mode follows. Until
the user answers, treat each finding such an entry rejected as a reversal of
an ignore-file entry: in the batch mode it is asked, never decided.

## Offer the batch mode

Right after the index, ask one question before the first report:

> Grill each report (default), or apply my recommendation to every finding
> and ask only the contested ones?

A user reply in that spirit selects the batch mode too — "your recs to
everything except controversial stuff" is one. Any other reply is the
default: grill every fresh finding per § Grilling a report, unchanged. Ask
once per sweep; never re-offer between reports.

The per-finding grill exists because a decision is the user's, not the
agent's (#526, #579). The batch mode keeps that: the user opted in, and these
categories still go to the user as questions, never decided by the agent:

- a doc-vs-code contradiction — the user's precedence rules make it the
  user's call;
- anything irreversible, or anything that needs a golden re-freeze;
- a reversal of an ADR or of an existing ignore-file entry, wherever that
  entry is kept;
- a choice where the evidence is thin, or where the audit itself defers to
  the user ("your ruling which").

For every other finding, the agent decides, walking the reports in the same
order as the default mode:

- **Read every report** in full, from its record (below), not its summary.
- **Spot-check against the source** the claims it is about to act on, and
  the claims behind each DROP. A finding is the audit's claim, not a fact.
- **Apply the auto-carry rule unchanged** (below).
- **Write each DROP to the ignore file as it is decided**, exactly per
  § Grilling a report. A contested finding is not decided until the user
  answers, so its DROP is written then.

When the walk is done, send **one reply** carrying:

1. the contested questions, numbered, each with a recommendation;
2. **Calls I applied without asking** — a short list of the close calls the
   agent decided that were reversible, so the user can overrule any one;
3. the specs and ticket drafts (§ Land one spec per area, step 1),
   written as if every recommendation in item 1 were taken.

That reply is the single confirmation gate of § Land one spec per area,
step 2, unchanged. An answer that differs from a recommendation, or
an overrule of an applied call, is a change to the draft: apply it, then show
the redrafted specs and tickets again before anything is filed. An answer
that makes a finding a DROP writes its ignore entry right then. An overrule
that turns a written DROP into an ACT deletes that entry, and its ADR if it
got one (`IGNORE-FILE.md` § Reversing a rejection) — otherwise every later
sweep keeps hiding the finding its ticket is about.

## Grilling a report

Grill every report the sweep produced, one after another. Start at the top of
the order below and work down. Run the `grilling` skill over **one report's findings at a
time**. Grill the findings toward decisions — which to act on, which to drop,
which need a closer look. Walk one audit at a time; never merge two reports
into one grilling — a comment cut and an architecture deepening share no
design tree.

**Order: widest-reaching first, fixed.** Grill in this order, so the run
that touches the most decisions settles first and cheapens everything after
it. Skip any name below that has no report in this run:

1. `improve-codebase-architecture` — shallow modules and deepening opportunities.
2. `thermo-nuclear-code-quality-review` — abstraction quality, giant files, spaghetti growth.
3. `crap-audit` — per-function CRAP score, real risk hotspots.
4. `ponytail-audit` — over-engineering: what to delete, shrink, or replace with stdlib.
5. `duplication` — one behavior with two homes.
6. `dead-code` — functions, classes, imports nobody calls.
7. `error-handling` — swallowed errors against the fail-loud rule.
8. `type-tightness` — loose `Any`, unexplained `# type: ignore`, fake boundaries.
9. `domain-drift` — code vocabulary that drifts from the project's domain terms.
10. `docstring-coverage` — undocumented public API on a `py.typed` surface.
11. `test-audit` — tests that prove nothing or check the wrong thing.
12. `comment-audit` — comments that do not earn their place.
13. `audit-instructions` — instruction files against Anthropic's current guidance.

Read the findings from the audit's own record: for an audit that writes
`findings.jsonl` (see [`findings-schema.md`](findings-schema.md)), the full
list is there — read that, not the summary HTML, which holds only
grouped counts. For an audit that renders a full HTML report instead, the
report is the record.

**Rule: a semantic match with a settled decision is carried forward, never
asked again.** You grill the audits one after another in the same session, so
the decisions you have already reached are in context — use them. For every
finding in the current report, check it against what you already decided. The
match test is **semantic, not same-file**: the same underlying issue or fix,
even if two reports word it differently or name different files, is a match;
two audits touching one file for unrelated reasons is **not** a match. For a
finding that matches a settled decision, do not grill it cold and do not put
it to the user as a question — surface it as carried forward: "already decided
`<decision>` while grilling `<audit>` — carrying it forward (say if you want
it re-opened instead)." Grill only the fresh, non-matching findings from
scratch.

Grilling changes no code and opens no PR — the sweep and its grill are
report-and-decide-and-file only; applying any finding's fix is a separate,
opt-in step outside this workflow.

**Write down each rejection as you reach it.** The moment a finding is
decided DROP, append it to the audited repo's `.audit-ignore.md` right then —
don't wait for the sweep to finish grilling. One entry per rejection, in the
format `harness/IGNORE-FILE.md` defines (finding, reason, date, audit). This
is independent of whether the spec below ever gets approved: a rejection is
real the moment it's decided, and a session that ends mid-sweep must not lose
the DROPs it already made. A DROP that is a standing architectural decision —
not just "not now" but "not ever, and here's why" — also gets an ADR written
in the audited repo (its `docs/adr/` convention if it has one, else a new
`docs/adr/` there), and that ignore entry's `adr:` field links to it. Most
rejections are too small for this; reserve it for the ones worth prose on
their own.

## Land one spec per area

Once every report in the run is grilled, land the sweep's ACT decisions as
**one spec per area, each sliced into tickets** — never one spec per audit,
and never a map. An area cuts across audits, so the per-audit structure
survives as a section per audit inside each area's spec. A later audit's
amendment or overrule of an earlier one stays readable in the same document —
call out each amendment or overrule explicitly in the section of the audit
that made it, naming the decision it changes. When the decision it changes
sits in another area's spec, name it in both.

Why areas: with one spec for the whole sweep, the parent stays open until the
slowest area finishes and its closing live check covers every area at once.
An area closes on its own.

**Grouping** (ruled by Chris, 2026-10-13):

- **An area is your judgement of which accepted findings touch the same
  code.** It is not a mechanical grouping by include closure or by directory:
  a flat repo would put nearly everything in one area.
- **The floor.** An area with fewer than three tickets folds into its nearest
  neighbour. A sweep with fewer than about ten tickets in all stays one spec.
- **A ticket that crosses areas** goes in the spec of the area whose code it
  changes most, with a native blocker edge to the other area's ticket. The two
  areas do not merge.
- **No parent over the specs.** Each spec carries one line naming the sweep
  run, as `Sweep run: <the run folder holding index.html>`, and nothing else
  ties them together.

1. **Draft the specs and their slices, together.** Group the ACT decisions
   into areas first. Then write each spec directly using `/to-spec`'s
   template — skip its interview and its seam-check-with-the-user step, since
   every decision the template needs is already settled from grilling. Each
   ACT item becomes an implementation decision, grouped under its audit's
   section; write it as a user story only where a real actor and benefit
   exist — most audit findings are internal code-quality fixes with neither,
   and forcing "as a developer, I want fewer unused functions" onto one is
   padding, not a story. DROPs stay out of the specs; they already went to
   the ignore file above. Then, still in this same drafting pass and before
   showing the user anything, break each spec into vertical slices using
   `/to-tickets`'s own rules — title, blocking edges, what it delivers, seams
   under test per ticket — including the cross-area edges above. One
   confirmation has to cover the whole shape, so the shape has to exist before
   that confirmation, not after.
2. **One confirmation, then file — and only one.** Show the user every
   drafted spec and the full ticket breakdown (not just titles — blocking
   edges and seams too, the cross-area edges marked), and wait for one
   approval covering all of it. Nothing is written to the tracker until it
   lands; asked for changes, redraft and show again; declined outright, stop —
   the draft stays in this session only. A thirteen-audit sweep can propose
   twenty-plus tickets in one go, so this is the one point in the whole run
   the agent writes something the user would otherwise delete by hand.
3. **On approval, publish — specs first, unlabelled, then tickets, then
   cross-area edges, then both labels on each parent last.** File each
   approved spec as an issue with no `spec` label yet. Publish the approved
   tickets as their spec's children, each labelled `ready-for-agent`, using
   `/to-tickets`'s publish step and its blocking-edge and parent-linking
   conventions — its own quiz-and-iterate step is skipped, since the breakdown
   was already approved in step 2. A cross-area blocker edge needs both
   tickets to exist, so add those edges only after every spec's children are
   filed. Only once every child is linked and every edge is in place, label
   each parent `spec` **and** `ready-for-agent` — plain `implement-dispatch`
   refuses a `spec`-labelled issue, so that pair sends it to `/implement-spec`
   instead of an ordinary agent building it unsliced, and a parent labelled
   early could be dispatched before its blockers exist.
