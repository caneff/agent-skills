# visual-teach — component catalog

`visual-teach` ships as a **base + standalone components**. Each component is
self-contained: its CSS file, optional JS, and a co-located `demo.html` that is
both the usage doc and the rendering proof. See `demo/showcase.html` for all
components on one page.

**These blocks are a floor, not a ceiling.** `vt-*` covers the commodity parts.
Before reaching for the nearest block, ask what interaction actually practices
this lesson's tangible win — _then_ map it to a component. If the win is to
**produce or manipulate** something (write a regex, write a flex rule, trace a
binary search), a pick-an-option `vt-quiz` only tests recognition, not the skill.
Build the bespoke live exercise (a free-input box, a draggable, a stepper) in
`./assets/` alongside the `vt-*` blocks — that the catalog _could_ show a quiz is
not a reason to settle for one.

## Linking — base + pick your components

Link the Base spine, then add only the CSS and JS for the components this lesson
uses. There is no aggregate bundle: each component is self-contained so it can be
copied on its own.

```html
<link rel="stylesheet" href="../assets/base/base.css" />
<link rel="stylesheet" href="../assets/components/callout/callout.css" />
<!-- add only the component CSS files this lesson needs -->
<script src="../assets/base/base.js"></script>
<!-- add interactive component scripts as needed, e.g.: -->
<script src="../assets/components/quiz/quiz.js"></script>
```

> **Do NOT add `type="module"` to these `<script>` tags.** `base.js` and the
> component scripts are plain UMD/IIFE scripts, not ES modules. Adding
> `type="module"` causes browsers to load them under CORS rules — which blocks
> file:// delivery with a CORS policy error, silently disabling all interactive
> components (quizzes, checklists, theme toggle, copy buttons). The primary
> delivery mode is file://, so this footgun kills the whole page with no visible
> error unless you inspect the console.

> **Heavy deps:** after copy-all seeding, `./assets/` includes `katex/`, `prism/`,
> and `mermaid.js`. If none of your lessons use those components (`math`, `code`,
> `diagram`), you may delete those subdirectories/files — they are unreferenced
> unless explicitly linked.

## Page shell

Copy this `<main>` skeleton when starting a new lesson. It is the structural
frame only — not a complete lesson with fixed slots to fill.

> **Start every lesson file with `<!DOCTYPE html>`.** Without it, file://
> delivery renders in quirks mode — KaTeX's `render()` (the auto-render
> path behind inline `\(...\)` math) refuses outright in quirks mode, so
> inline formulas stay raw LaTeX while `.vt-math` display blocks (rendered
> via `renderToString`) still work. That asymmetry makes the failure easy
> to misdiagnose.

```html
<main>
  <p class="vt-kicker">Topic · Lesson 1</p>
  <h1>Lesson title</h1>
  <p class="vt-lede">One-sentence promise of the lesson.</p>

  <!-- Meta bar: time / prereqs / difficulty / lesson position -->
  <div class="vt-metabar">
    <span class="item">⏱ <strong>~15 min</strong></span>
    <span class="item">Needs: <strong>Lesson 1 complete</strong></span>
    <span class="item"
      ><span class="vt-level intermediate">Intermediate</span></span
    >
    <span class="item">Lesson <strong>3</strong> of 9</span>
  </div>

  <!-- Intro card: whatever sets up the lesson — objectives, why-it-matters,
       a hook. Any prose/list inside; <p class="h"> gives a bold lead line. -->
  <div class="vt-objectives">…</div>

  <!-- h2 sections: JS auto-adds id (slug of text) + hover "#" anchor -->
  <h2><span class="vt-num">1</span>Section heading</h2>
  …prose: plain p / ul / code / a, auto-themed…

  <!-- Recap + up-next teaser -->
  <div class="vt-recap">
    <p class="h">✦ What you earned</p>
    One-sentence summary.
  </div>

  <!-- Optional teacher-box: invite questions AFTER the recap, just before the
       up-next teaser. Closing order is recap → teacher → up-next: earn it,
       offer help on it, then point forward. -->
  <div class="vt-teacher">
    <div>
      <p class="h">I'm your teacher — ask me anything</p>
      <p>Write this fresh each lesson; never reuse the template wording.</p>
    </div>
  </div>

  <!-- Optional forward teaser. Omit on the final lesson — nothing comes next. -->
  <p class="vt-upnext"><em>Up next:</em> next topic.</p>
</main>
```

## Component catalog

Open only the component demos this lesson needs — loading all of them at once
produces stamped, same-chrome-every-lesson output. Most lessons use 2–4
components, not all of them.

| Component   | Reach for when…                                                                                                                    | Demo                                                                 |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| callout     | you need a tip, warning, insight, success, or risk box                                                                             | [components/callout/demo.html](components/callout/demo.html)         |
| code        | showing code snippets, shell output, or input→output pairs                                                                         | [components/code/demo.html](components/code/demo.html)               |
| table       | comparing options, listing key-value pairs, or status grids                                                                        | [components/table/demo.html](components/table/demo.html)             |
| chip        | labeling status, steps, or keyboard shortcuts (.vt-pill / .vt-badge / .vt-kbd) — difficulty `.vt-level` is shell, always available | [components/chip/demo.html](components/chip/demo.html)               |
| quiz        | a knowledge check (single or multi-select, retry-until-correct)                                                                    | [components/quiz/demo.html](components/quiz/demo.html)               |
| reveal      | free-recall prompt with a click-to-reveal answer (active recall, self-graded — vs quiz's recognition)                              | [components/reveal/demo.html](components/reveal/demo.html)           |
| checklist   | a step-by-step procedure with persisted progress                                                                                   | [components/checklist/demo.html](components/checklist/demo.html)     |
| diagram     | visualizing structure, flow, comparisons, or abstract concepts                                                                     | [components/diagram/demo.html](components/diagram/demo.html)         |
| math        | equations, formulas, or symbolic notation (KaTeX)                                                                                  | [components/math/demo.html](components/math/demo.html)               |
| sandbox     | the win is to **produce or manipulate** something live — type a regex, enter a value, see an instant result (free-input tester)    | [components/sandbox/demo.html](components/sandbox/demo.html)         |
| teacher-box | inviting the learner to ask a question (write fresh each time — never reuse template)                                              | [components/teacher-box/demo.html](components/teacher-box/demo.html) |

## Automatic breakout — wide tables, code, and diagrams

Wide tables (`vt-table-wrap`), code blocks (`vt-code`), and diagrams (`vt-diagram`)
that are **direct children of `<main>`** automatically break out of the prose column
when their content is wider than the measure. `base.js` measures each block on load
and re-evaluates on window resize; it adds or removes `.vt-wide` accordingly.

**Do not add `.vt-wide` by hand.** The class is JS-managed — any hand-placed class
will be overwritten on load. A block that genuinely fits in the prose column stays
there; only blocks whose content actually overflows break out.

- **No JS / JS disabled:** nothing widens. Tables and code blocks scroll horizontally
  via `overflow-x: auto`; diagrams shrink to fit (the pre-JS default).
- **Layout shift:** only the wide minority jump on first load; this is accepted.
- **Wide diagrams with SVG:** a wide SVG keeps full size and scrolls within the frame
  (does not shrink to mush). Normal diagrams keep their shrink-to-fit mobile behavior.

## Quiz authoring rules

Keep option text to roughly equal visible length. Use uniform inline `<code>` so
options stay scannable. Don't spell out punctuation: write `git merge` not
"run 'git merge'".

## Footer / sources

Source types for `data-type`: `spec` `doc` `video` `forum` `book`

List the lesson's **primary source first** — the one high-trust resource you'd
have the learner read or watch. The footer carries this; there is no separate
primary-source card.

```html
<footer class="vt-sources">
  <span class="lbl">Sources</span>
  <ul class="vt-reflist">
    <li>
      <span class="vt-src-ic" data-type="spec"></span
      ><a href="#">Official tutorial</a>
      <span class="note">— one-line note.</span>
    </li>
    <li>
      <span class="vt-src-ic" data-type="doc"></span
      ><a href="#">Reference docs</a>
    </li>
    <li>
      <span class="vt-src-ic" data-type="video"></span
      ><a href="#">Quick-start (video)</a>
    </li>
    <li>
      <span class="vt-src-ic" data-type="forum"></span
      ><a href="#">Community forum</a>
    </li>
  </ul>
  <div class="vt-companion">
    <span class="vt-src-ic" data-type="book"></span>Companion reference:
    <a href="#">Glossary &amp; concept map</a>
  </div>
  <div class="meta">Lesson 0001 · verified 2026-06-19</div>
</footer>
```

## Theming — keep the defaults unless you have a real reason:

The base tokens already ship a tuned, dark-mode-correct palette. **Use it as-is by
default** — do not override the accent just to make a course look "custom." The
shared default is what keeps every course in the same visual family; if each
course picks its own accent, the set stops looking like one product. Vary lessons
by the **components** they use (see the catalog), never by recoloring.

Override only with a genuine reason — e.g. the course has an established brand
color, or its subject has a strong conventional color (a "TLS green" security
course). When you do, set it **once** in the shared course stylesheet every
lesson links, so the whole course stays consistent and you never hand-copy a
color — never give each lesson its own accent.

The base color tokens are each defined with `light-dark(light, dark)`, so the
palette is dark-mode-correct out of the box. **A flat hex override replaces both
sides of `light-dark()` at once** — the same dark green that's legible in light
mode renders unreadable on the near-black dark paper. So override with a
`light-dark()` pair, picking the dark value to stay legible on the dark
background exactly as the base palette does:

```css
/* course.css — linked by every lesson, alongside base.css. Only if needed. */
:root {
  /* light value / dark value — verify contrast in BOTH themes */
  --vt-accent: light-dark(#047857, #34d399); /* emerald 700 / 400 */
  --vt-accent-fg: light-dark(#fff, #04231a); /* text on the accent fill */
}
```

A flat (non-`light-dark`) override is only safe for a color that genuinely reads
well on both light and dark backgrounds — rare. When in doubt, supply the pair.

Color tokens you may override (each is `light-dark()` in the base): `--vt-ink
--vt-muted --vt-accent --vt-accent-fg --vt-rule --vt-paper --vt-good --vt-bad
--vt-warn`.

Derived tokens (`--vt-soft --vt-stripe --vt-neutral-soft --vt-accent-dk
--vt-accent-soft`) update automatically from the base tokens and need not be
overridden.
