---
name: create-lmd-page
description: Generate a Logic Masters Deutschland puzzle page (HTML) from a ruleset, a SudokuPad link, and an image id. Use when the user wants to create/format an LMD puzzle post, says "create lmd page", "/create-lmd-page", or gives a new ruleset + sudokupad link for a puzzle page.
disable-model-invocation: true
---

# Create LMD Page

Generate the HTML for a Logic Masters Deutschland puzzle post from three inputs.

## Inputs

Collect from the user **one at a time** — ask for each missing input in its own
message and wait for the reply before asking the next. Do not batch them into a
single prompt. Skip any input the user already supplied. Order:

1. **SudokuPad link** — e.g. `https://sudokupad.app/abc123`. This *also supplies
   the ruleset*: run the extractor (below) to pull the rules straight from the
   puzzle. Only ask for rules text if extraction fails.
2. **Image id** — e.g. `001344`, used in the `<img:ID>` placeholder
3. **Notes** (optional) — intro/flavor text shown at the *top* of the page, above the image, with no header. If not given, omit the intro block entirely.

**Linking a setter's name in the notes.** When the user says "link to <name>'s LMD page" (or asks to link a name mentioned in the notes), wrap that name in an anchor to their LMD user page: `https://logic-masters.de/Raetselportal/Benutzer/eingestellt.php?name=<NAME>` (substitute the name, URL-encoding it if needed). Don't ask for the URL — build it from this template.

### Auto-extract rules from the link

After the link, run:

```
skills/create-lmd-page/extract_puzzle.py "<sudokupad-url-or-id>"
```

(absolute path: `~/.claude/skills/create-lmd-page/extract_puzzle.py`; needs `uv`,
shebang pulls `lzstring`). It prints JSON `{title, author, rules, layout}` pulled
from the puzzle's `metadata`. The `rules` field is the ruleset — one named rule
per paragraph, `\n\n`-separated — use it as if the user pasted it. Show the
extracted rules and let the user correct them before building. `layout`
(`"two"`/`"one"`) picks the template column count — see the Template section.

If the script errors (non-zero exit: fetch failed, unknown blob format, or no
rules field), fall back to asking the user for the ruleset as plain text (and
judge `layout` by eye: one column if the rules would run taller than the ~450px
image). Do not block on the extractor.

## Output

Fill the template below, then:

1. Write it to `~/lmd-pages/<puzzle-slug>.html` (create the dir if needed; slug from the puzzle/rule name, e.g. `scell-squish.html`).
2. Load it onto the clipboard: `clip.exe < FILE` (WSL) / `pbcopy < FILE` (macOS) / `xclip -selection clipboard < FILE` (Linux).
3. Tell the user it's on the clipboard AND state the file path, so they can re-copy it later without regenerating.

**Never have the user copy the HTML out of the terminal.** Drag-selecting long soft-wrapped lines in the TUI silently drops chunks mid-line (screen-cell copy during redraws) — this corrupted rule text and tags repeatedly before the clipboard workflow was adopted. Also show the HTML in a code block for review, but the clipboard is the source of truth.

Formatting rules:

- Each named rule becomes one block inside the Rules card: `<strong style="display: block;">` name on its own line, then the rule text as a `<ul style="color: #444; margin: 4px 0 0; padding-left: 18px; max-width: none;">` with one `<li style="max-width: none;">` per point (the `max-width: none` is the gutter fix below). Always use the bullet list — even a single-statement rule is one `<li>` bullet, so every rule reads consistently. Last block gets `margin-bottom: 0;`, all others `margin-bottom: 14px;`.
- **Rules card right-gutter (the important gotcha).** If the rules are rendered as a bullet list (`<ul><li>`), LMD's own CSS caps list-item text to a fixed measure (~560px). The lines then wrap short no matter how wide you make the card, leaving a big empty band on the right — and it comes back every time you widen the card, because the site is overriding you. **Fix: add `max-width: none;` to every `<ul>` and `<li>` in the Rules card.** That releases the cap so the text fills the card width. Once released, the card can be as wide as you like with no gutter. (Symmetric `16px 18px` card padding keeps the small left/right gutters even.) `<span>`-based (non-bullet) rule text isn't capped, so it only matters when you use bullets — but adding it is harmless, so the templates below include it.
- Escape special characters as HTML entities (`&ouml;`, `&deg;`, `&amp;`, etc.).
- Fix obvious typos in rule text (e.g. "sum the the" → "sum to the"), but never change rule meaning. Mention any fix you made.
- Rule text is deliverable prose — write it normally, never compress it.
- The SudokuPad link goes in **both** the image anchor and the caption anchor, **verbatim as the user gave it** — keep any `?setting-...` query (e.g. `?setting-nogrid=true`), it changes how the puzzle loads. Only the extractor strips the query, and that's just for its API fetch, not the page links.

The template is styled to blend into the Logic Masters Deutschland site (logic-masters.de), whose CSS the page inherits:

- No `font-family` — the site sets `sans-serif` at 90% on the page; inheriting matches the surrounding text.
- Background `#eef` and border `#ddf` match LMD's sidebar boxes and image borders; `border-radius: 5px` matches LMD's `.box`.
- Headings at `font-size: 120%` match LMD's in-box `H2` sizing; the caption's `#888` matches LMD metadata lines (e.g. "eingestellt von...").
- Use `%`/`px` units like the site does, not `rem` (site font-size is 90%, so rem values don't line up).
- `.rp_html IMG` already gets `max-width: 100%` from site CSS.
- The whole post sits in a thin frame: `background: #fafaff; border: 1px solid #ddf; border-radius: 8px; padding: 26px 30px` on the `<section>` (both layouts). Same `#ddf`/`5px`-family hairline as the Rules card; the `#fafaff` fill is a barely-there lavender tint, deliberately lighter than the `#eef` card so the card still reads as the darker inner panel. Frame widths: 820px two-column, 840px one-column (a wide single column filled by a large centered image up top and a wide rules card below — see the gutter gotcha above for why the card can be wide).

**LMD embeds pasted HTML verbatim — there is no sanitizer.** Verified by extracting a live puzzle's source (search the page source for `HTML-Code des Raetsels: Anfang`; the raw HTML follows). Divs, inline styles, `<hr>`, headings all pass through untouched. If the rendered page loses tags or text, the paste was corrupted (see Output section) — do not redesign the HTML around it. LMD's own docs recommend `<div style="clear:both;text-align:center">` as the image wrapper.

The image is referenced with LMD's custom syntax `<img:XXXXXX>` where XXXXXX is the uploaded file's id — beware stray spaces inside it. Extra attributes are passed through to the rendered `<img>` tag: `width="420"` (two-column) / `width="600"` (one-column) sets the display size; `max-width: 100%` keeps it from overflowing (it shrinks to full width when the columns stack on mobile).

Layout — pick by the `layout` field (see the two variants under Template):
- **Two-column** (`"two"`, shorter rulesets): a centered italic epigraph on top, then a flex row — image left (`flex: 3`), Rules card right (`flex: 2 1 280px`, `#eef`/`#ddf` with a `#ddf` header bar). The ~3:2 split keeps short rules beside the image.
- **One-column** (`"one"`, long rulesets): epigraph, then a large centered image, then a wide full-width Rules card below — so a verbose ruleset runs across the page instead of towering as a tall side column.

`flex-wrap` stacks the columns vertically on narrow screens. **Flexbox on LMD is unverified — check a real preview; if it doesn't hold, the wrap makes it degrade to stacked blocks anyway.**

## Template

Two variants below — two-column and one-column. The `<section>` max-width, the image
`width`, and the `<aside>` flex line are the only things that differ between them; the
epigraph, `#ddf` bar, and rule blocks are identical in both.

### Two-column (`layout == "two"`)

```html
<section style="max-width: 820px; margin: 20px auto; background: #fafaff; border: 1px solid #ddf; border-radius: 8px; padding: 26px 30px;">
  <!-- Intro: only when notes given. Omit this whole <p> (no header, no placeholder) if there are none.
       Author's-note epigraph — italic, centered, muted, hairline divider beneath.
       Text is capped at 620px and centered; the divider rule spans the full column. -->
  <p style="margin: 0 auto 20px; padding-bottom: 15px; border-bottom: 1px solid #ccd; font-style: italic; text-align: center; color: #555; line-height: 1.6;">
    <span style="display: block; max-width: 620px; margin: 0 auto;">{{NOTES}}</span>
  </p>

  <!-- Image left, Rules card right. flex-wrap stacks them on narrow screens.
       The flex: 2 1 280px card hugs its own column, so its 18px side gutters stay balanced. -->
  <div style="display: flex; flex-wrap: wrap; gap: 20px; align-items: stretch;">
    <div style="flex: 3 1 320px; text-align: center;">
      <a href="{{SUDOKUPAD_LINK}}"><img:{{IMAGE_ID}} width="420" style="max-width: 100%; display: block; margin: 0 auto;"></a>
      <div style="margin-top: 8px;"><a href="{{SUDOKUPAD_LINK}}" style="color: #557; font-weight: bold; text-decoration: none;">Play Now! &rarr;</a></div>
    </div>
    <aside style="flex: 2 1 280px; background: #eef; border: 1px solid #ddf; border-radius: 5px; overflow: hidden;">
      <div style="background: #ddf; padding: 8px 18px; font-weight: bold;">Rules</div>
      <div style="padding: 16px 18px;">
        <div style="margin-bottom: 14px; line-height: 1.5;"><strong style="display: block;">{{RULE_NAME}}</strong><ul style="color: #444; margin: 4px 0 0; padding-left: 18px; max-width: none;"><li style="max-width: none;">{{RULE_POINT}}</li></ul></div>
        <!-- one block per rule (last uses margin-bottom: 0). One <li> per bullet point.
             A single-statement rule is still a <ul> with one <li> — always bullet. -->
      </div>
    </aside>
  </div>
</section>
```

### One-column (`layout == "one"`, long rules)

The image and Rules card each take a full row (card falls below the image instead of
towering beside it). Frame is **wide** (`max-width: 840px`): a large centered image
(`width="600"`) up top, and a wide rules card (`flex: 1 1 100%; max-width: 780px;
margin: 0 auto`) below. The card is wide *and* gutter-free because the `<ul>`/`<li>`
carry `max-width: none` (the gutter gotcha above) — the text fills the full card width
instead of wrapping short. The image column is also `flex: 1 1 100%` so it stacks.
Everything else is identical to two-column.

```html
<section style="max-width: 840px; margin: 20px auto; background: #fafaff; border: 1px solid #ddf; border-radius: 8px; padding: 26px 30px;">
  <p style="margin: 0 auto 20px; padding-bottom: 15px; border-bottom: 1px solid #ccd; font-style: italic; text-align: center; color: #555; line-height: 1.6;">
    <span style="display: block; max-width: 620px; margin: 0 auto;">{{NOTES}}</span>
  </p>

  <div style="display: flex; flex-wrap: wrap; gap: 20px; align-items: stretch;">
    <div style="flex: 1 1 100%; text-align: center;">
      <a href="{{SUDOKUPAD_LINK}}"><img:{{IMAGE_ID}} width="600" style="max-width: 100%; display: block; margin: 0 auto;"></a>
      <div style="margin-top: 8px;"><a href="{{SUDOKUPAD_LINK}}" style="color: #557; font-weight: bold; text-decoration: none;">Play Now! &rarr;</a></div>
    </div>
    <aside style="flex: 1 1 100%; max-width: 780px; margin: 0 auto; background: #eef; border: 1px solid #ddf; border-radius: 5px; overflow: hidden;">
      <div style="background: #ddf; padding: 8px 18px; font-weight: bold;">Rules</div>
      <div style="padding: 16px 18px;">
        <div style="margin-bottom: 14px; line-height: 1.5;"><strong style="display: block;">{{RULE_NAME}}</strong><ul style="color: #444; margin: 4px 0 0; padding-left: 18px; max-width: none;"><li style="max-width: none;">{{RULE_POINT}}</li></ul></div>
        <!-- one block per rule (last uses margin-bottom: 0). One <li> per bullet point.
             A single-statement rule is still a <ul> with one <li> — always bullet. -->
      </div>
    </aside>
  </div>
</section>
```
