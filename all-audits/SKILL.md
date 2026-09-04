---
name: all-audits
description: Run every repo audit at once — thirteen audit skills in parallel, one HTML index linking each report, then grill through them one at a time. Slash-only.
disable-model-invocation: true
argument-hint: "[path]"
---

Run the whole audit set over one repo in a single sweep. Thirteen audit skills fan
out in parallel, each as its own process; each writes a self-contained report;
the reports collect under one folder behind an `index.html` that links them. The
sweep **reports only** — it applies nothing and
opens no PR. When it finishes it stops and hands you the index, so you decide what
to grill.

Scope: `$ARGUMENTS` if given, else the current working directory — the repo you
are standing in. The whole repo, not a branch diff.

## The set — thirteen skills

Each audits the whole repo and renders a visual-teach HTML report:

- `ponytail-audit` — over-engineering: what to delete, shrink, or replace with stdlib.
- `test-audit` — tests that prove nothing or check the wrong thing.
- `comment-audit` — comments that do not earn their place.
- `thermo-nuclear-code-quality-review` — abstraction quality, giant files, spaghetti growth.
- `improve-codebase-architecture` — shallow modules and deepening opportunities.
- `audit-instructions` — instruction files (`CLAUDE.md`, `SKILL.md`) against Anthropic's current guidance.
- `dead-code` — functions, classes, imports nobody calls.
- `duplication` — one behavior with two homes, token clones and same-data-two-ways.
- `error-handling` — swallowed errors against the repo's fail-loud rule.
- `docstring-coverage` — undocumented public API on a `py.typed` surface.
- `domain-drift` — code vocabulary that drifts from the project's domain terms.
- `type-tightness` — loose `Any`, unexplained `# type: ignore`, fake boundaries.
- `crap-audit` — per-function CRAP score (complexity² × uncovered fraction³ + complexity), real risk hotspots.

`skill-audit` is **not** in the set — it scans the global skills directory, not
this repo. `mutation-audit` is **not** in the set either — it is opt-in and
targeted at one module (never a whole-repo sweep); invoke it by name.

**Every audit skill in the set reports by default.** Applying edits is opt-in —
the user asks by name — and lands as a reviewable PR on its own branch, never a
direct commit to main. Carry this contract into any new audit skill you add here.

## The runnable sweep — `run-audits.sh`

`run-audits.sh` is the bash orchestrator that runs each guarded audit as its own
`claude -p "/name"` process and collects the reports. Flags:

- **`run-audits.sh [REPO]`** — a fresh sweep of all thirteen into a new run dir.
- **`--out DIR`** — write into `DIR` instead of a fresh dir, accumulating (no
  wipe). Re-running with the same `--out` refreshes that dir.
- **`--only NAME[,NAME]`** — run just the named audits, leaving any other audit's
  prior output in the dir in place.
- **`--short`** — the short set: run only the three widest-reaching structural
  audits — `thermo-nuclear-code-quality-review`, `improve-codebase-architecture`,
  and `ponytail-audit`. A named alias for that `--only` list, for a fast pass
  when the full thirteen is more than you want.
- **`--index`** (with `--out DIR`) — run no audits; rebuild `index.html` + the
  synthesis lede over whatever reports already sit in `DIR`. Point several
  `--only` runs at one `--out DIR`, then `--index` it, for a complete index with
  no full re-sweep.
- **`--force` / `--all`** — bypass the staleness cache below and run everything.

**Staleness cache.** The two expensive LLM passes — `domain-drift` and
`type-tightness` — are gated: while the repo is materially unchanged since their
last run, they are skipped and their cached report is reused in the index, marked
"unchanged since `<sha>`". `should_run` (`should_run.py`) owns the skip/run
decision; `cache.py` gathers git state, reads/writes the per-repo record at
`~/.cache/all-audits/<repo-key>.json`, and persists each gated report to a stable
location that survives the run-dir TTL prune. Skip holds only when the tree is
clean, fewer than `N` files (default 10) changed since the last-run SHA, no
change touched `domain-drift`'s ground-truth (`CONTEXT.md`, `docs/adr/`), and the
last run is within the time backstop (default 30 days).

## Run

Two front doors, one engine. `run-audits.sh` runs the whole sweep — it fans each
audit out as its own `claude -p "/name"` process, collects the report folders,
and builds `index.html` with the synthesis lede. Both front doors call it.

The `claude -p "/name"` path is why the script, not a subagent, runs the audits.
Several audit skills set `disable-model-invocation`, so the `Skill` tool refuses
them from any agent — a subagent fan-out silently loses them. A `-p "/name"`
process is an explicit slash invocation, which the gate honors, so every audit
runs the same way.

From a terminal, run `run-audits.sh` directly for the flags above (`--only`,
`--index`, `--force`, `--short`, the staleness cache).

When you are invoked in-session as `/all-audits [path]`:

1. **Resolve the repo.** Use `$ARGUMENTS` if given, else the current directory. If
   the argument is `short` (`/all-audits short [path]`), add `--short` to run only
   the three structural audits.

2. **Run the script in the background.** Run
   `run-audits.sh [--short] <repo>`. It does the fan-out, the collection, the
   `index.html`, and the lede. It reports only — it applies nothing and opens no
   PR. Do not fan out subagents yourself and do not invoke any audit through the
   `Skill` tool; that is the broken path this replaces.

3. **Report the index, then stop.** The script prints `index: <path>` and opens
   that page itself — do not open it again. Print its absolute path, list the
   audits, and tell the user they can grill any one by name. **Do not start
   grilling on your own.**

## Grilling a report

When the user picks an audit to grill, run the `grilling` skill over **that one
report's findings**. Grill the findings toward decisions — which to act on, which
to drop, which need a closer look. Walk one audit at a time; do not merge them
into one grilling — a comment cut and an architecture deepening share no design
tree.

Read the findings from the audit's own record: for `test-audit` and
`comment-audit`, the full list is in `findings.jsonl` (`log_path`) — read that,
not the summary HTML, which holds only grouped counts. For the audits that render
a full HTML report, the report is the record.

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
