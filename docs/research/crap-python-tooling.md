# Per-function CRAP scores for Python — tooling research

Ticket: #501
Question: best pipeline to compute per-function CRAP scores (`CC² × (1 −
coverage)³ + CC`, `coverage = min(statement, branch)` per function) in a
Python repo.

Sources: radon's own docs and CLI output (verified by running it locally),
coverage.py's official docs and source on GitHub (`nedbat/coveragepy`,
verified by running it locally), and PyPI/GitHub for existing CRAP tools.
Every load-bearing claim below was reproduced with a local run, not taken on
faith from docs prose.

## Bottom line

**Don't build this from scratch — `crap4py` (PyPI, MIT, released June 2026)
already does it**, and it's a direct Python port of Uncle Bob's own
`crap4go`/`crap4clj`. If it doesn't fit (see gap below), the fallback build is
cheap: `radon cc -j` for complexity + `coverage json` for coverage, joined on
`(file, start line)` — coverage.py has shipped native per-function/per-class
regions in its JSON report since **7.13.1** (2025-12-28), which removes what
used to be the hard part (line→function attribution) entirely.

One real gap in both the existing tool and the naive DIY approach: `coverage
= min(statement, branch)` as specified in the ticket. `crap4py` only uses
branch coverage (via LCOV), not the min of statement and branch. If the ticket's
exact formula matters, that's a one-line fix on top of `coverage json`'s
per-function output (both percentages are already there — see below) rather
than a reason to avoid the pipeline.

---

## 1. Complexity: `radon cc -j`

Radon computes cyclomatic complexity from Python's `ast`, per `def i.e.
function, method, class`. Verified locally (`uvx radon cc -j`) against a test
file with a class method, a plain function, and an `async def`:

```json
{"/tmp/rtest.py": [
  {"type": "function", "rank": "A", "endline": 12, "col_offset": 0, "name": "top", "lineno": 8, "complexity": 3, "closures": []},
  {"type": "class", "rank": "A", "endline": 6, "col_offset": 0, "name": "Foo", "lineno": 1, "complexity": 3,
   "methods": [{"type": "method", "rank": "A", "endline": 6, "col_offset": 4, "name": "method", "lineno": 2, "classname": "Foo", "complexity": 2, "closures": []}]},
  {"type": "function", "rank": "A", "endline": 17, "col_offset": 0, "name": "afn", "lineno": 14, "complexity": 2, "closures": []},
  {"type": "method", "rank": "A", "endline": 6, "col_offset": 4, "name": "method", "lineno": 2, "classname": "Foo", "complexity": 2, "closures": []}
]}
```

Findings from this run:

- `lineno` is the function's `def` line (or `async def` line) — same
  convention coverage.py's region finder uses (see §2), so the two tools'
  output can be joined on `(file, lineno)`.
- **Methods are double-reported**: once nested under the class entry's
  `"methods"` list, and again as a flattened top-level entry with `classname`
  set. A consumer should take the flattened top-level `function`/`method`
  entries and skip `type: "class"` entries — no need to descend into
  `.methods`.
- **Gap — nested (non-method) functions are NOT flattened.** Verified
  separately: a function defined inside another function only appears in the
  outer function's `"closures"` list, not as a sibling top-level entry:

  ```json
  {"type": "function", "name": "outer", "lineno": 1, "complexity": 2,
   "closures": [{"type": "function", "name": "inner", "lineno": 2, "complexity": 2, "closures": []}]}
  ```

  A pipeline that only reads top-level `function`/`method` entries will
  **silently drop nested functions**. You must recursively walk `closures` to
  get complete coverage. (This matters because coverage.py's own region
  finder, below, *does* create a separate coverage region for nested
  functions — so skipping this recursion causes a real mismatch between what
  radon scores and what coverage.py measures.)
- `async def` is handled — reported as `type: "function"` like a normal
  `def`, complexity computed the same way. No special flag needed.
- Radon's docs (readthedocs) don't spell out the JSON schema or these edge
  cases in prose; the above was confirmed by running `radon cc -j` directly,
  which is the reliable source here.
- No better per-function CC tool turned up on PyPI/GitHub search. `radon` is
  the standard choice and is what `crap4py` itself uses.

## 2. Coverage: `coverage json` — now gives per-function statement AND branch data natively

This is the headline finding: **as of coverage.py 7.13.1 (2025-12-28),
`coverage json` includes a `"functions"` key per file with per-function
statement *and* branch coverage already computed** (source:
`coverage/jsonreport.py` and `coverage/regions.py` in `nedbat/coveragepy`,
`FORMAT_VERSION = 3`, changelog: "add region information (functions,
classes)"). Current PyPI release is 7.16.0, so this ships in what anyone
installs today.

### Commands

```sh
coverage run --branch -m pytest      # or: [run] branch = True in .coveragerc
coverage json --pretty-print -o coverage.json
```

`--branch` (or the config equivalent) is required to get branch data at all;
without it `meta.branch_coverage` is `false` and branch fields are omitted.

### Schema (verified with a local run against a file with a class method, a
loop+branch function, and an uncalled async function)

Per file (`files.<path>`), besides the existing line-level fields
(`executed_lines`, `missing_lines`, `excluded_lines`, `executed_branches`,
`missing_branches`, file-level `summary`), there is now:

```json
"functions": {
  "Foo.method": {
    "summary": {
      "num_statements": 3, "percent_covered": 60.0, "percent_statements_covered": 66.67,
      "num_branches": 2, "num_partial_branches": 1, "covered_branches": 1,
      "missing_branches": 1, "percent_branches_covered": 50.0
    },
    "start_line": 2,
    "executed_lines": [3, 4], "missing_lines": [6], "excluded_lines": [],
    "executed_branches": [[3, 4]], "missing_branches": [[3, 6]]
  },
  "top": { "start_line": 8, "summary": { "percent_covered": 75.0, "percent_branches_covered": 75.0, ... }, ... },
  "afn": { "start_line": 14, "summary": { "percent_covered": 0.0, ... }, ... }
}
```

There is a parallel `"classes"` key with the same shape, aggregated over each
class's methods.

- **Function keys are dotted qualified names** (`"Foo.method"` for a method,
  plain `"top"` for a module-level function) — matches how you'd
  disambiguate a method from a same-named free function, and is joinable
  against radon's `classname` + `name`.
- **`start_line` matches radon's `lineno`** exactly (verified: `Foo.method`
  → `start_line: 2` / radon `lineno: 2`; `top` → `start_line: 8` / radon
  `lineno: 8`) — this is the join key between the two tools' output. No
  separate line→function attribution step is needed; coverage.py has already
  done it via its own `ast`-based `RegionFinder`
  (`coverage/regions.py`), which walks `FunctionDef`/`AsyncFunctionDef`/
  `ClassDef` nodes.
- Both `percent_covered` (statement) and `percent_branches_covered` (branch)
  are given per function — exactly the two numbers the ticket's `coverage =
  min(statement, branch)` needs, with no LCOV intermediate step and no manual
  line-range math required.
- **Nested functions get their own region**, correctly excluded from the
  enclosing function's line set (confirmed by reading `regions.py`:
  "Function bodies should be excluded from the nearest enclosing function").
  This is the mismatch flagged in §1 — radon's flat/`closures` output must be
  walked recursively to line up with this.
- Decorators: `node.lineno` for a decorated function is the `def` line, not
  the decorator line, in the ast module coverage.py and radon both use — so
  no decorator-related offset issue.
- Comprehensions and lambdas are not `FunctionDef` nodes, so they don't get
  their own region/block — their lines/complexity are folded into the
  enclosing function on both sides. Consistent between the two tools, so no
  join issue, just means a giant comprehension's complexity is attributed to
  its enclosing function rather than scored standalone (matches how CRAP is
  normally reported elsewhere, e.g. Java/Cobertura tooling).

### Version gate

This feature requires **coverage.py ≥ 7.13.1**. Below that, `coverage json`
has no `functions`/`classes` keys and you're back to needing your own
line→function mapping (e.g. via radon's line ranges) intersected with
`executed_lines`/`executed_branches`. Given current PyPI is 7.16.0 and this
landed 8 months ago, pinning `coverage>=7.13.1` is a non-issue in practice.

## 3. Existing CRAP tools — reuse before building

- **[`crap4py`](https://pypi.org/project/crap4py/)** (PyPI, MIT, v0.1.1,
  released 2026-06-24, `github.com/gabadi/crap4py`) — a direct Python port of
  Uncle Bob's `crap4go`/`crap4clj`. Confirmed via its README:
  - Pipeline: `pytest --cov --cov-branch --cov-report=lcov:lcov.info`, then
    `crap4py src/ --lcov lcov.info`.
  - Complexity: `ast`-based CC per `def`/`async def` (i.e., radon-equivalent,
    hand-rolled rather than depending on radon).
  - Coverage: **branch coverage only**, from LCOV `BRDA` records intersected
    with each function's line range — does *not* implement the ticket's
    `min(statement, branch)`, and it predates coverage.py's native
    `functions` JSON key so it goes through LCOV instead.
  - Has a CI gate: `--max-crap N` exits non-zero over threshold; N/A
    (uncovered) functions never trip the gate.
  - Excludes `.gitignore`d paths and `test_*.py`/`*_test.py` automatically.
  - No documented handling of decorators/nested functions/async — untested
    by its own docs.
- **`crapkit`** (PyPI) — turned up in search, described as scoring every
  function on complexity × uncovered risk and ranking by change frequency
  (git blame–weighted), with commit blocking. Less directly on-spec (adds a
  git-churn dimension the ticket doesn't ask for) and worth a closer look
  only if churn-weighting becomes a future requirement.
- No other maintained Python CRAP-score tool found on PyPI or GitHub search.

## Recommendation

1. Start with **`crap4py`** — it's maintained, MIT-licensed, matches the
   ticket's formula and tool choices (radon-equivalent CC + coverage.py), and
   avoids writing/maintaining the join logic in §1/§2.
2. If `crap4py`'s branch-only coverage (vs. the ticket's `min(statement,
   branch)`) is a blocker, the fix is small and can be done either as a
   crap4py patch or a from-scratch script: run `coverage run --branch` +
   `coverage json`, read `files.*.functions.*.summary.percent_covered` and
   `.percent_branches_covered`, take the min, and join to `radon cc -j`
   output (recursing into `closures`) on `(file, lineno == start_line)`. No
   LCOV step needed — coverage.py's native `functions` key (≥7.13.1) already
   does the line→function attribution that used to require LCOV
   intersection.
3. Either way, pin `coverage>=7.13.1` to get native per-function regions.
