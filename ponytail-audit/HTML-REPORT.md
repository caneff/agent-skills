# HTML Report Format

For the shared render mechanism — asset delivery, scaffold rules, the
`type="module"` warning, theme toggle — see
[`all-audits/harness/HTML-REPORT.md`](../all-audits/harness/HTML-REPORT.md).
For the report's overall shape — verdict, top cut, ranked cards, Deliberately
leaving alone — see this skill's own `SKILL.md`. Everything below is what
neither of those covers: card anatomy and the tag→badge palette.

There is no committed sample in this skill. Use a sibling skill's sample as the
visual reference — open
`improve-codebase-architecture/sample/architecture-review-sample.html` or
`thermo-nuclear-code-quality-review/sample/code-quality-review-sample.html`,
toggle the theme, and match that look.

## Tag badges

Every card carries exactly one tag `vt-pill`, colored by kind, plus a
line-count `vt-chip` (`−45 lines`) so the reader scans the ranking by size:

- `delete:` — `vt-pill bad` (red). Dead code, unused flexibility, speculative
  feature. Replacement: nothing.
- `stdlib:` / `native:` — `vt-pill accent`. Hand-rolled thing the stdlib or
  platform already ships. Name the function/feature.
- `yagni:` — `vt-pill warn` (amber). One-implementation abstraction, config
  nobody sets, layer with one caller.
- `shrink:` — `vt-pill neutral` (slate). Same logic, fewer lines.

Put the monospaced file list after the badges (e.g. `verdict.py:51`).

## Finding card

Each finding is an `<h2>` heading followed by a badge row and a before/after —
the centerpiece. Prose is sparse and plain. Anatomy:

- **Title** — names the cut as an action ("Delete `canonical_identity`", "Replace
  the hand-rolled decode with `decode_document`"), in the `<h2>`.
- **Badge row** — the tag `vt-pill` + the line-count `vt-chip` + a monospaced
  file list.
- **Problem** — one sentence in a `<p>`. What the code is and why it does not
  earn its place: never called outside tests, config never set off its default,
  a wrapper that only delegates. State the proof (the grep result) plainly.
- **Before / After** — the centerpiece, a `vt-split` with a `.before` panel
  (border and label turn red) and an `.after` panel (green). Put a `vt-code`
  block in each — the code as it stands, and the one-line replacement (or a
  `vt-code vt-static` reading `— gone —` for a straight delete). For a
  shape-cut, a `vt-mermaid` before/after (seam → sole caller) instead.
- **Wins** — a `<ul>`, one short clause each: "−45 lines", "−1 dependency
  (moment.js)", "one fewer indirection", "the invariant now lives in one place".

No paragraphs of explanation. If the before/after needs a paragraph to be
understood, the cut is not as clean as the card claims — re-check it.

For a display-only snippet that should not be copied (`— gone —`, sample
output), add `vt-static` to the `vt-code` and drop the copy button.

Token roles for this card: `--vt-bad` for the before / the deleted, `--vt-good`
for the after / the replacement, `--vt-warn` for `yagni`, `--vt-accent` for
`stdlib`/`native`. Widen the content column for the side-by-side before/after —
set `main { --vt-measure: 1080px; }`, never `max-width`, in a local `<style>`.
