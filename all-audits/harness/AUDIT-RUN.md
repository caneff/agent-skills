# Audit Run — scope and the write-and-deliver step

Every audit skill in the set (see `all-audits/SKILL.md`) shares this scope
rule and this final step. A skill's own `SKILL.md` keeps only its bucket
names, category vocabulary, and metabar shape — it points here instead of
restating either paragraph below.

## Scope

Whole-repo is the default — the tree, not a git diff or recent-changes
review, and not any audit's own hot-spot default; `driver.py`'s
`audit_prompt` enforces this on each audit process it launches. This is the
one place the rule is stated: an audit that takes an explicit branch scope
instead resolves it via `git merge-base` against the origin's default
branch — never an assumed `main`.

## Shared code

A parser-style audit (one with an `audit.py`) imports
[`auditlib.py`](auditlib.py) via a two-line path hook instead of carrying its
own excluded-directory set, source walk, or parse/`--selfcheck` CLI dispatch
— see `dead-code/audit.py` for the pattern. `auditlib.EXCLUDED_DIRS` is the
one definition of the excluded-directory set; regenerate its JSON mirror
(`excluded-dirs.json`, read by the `test-audit/audit.mjs` JS twin) with
`python3 auditlib.py --write-json-mirror excluded-dirs.json` whenever the set
changes. `walk_source`'s optional `skip=` predicate filters out test files,
fixtures, and `__init__.py` on top of the directory pruning; `auditlib.is_test_or_fixture`
is the one definition of that check (mutation-audit's `_sibling_tests` uses it
directly rather than keeping its own copy).

## Write the findings log and render the summary — the default deliverable

Write every finding to `findings.jsonl`, then draw a grouped summary
`report.html` from it, following
[`findings-schema.md`](findings-schema.md) for both — the JSONL schema and
the summary's grouped-overview shape. Resolve `<tmpdir>` from `$TMPDIR`,
falling back to `/tmp`. Write both to `<tmpdir>/<skill>-<timestamp>/`, then
open the summary and hand off its path per
[`HTML-REPORT.md`](HTML-REPORT.md)'s asset-delivery section. Print the
one-line verdict and the summary's absolute path, nothing else.

## The manifest (#559)

When `driver.py` runs an audit as part of a sweep, its prompt names an
absolute manifest path and asks for one more file after the report:
a JSON object at that path —

```json
{"report_path": "/abs/path/to/report.html", "count": 3, "headline": "one-line verdict"}
```

`driver.py` reads this file to find your report; it never scans your
process's stdout for a path. A run outside a sweep (invoked directly as
`/name`, no manifest path in the prompt) writes no manifest — there's
nothing to hand it to. A sweep audit that crashes or times out with no
manifest renders as a named failure row in the index, never a silent
"no report" that could be mistaken for a clean pass.
