---
name: crap-audit
description: Score every function's CRAP (Change Risk Anti-Patterns — complexity squared times uncovered fraction cubed, plus complexity) from a fresh test run and rank the real risk hotspots. Slash-only.
disable-model-invocation: true
argument-hint: "[path]"
---

Run the repo's own test suite fresh with branch coverage, measure
complexity, and join the two into a per-function CRAP score:
`complexity² × (1 − coverage)³ + complexity`, `coverage = min(statement%,
branch%) / 100`. High CRAP means a function is both likely to break on a
change and unlikely to be caught by a test — the two properties multiply,
not add, so a function needs to be *both* complex *and* undertested to rank
high. `audit.py`'s `score` does this math for every language this skill
supports; only the input side (`normalize` for Python, `normalize_ts` for
TypeScript) differs — the work here is getting real, fresh tool output and
turning the ranking into a report.

**Python** repos: radon (`cc -j`) + coverage.py (`coverage json`), joined by
`audit.py`'s `normalize`. **TypeScript** repos (Vitest or Jest): a single
tool, `@barney-media/crap-typescript-core`, via its `npx`-invoked CLI
(`@barney-media/crap-typescript`), read by `audit.py`'s `normalize_ts`. Its
coverage rule was verified to match this skill's exactly — see "TypeScript
path" below — so both languages feed the same unmodified `score()`.

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
   `**/test_*.py`, `**/*_test.py`, `**/*.test.ts`, `**/*.spec.ts`,
   `**/tests/*`, `**/__tests__/*`, `**/fixtures/*`, `node_modules`, `.venv`,
   `dist`, `vendor`, build output, lockfiles, `.git/`, `worktrees/`, and
   anything the repo itself marks generated (`# generated`/`@generated`
   headers, `*_pb2.py`, migration folders). TypeScript: `crap-typescript`
   already excludes test/spec files, `__tests__/`, `dist/`, `coverage/`, and
   `node_modules/` by default — its `--exclude`/`--exclude-path-regex`
   flags are for anything beyond that baseline.

2. **Detect the language, then discover the test command by judgment.**
   TypeScript if the scope has a `package.json` plus a `tsconfig.json` or
   `.ts`/`.tsx` source files and no Python project marker takes priority;
   Python (`pyproject.toml`/`setup.py`/`.py` sources) otherwise. A mixed
   repo audits both, one pass each, same report.

   - **Python:** a `Makefile` target named `test`/`coverage`, a
     `test`/`coverage` script in `package.json` (a Python subproject driven
     from npm), or instructions in `AGENTS.md`/`CONTRIBUTING.md`. Falls back
     to:
     ```sh
     uv run coverage run --branch -m pytest
     uv run coverage json -o coverage.json
     ```
     If the repo already tracks a `.coveragerc`/`[tool.coverage]` config,
     respect its `omit`/`source` settings instead of overriding them — don't
     fight a repo's own exclusion list, add the audit's own exclusions
     (fixtures/vendored/generated) on top of it if missing.
   - **TypeScript:** don't discover a bespoke test command — the
     `crap-typescript` CLI (see step 4) drives the test run itself, via its
     own `--test-runner auto|vitest|jest` detection. Only check that the
     coverage flags it needs are reachable: Vitest needs
     `coverage.provider: 'istanbul'` in `vitest.config.ts` (its *default*
     provider, `v8`, does not emit the Istanbul-shaped
     `fnMap`/`branchMap`/`statementMap` this whole pipeline depends on — a
     repo on the `v8` provider needs that one-line config change, or the
     tool falls back to no coverage and every function scores `cov: null`);
     Jest's default `coverageProvider: "babel"` already produces this shape,
     nothing to add. If neither config is present and the repo can't be
     changed, use the ESLint/Istanbul fallback in "TypeScript path" below
     instead.

3. **Run fresh, every time.** Never reuse a stale `coverage.json` /
   `.coverage` / `coverage-final.json` file lying around in the repo —
   coverage numbers from a run before the current diff are worse than no
   numbers, because they look authoritative (Python: delete `coverage.json`
   first; TypeScript: delete the `coverage/` directory the test runner
   writes to before invoking `crap-typescript`, which otherwise may reuse
   it). **Fail loudly and stop** — no partial score, no silent fallback to a
   stale file — if: the test command exits non-zero for reasons other than
   the CRAP threshold itself, coverage collection produces no coverage data
   at all, the complexity tool errors out, or (Python) radon and
   coverage.json share no file keys at all — `normalize` raises `ValueError`
   for that last case rather than silently scoring every function 0%/0%.
   `normalize` also raises when only *some* radon files fail to join and the
   failure looks like the same file under two path spellings (its basename
   collides with an otherwise-unmatched coverage file) rather than a file
   that's genuinely never imported by the test run.
   Report exactly what failed and why; this audit needs real inputs to mean
   anything.

4. **Run the language's complexity+coverage tool.** Resolve `<tmpdir>` from
   `$TMPDIR`, fall back to `/tmp` — same resolution as step 6, done once and
   reused for every scratch file below.

   Python — radon for complexity, joined to the coverage.json from step 3.
   **`<scope>` here must be cwd-relative, exactly matching what step 3's
   `coverage json` wrote its file keys as** — coverage.py's keys are always
   cwd-relative, and radon's `cc -j` keys mirror whatever path string it was
   invoked with verbatim. Run both from the same directory and pass the same
   relative path to both; an absolute `<scope>` here (e.g. from
   `$ARGUMENTS`) makes every radon key miss every coverage key, and
   `normalize` now raises loudly on that rather than silently scoring
   everything 0%/0%. That guard catches a *total* mismatch only — if some
   keys join and some don't (radon's scope is wider than coverage.py's
   `source`/`omit`, say), the unmatched files score 0%/0% silently and read
   as real findings. Compare the two key sets yourself when radon's scope
   and the coverage config were not derived from the same path:
   ```sh
   uvx radon cc -j <scope> \
     --exclude "*/node_modules/*,*/.venv/*,*/dist/*,*/vendor/*,*/.git/*,*/build/*,*/worktrees/*,test_*,*_test.py,*/test_*,*/*_test.py,tests/*,*/tests/*,fixtures/*,*/fixtures/*" \
     > <tmpdir>/radon.json
   ```

   TypeScript — `@barney-media/crap-typescript`, exact-pinned via `npx`
   (never a bare unpinned `npx crap-typescript`, which floats to whatever
   `latest` resolves to on the day the audit runs):
   ```sh
   npx --yes -p @barney-media/crap-typescript@0.5.1 crap-typescript \
     --format json --test-runner auto <scope> > <tmpdir>/crap_typescript.json
   ```
   Exit code `2` means "CRAP threshold exceeded" (the package's *own* 6.0
   default gate, unrelated to this skill's floor/gates) — not a failure of
   the run; still read `<tmpdir>/crap_typescript.json`, it's valid. Exit code
   `1` is a real failure (bad args, IO, parse error) — fail loudly per step
   3. See "TypeScript path" below for the fallback if the package can't run
   at all.

5. **Score.** Feed the captured JSON to the tested pure core — same
   `score()` either way:
   ```sh
   python3 crap-audit/audit.py <tmpdir>/radon.json coverage.json          # Python
   python3 crap-audit/audit.py --ts <tmpdir>/crap_typescript.json         # TypeScript
   ```
   `audit.py`'s `main()` only prints `findings` (bucket ≥ floor) as JSONL —
   for the full ranking asset and gate values, call `score()` directly (a
   one-line Python script or `-c` invocation) on `normalize(...)` or
   `normalize_ts(...)`'s rows, and keep the whole returned dict: `findings`,
   `under_floor` (`count` + a small `sample`), `gates` (`classic`,
   `above_current_max`), `ranking` (every row, sorted).

6. **Write the deliverables and render the report — the default output.**
   This audit touches no code: it's a report, not a fix. Resolve
   `<tmpdir>` from `$TMPDIR`, fall back to `/tmp`. Write to
   `<tmpdir>/crap-audit-<timestamp>/`:

   - **`findings.jsonl`** — one line per finding (CRAP ≥ floor), the
     `score()` result's `findings` list verbatim, each row already carrying
     the required `bucket`/`file`/`line`/`category`/`summary`/`failure`
     fields plus `extra.{complexity,statement_coverage,branch_coverage,
     coverage,crap}`. On the TypeScript path the tool reports only the
     lower of the two axes, so **the unmeasured one is `null` here** —
     never the synthetic `100.0` `normalize_ts` uses internally to keep
     `min()` honest. Read `extra.coverage` for the effective figure.
   - **`ranking.jsonl`** — the full-ranking asset: every scored function,
     `score()`'s `ranking` list, one line each, sorted by CRAP descending.
     This is the calibration asset — what a repo re-scores against if it
     adopts a different gate later. Not filtered by the floor. Carries the
     same null convention as `findings.jsonl`: on a TypeScript row, the
     unmeasured axis is `null` here too, not the synthetic `100.0`
     `normalize_ts` uses internally to keep `min()` honest — `score()`
     nulls it once, in `ranking`, before deriving `findings` from it. A TS
     row also carries `coverage_axis` (`stmt`, `branch`, or `both`) naming
     which axis was really measured; Python rows have no `coverage_axis`
     and both their axes are always measured.
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

## TypeScript path

`@barney-media/crap-typescript-core`'s coverage rule was verified against
this skill's `coverage = min(statement%, branch%) / 100` by reading the
published package's source (`coverageNormalization.js`): its
`combineCoverageMetrics` takes `Math.min(...measuredPercents)` over
statement and branch, same rule, and its `crapScore.js` computes
`complexity² × (1 − coverage)³ + complexity`, the same formula. **Verdict:
matches — no fallback needed for the arithmetic.** The one real gap is
shape, not math: the CLI's `--format json` report exposes only the
already-combined `cov`/`covKind` per method (which axis was lower), never
both raw percentages — `normalize_ts` (`crap-audit/audit.py`) fills the
non-dominant axis with `100.0` (can't be the minimum), so `score()` —
ticket 1's, unmodified — still reproduces the package's own `crap` value
exactly. See `crap-audit/fixtures/ts_sample_project/answer-key.md` for the
full worked verification, including both `covKind: "N/A"` cases (missing
coverage data vs. structural_na).

**Fallback**, only if the package itself can't run against a repo (parse
failure, unsupported config): ESLint's `complexity` rule at `max: 0` with
`--format json` for per-function complexity (the rule always computes the
real value; `max: 0` forces every function into the report, and the number
is embedded in the message string), plus a hand-rolled spatial join of
Istanbul's `coverage-final.json` (`fnMap` for function ranges,
`statementMap`/`s` and `branchMap`/`b` for per-function statement/branch
coverage — Istanbul does not provide this join itself) — worked in full,
including the exact Vitest/Jest commands and known gaps (arrow-function
`fnMap` attribution, TS source-map coordinate space, `v8`/`istanbul`
provider non-equivalence), in `docs/research/crap-ts-tooling.md`
(`research/crap-ts-tooling` branch, commit `2bb412b`).

## Verify against the fixtures

**Python** — `crap-audit/fixtures/sample_project/` (`radon.json` +
`coverage.json`, real captured tool output) plus
`crap-audit/fixtures/sample_project/answer-key.md` (the worked-by-hand CRAP arithmetic) is
the acceptance fixture: `inner` at 32.244 (`critical`), `uncovered_fn` at
20.0 (`hotspot`), three functions under the floor (`entirely_uncovered`,
`outer`, `branchless_fn`), gates `classic=30` / `above_current_max=33`.

**TypeScript** — `crap-audit/fixtures/ts_sample_project/`
(`crap_typescript.json`, real captured `crap-typescript` `--format json`
output, plus the small Vitest project it was captured from) and
`crap-audit/fixtures/ts_sample_project/answer-key.md`: `inner` (nested,
radon-closures-equivalent) at 24.432 and `uncoveredFn` at 20.0, both
`hotspot`; `arrowFn` (the arrow-function attribution case) at 2.0, under
floor along with `entirelyUncovered`/`outer`/`branchlessFn`; gates
`classic=30` / `above_current_max=25`.

Running this skill's steps 5–6 directly against either fixture's captured
JSON (skipping the test-run/tool-run steps, since it's already captured)
should reproduce its table exactly — `crap-audit/test_audit.py` already
asserts this programmatically for both scoring paths; this skill's own dry
run confirms the report-writing step reproduces the same numbers end to
end.
