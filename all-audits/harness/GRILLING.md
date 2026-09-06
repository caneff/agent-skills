# Post-sweep grilling workflow

`all-audits/SKILL.md` points here after it reports the index and stops. This
is the grill's own walk of every report the sweep produced — the user never
names one for it to start.

## Grilling a report

Grill every report the sweep produced, one after another, without waiting to
be told which one. Run the `grilling` skill over **one report's findings at a
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

A grill ends at **decisions**. Do not chain into `/to-spec`, `/to-tickets`, or any
build step — handing a decision off to the build pipeline is a separate call the
user makes when ready. Grilling changes no code and opens no PR — the sweep and
its grill are report-and-decide only; applying anything is a separate, opt-in
step outside this workflow.

## Turn the decisions into a map

The sweep's decisions land on the tracker as **one `wayfinder:map` issue for the
run**, with each audit's decisions a cluster of decision tickets under it. The map
is an index, not a store: each decision lives in its own child ticket; the map
gists and links. The map is self-contained and ephemeral — once `/to-spec` and
`/to-tickets` slice the ACT items into build tickets, its job is done. Do **not**
point the map or its tickets at the HTML reports; the context and decisions live
in the map and tickets, and the reports are throwaway scaffolding.

At the end of each audit's grill, produce the filing command — never run it, the
map pipeline is the user's to drive:

- **First audit grilled** — write the brief to a file in the run's collection dir
  (destination, then the settled decisions), and emit **`/wayfinder read @<file>`**
  for the user to run — a file reference, not a wall of inline text. Seed the brief
  so wayfinder records the decisions rather than re-grilling: mark each ACT item as
  build-bound, each DROP as a recorded rejection (so a later audit does not
  resurface it), and flag any `ADR-NNNN` a decision revisits.
- **Later audits** — the map already exists. Emit the instruction to add each new
  decision as a **child ticket under that map** (`#NNN`), not a fresh `/wayfinder`
  — a second `/wayfinder` starts a second map.
