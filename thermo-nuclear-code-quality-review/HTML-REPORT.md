# HTML Report Format

The code-quality review is rendered as a self-contained HTML file in the OS temp directory. It is styled with the **visual-teach** design system — the same vendored, semantic `vt-*` components and `--vt-*` theme tokens the teaching lessons use — so the report opens offline, carries a working light/dark mode, and shares one visual identity with the rest of the skills. No web-framework, no remote diagram library, nothing that phones home.

The centrepiece of most findings is a **before/after code block**, not a graph — a restructuring reads best as source you can compare line for line. Reach for a diagram only when the point is graph-shaped: "this format is written in three places," "this parser is duplicated across two scripts," "this failure is coupled to that flow." Mix the two. Don't force every finding into a diagram.

A committed sample lives at [`sample/code-quality-review-sample.html`](sample/code-quality-review-sample.html). Open it, toggle the theme, and read it as the reference for everything below.

## Asset delivery — copy alongside at render time

The report renders to the OS temp dir, so it cannot relative-reference the skills folder. **Copy the assets the report uses next to the report at render time and link them relatively.** Do not inline them, and do not point at a remote host.

Copy only what the report uses — never KaTeX:

- `visual-teach.css` — the whole design system (styles + dark-mode token layer).
- `visual-teach.js` — copy buttons, the theme toggle, Prism init.
- `mermaid.js` + `mermaid.min.js` — only if the report has a diagram. The bridge (`mermaid.js`) loads the full library (`mermaid.min.js`) from the file sitting next to it, so **copy both together**.
- `prism/` grammars — only if code is highlighted. Copy `prism-core.min.js`, `prism-clike.min.js`, and the one grammar per language used (e.g. `prism-python.min.js`).

Sketch of the render step:

```sh
tmp="${TMPDIR:-/tmp}/code-quality-review-$(date +%s)"
mkdir -p "$tmp/assets/prism"
cp visual-teach/assets/visual-teach.css "$tmp/assets/"
cp visual-teach/assets/visual-teach.js "$tmp/assets/"
cp visual-teach/assets/mermaid.js visual-teach/assets/mermaid.min.js "$tmp/assets/"   # only with a diagram
cp visual-teach/assets/prism/prism-core.min.js "$tmp/assets/prism/"                    # only with highlighting
# ...one grammar per language used...
# write the report to "$tmp/report.html" linking href="assets/visual-teach.css" etc.
```

The report then references `assets/visual-teach.css`, `assets/mermaid.js`, and so on. Because the bridge resolves `mermaid.min.js` relative to its own location, dropping both in the same folder is all it needs.

> The committed sample is the one exception: it lives in the repo, so it links the vendored copies at `../../visual-teach/assets/…` instead of copying them. Same relative-link model, fixed location.

## Scaffold

`<!doctype html>` on line 1 is required. Link `visual-teach.css` in the `<head>`; load the Prism grammars **before** `visual-teach.js` so its auto-init can highlight the code; add the `mermaid.js` bridge last.

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Code quality review — {{repo name}}</title>

    <link rel="stylesheet" href="assets/visual-teach.css" />

    <!-- Prism: one grammar per language used, before visual-teach.js -->
    <script src="assets/prism/prism-core.min.js"></script>
    <script src="assets/prism/prism-clike.min.js"></script>
    <script src="assets/prism/prism-python.min.js"></script>
    <script src="assets/visual-teach.js"></script>

    <!-- Mermaid bridge (only if the report has a diagram) -->
    <script src="assets/mermaid.js"></script>
  </head>
  <body>
    <main>
      <p class="vt-kicker">Thermo-nuclear code quality review</p>
      <h1>{{repo}} · branch <code>{{branch}}</code></h1>
      <p class="vt-lede">{{one-line verdict}}</p>
      <!-- headline card, findings, leaving-alone -->
    </main>
  </body>
</html>
```

> **Never add `type="module"` to the `visual-teach.js` tag.** It is a plain script. `type="module"` makes the browser load it under CORS rules, which `file://` blocks — the toggle, copy buttons, and Prism then silently die. See the visual-teach cheatsheet.

The theme toggle and dark mode need no code of yours: `visual-teach.css` holds the `--vt-*` token layer (light `:root`, a `prefers-color-scheme` dark block, and a `[data-theme]` override), and `visual-teach.js` injects a fixed toggle that flips `data-theme`. The default view follows the OS theme; the toggle forces either. Mermaid re-themes on the flip through the bridge.

## Header

Repo name, branch, date, and a one-line **verdict** — the honest state of the code in a sentence (e.g. "Clean branch; one change removes the row layout from three files and resolves four findings, plus a real reliability fix"). Use `vt-kicker` for the skill label, `<h1>` for the repo, `vt-lede` for the verdict, and a `vt-metabar` for date / files-changed / finding count. Then a compact legend of the severity badges. No throat-clearing paragraph — straight into the headline.

## Severity badges

Every finding carries exactly one, built from `vt-pill`:

- **Blocker** — `vt-pill bad` (red). A real defect or a regression that must not ship.
- **Strong** — `vt-pill warn` (amber). A high-conviction structural fix; do it.
- **Worth it** — `vt-pill` (accent). A clear improvement, lower stakes.
- **Nit** — `vt-pill neutral` (grey). Cosmetic; listed only if it rides along cheaply.

A second **category tag** — `vt-pill neutral outline sm` (`duplication`, `spaghetti`, `boundary`, `file-size`, `dead-abstraction`, `reliability`, `simplification`) — sits next to the badge so the reader can scan by kind. Put the file list after the badges in a monospaced span.

## Headline card

One prominent block at the top for the single strongest restructuring — the one move that deletes the most complexity, or resolves several findings at once. Use a `vt-mission` block (accent-bordered "do this first") for the callout, name the move as a verb in the `<h2>` ("Extract one `row_format` module"), state in one sentence what it collapses, and show the key before/after or the fan-in diagram. This is the thing you'd do first; make it look like it.

## Finding card

Each finding is an `<h2>` heading followed by a badge row and the before/after. Prose is sparse and plain. Anatomy:

- **Title** — short, names the fix as an action ("Move the row layout into one module"), in the `<h2>`.
- **Badge row** — the severity `vt-pill` + the category `vt-pill neutral outline sm` + a monospaced file list, e.g. `parquet_source.py:38`.
- **Problem** — one sentence in a `<p>`. What's wrong and what it costs.
- **Before / After** — the centrepiece. A `vt-split` with a `.before` panel (its border and label turn red) and an `.after` panel (green). Put a `vt-code` block inside each with a filename head and a copy button; use `language-…` on the `<code>` for highlighting. Keep each side short — the smallest snippet that makes the move obvious; elide with `…` rather than pasting whole functions.
- **Wins** — a `<ul>`, one short clause each: "one source of the row layout", "a new source gets the layout for free", "the manifest matches what the sources write".
- **Standard callout** (when relevant) — a `vt-callout warn` if the fix touches a documented coding standard or ADR, e.g. _"CODING_STANDARDS.md: shared record shapes live in one module."_

No paragraphs of explanation. If a finding needs a paragraph, tighten it into problem + before/after + wins.

For a display-only snippet that should not be copied (a one-liner, sample output), add `vt-static` to the `vt-code` and drop the copy button.

## Diagram patterns

Use a diagram only when it beats a code block. Write it inside a `vt-mermaid` block; the bridge re-themes it with the page.

### Fan-in (the workhorse for duplication)

"This format / rule / parse is written in N places" → one canonical home. Fill the duplicate nodes solid red so the problem sites read at a glance; leave the canonical home in the default fill.

```html
<div class="vt-mermaid">
  flowchart LR
    A[csv_source.write_row] -.writes layout.-> F[(row_format)]
    B[json_source.write_row] -.writes layout.-> F
    C[parquet_source.write_row] -.writes layout.-> F
    classDef dup fill:#c5221f,stroke:#c5221f,color:#ffffff;
    class A,B,C dup
</div>
```

Mermaid bakes `classDef` colours at parse time and cannot read a `--vt-*` token, so this one red is a hardcoded hex — set it to visual-teach's `--vt-bad` (`#c5221f`). It stays that red in both themes, which reads clearly on either background.

### Coupling / blast-radius (good for reliability findings)

Show one fragile node whose failure currently takes down a reliable one; the "after" splits them. A `flowchart` with the fragile path in red and a dashed line where the seam should go.

### Before/after code columns (the default — no diagram needed)

A `vt-split` with a `.before` and an `.after` panel, each holding a `vt-code`. This carries most findings; the mermaid patterns are the exception, not the rule.

For a static, no-JS diagram that also prints, the visual-teach CSS vocabulary (`vt-diagram`, inline `<svg>` in `currentColor`, `vt-flow`, `vt-row`) is available too — reach for it when a hand-composed picture is clearer than an auto-laid-out graph.

## Deliberately leaving alone

Close with a short section — a `vt-callout` holding a plain list — of the things you looked at and consciously kept: real duplication that isn't worth the cross-import, a hacky-but-correct attribute, a `ponytail:`-commented shortcut whose ceiling is already named. This proves the review was thorough and not just a pile of demands, and it stops the reader from "fixing" something that was a deliberate call.

## Style guidance

- Lean on the `vt-*` components; add a small local `<style>` only for the few things they don't cover (the legend row, the finding meta row). Never hardcode a colour — use the `--vt-*` tokens so both themes stay correct.
- **Widen the content column.** visual-teach caps `main` at 760px for a prose reading width; a review carries side-by-side before/after code, so override it to ~1080px (`main { max-width: 1080px; }`) in the local `<style>` to give the two columns room.
- The token roles: `--vt-bad` for defects/before, `--vt-good` for the fixed/after, `--vt-warn` for warnings and standards, `--vt-accent` for structure. The `vt-split` and `vt-pill` classes already map to these.
- Keep before/after columns short enough to sit side by side without horizontal scroll on a laptop; long lines scroll inside their own `vt-code`.
- Monospace every file path, symbol, and code fragment. Findings are about specific lines — cite them (`file.py:123`).
- The only scripts are the vendored visual-teach assets. The report is otherwise static and loads no external host.

## Tone

Direct, serious, and demanding about quality — the same standard as the terminal review, not softened because it is now in a browser. Name the problem plainly. Do not hedge it into a mild suggestion. Rank without mercy: the headline and the Blockers come first; the Nits ride along at the bottom or not at all.

**Write the prose in Simplified Technical English** (see the SKILL.md "Write the review in plain language" section). Short sentences. One idea per sentence. Active voice, present tense. Use the **target repo's own domain terms** — its `CONTEXT.md` names them if it has one — instead of inventing new ones. Keep real technical terms (module, regex, atomic write). **Do not put this skill's metaphors — "code judo", "spaghetti", "seam leak" — into the card text.** A card that needs the dialect to be understood has failed; rewrite it.

- Good: "This layout is written in three places. Change it and all three must stay the same."
- Good: "One bad row stops the whole import. Skip the bad row and keep the rest."
- Avoid (dialect): "There's a code-judo move that deletes this whole layer of spaghetti."
- Avoid (hedging): "It might be slightly cleaner to consider possibly extracting…"

If a finding is not high-conviction, cut it. A short report of real changes beats a long one padded with cosmetics.
