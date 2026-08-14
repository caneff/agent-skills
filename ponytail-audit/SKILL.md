---
name: ponytail-audit
description: >
  Whole-repo audit for over-engineering. Like ponytail-review, but scans the
  entire codebase instead of a diff: a ranked list of what to delete, simplify,
  or replace with stdlib/native equivalents. Use when the user says "audit this
  codebase", "audit for over-engineering", "what can I delete from this repo",
  "find bloat", "ponytail-audit", or "/ponytail-audit". One-shot report, does
  not apply fixes.
---

ponytail-review, repo-wide. Scan the whole tree instead of a diff. Rank
findings biggest cut first.

## Tags

Same as ponytail-review:

- `delete:` dead code, unused flexibility, speculative feature. Replacement: nothing.
- `stdlib:` hand-rolled thing the standard library ships. Name the function.
- `native:` dependency or code doing what the platform already does. Name the feature.
- `yagni:` abstraction with one implementation, config nobody sets, layer with one caller.
- `shrink:` same logic, fewer lines. Show the shorter form.

## Hunt

Deps the stdlib or platform already ships, single-implementation interfaces,
factories with one product, wrappers that only delegate, files exporting one
thing, dead flags and config, hand-rolled stdlib.

Verify before you list — grep the symbol across the tree (excluding tests) and
confirm zero real callers, so a finding survives a skeptic. A dead export whose
only caller is its own test still counts; say so.

## Present the audit as an HTML report

Deliver the audit as a **single self-contained HTML file**, the same way
`/improve-codebase-architecture` and `/thermo-nuclear-code-quality-review` do —
not as a wall of terminal one-liners.

Write the file to the OS temp directory so nothing lands in the repo. Resolve
the temp dir from `$TMPDIR`, falling back to `/tmp` (or `%TEMP%` on Windows),
and write to `<tmpdir>/ponytail-audit-<timestamp>/report.html` so each run gets
a fresh folder. Copy the assets the report uses next to it (see HTML-REPORT.md),
then open it — `xdg-open <path>` on Linux, `open <path>` on macOS, `start
<path>` on Windows — and tell the user the absolute path.

The report is styled with the **visual-teach** design system — vendored `vt-*`
components and `--vt-*` theme tokens, the same system the teaching lessons and
the two sibling review skills use. It loads **no external host**: CSS, JS, Prism
grammars, and Mermaid all come from local files copied beside the report, so it
opens offline and carries a working light/dark mode. Show each cut as a
**before/after** — the code as it stands beside the one-line replacement (or
`— gone —` for a straight delete). Reach for a `vt-mermaid` graph only when the
cut is a shape — a one-implementation seam collapsing into its sole caller, a
wrapper chain flattening — not for every card.

The report leads with a one-line **verdict**, then a **top cut** headline card
for the single biggest reduction, then the ranked finding cards (each with a tag
badge, a line-count chip, the files, the one-sentence problem, the before/after,
and win bullets), and closes with a **Deliberately leaving alone** list so the
reader sees what was considered and consciously kept — the real abstractions and
the deliberate redundancy.

Ranking is unchanged: **biggest cut first.** The header carries the only metric
that matters — `net: -<N> lines, -<M> deps possible` — and each card its own
line count. Nothing to cut: a one-card report whose verdict is `Lean already.
Ship.`

See [HTML-REPORT.md](HTML-REPORT.md) for the full scaffold, asset recipe, card
anatomy, and the tag→badge palette.

## Write the findings in plain language

The HTML is a deliverable a reader judges — write every finding in plain,
present-tense sentences a maintainer understands on the first read. The tags
(`delete:`/`stdlib:`/…) and ponytail's steering metaphors ("bloat", "dead
flexibility") are for you; the card prose says what is actually true and what it
costs. "This class is never constructed outside its own test" beats "speculative
YAGNI cruft". State the replacement concretely — the stdlib function by name,
the one-line form, or "nothing".

## Boundaries

Complexity only. Correctness bugs, security holes, and performance go to a
normal review pass, not this one. A single smoke test or `assert`-based
self-check is the ponytail minimum, not bloat — never flag it for deletion.
Lists findings, applies nothing. One-shot.
"stop ponytail-audit" or "normal mode" to revert.
