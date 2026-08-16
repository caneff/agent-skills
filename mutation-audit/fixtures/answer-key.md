# Answer key

`fixtures/sample.py` + `fixtures/test_sample.py` + `fixtures/setup.cfg` is a
real mutmut 3.x run (via `uvx --with pytest mutmut run`), not a hand-built
guess: `is_adult` is tested at and around its boundary (both mutants die),
`clamp` is only tested in-range (both boundary mutants survive).
`fixtures/mutmut-results.txt` is the exact `mutmut results --all true`
output captured from that run.

```
    sample.x_is_adult__mutmut_1: killed
    sample.x_is_adult__mutmut_2: killed
    sample.x_clamp__mutmut_1: survived
    sample.x_clamp__mutmut_2: survived
```

## Pass one — `audit.py fixtures/mutmut-results.txt`

Mechanical: 2 candidate rows, one per survivor, killed mutants dropped
(they aren't findings), `killed_count`/`survived_count` = 2/2 on both:

```json
{"bucket": "rewrite", "file": "sample.py", "line": null, "category": "surviving-mutant", "summary": "mutant survives in clamp() (sample.x_clamp__mutmut_1)", "failure": "the mutation at sample.x_clamp__mutmut_1 survives — no test fails when clamp() is mutated", "extra": {"mutant": "sample.x_clamp__mutmut_1", "killed": false, "survived": true, "killed_count": 2, "survived_count": 2}}
{"bucket": "rewrite", "file": "sample.py", "line": null, "category": "surviving-mutant", "summary": "mutant survives in clamp() (sample.x_clamp__mutmut_2)", "failure": "the mutation at sample.x_clamp__mutmut_2 survives — no test fails when clamp() is mutated", "extra": {"mutant": "sample.x_clamp__mutmut_2", "killed": false, "survived": true, "killed_count": 2, "survived_count": 2}}
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
neither boundary is ever exercised. Both stay `rewrite` (a real test already
covers `clamp`, it just never reaches the edges — not a `cut`, since deleting
`test_clamp_within_range` would lose the only coverage `clamp` has):

| # | Mutant | File:Line | Bucket | before / after |
|---|--------|-----------|--------|-----------------|
| 1 | `sample.x_clamp__mutmut_1` | `sample.py:14` | **rewrite** | before: `test_clamp_within_range` asserts only `clamp(5, 0, 10) == 5`. after: add `assert clamp(0, 0, 10) == 0` — the `<` → `<=` mutation at line 14 survives because no test puts `value` exactly at `low`. |
| 2 | `sample.x_clamp__mutmut_2` | `sample.py:16` | **rewrite** | before: same single in-range case. after: add `assert clamp(10, 0, 10) == 10` — the `>` → `>=` mutation at line 16 survives because no test puts `value` exactly at `high`. |

Tally: 2 killed, 2 survived, 2 rewrite findings, 0 cut.

## Candidate suggester

Given this fixture directory's paths (`sample.py`, `test_sample.py`,
`setup.cfg`, `mutmut-results.txt`, `answer-key.md`), `suggest_candidates`
returns `["sample.py"]` — the only plain module with a sibling test file;
`test_sample.py` is a test file itself and `setup.cfg`/`mutmut-results.txt`/
`answer-key.md` aren't `.py` modules at all.
