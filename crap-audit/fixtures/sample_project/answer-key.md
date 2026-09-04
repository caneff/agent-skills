# Answer key

`radon.json` and `coverage.json` are real captured output — `uvx radon cc -j
sample.py untested.py` and `uvx coverage run --branch -m pytest` +
`uvx coverage json` (coverage.py 7.16.0) run against `sample.py` /
`untested.py` / `test_sample.py` in this directory. Nothing here is
hand-fabricated JSON; only the CRAP arithmetic below is worked by hand, as
an independent check on `normalize`/`score`.

`CRAP = complexity² × (1 − coverage)³ + complexity`, `coverage =
min(statement%, branch%) / 100`. A function absent from `coverage.json`
entirely (its file was never imported by the test run) counts as 0%
covered on both axes.

| Function | File:line | Complexity | Stmt % | Branch % | Coverage source | Effective coverage | CRAP | Bucket |
|---|---|---|---|---|---|---|---|---|
| `inner` (nested in `outer`, radon `closures`) | sample.py:2 | 6 | 14.29 | 10.0 | present, partially executed | 0.10 | 6²×0.9³+6 = 26.244+6 = **32.244** | `critical` (≥30) |
| `uncovered_fn` | sample.py:17 | 4 | 0.0 | 0.0 | present, never executed | 0.0 | 4²×1³+4 = 16+4 = **20.0** | `hotspot` (15–30) |
| `entirely_uncovered` | untested.py:1 | 3 | — | — | **absent** — `untested.py` is never imported by `test_sample.py`, so it has no entry in `coverage.json["files"]` at all | 0.0 (missing-data rule) | 3²×1³+3 = 9+3 = **12.0** | under floor |
| `outer` | sample.py:1 | 1 | 100.0 | 100.0 | present, fully executed | 1.0 | 1²×0³+1 = 0+1 = **1.0** | under floor |
| `branchless_fn` (0 branches) | sample.py:27 | 1 | 100.0 | 100.0 (coverage.py reports 100% branch coverage when `num_branches` is 0 — the branch term is trivially satisfied, so effective coverage reduces to statement coverage) | present, fully executed | 1.0 | 1²×0³+1 = 0+1 = **1.0** | under floor |

Findings floor is CRAP ≥ 15, so only `inner` and `uncovered_fn` produce
findings rows; both are dominated by the coverage-penalty term
(complexity² × (1−coverage)³ ≥ complexity), so both categorize
`low-coverage`.

Full ranking, scan order then sorted by CRAP descending:; `inner` (32.244),
`uncovered_fn` (20.0), `entirely_uncovered` (12.0), `outer` (1.0),
`branchless_fn` (1.0) — `outer` sorts before `branchless_fn` on the tie
because the sort is stable and `outer` appears first in `radon.json`'s scan
order.

Under-floor: count = 3 (`entirely_uncovered`, `outer`, `branchless_fn`), all
three fit in one sample (sample cap is larger than the count here).

Suggested gates: classic = **30** (fixed); above-current-max = **33**
(`floor(32.244) + 1` — the smallest integer strictly greater than the
fixture's current worst score, so both gates are adoptable today with zero
existing failures).
