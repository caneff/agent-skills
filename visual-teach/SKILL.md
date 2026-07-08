---
name: visual-teach
description: Rich interactive blocks for teaching lessons — quizzes with feedback, persisted checklists, callouts, annotated code, themeable styling. Use when authoring, building, or improving a teaching lesson's HTML (especially with the `/teach` skill): emit `vt-*` blocks linked to shared assets instead of inlining per-lesson CSS/JS. Also converts/retrofits existing lesson HTML to these blocks.
when_to_use: Whenever a teaching lesson HTML file is being written or edited — a `/teach` lesson, or any standalone lesson. Reach for it the moment you would otherwise inline a quiz, checklist, callout, or lesson stylesheet.
---

# visual-teach

A passive component library for teaching lessons: one stylesheet
(`assets/visual-teach.css`) + one script (`assets/visual-teach.js`) that supply
look and behavior via `vt-*` CSS classes. It does **not** own a lesson format, a
schema, or pedagogy — that's `/teach`'s job (`mattpocock/skills`,
`skills/productivity/teach`). visual-teach only makes lesson HTML rich and
consistent. No `/teach` installed → there's nothing to enrich; install it first.

The authoring reference is **`assets/visual-teach.md`** (the cheatsheet). Read it
before emitting blocks.

**Authoring a new lesson:** don't assemble from scratch — start from the **Page
shell** block near the top of the cheatsheet (the canonical `<main>` skeleton:
metabar, objectives, sections, recap) plus the asset `<link>`/`<script>` snippet
above it, then fill it in and add blocks per the cheatsheet, deleting any you
don't need. Cloning a known-good shell avoids the common misses (wrong asset
paths, dropped wrapper divs).

## How it reaches `/teach`

`/teach` consumes the components from the **filesystem**: once the asset files
sit in a workspace's `./assets/`, `/teach` reuses them by its own charter ("read
`./assets/` and build from the components already there"). So the one job that
matters is **getting those files into `./assets/`** — then author with `vt-*`
blocks per the cheatsheet, never inlining a per-lesson `<style>`/`<script>`. The
blocks are a **floor, not a ceiling**: keep building bespoke `./assets/`
components when a topic needs an interaction the catalog can't express, so lessons
don't turn samesy (see the cheatsheet's "floor, not a ceiling" note).

**Seeding is this skill's first action.** When this skill is active during a
`/teach` authoring or extension turn and the workspace `./assets/` lacks the
library, copy the assets in from **this skill's own bundled `assets/` directory**
— the `assets/` folder that ships alongside this `SKILL.md` in the skill's base
directory (for a normal global install, `~/.claude/skills/visual-teach/assets/`).
Use the skill base directory announced when this skill loads; do **not** hardcode
a developer checkout path. From the workspace root:

```sh
mkdir -p ./assets
cp -R "<this skill's base dir>/assets/." ./assets/
```

Do this before the first lesson, or let Convert (below) do it on an existing one.

## Convert existing lessons (`/visual-teach [file|all]`)

Retrofit a lesson's HTML to `vt-*` blocks + shared assets. Mechanical edit — no
content changes. For each targeted file:

1. Ensure `./assets/visual-teach.{css,js,md}` exist; copy from this skill if not.
2. In the `<head>`, move any topic-specific color variables from the inline
   `<style>` into a `<style>` `:root { }` override block (keep only the custom
   token values, not component styles).
3. Remove the remaining inline `<style>` block entirely.
4. Remove any inline `<script>` block(s).
5. Add asset links (relative to the lesson, typically `lessons/`):
   ```html
   <link rel="stylesheet" href="../assets/visual-teach.css" />
   ```
   and before `</body>`:
   ```html
   <script src="../assets/visual-teach.js"></script>
   ```
   **Do NOT add `type="module"` to this `<script>` tag.** `visual-teach.js` is a
   plain UMD/IIFE script, not an ES module. Adding `type="module"` causes browsers
   to fetch it as a module subject to CORS — which breaks file:// delivery with a
   CORS policy error, silently disabling every interactive component.
   Strip `type="module"` from the `visual-teach.js` script tag if found.
6. Swap class names to their `vt-*` equivalents per `assets/visual-teach.md`.
   Preserve all semantic content, headings, body text, `data-*` attributes, and
   interactive markup.
7. Report each file changed and confirm no content was removed.
