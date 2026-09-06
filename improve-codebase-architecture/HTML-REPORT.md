# HTML Report Format

The architectural review is rendered as a single self-contained HTML file in the OS temp directory. It is styled with the **visual-teach** design system — the same vendored, semantic `vt-*` components and `--vt-*` theme tokens the teaching lessons use — so the report opens offline, carries a working light/dark mode, and shares one visual identity with the rest of the skills. No web-framework, no remote diagram library, nothing that phones home.

**The diagrams carry the weight.** A deepening reads best as a picture: four shallow modules collapsing into one, an interface as wide as its implementation, a call leaking across a seam. Mermaid handles graph-shaped structure (call graphs, dependencies, sequences); hand-built `vt-diagram` divs and inline SVG handle the more editorial visuals (mass diagrams, cross-sections). Mix the two — don't lean on Mermaid for everything, it starts to look generic. A before/after code block is the exception here, not the rule; reach for it when the change is a few lines of source, not a change of shape.

A committed sample lives at [`sample/architecture-review-sample.html`](sample/architecture-review-sample.html). Open it, toggle the theme, and read it as the reference for everything below.

For the shared asset-delivery mechanism (copy the `vt-*` assets beside the
report, scaffold rules, the `type="module"` warning, theme toggle) see
[`all-audits/harness/HTML-REPORT.md`](../all-audits/harness/HTML-REPORT.md).

> The committed sample is the one exception to copy-at-render-time: it lives
> in the repo, so it links the vendored copies at
> `../../visual-teach/assets/…` instead of copying them. Same relative-link
> model, fixed location.

## Scaffold

Fills the harness's page shell (see `all-audits/harness/HTML-REPORT.md`
"Page shell") with: `{{title}}` = `Architecture review — {{repo name}}`,
`{{kicker}}` = `Improve codebase architecture`, `{{h1}}` = `{{repo}} ·
deepening review`, verdict = the shape of the code in one sentence.
Components: `callout`, `chip`, `code`, `diagram` — plus Prism grammars
(before `base.js`/`code.js`) when a candidate carries a before/after
snippet, and the `mermaid.js` bridge for the graph-shaped diagrams.

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

"X calls Y calls Z, and look at the mess" → a `flowchart`. Fill leaking and shallow nodes solid red with `classDef` so the problem sites read at a glance; a sequence diagram works well for "before: 6 round-trips; after: 1." **Write one statement per line inside `vt-mermaid`** — a line wrapped mid-edge is a syntax error.

```html
<div class="vt-mermaid">
flowchart LR
  A[OrderIntake] --> B[OrderRepo]
  B -.leaks pricing.-> C[PricingClient]
  B --> D[(orders db)]
  classDef leak fill:#c5221f,stroke:#c5221f,color:#ffffff;
  class B,C leak
</div>
```

Mermaid bakes `classDef` colours at parse time and cannot read a `--vt-*` token, so these are hardcoded hex set to the matching token value: red is `--vt-bad` (`#c5221f`) for shallow/leak, green is `--vt-good` (`#0d7d4d`) for the deepened module. They stay those colours in both themes, which reads clearly on either background.

### Call-graph collapse (before/after in two Mermaid panels)

The default for a deepening. Before: a chain of shallow hops, each node filled solid red. After: one deep module, its old hops now internal and faded. Put one `vt-mermaid` in each panel of a `vt-split`.

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
- **Widen the content column.** visual-teach sizes `main`'s content column from `--vt-measure` (the prose reading width); a review carries side-by-side before/after diagrams, so raise it to ~1080px (`main { --vt-measure: 1080px; }`) in the local `<style>` to give the two columns room. Override `--vt-measure`, **not** `max-width` — `base.css` pins the center grid column to `--vt-measure` and only widens the frame via `max-width`, so a `max-width` override alone just adds gutters and leaves the diagrams as narrow as before. The frame follows automatically (`--vt-frame: calc(var(--vt-measure) * 1.35)`).
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
