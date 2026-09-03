---
name: crap-audit
description: Score every function's CRAP (Change Risk Anti-Patterns — complexity squared times uncovered fraction cubed, plus complexity) from a fresh test run and rank the real risk hotspots. Slash-only.
disable-model-invocation: true
argument-hint: "[path]"
---

Run the repo's own test suite fresh with branch coverage, run radon for
cyclomatic complexity, and join the two into a per-function CRAP score:
`complexity² × (1 − coverage)³ + complexity`, `coverage = min(statement%,
branch%) / 100`. High CRAP means a function is both likely to break on a
change and unlikely to be caught by a test — the two properties multiply,
not add, so a function needs to be *both* complex *and* undertested to rank
high. `audit.py`'s `normalize`/`score` do this math; the work here is
getting them real, fresh inputs and turning the ranking into a report.

**One pass, not two.** Unlike the vulture/mutmut/jscpd-backed audits in this
family, CRAP's arithmetic is fully deterministic — there's no judgment call
between "the tool flagged it" and "it's really a hotspot" the way dead-code
sorts `dead` from `dynamic`. The judgment this skill does is upstream of the
score: discovering the right test command, keeping scope to real source, and
failing loudly rather than scoring on stale or partial data.

## Buckets & categories

- **`critical`** — CRAP ≥ 30 (Uncle Bob's classic gate).
- **`hotspot`** — CRAP ≥ the floor (15) but below 30.

Below the floor, a function isn't reported as a finding at all — see
"Under-floor" below.

`category` names which term dominates the score: **`low-coverage`** when the
coverage penalty (`complexity² × (1 − coverage)³`) is at least as large as
the flat `complexity` term, **`high-complexity`** otherwise. A
`high-complexity` finding is well-tested but still risky because it's hard
to reason about; a `low-coverage` finding is the more urgent kind — the test
suite isn't watching it at all.

## Run

1. **Scope tight.** Audit `$ARGUMENTS` if given, else the current working
   directory. Exclude tests, fixtures, generated code, and vendored/
   dependency trees from both the complexity scan and the coverage run —
   they inflate or deflate scores for code nobody is asking about:
   `**/test_*.py`, `**/*_test.py`, `**/tests/*`, `**/fixtures/*`,
   `node_modules`, `.venv`, `dist`, `vendor`, build output, lockfiles,
   `.git/`, `worktrees/`, and anything the repo itself marks generated
   (`# generated`/`@generated` headers, `*_pb2.py`, migration folders).

2. **Discover the test command by judgment**, in this order: a `Makefile`
   target named `test`/`coverage`, a `test`/`coverage` script in
   `package.json` (for a mixed repo with a Python subproject driven from
   npm), or instructions in `AGENTS.md`/`CONTRIBUTING.md`. Falls back to:
   ```sh
   uv run coverage run --branch -m pytest
   uv run coverage json -o coverage.json
   ```
   If the repo already tracks a `.coveragerc`/`[tool.coverage]` config,
   respect its `omit`/`source` settings instead of overriding them — don't
   fight a repo's own exclusion list, add the audit's own exclusions
   (fixtures/vendored/generated) on top of it if missing.

3. **Run the suite fresh, every time.** Never reuse a stale `coverage.json`
   or `.coverage` file lying around in the repo — coverage numbers from a
   run before the current diff are worse than no numbers, because they look
   authoritative. **Fail loudly and stop** — no partial score, no silent
   fallback to a stale file — if: the test command exits non-zero, coverage
   collection produces no `coverage.json` or an empty `files` map, or radon
   errors out. Report exactly what failed and why; this audit needs real
   inputs to mean anything.

4. **Run radon for complexity:**
   ```sh
   uvx radon cc -j <scope> \
     --exclude "*/node_modules/*,*/.venv/*,*/dist/*,*/vendor/*,*/.git/*,*/build/*,*/worktrees/*,test_*,*_test.py,*/test_*,*/*_test.py,tests/*,*/tests/*,fixtures/*,*/fixtures/*" \
     > /tmp/radon.json
   ```

5. **Score.** Feed both captured JSON files to the tested pure core:
   ```sh
   python3 crap-audit/audit.py /tmp/radon.json coverage.json
   ```
   `audit.py`'s `main()` only prints `findings` (bucket ≥ floor) as JSONL —
   for the full ranking asset and gate values, call `score()` directly (a
   one-line Python script or `-c` invocation) and keep the whole returned
   dict: `findings`, `under_floor` (`count` + a small `sample`), `gates`
   (`classic`, `above_current_max`), `ranking` (every row, sorted).

6. **Write the deliverables and render the report — the default output.**
   This audit touches no code: it's a report, not a fix. Resolve
   `<tmpdir>` from `$TMPDIR`, fall back to `/tmp`. Write to
   `<tmpdir>/crap-audit-<timestamp>/`:

   - **`findings.jsonl`** — one line per finding (CRAP ≥ floor), the
     `score()` result's `findings` list verbatim, each row already carrying
     the required `bucket`/`file`/`line`/`category`/`summary`/`failure`
     fields plus `extra.{complexity,statement_coverage,branch_coverage,
     coverage,crap}`.
   - **`ranking.jsonl`** — the full-ranking asset: every scored function,
     `score()`'s `ranking` list, one line each, sorted by CRAP descending.
     This is the calibration asset — what a repo re-scores against if it
     adopts a different gate later. Not filtered by the floor.
   - **`report.html`** — a grouped visual-teach summary, following
     `~/.agents/skills/all-audits/harness/findings-schema.md` (the shared
     JSONL/summary contract) and
     `~/.agents/skills/all-audits/harness/HTML-REPORT.md` (asset delivery —
     copy `base/`, `components/callout`, `components/chip` next to the
     report and link relatively; `<!doctype html>` on line 1; no
     `type="module"`).

     - **Header** — `vt-kicker` "crap-audit", `<h1>` repo name, `vt-lede`
       one-line verdict, `vt-metabar`: `"N scored · F findings (C critical ·
       H hotspot) · U under floor"`.
     - **Gate values, named explicitly in the lede or a `vt-callout`** —
       both `gates.classic` (30, the fixed Uncle Bob gate) and
       `gates.above_current_max` (the smallest integer strictly above this
       run's worst score, i.e. a gate the repo could adopt today with zero
       existing failures). Naming both is a hard requirement, not a nice
       detail — this is the "adopt a CI gate" decision the report exists to
       inform.
     - **Grouped overview** — findings by bucket then category
       (`critical`/`hotspot` × `low-coverage`/`high-complexity`) with
       counts, plus a per-file roll-up if the repo is large.
     - **Standouts** — a `vt-callout` naming the handful of highest-CRAP
       functions by `file:line`, not every finding.
     - **Under-floor, expandable and sampled, never dumped in full** — show
       `under_floor.count` plainly, and `under_floor.sample` (already
       capped by `score()`) behind a `<details>`/expandable section. A repo
       can have hundreds of clean functions; don't list them.
     - **Full record** — one line pointing at `findings.jsonl` and one at
       `ranking.jsonl`, both beside the report.

   Print the marker on its own line after writing:
   `ALL_AUDITS_REPORT=/abs/path/to/report.html`. Then open the report
   (`xdg-open`/`open`/`start`) and print its absolute path, unless invoked
   from inside an `all-audits` sweep, which says not to.

## Verify against the fixtures

`crap-audit/fixtures/sample_project/` (`radon.json` + `coverage.json`,
real captured tool output) plus `crap-audit/fixtures/answer-key.md` (the
worked-by-hand CRAP arithmetic) is the acceptance fixture: `inner` at
32.244 (`critical`), `uncovered_fn` at 20.0 (`hotspot`), three functions
under the floor (`entirely_uncovered`, `outer`, `branchless_fn`), gates
`classic=30` / `above_current_max=33`. Running this skill's steps 5–6
directly against those two captured files (skipping the test-run/radon-run
steps, since the fixture JSON is already captured) should reproduce that
table exactly — `crap-audit/test_audit.py` already asserts this
programmatically for the scoring core; this skill's own dry run confirms
the report-writing step reproduces the same numbers end to end.
