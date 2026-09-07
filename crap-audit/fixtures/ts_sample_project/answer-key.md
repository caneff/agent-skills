# Answer key — TypeScript path

`crap_typescript.json` is real captured tool output: `npx --yes -p
@barney-media/crap-typescript-core@0.5.1 -p @barney-media/crap-typescript@0.5.1
crap-typescript --format json --test-runner vitest` run against `src/sample.ts`
/ `src/untested.ts` / `src/sample.test.ts` in this directory (Vitest 3.2.4,
`@vitest/coverage-istanbul` 3.2.4, `provider: 'istanbul'`). Nothing here is
hand-fabricated JSON; only the `normalize_ts` → `score()` chain below is
independently re-derived, as a check that ticket 1's unmodified `score()`
reproduces the package's own `crap` field exactly.

Coverage-definition verdict (per this ticket's first acceptance criterion):
**matches, no fallback needed.** Reading the published package's
`coverageNormalization.js` (`combineCoverageMetrics` /
`combinedKnownCoverage`) shows it takes `Math.min(...measuredPercents)` over
statement and branch coverage when both are measured, and its
`crapScore.js` computes `complexity² × (1 − coverage)³ + complexity` —
byte-identical to this skill's formula and to ticket 1's `_effective_coverage`
rule. The one adaptation `normalize_ts` makes: the package's `--format json`
report only exposes the already-combined `cov`/`covKind` per method (which
axis was the lower one), never both raw percentages side by side. Since
`min(a, b)` doesn't care which axis is missing as long as the other is set to
something that can't be the minimum, `normalize_ts` fills the non-dominant
axis with `100.0` — reusing `score()` unchanged still reproduces the
package's own `crap` value exactly (see table below). The ESLint-`complexity`
+ Istanbul-spatial-join fallback documented in
`docs/research/crap-ts-tooling.md` (also referenced from `SKILL.md`) stays a
real fallback for when the package itself can't run (unsupported test
runner, parse failure) — not exercised here since the primary path checks
out.

`cov: null` / `covKind: "N/A"` (a method the tool could not attribute any
coverage to — missing/unparseable/ambiguous report) is `normalize_ts`'s
missing-data rule: 0% both axes, same as ticket 1's Python path for a
function entirely absent from `coverage.json`. `cov: 100` / `covKind: "N/A"`
(structural_na — nothing to instrument, e.g. an ambient signature) is the
other "N/A" case: 100% both axes, same treatment as a branchless Python
function. Neither case appears in this fixture's captured methods (every
method here has real statements to cover); both are covered instead by two
small synthetic rows in `crap-audit/audit_test.py`.

| Function | File:line | Complexity | Captured `cov`/`covKind` | Effective coverage | CRAP | Bucket |
|---|---|---|---|---|---|---|
| `inner` (nested in `outer`) | sample.ts:2 | 6 | 20 / `branch` | 0.20 | 6²×0.8³+6 = 23.04+1.392... → **24.432** | `hotspot` (15–30) |
| `uncoveredFn` | sample.ts:23 | 4 | 0 / `stmt` | 0.0 | 4²×1³+4 = 16+4 = **20.0** | `hotspot` |
| `entirelyUncovered` | untested.ts:1 | 2 | 0 / `stmt` (never called; Vitest's istanbul provider instruments every selected file, so this reports as measured-0%, not a missing report — same effective-coverage outcome as ticket 1's Python "file never imported" case) | 0.0 | 2²×1³+2 = 4+2 = **6.0** | under floor |
| `arrowFn` (arrow function) | sample.ts:36 | 2 | 100 / `stmt` | 1.0 | 2²×0³+2 = 0+2 = **2.0** | under floor |
| `outer` | sample.ts:1 | 1 | 100 / `stmt` | 1.0 | 1²×0³+1 = 0+1 = **1.0** | under floor |
| `branchlessFn` (0 branches) | sample.ts:43 | 1 | 100 / `stmt` | 1.0 | 1²×0³+1 = 0+1 = **1.0** | under floor |

Findings floor is CRAP ≥ 15, so `inner` and `uncoveredFn` produce findings
rows; both are dominated by the coverage-penalty term, so both categorize
`low-coverage`.

Full ranking, sorted by CRAP descending: `inner` (24.432), `uncoveredFn`
(20.0), `entirelyUncovered` (6.0), `arrowFn` (2.0), `outer` (1.0),
`branchlessFn` (1.0) — `outer` sorts before `branchlessFn` on the tie because
the sort is stable and `outer` appears first in the captured report's scan
order.

Under-floor: count = 4 (`entirelyUncovered`, `arrowFn`, `outer`,
`branchlessFn`), all four fit in one sample.

Suggested gates: classic = **30** (fixed); above-current-max = **25**
(`floor(24.432) + 1`).
