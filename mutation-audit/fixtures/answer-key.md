# Answer key

`fixtures/sample.py` + `fixtures/test_sample.py` + `fixtures/setup.cfg` is a
real mutmut 3.x run (via `uvx --with pytest mutmut run`), not a hand-built
guess, covering all three buckets: `is_adult` is tested at and around its
boundary (both mutants die), `clamp` is only tested in-range (both boundary
mutants `survived`), and `scale` has no test at all (both its mutants are
`no tests`). `fixtures/mutmut-results.txt` is the exact `mutmut results
--all true` output captured from that run.

```
    sample.x_is_adult__mutmut_1: killed
    sample.x_is_adult__mutmut_2: killed
    sample.x_clamp__mutmut_1: survived
    sample.x_clamp__mutmut_2: survived
    sample.x_scale__mutmut_1: no tests
    sample.x_scale__mutmut_2: no tests
```

## Pass one — `audit.py fixtures/mutmut-results.txt`

Mechanical: 4 candidate rows, one per mutant that isn't killed. `survived`
becomes `rewrite`, `no tests` becomes `no-coverage` — mutmut's own status is
the coverage signal, so pass one reads the bucket straight off it. Killed
mutants are dropped (they aren't findings). Run tally on every row:
`killed_count`/`survived_count`/`no_coverage_count` = 2/2/2.

```json
{"bucket": "rewrite", "file": "sample.py", "line": null, "category": "surviving-mutant", "summary": "mutant survives in clamp() (sample.x_clamp__mutmut_1)", "failure": "the mutation at sample.x_clamp__mutmut_1 survives — no test fails when clamp() is mutated", "extra": {"mutant": "sample.x_clamp__mutmut_1", "killed": false, "survived": true, "killed_count": 2, "survived_count": 2, "no_coverage_count": 2}}
{"bucket": "rewrite", "file": "sample.py", "line": null, "category": "surviving-mutant", "summary": "mutant survives in clamp() (sample.x_clamp__mutmut_2)", "failure": "the mutation at sample.x_clamp__mutmut_2 survives — no test fails when clamp() is mutated", "extra": {"mutant": "sample.x_clamp__mutmut_2", "killed": false, "survived": true, "killed_count": 2, "survived_count": 2, "no_coverage_count": 2}}
{"bucket": "no-coverage", "file": "sample.py", "line": null, "category": "surviving-mutant", "summary": "mutant survives in scale() (sample.x_scale__mutmut_1)", "failure": "the mutation at sample.x_scale__mutmut_1 survives — no test covers scale(), so nothing can catch it", "extra": {"mutant": "sample.x_scale__mutmut_1", "killed": false, "survived": false, "killed_count": 2, "survived_count": 2, "no_coverage_count": 2}}
{"bucket": "no-coverage", "file": "sample.py", "line": null, "category": "surviving-mutant", "summary": "mutant survives in scale() (sample.x_scale__mutmut_2)", "failure": "the mutation at sample.x_scale__mutmut_2 survives — no test covers scale(), so nothing can catch it", "extra": {"mutant": "sample.x_scale__mutmut_2", "killed": false, "survived": false, "killed_count": 2, "survived_count": 2, "no_coverage_count": 2}}
```

## Pass two — judgment (reads `mutmut show <mutant>` + `fixtures/sample.py`)

`mutmut show sample.x_clamp__mutmut_1` and `..._mutmut_2` give:

```diff
# sample.x_clamp__mutmut_1: survived
-    if value < low:
+    if value <= low:

# sample.x_clamp__mutmut_2: survived
-    if value > high:
+    if value >= high:
```

Reading `fixtures/sample.py` locates the real lines (11: `def clamp(...)`,
14: `if value < low:`, 16: `if value > high:`). `fixtures/test_sample.py`
only calls `clamp(5, 0, 10)` — a value strictly inside the range — so
neither boundary is ever exercised. Both stay `rewrite`, not `no-coverage`:
a real test *does* run `clamp` (so there is a test to strengthen), it just
never reaches the edges. And not a `cut`, since deleting
`test_clamp_within_range` would lose the only coverage `clamp` has:

`mutmut show sample.x_scale__mutmut_1` and `..._mutmut_2` give:

```diff
# sample.x_scale__mutmut_1: no tests
-    return x * 2
+    return x / 2

# sample.x_scale__mutmut_2: no tests
+    return x * 3
```

`scale` sits at `sample.py:27` and `fixtures/test_sample.py` never imports or
calls it, so no test runs the line — mutmut reports both mutants as `no
tests`, and pass one already bucketed them `no-coverage`. Pass two leaves
`before`/`after` empty (there is no covering test to edit) and instead names
the test to write:

| # | Mutant | File:Line | Bucket | fix |
|---|--------|-----------|--------|-----|
| 1 | `sample.x_clamp__mutmut_1` | `sample.py:14` | **rewrite** | before: `test_clamp_within_range` asserts only `clamp(5, 0, 10) == 5`. after: add `assert clamp(0, 0, 10) == 0` — the `<` → `<=` mutation at line 14 survives because no test puts `value` exactly at `low`. |
| 2 | `sample.x_clamp__mutmut_2` | `sample.py:16` | **rewrite** | before: same single in-range case. after: add `assert clamp(10, 0, 10) == 10` — the `>` → `>=` mutation at line 16 survives because no test puts `value` exactly at `high`. |
| 3 | `sample.x_scale__mutmut_1` | `sample.py:27` | **no-coverage** | no before/after — no test calls `scale`. Add `test_scale` that asserts `scale(3) == 6`; the `*` → `/` mutation then fails. |
| 4 | `sample.x_scale__mutmut_2` | `sample.py:27` | **no-coverage** | same missing test — `assert scale(3) == 6` also kills the `* 2` → `* 3` mutation. |

Tally: 2 killed, 2 survived, 2 no-coverage; 2 rewrite findings, 2 no-coverage
findings, 0 cut. Kill rate `2 / (2 + 2 + 2)` = 33%.

## Candidate suggester

Given this fixture directory's paths (`sample.py`, `test_sample.py`,
`setup.cfg`, `mutmut-results.txt`, `answer-key.md`), `suggest_candidates`
returns `["sample.py"]` — the only plain module with a sibling test file;
`test_sample.py` is a test file itself and `setup.cfg`/`mutmut-results.txt`/
`answer-key.md` aren't `.py` modules at all.
