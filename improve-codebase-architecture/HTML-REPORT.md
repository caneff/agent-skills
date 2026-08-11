# HTML Report Format

The architectural review is rendered as a single self-contained HTML file in the OS temp directory. It is styled with the **visual-teach** design system — the same vendored, semantic `vt-*` components and `--vt-*` theme tokens the teaching lessons use — so the report opens offline, carries a working light/dark mode, and shares one visual identity with the rest of the skills. No web-framework, no remote diagram library, nothing that phones home.

**The diagrams carry the weight.** A deepening reads best as a picture: four shallow modules collapsing into one, an interface as wide as its implementation, a call leaking across a seam. Mermaid handles graph-shaped structure (call graphs, dependencies, sequences); hand-built `vt-diagram` divs and inline SVG handle the more editorial visuals (mass diagrams, cross-sections). Mix the two — don't lean on Mermaid for everything, it starts to look generic. A before/after code block is the exception here, not the rule; reach for it when the change is a few lines of source, not a change of shape.

A committed sample lives at [`sample/architecture-review-sample.html`](sample/architecture-review-sample.html). Open it, toggle the theme, and read it as the reference for everything below.

## Asset delivery — copy alongside at render time

The report renders to the OS temp dir, so it cannot relative-reference the skills folder. **Copy the assets the report uses next to the report at render time and link them relatively.** Do not inline them, and do not point at a remote host. This is the same mechanism the thermo review uses — one asset-delivery pattern across both reports.

Copy only what the report uses — never KaTeX:

- `visual-teach.css` — the whole design system (styles + dark-mode token layer).
- `visual-teach.js` — copy buttons, the theme toggle, Prism init.
- `mermaid.js` + `mermaid.min.js` — for the diagrams. The bridge (`mermaid.js`) loads the full library (`mermaid.min.js`) from the file sitting next to it, so **copy both together**. A diagram-centric review almost always needs these.
- `prism/` grammars — only if a before/after code block is highlighted. Copy `prism-core.min.js`, `prism-clike.min.js`, and the one grammar per language used (e.g. `prism-python.min.js`).

Sketch of the render step:

```sh
tmp="${TMPDIR:-/tmp}/architecture-review-$(date +%s)"
mkdir -p "$tmp/assets/prism"
cp visual-teach/assets/visual-teach.css "$tmp/assets/"
cp visual-teach/assets/visual-teach.js "$tmp/assets/"
cp visual-teach/assets/mermaid.js visual-teach/assets/mermaid.min.js "$tmp/assets/"   # the diagrams
cp visual-teach/assets/prism/prism-core.min.js "$tmp/assets/prism/"                    # only with a code snippet
# ...one grammar per language used...
# write the report to "$tmp/report.html" linking href="assets/visual-teach.css" etc.
```

The report then references `assets/visual-teach.css`, `assets/mermaid.js`, and so on. Because the bridge resolves `mermaid.min.js` relative to its own location, dropping both in the same folder is all it needs.

> The committed sample is the one exception: it lives in the repo, so it links the vendored copies at `../../visual-teach/assets/…` instead of copying them. Same relative-link model, fixed location.

## Scaffold

`<!doctype html>` on line 1 is required. Link `visual-teach.css` in the `<head>`; load any Prism grammars **before** `visual-teach.js` so its auto-init can highlight code; add the `mermaid.js` bridge last.

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Architecture review — {{repo name}}</title>

    <link rel="stylesheet" href="assets/visual-teach.css" />

    <!-- Prism: one grammar per language used, before visual-teach.js.
         Only needed if a candidate carries a before/after code snippet. -->
    <script src="assets/prism/prism-core.min.js"></script>
    <script src="assets/prism/prism-clike.min.js"></script>
    <script src="assets/prism/prism-python.min.js"></script>
    <script src="assets/visual-teach.js"></script>

    <!-- Mermaid bridge for the graph-shaped diagrams -->
    <script src="assets/mermaid.js"></script>
  </head>
  <body>
    <main>
      <p class="vt-kicker">Improve codebase architecture</p>
      <h1>{{repo}} · deepening review</h1>
      <p class="vt-lede">{{one-line verdict — the shape of the code in a sentence}}</p>
      <!-- top recommendation, candidate cards, leaving-alone -->
    </main>
  </body>
</html>
```

> **Never add `type="module"` to the `visual-teach.js` tag.** It is a plain script. `type="module"` makes the browser load it under CORS rules, which `file://` blocks — the toggle, copy buttons, and Prism then silently die. See the visual-teach cheatsheet.

The theme toggle and dark mode need no code of yours: `visual-teach.css` holds the `--vt-*` token layer (light `:root`, a `prefers-color-scheme` dark block, and a `[data-theme]` override), and `visual-teach.js` injects a fixed toggle that flips `data-theme`. The default view follows the OS theme; the toggle forces either. Mermaid re-themes on the flip through the bridge.

## Header

Repo name, date, and a one-line **verdict** — the honest shape of the code in a sentence (e.g. "The Order intake pipeline is four shallow modules that should be one deep module; pricing leaks across the repo seam; the rest is well-shaped"). Use `vt-kicker` for the skill label, `<h1>` for the repo, `vt-lede` for the verdict, and a `vt-metabar` for date / hot-spot / candidate count. Then a compact legend of the recommendation-strength badges. No throat-clearing paragraph — straight into the top recommendation.

## Recommendation-strength badges

Every candidate carries exactly one, built from `vt-pill`:

- **Strong** — `vt-pill good` (emerald). A high-conviction deepening; do it.
- **Worth exploring** — `vt-pill warn` (amber). A real opportunity, less certain.
- **Speculative** — `vt-pill neutral` (slate). Plausible, lower payoff; listed to be honest.

A second **dependency-category tag** — `vt-pill neutral outline sm` (`in-process`, `local-substitutable`, `ports & adapters`, `mock`) — sits next to the badge so the reader can scan by the kind of seam the deepening introduces. Put the file list after the badges in a monospaced span.

## Top recommendation

One prominent block at the top for the single deepening you'd tackle first — the one that collapses the most shallowness or unblocks the others. Use a `vt-mission` block (accent-bordered "start here") for the callout, name the move as a verb in the `<h2>` ("Collapse the Order intake pipeline"), state in one sentence what it deepens, and let the candidate card below carry the diagram. This is the thing you'd do first; make it look like it.

## Candidate card

Each candidate is an `<h2>` heading followed by a badge row and a before/after **diagram** — the centrepiece. Prose is sparse and plain, and uses the glossary terms (from the `/codebase-design` skill) without ceremony. Anatomy:

- **Title** — short, names the deepening as an action ("Deepen Order intake into one module"), in the `<h2>`.
- **Badge row** — the strength `vt-pill` + the dependency-category `vt-pill neutral outline sm` + a monospaced file list, e.g. `order/repo.py:64`.
- **Problem** — one sentence in a `<p>`. Where the friction is and what it costs, in glossary terms (shallow, leaks, no locality).
- **Before / After** — the centrepiece, a `vt-split` with a `.before` panel (border and label turn red) and an `.after` panel (green). Put the diagram inside each — a `vt-mermaid` graph, a hand-built `vt-diagram`, or (only when the change is a few lines of source) a `vt-code` block. See patterns below. Keep each side to the smallest picture that makes the deepening obvious.
- **Wins** — a `<ul>`, one short clause each, named in glossary terms: "leverage: one interface, N call sites", "locality: bugs concentrate in one module", "interface shrinks; the implementation absorbs the wrappers".
- **ADR callout** (when relevant) — a `vt-callout warn` if the candidate contradicts an existing ADR, e.g. _"Contradicts ADR-0007 — but worth reopening because…"_. Only surface an ADR conflict when the friction is real enough to warrant revisiting it; don't list every refactor an ADR forbids.

No paragraphs of explanation. If the diagram needs a paragraph to be understood, redraw the diagram.

For a display-only snippet that should not be copied (a one-liner, sample output), add `vt-static` to the `vt-code` and drop the copy button.

## Diagram patterns

Pick the pattern that fits the candidate. Mix them — don't make every diagram look the same. A Mermaid graph goes inside a `vt-mermaid` block (the bridge re-themes it with the page); a hand-built diagram goes inside a `vt-diagram` block (pure CSS/SVG, prints, no JS).

### Mermaid graph (the workhorse for dependencies / call flow)

"X calls Y calls Z, and look at the mess" → a `flowchart`. Colour leakage edges and shallow nodes red with `classDef`; a sequence diagram works well for "before: 6 round-trips; after: 1." **Write one statement per line inside `vt-mermaid`** — a line wrapped mid-edge is a syntax error.

```html
<div class="vt-mermaid">
flowchart LR
  A[OrderIntake] --> B[OrderRepo]
  B -.leaks pricing.-> C[PricingClient]
  B --> D[(orders db)]
  classDef leak stroke:#c5221f,stroke-width:2px;
  class B,C leak
</div>
```

Mermaid bakes `classDef` colours at parse time and cannot read a `--vt-*` token, so these are hardcoded hex set to the matching token value: red is `--vt-bad` (`#c5221f`) for shallow/leak, green is `--vt-good` (`#0d7d4d`) for the deepened module. They stay those colours in both themes, which reads clearly on either background.

### Call-graph collapse (before/after in two Mermaid panels)

The default for a deepening. Before: a chain of shallow hops, each node red. After: one deep module, its old hops now internal and faded. Put one `vt-mermaid` in each panel of a `vt-split`.

```html
<div class="vt-mermaid">
flowchart TB
  O[OrderIntake] --> I["validate · normalize · persist (now internal)"]
  classDef deep fill:#0d7d4d,stroke:#0d7d4d,color:#ffffff;
  classDef faded stroke-dasharray:4 4;
  class O deep
  class I faded
</div>
```

### Mass diagram (good for "interface as wide as implementation")

Two bars per module — interface surface over implementation. A shallow module's interface bar is nearly as tall as its implementation; a deep module's is short. Mermaid can't show relative surface area with the right weight, so hand-build it in a `vt-diagram` with a small local `<style>`: fixed-width stacked bars whose heights are the message, filled with `--vt-accent-soft` (interface) over `--vt-neutral-soft` (implementation). The sample's `.mass` block is the reference.

### Cross-section (good for layered shallowness)

Stack horizontal bands to show the layers a call passes through. Before: many thin bands each doing nothing. After: one thick band labelled with the consolidated responsibility. The `vt-row` / `vt-col` lane vocabulary or plain bordered divs carry this.

### Before/after code columns (only when the change is a few lines)

A `vt-split` with a `.before` and an `.after` panel, each holding a `vt-code`. Use this when the deepening reads best as source — a constructor that now takes a port, a method that stops reaching across a seam. It is the exception; most candidates are diagram-shaped.

## Deliberately leaving alone

Close with a short section — a `vt-callout` holding a plain list — of the modules you looked at and consciously kept: a small interface over a real implementation that is already deep, a one-adapter seam whose second adapter is the test suite, a port an ADR already justifies. This proves the review was thorough, and it stops the reader from "deepening" something that was already the right shape.

## Style guidance

- Lean on the `vt-*` components; add a small local `<style>` only for the few things they don't cover (the legend row, the candidate meta row, the mass diagram bars). Never hardcode a colour — use the `--vt-*` tokens so both themes stay correct.
- **Widen the content column.** visual-teach caps `main` at 760px for a prose reading width; a review carries side-by-side before/after diagrams, so override it to ~1080px (`main { max-width: 1080px; }`) in the local `<style>` to give the two columns room.
- The token roles: `--vt-bad` for shallow/leak/before, `--vt-good` for the deepened/after, `--vt-warn` for warnings and ADRs, `--vt-accent` for structure. The `vt-split` and `vt-pill` classes already map to these.
- Keep the before/after panels compact enough to sit side by side without the page scrolling horizontally on a laptop; a tall diagram scrolls inside its own panel.
- Use `text-transform: uppercase; letter-spacing` and a muted token for module labels inside hand-built diagrams — they should read as schematic, not as UI.
- Monospace every file path, symbol, and module name.
- The only scripts are the vendored visual-teach assets. The report is otherwise static and loads no external host.

## Tone

Plain English, concise — but the architectural nouns and verbs come straight from the `/codebase-design` skill. Concision is not an excuse to drift.

**Use exactly:** module, interface, implementation, depth, deep, shallow, seam, adapter, leverage, locality.

**Never substitute:** component, service, unit (for module) · API, signature (for interface) · boundary (for seam) · layer, wrapper (for module, when you mean module).

**Phrasings that fit the style:**

- "Order intake module is shallow — interface nearly matches the implementation."
- "Pricing leaks across the seam."
- "Deepen: one interface, one place to test."
- "Two adapters justify the seam: HTTP in prod, in-memory in tests."

**Wins bullets** name the gain in glossary terms: _"locality: bugs concentrate in one module"_, _"leverage: one interface, N call sites"_, _"interface shrinks; implementation absorbs the wrappers"_. Don't write _"easier to maintain"_ or _"cleaner code"_ — those terms aren't in the glossary and don't earn their place.

Use **CONTEXT.md vocabulary for the domain, and the `/codebase-design` vocabulary for the architecture.** If `CONTEXT.md` defines "Order," talk about "the Order intake module" — not "the FooBarHandler," and not "the Order service."

No hedging, no throat-clearing, no "it's worth noting that…". If a sentence could be a bullet, make it a bullet. If a bullet could be cut, cut it. If a term isn't in the `/codebase-design` glossary, reach for one that is before inventing a new one.
