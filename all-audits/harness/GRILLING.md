# Post-sweep grilling workflow

`all-audits/SKILL.md` points here after the sweep reports its index — the
sweep continues straight into this, the grill's own walk of every report it
produced, without being asked and without the user naming one to start.

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

## Land one spec for the whole sweep

Once every report in the run is grilled, land the sweep's ACT decisions as
**one spec, sliced into tickets** — never one spec per audit, and never a map.
Per-audit structure survives as a section per audit inside that one spec, so a
later audit's amendment or overrule of an earlier one stays readable in the
same document — call out each amendment or overrule explicitly in the section
of the audit that made it, naming the decision it changes.

1. **Draft the spec and its slices, together.** Write the spec directly using
   `/to-spec`'s template — skip its interview and its seam-check-with-the-user
   step, since every decision the template needs is already settled from
   grilling. Each ACT item becomes an implementation decision, grouped under
   its audit's section; write it as a user story only where a real actor and
   benefit exist — most audit findings are internal code-quality fixes with
   neither, and forcing "as a developer, I want fewer unused functions" onto
   one is padding, not a story. DROPs stay out of the spec;
   they already went to the ignore file above. Then, still in this same
   drafting pass and before showing the user anything, break it into vertical
   slices using `/to-tickets`'s own rules — title, blocking edges, what it
   delivers, seams under test per ticket. One confirmation has to cover the
   whole shape, so the shape has to exist before that confirmation, not after.
2. **One confirmation, then file — and only one.** Show the user the drafted
   spec and the full ticket breakdown (not just titles — blocking edges and
   seams too), and wait for one approval covering both. Nothing is written to
   the tracker until it lands; asked for changes, redraft and show again;
   declined outright, stop — the draft stays in this session only. A
   thirteen-audit sweep can propose twenty-plus tickets in one go, so this is
   the one point in the whole run the agent writes something the user would
   otherwise delete by hand.
3. **On approval, publish — spec first, unlabelled, then tickets, then the
   `spec` label last.** File the approved draft as the spec issue with no
   `spec` label yet — `/to-tickets`'s own guard treats a `spec`-labelled
   source as already sliced and stops instead of publishing children.
   Publish the approved tickets as its children, each labelled
   `ready-for-agent`, using `/to-tickets`'s publish step and its blocking-edge
   and parent-linking conventions — its own quiz-and-iterate step is skipped,
   since the breakdown was already approved in step 2. Only once the children
   are linked, label the parent `spec` — never `ready-for-agent` — so nothing
   starts building it unsliced.
