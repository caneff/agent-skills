# HTML Report Format

The audit is rendered as a single self-contained HTML file in the OS temp
directory, styled with the **visual-teach** design system — the same vendored
`vt-*` components and `--vt-*` theme tokens the two sibling review skills
(`/improve-codebase-architecture`, `/thermo-nuclear-code-quality-review`) use.
It opens offline, carries a working light/dark mode, and loads no external host.

**The before/after carries the weight.** A cut reads best as a picture of what
leaves: the code as it stands beside its one-line replacement, or `— gone —` for
a straight delete. A before/after code block is the workhorse here (most cuts
are a few lines of source); reach for a Mermaid graph only when the cut is a
*shape* — a one-implementation seam collapsing into its sole caller, a wrapper
chain flattening.

There is no committed sample in this skill. Use a sibling skill's sample as the
visual reference — open
`improve-codebase-architecture/sample/architecture-review-sample.html` or
`thermo-nuclear-code-quality-review/sample/code-quality-review-sample.html`,
toggle the theme, and match that look.

## Asset delivery — copy alongside at render time

The report renders to the OS temp dir, so it cannot relative-reference the
skills folder. **Copy the assets the report uses next to the report at render
time and link them relatively.** Do not inline them, and do not point at a
remote host — the same mechanism the two sibling reviews use.

The visual-teach assets live in the visual-teach skill's `assets/` folder
(`~/.agents/skills/visual-teach/assets/` in this setup — resolve it once and
reuse). Copy only what the report uses — never KaTeX:

- `base/base.css` + `base/base.js` — the spine: page shell, prose, the dark-mode
  token layer, the theme toggle. Always copy both.
- `components/<name>/<name>.css` — one per component used; an audit reaches for
  `callout`, `chip`, `code`, and (only for a shape-cut) `diagram`. Copy
  `components/code/code.js` too — it drives the copy buttons and highlighting.
- `prism/` grammars — for the before/after source: `prism-core.min.js`,
  `prism-clike.min.js`, and one grammar per language shown (e.g.
  `prism-python.min.js`).
- `mermaid.js` + `mermaid.min.js` — only if a card uses a shape diagram. The
  bridge (`mermaid.js`) loads the library from the file beside it, so copy both.

Sketch of the render step:

```sh
vt="$HOME/.agents/skills/visual-teach/assets"                                  # resolve the visual-teach assets once
tmp="${TMPDIR:-/tmp}/ponytail-audit-$(date +%s)"
mkdir -p "$tmp/assets/prism" "$tmp/assets/components"
cp -R "$vt/base" "$tmp/assets/"                                                # the spine (base.css + base.js)
for c in callout chip code diagram; do                                        # only the components used
  cp -R "$vt/components/$c" "$tmp/assets/components/"
done
cp "$vt/prism/prism-core.min.js" "$vt/prism/prism-clike.min.js" "$tmp/assets/prism/"
cp "$vt/prism/prism-python.min.js" "$tmp/assets/prism/"                        # one grammar per language shown
# cp "$vt/mermaid.js" "$vt/mermaid.min.js" "$tmp/assets/"                      # only with a shape diagram
# write the report to "$tmp/report.html" linking href="assets/base/base.css" etc.
```

The tmp dir already resolves `${TMPDIR:-/tmp}` — a skill reusing this pattern names
its own folder (`<tmpdir>/<skill>-<timestamp>/report.html`) and needs no separate
fallback note. Once the report is written, **open it and hand off the path**:
`xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on Windows, then
tell the user the absolute path.

## Scaffold

`<!doctype html>` on line 1 is required. Link `base/base.css` and each
component's CSS in the `<head>`; load Prism grammars **before** `base.js` /
`code.js` so their auto-init can highlight code; add the `mermaid.js` bridge last
(only if used).

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Ponytail audit — {{repo name}}</title>

    <link rel="stylesheet" href="assets/base/base.css" />
    <link rel="stylesheet" href="assets/components/callout/callout.css" />
    <link rel="stylesheet" href="assets/components/chip/chip.css" />
    <link rel="stylesheet" href="assets/components/code/code.css" />
    <link rel="stylesheet" href="assets/components/diagram/diagram.css" />

    <!-- Prism: one grammar per language shown, before base.js / code.js. -->
    <script src="assets/prism/prism-core.min.js"></script>
    <script src="assets/prism/prism-clike.min.js"></script>
    <script src="assets/prism/prism-python.min.js"></script>
    <script src="assets/base/base.js"></script>
    <script src="assets/components/code/code.js"></script>
  </head>
  <body>
    <main>
      <p class="vt-kicker">Ponytail audit</p>
      <h1>{{repo}} · over-engineering audit</h1>
      <p class="vt-lede">{{one-line verdict — the shape of the bloat in a sentence}}</p>
      <!-- metabar, legend, top cut, finding cards, leaving-alone -->
    </main>
  </body>
</html>
```

> **Never add `type="module"` to `base.js`, `code.js`, or the `mermaid.js`
> tag.** They are plain scripts; `type="module"` makes the browser load them
> under CORS rules, which `file://` blocks — the toggle, copy buttons, and Prism
> then silently die.

The theme toggle and dark mode need no code of yours: `base/base.css` holds the
`--vt-*` token layer and `base/base.js` injects a fixed toggle that flips
`data-theme`. The default view follows the OS theme; the toggle forces either.

## Header

Repo name, date, and a one-line **verdict** — the honest shape of the bloat in a
sentence (e.g. "Well-tended; the one real cut is a broke-diagnosis computed on
every verdict that nothing reads — the rest is ADR-backed and earns its keep").
Use `vt-kicker` for the skill label, `<h1>` for the repo, `vt-lede` for the
verdict, and a `vt-metabar` for date / files-scanned / **`net: −N lines, −M
deps`** — the only metric that matters, up front. Then a compact legend of the
tag badges. No throat-clearing paragraph — straight into the top cut.

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

## Top cut

One prominent block at the top for the single biggest reduction — the one that
removes the most lines or the most indirection. Use a `vt-mission` block for the
callout, name the move as a verb in the `<h2>` ("Delete the unread
broke-diagnosis"), state in one sentence what leaves and why nothing needs it,
and let the card below carry the before/after. This is the thing you'd cut
first; make it look like it.

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

## Deliberately leaving alone

Close with a short section — a `vt-callout` holding a plain list — of the things
you looked at and consciously kept: an abstraction with a real second
implementation, a redundancy that exists on purpose (an independent oracle), a
seam an ADR already justifies, the one smoke test per module. This proves the
audit was thorough and stops the reader from "simplifying" something that was
already the right shape. When a candidate contradicts an ADR, only surface it if
the bloat is real enough to warrant reopening the ADR — mark it in a `vt-callout
warn` — don't list every abstraction an ADR forbids.

## Style guidance

- Lean on the `vt-*` components; add a small local `<style>` only for the few
  things they don't cover (the legend row, the card meta row). Never hardcode a
  color — use the `--vt-*` tokens so both themes stay correct.
- **Widen the content column** for the side-by-side before/after: set `main {
  --vt-measure: 1080px; }` in a local `<style>`. Override `--vt-measure`, not
  `max-width`.
- Token roles: `--vt-bad` for the before / the deleted, `--vt-good` for the
  after / the replacement, `--vt-warn` for `yagni` and ADR warnings, `--vt-accent`
  for `stdlib`/`native`.
- Keep the before/after panels compact enough to sit side by side without the
  page scrolling horizontally on a laptop; a tall snippet scrolls inside its own
  panel.
- Monospace every file path, symbol, and module name.
- The only scripts are the vendored visual-teach assets. The report is otherwise
  static and loads no external host.

## Tone

Plain English, concise, present tense. State what the code is, that nothing
uses it, and what replaces it. No hedging, no "it's worth noting that…". The
steering metaphors ("bloat", "dead flexibility", "earns its keep") are for the
skill, not the card — translate each into what is actually true:

- "dead flexibility" → "the `concat` mode is never set; every call uses `sum`".
- "one-implementation YAGNI" → "one class subclasses this; the base exists only
  for a modifier type that does not exist yet".
- "hand-rolled stdlib" → "this loop rebuilds a dict that `dict(zip(...))` builds
  in one line".

If a term isn't carrying weight, cut it. If a bullet could be cut, cut it.
