# Post-sweep grilling workflow

`all-audits/SKILL.md` points here after it reports the index and stops. This
is what to do once the user picks a report to grill — the sweep itself does
not start this on its own.

## Grilling a report

When the user picks an audit to grill, run the `grilling` skill over **that one
report's findings**. Grill the findings toward decisions — which to act on, which
to drop, which need a closer look. Walk one audit at a time; do not merge them
into one grilling — a comment cut and an architecture deepening share no design
tree.

Read the findings from the audit's own record: for an audit that writes
`findings.jsonl` (see [`findings-schema.md`](findings-schema.md)), the full
list is there (`log_path`) — read that, not the summary HTML, which holds only
grouped counts. For an audit that renders a full HTML report instead, the
report is the record.

**Dedup against audits already grilled this run.** You grill the audits one after
another in the same session, so the decisions you have already reached are in
context — use them. For every finding in the current report, check it against what
you already decided. A match is **semantic**, not same-file: the same underlying
issue or fix, even if two reports word it differently or name different files; two
audits touching one file for unrelated reasons are *not* a match. For a finding
that repeats a settled one, do not grill it cold — surface it: "already decided
`<decision>` while grilling `<audit>` — carry it forward, or re-open?" Grill only
the fresh findings from scratch. Grilling the widest-reaching audit first
(architecture, thermo) settles the most before the narrower passes run.

A grill ends at **decisions**. Do not chain into `/to-spec`, `/to-tickets`, or any
build step — handing a decision off to the build pipeline is a separate call the
user makes when ready.

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
