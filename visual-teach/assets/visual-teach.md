# visual-teach blocks — authoring cheatsheet

These two assets (`visual-teach.css`, `visual-teach.js`) style and animate a
lesson. **Link them in every lesson and use the `vt-*` classes below instead of
inlining your own CSS/JS.** Colors come from 9 themeable tokens — override them in
a workspace stylesheet or the lesson `<head>` to match the topic; never hardcode
hex.

Link in `<head>` / before `</body>` (relative to `lessons/`):

```html
<link rel="stylesheet" href="../assets/visual-teach.css" />
<!-- ... -->
<script src="../assets/visual-teach.js"></script>
```

> **Do NOT add `type="module"` to the `<script>` tag above.** `visual-teach.js` is
> a plain UMD/IIFE script, not an ES module. Adding `type="module"` causes browsers
> to load it under CORS rules — which blocks file:// delivery with a CORS policy
> error, silently disabling all interactive components (quizzes, checklists, theme
> toggle, copy buttons). The primary delivery mode is file://, so this footgun kills
> the whole page with no visible error unless you inspect the console.

## These blocks are a floor, not a ceiling

The `vt-*` blocks cover the commodity parts of a lesson — chrome, callouts,
quizzes, code, tables, basic diagrams — so you don't reinvent them and lessons
share a consistent look. They are **not** a ceiling, and **not a mold every
lesson must fit**. When a topic has an interaction the catalog can't express — a
simulator, a manipulable diagram, a domain-specific widget — build it as a new
component in `./assets/` (per `/teach`'s own rule: "when a lesson needs something
new and reusable, write it as a component") and let it sit alongside the `vt-*`
blocks. That is a welcome **bonus, never a requirement**: reach for bespoke when
it genuinely serves the topic, not for its own sake. The point is to avoid
same-y, templated lessons — the catalog handles the commodity 80% so your effort
goes to whatever makes this particular lesson worth doing.

## Page shell

**Starting a new lesson? Copy this `<main>` block plus the asset link/script
snippet above as your skeleton, then fill it in and add the blocks below —
delete any part you don't need.**

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

  <!-- Objectives block -->
  <div class="vt-objectives">
    <p class="h">By the end of this lesson you'll be able to:</p>
    <ul>
      <li>First learning outcome</li>
      <li>Second learning outcome</li>
    </ul>
  </div>

  <!-- Mission tie-in -->
  <div class="vt-mission">
    <strong>Why this matters for your goal:</strong> …
  </div>

  <!-- Section heading. JS auto-adds id (slug of text) + hover "#" anchor — just write the h2. -->
  <h2><span class="vt-num">1</span>Section heading</h2>
  …prose: plain p / ul / code / a, auto-themed…

  <!-- Primary-source card -->
  <div class="vt-source">
    <div>
      <span class="h">Primary source</span> <a href="…">Source title</a> — one
      sentence on why this source.
    </div>
  </div>

  <!-- Recap + up-next teaser -->
  <div class="vt-recap">
    <p class="h">✦ What you earned</p>
    One sentence on what the learner can now do.
  </div>
  <p class="vt-upnext"><em>Up next:</em> next topic.</p>
</main>
```

## Difficulty pill — `vt-level` (use inside `.vt-metabar` or standalone)

Modifier classes: `beginner` `intermediate` `advanced`

```html
<span class="vt-level intermediate">Intermediate</span>
```

## Callout — `tone` via class: (default warn) `info` `insight` `success` `risk`

```html
<div class="vt-callout insight"><strong>Why it matters:</strong> …</div>
```

## Table — bare `<table>` or `.vt-table`

```html
<!-- Responsive wrapper (always use for .vt-table) -->
<div class="vt-table-wrap">
  <table class="vt-table">
    <!-- header column: th[scope="row"] on each data row -->
    <thead>
      <tr>
        <th>Capability</th>
        <th>Option A</th>
        <th>Option B</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <th scope="row">Scales</th>
        <td class="vt-ok"></td>
        <td class="vt-no"></td>
      </tr>
      <tr class="vt-row-key">
        <th scope="row">Key row</th>
        <td class="vt-partial"></td>
        <td class="vt-ok"></td>
      </tr>
    </tbody>
  </table>
</div>
<!-- Compact density: add class="vt-table compact" -->
<!-- Cell status: td.vt-ok (✓)  td.vt-no (✗)  td.vt-partial (~) -->
<!-- Optional flavor under the icon: <td class="vt-no"><span class="note">rewrite the list</span></td> -->
<!-- Recommended column: <col class="vt-col-pick"> on the column + matching header
     <th class="vt-th-pick"><span class="vt-pick-badge">Recommended</span>Name</th>.
     Both classes required — col frames the sides, th closes the top. -->
```

Key/value reference table (glossary, config keys):

```html
<table class="vt-kv">
  <tr>
    <th scope="row">Term</th>
    <td>Definition</td>
  </tr>
</table>
```

## Pills + level badges + keyboard keys

```html
<!-- Fills: (default accent)  neutral  good  bad  warn -->
<span class="vt-pill good">Done</span>
<!-- Outline: add class="outline" -->
<span class="vt-pill outline warn">Caution</span>
<!-- Size: add class="sm" -->
<!-- Status dot: add class="dot" -->
<span class="vt-pill outline good dot">Required</span>
<!-- Leading icon: add class="ic-check" or "ic-warn" -->
<span class="vt-pill good ic-check">Verified</span>

<!-- Difficulty pills -->
<span class="vt-level beginner">Beginner</span>
<span class="vt-level intermediate">Intermediate</span>
<span class="vt-level advanced">Advanced</span>

<!-- Step / count badge -->
<span class="vt-badge">3</span>

<!-- Keyboard keys -->
<kbd class="vt-kbd">Ctrl</kbd> + <kbd class="vt-kbd">K</kbd>
```

## Checklist (v1 — persists in localStorage; progress bar + count + reset auto-injected)

`data-key` must be unique per lesson.

```html
<ol class="vt-checklist" data-key="topic-0001">
  <li>
    <input type="checkbox" />
    <div>
      <span class="vt-step-title">Step title</span>
      <span class="vt-step-body">What to do.</span>
    </div>
  </li>
</ol>
```

A11y: label association and `aria-valuenow` on the progress bar are auto-injected.

## Quiz (v1)

`data-answer` = 0-based index of the correct option.

**Option text rules** — the goal is that no option visually singles itself out as the answer:

- Keep the visible text of each option roughly the same length.
- Inline code (`<code>` or `vt-pcode`) is fine **as long as it is used uniformly across all options** — the rule guards against only the correct answer having special formatting, not against formatting itself.
- Never spell out punctuation as words: write `re.findall`, not "re dot findall".

Required children (`button.opt`, `.feedback`) are declared in `wireQuiz` in
`visual-teach.js` and enforced at runtime — a console warning names any missing
child and leaves the block inert.

### Single-answer — retry until correct, with per-option misconceptions

```html
<div class="vt-quiz" data-answer="1">
  <p class="q">Question?</p>
  <button class="opt">Option A</button>
  <button class="opt">Option B — correct</button>
  <button class="opt">Option C</button>
  <div class="feedback"></div>
  <template class="why-good">Shown once the learner picks correctly.</template>
  <template class="why-bad"
    >Fallback shown when wrong, no per-option template.</template
  >
  <template data-opt="0">Misconception for option A specifically.</template>
  <template data-opt="2">Misconception for option C specifically.</template>
  <div class="vt-quiz-live" aria-live="polite" aria-atomic="true"></div>
</div>
```

Wrong pick shows feedback but never reveals the answer or locks — learner retries
until correct, and can still click wrong options afterward to read their explanations.
Optional: `template[data-opt="N"]` per-option misconception (falls back to `template.why-bad`),
`template.why-good`, `template.why-bad`, `div[aria-live]` for screen-reader feedback.

### Multi-select — add `data-multi`, set `data-answer` to a comma-separated list

```html
<div class="vt-quiz" data-answer="0,2" data-multi>
  <p class="q">Pick all correct options.</p>
  <button class="opt">Correct A</button>
  <button class="opt">Wrong B</button>
  <button class="opt">Correct C</button>
  <div class="feedback"></div>
  <template class="why-good">A and C are correct because…</template>
  <div class="vt-quiz-live" aria-live="polite" aria-atomic="true"></div>
</div>
```

A "Check answer" button is auto-injected. Clicking options toggles selection (`aria-pressed`).

## Recap + up-next teaser

A forward _teaser_ — plain prose, **not** a link/button (the next lesson isn't
written yet, so a "Next" link would be dead). Just name what's coming.

```html
<div class="vt-recap">
  <p class="h">✦ What you earned</p>
  One-sentence summary of what the learner can now do.
</div>
<p class="vt-upnext"><em>Up next:</em> topic name.</p>
```

## Teacher box (SVG cap icon, question chips) — one job: ask the agent

```html
<div class="vt-teacher">
  <div>
    <p class="h">Stuck or curious? Your teacher is the agent that made this.</p>
    <p>
      Ask anything — follow-up questions are the point, not an interruption. Not
      sure where to start:
    </p>
    <div class="vt-asks">
      <span class="vt-ask">Why did X happen?</span>
      <span class="vt-ask">How does this map to Y?</span>
      <span class="vt-ask">Show me a harder example</span>
    </div>
  </div>
</div>
```

Self-explanation prompt → reuse an insight callout (works mid-lesson too):

```html
<div class="vt-callout insight">
  <strong>Try this:</strong> explain [concept] back to me in your own words —
  I'll tell you what you missed.
</div>
```

Community pointer → a source block (lives with external references):

```html
<div class="vt-source">
  <div>
    <span class="h">Practice with others</span><a href="#">community link</a>
  </div>
</div>
```

## Code block (`.vt-code`) — filename header + copy button + optional Prism highlighting

```html
<div class="vt-code">
  <div class="vt-code-head">
    <span>filename.py</span
    ><button class="vt-code-copy" aria-label="Copy code"></button>
  </div>
  <pre><code class="language-python">def hello():
    return "world"</code></pre>
</div>
```

Add the Prism vendor scripts **before** `visual-teach.js`. The copy button and
Prism init are both wired automatically by `visual-teach.js`. Without Prism (or
JS disabled) the block stays readable — it degrades to styled plain text.

**Bundled grammars** (in `assets/prism/`) — default web set:

| File                      | Languages covered                           |
| ------------------------- | ------------------------------------------- |
| `prism-core.min.js`       | Prism engine (always required first)        |
| `prism-markup.min.js`     | HTML, XML, SVG                              |
| `prism-css.min.js`        | CSS                                         |
| `prism-clike.min.js`      | Shared C-style token rules (required by JS) |
| `prism-javascript.min.js` | JavaScript                                  |
| `prism-python.min.js`     | Python                                      |
| `prism-sql.min.js`        | SQL                                         |
| `prism-bash.min.js`       | Bash / shell                                |

Default web snippet (covers HTML/CSS/JS — the most common web lesson languages):

```html
<script src="../assets/prism/prism-core.min.js"></script>
<script src="../assets/prism/prism-markup.min.js"></script>
<script src="../assets/prism/prism-css.min.js"></script>
<script src="../assets/prism/prism-clike.min.js"></script>
<script src="../assets/prism/prism-javascript.min.js"></script>
<script src="../assets/visual-teach.js"></script>
```

Add extra grammars for non-web lessons (e.g. Python, SQL, Bash) by appending
the relevant `<script>` tags before `visual-teach.js`. If a `language-X` class
is used but no grammar is loaded, `visual-teach.js` logs a `console.warn` at
runtime naming the missing file so you can catch it immediately in DevTools.

To add a new language not yet in `assets/prism/`, download the `.min.js` file
from `https://cdn.jsdelivr.net/npm/prismjs/components/` into `assets/prism/` and
add the `<script>` tag to your lesson HTML.

### Display-only variant (`.vt-static`) — formulas, sample output, ASCII diagrams

Add `.vt-static` to `.vt-code` for preformatted boxes that should never be copied
— formulas, command results, ASCII art, or any labeled display content where a
copy button is meaningless. A `.vt-code.vt-static` block requires only a `<pre>`
(no `.vt-code-copy`), wires nothing, and emits no console warning.

```html
<div class="vt-code vt-static">
  <div class="vt-code-head"><span>Formula</span></div>
  <pre><code>zenith distance = 90° − Ho</code></pre>
</div>
```

Plain `.vt-code` (without `.vt-static`) still requires `.vt-code-copy` and warns
if it is absent — so genuine "forgot the button" mistakes are still caught.

For real mathematical equations, prefer `.vt-math` / `.vt-eq` (KaTeX/LaTeX) over
`.vt-code.vt-static` — they render proper math notation with correct spacing and
symbols. Use `.vt-static` only when plain preformatted text is the right medium
(ASCII art, pseudo-formulas, sample output).

## Input → output pair (`.vt-io`) — code beside its result

Side-by-side on wide viewports, stacked below 600 px. Copy button on the
input only — the output panel is not copyable. Prism highlighting applies to
the input slot; include the relevant `<script>` tags before `visual-teach.js`.
Long lines in either slot scroll horizontally within the block.

Required children (enforced at runtime): `.vt-io-input` and `.vt-io-output`;
inside `.vt-io-input`: `.vt-code-copy` and `pre`.

```html
<div class="vt-io">
  <div class="vt-io-input">
    <div class="vt-io-head">
      <span>pattern.py</span>
      <button class="vt-code-copy" aria-label="Copy code"></button>
    </div>
    <pre><code class="language-python">import re
print(re.findall(r'\d+', 'abc 123 def 456'))</code></pre>
  </div>
  <div class="vt-io-output">
    <div class="vt-io-head"><span>Output</span></div>
    <pre><code>['123', '456']</code></pre>
  </div>
</div>
```

## Math equations (`.vt-math` / `.vt-eq`) — KaTeX display + inline

Vendor KaTeX into `assets/katex/` (already included). Link the CSS and scripts
**before** `visual-teach.js`; `initKatex()` runs automatically on `DOMContentLoaded`.

```html
<link rel="stylesheet" href="../assets/katex/katex.min.css" />
<script src="../assets/katex/katex.min.js"></script>
<script src="../assets/katex/auto-render.min.js"></script>
<script src="../assets/visual-teach.js"></script>
```

**Display block** — wrap LaTeX in `class="vt-math"`. Add `vt-eq` for a
centered, type-sized equation (no inline `style` needed):

```html
<!-- display math, left-aligned -->
<div class="vt-math">\gamma = \frac{1}{\sqrt{1 - v^2/c^2}}</div>

<!-- display math, centered + enlarged (the recommended variant) -->
<div class="vt-math vt-eq">\gamma = \frac{1}{\sqrt{1 - v^2/c^2}}</div>
```

**Inline math** — use `\(...\)` delimiters anywhere in prose; auto-render
processes the whole document body:

```html
<p>The Lorentz factor \(\gamma \geq 1\) means moving clocks always run slow.</p>
```

**Block delimiters** — `\[...\]` renders display-mode inline in prose:

```html
<p>The energy-momentum relation: \[E^2 = (pc)^2 + (m_0 c^2)^2\]</p>
```

Degrades to readable raw LaTeX when KaTeX is absent (JS off, no-network).
Dark/light theming is automatic — KaTeX inherits `currentColor` and the block
uses `var(--vt-ink)`.

## Inline token emphasis (`.vt-pcode`) — spotlight one keyword

```html
<p>The <code class="vt-pcode">return</code> keyword exits a function.</p>
```

No JS required. Renders with accent background + border so it stands out from
plain `<code>` without being syntax-highlighted.

Inline `<code>` nested inside an `<a>` automatically loses its pill background
and side padding so it reads as normal link text without gap artifacts.

## Footer / sources (source-type icons, companion slot, verified-date)

Source types for `data-type`: `spec` `doc` `video` `forum` `book`

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

## Diagram vocabulary (all CSS, no JS, prints, light + dark)

### Panel

```html
<div class="vt-diagram">
  <!-- nodes, flow, rows, splits go here -->
  <p class="vt-diagram-caption">Optional figure caption.</p>
</div>
```

### Inline SVG — hand-drawn diagrams (force, geometry, stick figures)

Place raw `<svg>` directly inside `.vt-diagram`. Draw strokes and fills with
`currentColor` (or a `var(--vt-*)` token) — **never hardcoded hex**. The
`.vt-diagram svg` rule sets `color: var(--vt-ink)`, so `currentColor` resolves
to the correct foreground in both light and dark mode automatically.

```html
<div class="vt-diagram">
  <svg viewBox="0 0 120 60" xmlns="http://www.w3.org/2000/svg">
    <circle
      cx="30"
      cy="30"
      r="20"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
    />
    <line
      x1="50"
      y1="30"
      x2="90"
      y2="30"
      stroke="currentColor"
      stroke-width="2"
    />
    <circle
      cx="100"
      cy="30"
      r="15"
      fill="currentColor"
      opacity="0.15"
      stroke="currentColor"
      stroke-width="2"
    />
  </svg>
  <p class="vt-diagram-caption">
    Fig — force diagram (currentColor scales with theme)
  </p>
</div>
```

### Node / box — labeled card. Add `.em` for accent emphasis, `.muted` for secondary.

Inline `<sup>` and `<sub>` are safe inside a node and render as raised/lowered
exponents on the baseline (e.g. `β<sup>2</sup>`, `H<sub>2</sub>O`).

```html
<span class="vt-node">Step</span>
<span class="vt-node em">Key step</span>
<span class="vt-box muted">Optional</span>
<span class="vt-node">β<sup>2</sup></span>
<span class="vt-node">H<sub>2</sub>O</span>
```

### Flow — auto `→` connectors between direct children

**Sequence only** — injects a `→` before each sibling. For layout demos
(`justify-content` / `align-items`) use `vt-flex` below, not this.

```html
<div class="vt-flow">
  <span class="vt-node">Source</span>
  <span class="vt-node">Transform</span>
  <span class="vt-node em">Output</span>
</div>
```

### Flex playground — `vt-flex` / `vt-flex-item` (layout behavior demos)

Pure `display:flex`, no injected separators — modifier classes set the flex
property directly, so the demo matches what a learner would write.

`justify-content` modifiers: `jc-start` `jc-end` `jc-center` `jc-between` `jc-around` `jc-evenly`
`align-items` modifiers: `ai-start` `ai-end` `ai-center` `ai-stretch`

```html
<div class="vt-flex jc-between">
  <span class="vt-flex-item">A</span>
  <span class="vt-flex-item">B</span>
  <span class="vt-flex-item">C</span>
</div>
```

Stack several labeled blocks to compare values side by side:

```html
<p class="sc-sub">jc-between</p>
<div class="vt-flex jc-between">
  <span class="vt-flex-item">A</span>
  <span class="vt-flex-item">B</span>
  <span class="vt-flex-item">C</span>
</div>
<p class="sc-sub">jc-evenly</p>
<div class="vt-flex jc-evenly">
  <span class="vt-flex-item">A</span>
  <span class="vt-flex-item">B</span>
  <span class="vt-flex-item">C</span>
</div>
```

### Row / col — lane layout

```html
<div class="vt-row">
  <div class="vt-col">
    <span class="vt-col-label">Input</span>
    <span class="vt-node">CSV</span>
    <span class="vt-node">API</span>
  </div>
  <div class="vt-col">
    <span class="vt-col-label">Process</span>
    <span class="vt-node em">Transform</span>
  </div>
</div>
```

`vt-row` wraps by default. Add `.nowrap` to keep the columns on one line (and
scroll horizontally if they overflow) — for a row that must read as a single
unit, e.g. the five positional fields of a cron expression `* * * * *`:

```html
<div class="vt-row nowrap">…</div>
```

### Split — before / after. Add `.before` / `.after` on panels for colour cues.

```html
<div class="vt-split">
  <div class="vt-split-panel before">
    <div class="vt-split-label">Before</div>
    …
  </div>
  <div class="vt-split-panel after">
    <div class="vt-split-label">After</div>
    …
  </div>
</div>
```

`vt-code` is safe inside `vt-split` panels — long lines scroll horizontally within the block.

## Computed graphs — opt-in mermaid (sequence / state / ER only)

**Default to the CSS diagram vocabulary above** — prints, offline, zero JS. Use
mermaid **only** when the graph needs auto-layout: sequence, state, ER.

```html
<!-- 1. Add the bridge script (after visual-teach.js, or just before </body>) -->
<script src="../assets/mermaid.js"></script>

<!-- 2. Write your diagram inside .vt-mermaid — mermaid CDN loads only if this
     element is found on the page. -->
<div class="vt-mermaid">
  sequenceDiagram Client->>Server: Request Server-->>Client: Response
</div>
```

The bridge reads the 9 `--vt-*` tokens at render time and maps them to
mermaid's `themeVariables`, so diagrams match the lesson palette and switch
automatically with dark mode.

## Theming — override any of the 9 tokens in the lesson `<head>`:

```html
<style>
  :root {
    --vt-accent: #4338ca;
    --vt-accent-fg: #fff;
  }
</style>
```

A flat `:root` override is safe for **all 9 tokens** in both light and dark mode.
vt's forced-dark rule uses `:root[data-theme="dark"]` (specificity 0,2,0), which beats
a flat `:root` (0,1,0) — so vt's dark accent wins automatically and dark-mode contrast
stays correct without any per-theme blocks in your stylesheet.

Theme-varying tokens (vt re-sets these in dark mode): `--vt-ink --vt-muted --vt-accent
--vt-accent-fg --vt-rule --vt-paper --vt-good --vt-bad --vt-warn`.

Derived tokens (`--vt-soft --vt-stripe --vt-neutral-soft --vt-accent-dk --vt-accent-soft`)
update automatically from the base tokens and need not be overridden.

Topic-specific colors (e.g. a product's own UI palette) belong here, not in
`visual-teach.css`.
