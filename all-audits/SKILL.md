---
name: all-audits
description: Run every repo audit at once — thirteen audit skills in parallel, one HTML index linking each report, then grill through them one at a time.
disable-model-invocation: true
argument-hint: "[path]"
---

Run the whole audit set over one repo in a single sweep. Thirteen audit skills fan
out in parallel, each as its own process; each writes a self-contained report;
the reports collect under one folder behind an `index.html` that links them. The
sweep runs to completion on its own: past the index, it grills every report
widest-first and lands the run as one spec — the only stop in the whole run is
the single confirmation before anything is written to the tracker. It
**reports and files only** — no edit is applied, no PR is opened.

## Scope

`$ARGUMENTS` names the repo path if given, else the current working directory.

Whole-repo is the default for every audit — the tree, not a git diff or
recent-changes review, and not any audit's own hot-spot default;
`run-audits.sh`'s `audit_prompt` enforces this on each audit process it
launches. This is the one place the rule is stated: an audit that takes an
explicit branch scope instead resolves it via `git merge-base` against the
origin's default branch — never an assumed `main`.

## The set — thirteen skills

Each audits the whole repo and writes a `findings.jsonl` + grouped-summary
`report.html` pair (see `harness/findings-schema.md`):

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
targeted at one module (never a whole-repo sweep); invoke it by name, or run
`run-audits.sh --mutation a.py,b.py` for the scripted per-module form.

## Opt-in edits

**Every audit skill in the set reports by default.** Applying edits is opt-in —
the user asks by name — and lands as a reviewable PR on its own branch, never a
direct commit to main. Carry this contract into any new audit skill you add here.

## The runnable sweep — `run-audits.sh`

`run-audits.sh` is the bash orchestrator that runs each guarded audit as its own
`claude -p "/name"` process and collects the reports. Its own `# Usage:` header
comment is the flag reference (`[REPO]`, `--out`, `--only`, `--short`,
`--index`, `--force`/`--all`, `--mutation`) — this doc doesn't restate it, so
the two can't drift apart.

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

**Ignore file.** A repo can carry `.audit-ignore.md` at its root to suppress
findings it has already reviewed and rejected, so a sweep stops re-raising
them. Opt-in per repo — see [`harness/IGNORE-FILE.md`](harness/IGNORE-FILE.md).

## Run

Two front doors, one engine. `run-audits.sh` runs the whole sweep — it fans each
audit out as its own `claude -p "/name"` process, collects the report folders,
and builds `index.html` with the synthesis lede. Both front doors call it.

The `claude -p "/name"` path is why the script, not a subagent, runs the audits.
Several audit skills set `disable-model-invocation`, so the `Skill` tool refuses
them from any agent — a subagent fan-out silently loses them. A `-p "/name"`
process is an explicit slash invocation, which the gate honors, so every audit
runs the same way.

From a terminal, run `run-audits.sh` directly for its flags and the staleness
cache.

When you are invoked in-session as `/all-audits [path]`:

1. **Resolve the repo.** Use `$ARGUMENTS` if given, else the current directory. If
   the argument is `short` (`/all-audits short [path]`), add `--short` to run only
   the three structural audits.

2. **Run the script in the background.** Run
   `run-audits.sh [--short] <repo>`. It does the fan-out, the collection, the
   `index.html`, and the lede. It reports only — it applies nothing and opens no
   PR. Do not fan out subagents yourself and do not invoke any audit through the
   `Skill` tool; that is the broken path this replaces.

3. **Report the index, then grill.** The script prints `index: <path>` and opens
   that page itself — do not open it again. Print its absolute path and list the
   audits, then continue straight into the grill — no separate ask needed —
   which walks every report widest-first per
   [`harness/GRILLING.md`](harness/GRILLING.md).

## After the sweep

The sweep never stops at the index waiting to be told to grill — it continues
on its own. For the grill's walk of every report — order, per-report grilling,
the auto-carry rule, and how the run lands as one spec with its rejections
written to `.audit-ignore.md` as they're decided — see
[`harness/GRILLING.md`](harness/GRILLING.md).
