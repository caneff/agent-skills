---
name: all-audits
description: Run every repo audit at once — thirteen audit skills in parallel, one HTML index linking each report, then grill through them one at a time and land the sweep as one spec per area.
disable-model-invocation: true
argument-hint: "[path] | multi [paths…] | triage <issue>"
---

Run the whole audit set over one repo in a single sweep. Thirteen audit skills fan
out in parallel, each as its own process; each writes a self-contained report;
the reports collect under one folder behind an `index.html` that links them. The
sweep runs to completion on its own: past the index, it grills every report
widest-first and lands the run as one spec per area. Grilling itself still
questions the user on each fresh finding, unless the user takes the batch
mode and is asked only the contested ones, and writes each rejection to the
audited repo's ignore file as it's decided; the single confirmation gate is only
about the tracker — nothing goes to a spec issue or its tickets before that
one approval. It **reports and files only** — no edit is applied, no PR is
opened.

## Scope

`$ARGUMENTS` names the repo path if given, else the current working directory.

Whole-repo by default, and the branch-scope exception — see
[`harness/AUDIT-RUN.md`](harness/AUDIT-RUN.md#scope).

## The set — thirteen skills

Each audits the whole repo. Most write a `findings.jsonl` + grouped-summary
`report.html` pair (see `harness/findings-schema.md`); the three structural
audits — `ponytail-audit`, `thermo-nuclear-code-quality-review`, and
`improve-codebase-architecture` — render a full HTML report as their record
instead, with no separate log file:

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
targeted at one module; invoke it by name, or run
`driver.py --mutation a.py,b.py` for the scripted per-module form. The whole
repo is a separate explicit ask, never part of this sweep:
`driver.py --mutation-all` (`mutation-audit/SKILL.md` § Whole-repo mode).
Mutation mode runs up to `MUTATION_JOBS` modules at once (default 4). No
module's run opens its report; the driver opens the mutation index
(`collection/mutation/index.html`, printed as `index:`) once, when the run
finishes, and nothing when no page exists. A standalone `/mutation-audit <module>` still opens its own.
With no value, `--mutation` takes its candidates from `mutation-audit/audit.py
--suggest` (the model's prepass only ranks that list) and orders them never-run
first, then changed since their recorded sha, then oldest run first, before
`MUTATION_MAX` cuts. Each finished module is recorded under `mutation_modules`
in the per-repo cache file.

## Opt-in edits

**Every audit skill in the set reports by default.** Applying edits is opt-in —
the user asks by name — and lands as a reviewable PR on its own branch, never a
direct commit to main. Carry this contract into any new audit skill you add here.

## The runnable sweep — `driver.py`

`driver.py` is the Python orchestrator that runs each guarded audit as its own
`claude -p "/name"` process and collects the reports. `driver.py --help` is
the flag reference — argparse prints it from the module docstring, and this
doc doesn't restate it, so the two can't drift apart. A run is three steps:
`plan_sweep` asks the staleness cache what still needs running, `execute`
spawns the audits (the only step that does), and `collect` assembles the
collection and renders the index — `--index` calls `collect` alone.
`audits_data.py` holds the audit set — adding an audit is one entry there.

**Staleness cache.** The two expensive LLM passes — `domain-drift` and
`type-tightness` — are gated: while the repo is materially unchanged since their
last run, they are skipped and their cached report is reused in the index, marked
"unchanged since `<sha>`". `should_run()` in `driver.py` owns the skip/run
decision; `driver.decide`/`driver.update_cache` gather git state, read/write the per-repo record at
`~/.cache/all-audits/<repo-key>.json`, and persists each gated report to a stable
location that survives the run-dir TTL prune (`RunDir` owns that folder layout
and the 3-day prune, for both the sweep and mutation mode). Skip holds only when the tree is
clean, fewer than `N` files (default 10) changed since the last-run SHA, no
change touched `domain-drift`'s ground-truth (`GLOSSARY.md`, `docs/adr/`), and the
last run is within the time backstop (default 30 days).

**Ignore file.** A repo can carry `.audit-ignore.md` at its root to suppress
findings it has already reviewed and rejected, so a sweep stops re-raising
them. Opt-in per repo — see [`harness/IGNORE-FILE.md`](harness/IGNORE-FILE.md).

## Run

Two front doors, one engine. `driver.py` runs the whole sweep — it fans each
audit out as its own `claude -p "/name"` process, collects the report folders,
and builds `index.html` with the synthesis lede. Both front doors call it.

The `claude -p "/name"` path is why the script, not a subagent, runs the audits.
Several audit skills set `disable-model-invocation`, so the `Skill` tool refuses
them from any agent — a subagent fan-out silently loses them. A `-p "/name"`
process is an explicit slash invocation, which the gate honors, so every audit
runs the same way.

From a terminal, run `driver.py` directly for its flags and the staleness
cache.

When you are invoked in-session as `/all-audits [path]`:

1. **Resolve the repo.** Use `$ARGUMENTS` if given, else the current directory. If
   the argument is `short` (`/all-audits short [path]`), add `--short` to run only
   the three structural audits.

2. **Run the script in the background.** Run
   `driver.py [--short] <repo>`. It does the fan-out, the collection, the
   `index.html`, and the lede. It reports only — it applies nothing and opens no
   PR. Do not fan out subagents yourself and do not invoke any audit through the
   `Skill` tool; that is the broken path this replaces.

3. **Report the index, then grill.** The script prints `index: <path>` and opens
   that page itself — do not open it again. Print its absolute path and list the
   audits, then continue straight into the grill — no separate ask to start
   it — which walks every report widest-first per
   [`harness/GRILLING.md`](harness/GRILLING.md). It opens with one question,
   `harness/GRILLING.md` § Offer the batch mode.

## Multi-repo — `/all-audits multi [paths…]`

Sweeps several owned repos in one background run. Each repo is swept from a
fresh worktree of its `origin/main`, one after another, and stored under
`~/.local/share/all-audits/<repo>/<sweep-id>/` (`driver.py --multi`). One page,
`~/.local/share/all-audits/multi/<sweep-id>/index.html`, links every repo's
sweep: the pass rewrites it after each repo finishes, so it is also the pass's
progress page, and opens it once at the end. No repo's own index opens during
the pass. The pass prints its path first, as `multi-repo index (rewritten as
each repo finishes): <path>`, and last, as `index: <path>`.

1. **Pick the repos.** With paths, use them and skip the ask. With none, run
   `driver.py --suggest`. It prints one `suggest: <path>` line per owned repo
   with a PR you authored in the last 14 days and a local checkout directly
   under `~/src` or `~/.agents` (`--roots DIR,DIR` changes where it looks), and one `skipped:
   <owner/name> (no local checkout)` line per repo with recent PRs and no
   checkout. A repo with two checkouts is listed once. If the verb exits
   non-zero, show its error and stop: do not fall back to a guessed list.
2. **Ask once.** Show the `suggest:` paths as one pre-ticked list, name the
   `skipped:` repos, and take the user's final list. This is the only
   question of the run.
3. **Launch it under `job-run`, then end the turn.**
   `job-run --name all-audits-multi -- driver.py --multi <path> <path>…`.
   Do not poll or sleep; the job's completion wakes the session.
4. **On wake, report from the page.** Read the pass's `index:` line, the last
   line of the job's progress (`job-run --status all-audits-multi`), and give
   that page's path first: it is already open. Then give each repo's outcome
   from the `== multi-repo summary ==` block above it, which says what the
   page's rows say: `swept` with its audit record link (the
   `audit record: <issue url>` on its line, or "no audit record" when it found
   nothing), `refused` or `failed` with its reason and any record link. A failed repo is reported as failed, never as swept.
   `triage pending (<issue link>)` means the repo's last audit record is still
   open, so nothing was swept; say so and give the link. Only when the user
   asks, re-run that repo with `--force`: it bypasses the staleness cache for
   the repo's audits too (fresh results) and the new record links the open one.
   A pass with no page (one started before the page existed, or a page
   deleted) gets one from `driver.py --multi-index <sweep-id>`, which runs no
   `claude` and prints `index: <path>`.

## Triage — `/all-audits triage <issue>`

Opens a saved audit by its audit record's issue number, walks the user through
deciding on each problem, files what they accept, and closes the record.

1. **Load.** Run `driver.py --load <issue> [repo-name]`. It finds the stored
   sweep whose `audit-record.json` names that issue, rebuilds its collection
   and `index.html` as it was swept (failed and unchanged audits keep their
   notes, and no `claude` runs), and prints `stored: <dir>`, `repo:
   <owner/name>`, `checkout: <local path>` and `index: <path>`. Give the
   repo name only when the verb says two repos share the number. A non-zero
   exit (no stored sweep, or a sweep whose collection is gone) is reported
   verbatim with its path, and the triage stops: do not re-sweep, and do not
   work from the issue body alone.
2. **Grill.** Continue straight into [`harness/GRILLING.md`](harness/GRILLING.md)
   over the stored collection: the batch-mode offer, the per-finding grill,
   rejections written to the audited repo's `.audit-ignore.md`, and one spec per
   area after one confirmation. The audited repo is the record's repo, not the
   current directory: `.audit-ignore.md` goes in the `checkout:` path, and specs
   are filed with `--repo <owner/name>`.
3. **Close the record.** Comment on audit record `<issue>` listing the specs the
   grill filed (links), or saying none were filed, then close it:
   `gh issue comment <issue> --repo <owner/name> --body-file …` and
   `gh issue close <issue> --repo <owner/name>`.
   Closing is what lets `--multi` sweep that repo again, and what frees the
   stored sweep for deletion. If the grill stopped before the confirmation, close
   nothing: the record stays open and `triage pending`.

## After the sweep

The sweep never stops at the index waiting to be told to grill — it continues
on its own. For the grill's walk of every report — order, per-report grilling,
the auto-carry rule, and how the run lands as one spec per area with its
rejections written to `.audit-ignore.md` as they're decided — see
[`harness/GRILLING.md`](harness/GRILLING.md).
