# Post-sweep grilling workflow

`all-audits/SKILL.md` points here for the grill. This is the grill's own walk
of every report the sweep produced — the user never names one for it to
start.

## Grilling a report

Grill every report the sweep produced, one after another, without waiting to
be told which one. When the user asks to grill the sweep, start at the top of
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
list is there (`log_path`) — read that, not the summary HTML, which holds only
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

## Land one spec for the whole sweep

Once every report in the run is grilled, land the sweep's decisions as **one
spec, sliced into tickets** — never one spec per audit, and never a map.
Per-audit structure survives as a section per audit inside that one spec, so a
later audit's amendment or overrule of an earlier one stays readable in the
same document.

1. **Draft the spec.** Follow `/to-spec`'s template and process, but skip its
   interview — every decision needed is already settled from grilling. Each
   ACT item becomes a user story and an implementation decision, grouped under
   its audit's section; a DROP is not included in the spec (see below for
   where it goes). Note any `ADR-NNNN` a decision revisits.
2. **One confirmation, then file.** Show the user the drafted spec and the
   list of proposed ticket titles `/to-tickets` would slice it into. Wait for
   one approval. This is the only point in the whole sweep where the agent
   writes something the user would otherwise have to delete by hand — a
   thirteen-audit sweep can propose twenty-plus tickets in one go, so ask
   once, before any of it exists on the tracker.
3. **Nothing is written until that approval lands.** If the user asks for
   changes, redraft and show again — still nothing is filed. If the user
   declines outright, stop; the decisions stay in this session only.
4. **On approval, publish.** Run `/to-spec` to publish the spec issue —
   labelled `spec`, never `ready-for-agent`, so nothing starts building it
   unsliced — then `/to-tickets` to slice it into the approved tickets.

## Write down every rejection

At the same point — after approval, alongside filing the spec — append every
DROP decision from the whole sweep to the audited repo's `.audit-ignore.md`,
one entry per rejection, in the format `harness/IGNORE-FILE.md` defines
(finding, reason, date, audit). This runs whether or not any ACT item existed;
a sweep that only rejected findings still writes its rejections down.

A DROP that is a standing architectural decision — not just "not now" but "not
ever, and here's why" — also gets an ADR written in the audited repo (its
existing `docs/adr/` convention), and that ignore entry's `adr:` field links to
it. Most rejections are too small for this; reserve it for the ones worth
prose on their own.
