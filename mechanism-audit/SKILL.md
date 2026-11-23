---
name: mechanism-audit
description: "Find stated rules that nothing carries out — a rule in an instruction file or a promising comment with no mechanism, or a mechanism no trigger reaches — each finding listing every place searched."
disable-model-invocation: true
argument-hint: "[path]"
---

Find the rules a repo states and nothing carries out (defect class 2,
`~/.agents/skills/docs/agents/defect-classes.md` § 2). A rule that reads as policy and has no
mechanism is decoration; per-PR review sees one diff, so it misses an old rule
and a rule in one file broken by a change in another. This audit reads the
whole tree. It touches no code and fixes nothing.

**Mechanism** is defined in `~/.agents/skills/GLOSSARY.md` and means exactly that:
the code, hook, test, scheduled job, or reliably triggered skill step that
carries out a stated rule. A skill step counts only when something invokes that
skill on the rule's occasion (a slash command the flow runs, a calling skill, a
hook); a rule whose only carrier is someone remembering has none. Class 1 and
class 3 stay with `error-handling`, `test-audit` and `mutation-audit`.

## Buckets & categories

- **`gap`** (actionable) — the rule has no working mechanism. `category`:
  - `no-mechanism` — nothing in the searched places carries it out.
  - `never-reached` — a mechanism exists but nothing triggers it on the rule's
    occasion (code nothing calls, a hook not wired, a skill no flow invokes).
- **`carried`** (not actionable) — the rule has a working mechanism.
  `category`: `has-mechanism`. Logged so the report shows what was judged.

## Run

1. **Scope.** Audit `$ARGUMENTS` if given; with no argument, scope defaults per
   `~/.agents/skills/all-audits/SKILL.md`'s Scope section. Every repo is in
   scope, including one with no instruction files: it is read on its comments
   alone. Skip vendored, generated and dependency trees and any `.git/` or
   `worktrees/` tree.

2. **Pass one — list the claims.**
   ```sh
   python3 ~/.agents/skills/mechanism-audit/audit.py candidates "$(realpath "${ARGUMENTS:-.}")"
   ```
   One JSON row per line that states a rule: every imperative line in an
   instruction file (`SKILL.md`, `AGENTS.md`, `CLAUDE.md`, a `.md` under
   `flow/claude/`), and the comment or docstring lines in source carrying a
   trigger word ("otherwise", "falls back to", "if absent", "every … must",
   "refuses"). It is a candidate list, not a verdict: many rows are not rules
   (a description of what a thing is) and are dropped in pass two. Never widen
   it to every comment.

3. **Pass two — judge each rule, searching for its mechanism.** For each
   candidate that is a rule, name what would carry it out, then look for it in
   all of these and record each place:
   - the swept repo: `rg` for the function, flag or file the rule names, and
     for a caller of whatever it finds;
   - the repo's tests, scheduled jobs and the skill that invokes the step;
   - the global harness: `~/.claude/settings.json` hooks (and the hook script
     each names), the agent-skills checkout at `~/.agents/skills`, and the
     tools it built into `~/.local/bin`. A rule enforced from the harness is
     not a finding.

   Then the verdict: no mechanism found is `no-mechanism`; one found but with
   no trigger on the rule's occasion is `never-reached` (read the caller, the
   hook wiring and the calling skill, since a function that exists proves
   nothing); one found and reached is `carried`.

4. **Every row carries its searches.** `extra.searched` is a list of
   `{"where": "<the grep pattern, the hooks file, the crontab, the calling
   skill>", "result": "<what it returned>", "ok": true|false}`, one per place
   looked. `ok` is false when the search itself failed (a file unreadable, a
   command erroring, a timeout): a failed search is never an absence, and
   `validate` refuses a `gap` carrying one, so rerun it or leave the rule out.
   A `gap` lists at least two places, the swept repo and then the harness
   (settings hooks, the skills checkout, `~/.local/bin`). `file`/`line` is the
   rule itself, `path:line`. A `gap`'s `failure` names what goes wrong while the
   mechanism is missing.

5. **Validate, then write the log and render the summary.**
   ```sh
   python3 ~/.agents/skills/mechanism-audit/audit.py validate <tmpdir>/findings.jsonl
   ```
   A row with no searched list, an empty one, or a place missing its `where` or
   `result` fails validation: fix the row, never drop the check. A finding with
   no search list is invalid. See
   `~/.agents/skills/all-audits/harness/AUDIT-RUN.md` for the shared
   write-and-deliver step (`findings.jsonl` + `report.html`, opening, and the
   final print). Rejections go to the swept repo's `.audit-ignore.md`
   (`~/.agents/skills/all-audits/harness/IGNORE-FILE.md`), as for every audit.
   This skill's own shape:

   - **Log** — one line per judged rule, per `~/.agents/skills/all-audits/harness/findings-schema.md`.
   - **Summary** — the verdict, the `G gap` metabar (`N no-mechanism · M
     never-reached`), findings grouped by category with counts. `carried` is
     not actionable and has no tile. Close with a `vt-callout` naming the
     standouts by `file:line`.

## Verify against the fixture

`fixtures/answer-key.md` is the spec: `fixtures/sample/` holds three rules and
`fixtures/findings.jsonl` the verdicts. `audit_test.py` checks that pass one
finds all three and that the log validates.
