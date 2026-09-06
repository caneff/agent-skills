# Ignore File — recording a rejected finding

A sweep re-raises the same finding every time it runs unless the decision to
reject it lives somewhere the audits actually read. `.audit-ignore.md`, at
the root of the repo being audited, is that home. Opt-in per repo: a repo
with no such file gets exactly today's sweep, nothing more.

## Location

`.audit-ignore.md` in the root of the audited repo — the repo carries its own
rejections, so they travel with clones and don't live in this skills repo.

## Format

One entry per rejected finding, a `###` heading naming the finding in a line,
then `- key: value` fields:

```
### <finding, one line>
- reason: <why it was rejected>
- date: <YYYY-MM-DD>
- audit: <name of the audit that raised it>
- adr: <path or URL> (optional — only when the rejection is a standing
  architectural decision with its own ADR)
```

Example:

```
### god object in solver.py
- reason: intentional single-file oracle, see ADR
- date: 2026-01-15
- audit: dead-code
- adr: docs/adr/0009-solver-shape.md
```

## Reversing a rejection

The file is hand-edited, not generated. Delete an entry and the finding is
back in scope on the next sweep — that's the whole undo mechanism.

## How it reaches the audit

Every audit in a sweep runs as its own non-interactive `claude -p` process
that never reads this skill's instructions, which is why `run-audits.sh`
already appends a whole-repo scope override to each audit's prompt (see
`audit_prompt()` in `all-audits/run-audits.sh`). When the audited repo has an
ignore file, its raw contents ride along on that same prompt, appended after
the override — not instead of it. No second channel, and no per-audit
filtering: every audit sees the whole file.
