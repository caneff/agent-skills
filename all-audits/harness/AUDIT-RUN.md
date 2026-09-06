# Audit Run — scope and the write-and-deliver step

Every audit skill in the set (see `all-audits/SKILL.md`) shares this scope
rule and this final step. A skill's own `SKILL.md` keeps only its bucket
names, category vocabulary, and metabar shape — it points here instead of
restating either paragraph below.

## Scope

Whole-repo is the default — the tree, not a git diff or recent-changes
review, and not any audit's own hot-spot default; `run-audits.sh`'s
`audit_prompt` enforces this on each audit process it launches. This is the
one place the rule is stated: an audit that takes an explicit branch scope
instead resolves it via `git merge-base` against the origin's default
branch — never an assumed `main`.

## Write the findings log and render the summary — the default deliverable

Write every finding to `findings.jsonl`, then draw a grouped summary
`report.html` from it, following
[`findings-schema.md`](findings-schema.md) for both — the JSONL schema and
the summary's grouped-overview shape. Resolve `<tmpdir>` from `$TMPDIR`,
falling back to `/tmp`. Write both to `<tmpdir>/<skill>-<timestamp>/`, then
open the summary and hand off its path per
[`HTML-REPORT.md`](HTML-REPORT.md)'s asset-delivery section. Print the
one-line verdict and the summary's absolute path, nothing else.
