---
name: all-audits
description: Run every repo audit at once — six audit skills in parallel, one HTML index linking each report, then grill through them one at a time. Slash-only.
disable-model-invocation: true
argument-hint: "[path]"
---

Run the whole audit set over one repo in a single sweep. Six audit skills fan out
in parallel, each into its own subagent; each writes a self-contained HTML report;
the reports collect under one folder behind an `index.html` that links them and
flags where they overlap. The sweep **reports only** — it applies nothing and
opens no PR. When it finishes it stops and hands you the index, so you decide what
to grill.

Scope: `$ARGUMENTS` if given, else the current working directory — the repo you
are standing in. The whole repo, not a branch diff.

## The set — six skills

Each audits the whole repo and renders a visual-teach HTML report:

- `ponytail-audit` — over-engineering: what to delete, shrink, or replace with stdlib.
- `test-audit` — tests that prove nothing or check the wrong thing.
- `comment-audit` — comments that do not earn their place.
- `thermo-nuclear-code-quality-review` — abstraction quality, giant files, spaghetti growth.
- `improve-codebase-architecture` — shallow modules and deepening opportunities.
- `audit-instructions` — instruction files (`CLAUDE.md`, `SKILL.md`) against Anthropic's current guidance.

`skill-audit` is **not** in the set — it scans the global skills directory, not
this repo.

## Run

1. **Make the collection folder.** Resolve the temp dir from `$TMPDIR`, fall back
   to `/tmp`. Create `<tmpdir>/all-audits-<timestamp>/` — this holds every
   report and the index.

2. **Fan out six subagents in parallel — one message, all six at once.** Spawn one
   general-purpose subagent per skill. These are judgment-heavy audits, so give
   each a capable model. Each subagent's instructions:

   - Invoke your one skill **by name** with the `Skill` tool (the slash-only flag
     does not block an explicit call), passing the repo path so it audits the
     **entire repo** — override any branch-diff or hot-spot default the skill has.
   - **Do not open the report.** Skip every `xdg-open` / `open` / `start` step the
     skill would run — only the orchestrator opens the final index. Just capture
     the report's absolute path.
   - The default mode is report-only. Do **not** apply changes or open a PR, even
     if the skill offers it.
   - Return this structure and nothing else:
     - `audit` — the skill name.
     - `headline` — the one-line verdict from the report.
     - `count` — how many findings.
     - `report_path` — absolute path to the report's `.html` file.
     - `findings` — a short list, one entry per finding: `{ target, note }`, where
       `target` is the repo-relative file path the finding is about and `note` is
       a one-line summary.

3. **Collect the reports.** Each skill writes a self-contained folder (report plus
   its copied `vt-*` assets). Move each whole folder into
   `<collection>/<audit-name>/` so its relative asset links survive. The report
   file keeps its own name — skills vary (`report.html`,
   `architecture-review-<ts>.html`, `code-quality-review-<ts>.html`), so take the
   filename from the returned `report_path`, never assume `report.html`.

4. **Flag the overlaps.** Compare the `findings` across all six audits. Any
   `target` file that two or more audits raise is an overlap — the same file
   flagged from different angles (e.g. `ponytail-audit` and `thermo` both on a
   bloated module, or `test-audit` and `comment-audit` both on one test file).
   Collect these. This is a plain same-file match, not semantic — a heuristic that
   points, it does not judge.

5. **Build `index.html` at the collection root.** Style it with the visual-teach
   base spine — copy `~/.agents/skills/visual-teach/assets/base/` into
   `<collection>/assets/base/` and link it, the same asset pattern the reports use
   (see `~/.agents/skills/ponytail-audit/HTML-REPORT.md`). The page holds:

   - An **Overlaps** panel at the top (a `vt-callout`): each overlapping target,
     and which audits raised it. Skip the panel if there are none.
   - A **table**, one row per audit: audit name · one-line verdict · finding count ·
     a link to that audit's report — relative, `<audit-name>/` plus the report
     file's own name from `report_path` (not always `report.html`).

6. **Open the index, then stop.** Open `index.html` — `xdg-open` on Linux, `open`
   on macOS, `start` on Windows — and print its absolute path. This is the only
   page that opens. List the six audits and tell the user they can grill any one
   of them by name. **Do not start grilling on your own.**

## Grilling a report

When the user picks an audit to grill, run the `grilling` skill over **that one
report's findings**. Grill the findings toward decisions — which to act on, which
to drop, which need a closer look. Walk one audit at a time; do not merge the six
into one grilling — a comment cut and an architecture deepening share no design
tree.

A grill ends at **decisions**. Do not chain into `/to-spec`, `/to-tickets`, or any
build step — handing a decision off to the build pipeline is a separate call the
user makes when ready.
