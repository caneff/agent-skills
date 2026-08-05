# HTML Report Format

The code-quality review is rendered as a single self-contained HTML file in the OS temp directory. Tailwind and Mermaid both come from CDNs. The centrepiece of most findings is a **before/after code block**, not a graph — a code-judo move reads best as source you can compare line for line. Reach for Mermaid only when the point is graph-shaped: "this format is written in three places," "this parser is duplicated across two scripts," "this failure is coupled to that flow." Mix the two. Don't force every finding into a diagram.

## Scaffold

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Code quality review — {{repo name}}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });
    </script>
    <style>
      /* small custom layer for things Tailwind doesn't cover cleanly */
      .dup { stroke: #dc2626; }
      pre code { white-space: pre; }
    </style>
  </head>
  <body class="bg-stone-50 text-slate-900 font-sans">
    <main class="max-w-5xl mx-auto px-6 py-12 space-y-12">
      <header>...</header>
      <section id="headline">...</section>
      <section id="findings" class="space-y-10">...</section>
      <section id="leaving-alone">...</section>
    </main>
  </body>
</html>
```

## Header

Repo name, date, and a one-line **verdict** — the honest state of the code in a sentence (e.g. "Clean codebase; one structural move resolves four findings, plus a real reliability fix"). Then a compact legend of the severity badges. No throat-clearing paragraph — straight into the headline.

## Severity badges

Every finding carries exactly one, coloured consistently:

- **Blocker** — rose. A real defect or a regression that must not ship.
- **Strong** — amber. A high-conviction structural fix; do it.
- **Worth it** — sky. A clear improvement, lower stakes.
- **Nit** — slate. Cosmetic; listed only if it rides along cheaply.

A second, neutral **category tag** (`duplication`, `spaghetti`, `boundary`, `file-size`, `dead-abstraction`, `reliability`, `simplification`) sits next to the badge so the reader can scan by kind.

## Headline card

One larger card at the top for the single strongest code-judo move — the one restructuring that deletes the most complexity, or resolves several findings at once. Name the move as a verb ("Extract a discord-free `todos.py`"), state in one sentence what it collapses, list the findings it resolves as chips, and show the key before/after. This is the thing you'd do first; make it look like it.

## Finding card

Each finding is one `<article>` in a bordered card. Prose is sparse and plain. Anatomy:

- **Title** — short, names the fix as an action ("Decouple retro failure from the digest").
- **Badge row** — severity badge + category tag + a monospaced file list (`font-mono text-sm`), e.g. `digest.py:185`.
- **Problem** — one sentence. What's wrong and what it costs.
- **Before / After** — the centrepiece. Two columns side by side (stack on mobile). Real source, syntax kept simple with `<pre class="…"><code>`. The `before` column tinted rose-50, the `after` column tinted emerald-50. Keep each side short — the smallest snippet that makes the move obvious; elide with `…` rather than pasting whole functions.
- **Wins** — bullets, ≤6 words each: "one source of the line format", "digest survives a retro hiccup", "toggle ambiguity gone".
- **Standard callout** (when relevant) — one line in an amber-tinted box if the fix touches a documented coding standard or ADR, e.g. _"CODING_STANDARDS.md mandates atomic writes for tracked vault files."_

No paragraphs of explanation. If a finding needs a paragraph, tighten it into problem + before/after + wins.

## Diagram patterns

Use a diagram only when it beats a code block. Wrap Mermaid in a Tailwind card so it doesn't feel parachuted in.

### Fan-in (the workhorse for duplication)

"This format / rule / parse is written in N places" → one canonical home. Colour the duplicate edges red.

```html
<div class="rounded-lg border border-slate-200 bg-white p-4">
  <pre class="mermaid">
    flowchart LR
      A[append_todo] -.writes line format.-> F[(todo.md format)]
      B[backfill_ids] -.writes line format.-> F
      C[_TODO_COMMENT] -.matches format.-> F
      classDef dup stroke:#dc2626,stroke-width:2px;
      class A,B,C dup
  </pre>
</div>
```

### Coupling / blast-radius (good for reliability findings)

Show one fragile node whose failure currently takes down a reliable one; the "after" splits them. A `flowchart` with the fragile path in red and a dashed line where the seam should go.

### Before/after code columns (the default — no library needed)

Two `<div>`s in a `grid md:grid-cols-2 gap-4`. Left tinted rose, right tinted emerald, each a `<pre><code>` block. This carries most findings; the Mermaid patterns are the exception, not the rule.

## Deliberately leaving alone

Close with a short section — a plain list or a muted card — of the things you looked at and consciously kept: real duplication that isn't worth the cross-import, a hacky-but-correct attribute, a `ponytail:`-commented shortcut whose ceiling is already named. This proves the review was thorough and not just a pile of demands, and it stops the reader from "fixing" something that was a deliberate call.

## Style guidance

- Lean editorial, not corporate-dashboard. Generous whitespace. Serif optional for headings (`font-serif` reads well with stone/slate).
- Colour sparingly: rose for defects/before, emerald for the fixed/after, amber for warnings and standards, one neutral accent (indigo or slate) for structure.
- Keep before/after columns short enough to sit side by side without horizontal scroll on a laptop.
- Monospace every file path, symbol, and code fragment. Findings are about specific lines — cite them (`file.py:123`).
- The only scripts are the Tailwind CDN and the Mermaid ESM import. The report is otherwise static.

## Tone

Direct, serious, and demanding about quality — the same standard as the terminal review, not softened because it is now in a browser. Name the problem plainly. Do not hedge it into a mild suggestion. Rank without mercy: the headline and the Blockers come first; the Nits ride along at the bottom or not at all.

**Write the prose in Simplified Technical English** (see the SKILL.md "Write the review in plain language" section). Short sentences. One idea per sentence. Active voice, present tense. Use the `CONTEXT.md` domain terms exactly (Vault, Capture, Digest, Todo board, Todo id). Keep real technical terms (module, regex, atomic write). **Do not put this skill's metaphors — "code judo", "spaghetti", "seam leak" — into the card text.** A card that needs the dialect to be understood has failed; rewrite it.

- Good: "This format is written in three places. Change it and all three must stay the same."
- Good: "One failed `claude -p` call stops the whole Digest. Split the retro from the scan."
- Avoid (dialect): "There's a code-judo move that deletes this whole layer of spaghetti."
- Avoid (hedging): "It might be slightly cleaner to consider possibly extracting…"

If a finding is not high-conviction, cut it. A short report of real changes beats a long one padded with cosmetics.
