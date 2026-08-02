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

- Each named rule becomes one block inside the Rules card: `<strong style="display: block;">` name on its own line, then the rule text in a `<span style="color: #444;">`. Last block gets `margin-bottom: 0;`, all others `margin-bottom: 14px;`.
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

**LMD embeds pasted HTML verbatim — there is no sanitizer.** Verified by extracting a live puzzle's source (search the page source for `HTML-Code des Raetsels: Anfang`; the raw HTML follows). Divs, inline styles, `<hr>`, headings all pass through untouched. If the rendered page loses tags or text, the paste was corrupted (see Output section) — do not redesign the HTML around it. LMD's own docs recommend `<div style="clear:both;text-align:center">` as the image wrapper.

The image is referenced with LMD's custom syntax `<img:XXXXXX>` where XXXXXX is the uploaded file's id — beware stray spaces inside it. Extra attributes are passed through to the rendered `<img>` tag: `width="420"` sets the display size to fit the image column of the two-column layout; `max-width: 100%` keeps it from overflowing (it shrinks to full width when the columns stack on mobile).

Layout: a centered italic epigraph intro on top (omit when no notes), then a two-column flex row — image on the left (`flex: 3`), a Rules card on the right (`flex: 2 1 280px`, `#eef`/`#ddf` with a `#ddf` header bar) — a ~3:2 split that gives verbose rulesets room to breathe instead of towering. `flex-wrap` stacks them vertically on narrow screens. **Flexbox on LMD is unverified — check a real preview; if it doesn't hold, the wrap makes it degrade to stacked blocks anyway.**

## Template

```html
<section style="max-width: 820px; margin: 20px auto;">
  <!-- Intro: only when notes given. Omit this whole <p> (no header, no placeholder) if there are none.
       Author's-note epigraph — italic, centered, muted, hairline divider beneath. -->
  <p style="max-width: 620px; margin: 0 auto 20px; padding-bottom: 15px; border-bottom: 1px solid #ccd; font-style: italic; text-align: center; color: #555; line-height: 1.6;">
    {{NOTES}}
  </p>

  <!-- Two columns: image left, Rules card right. flex-wrap stacks them on narrow screens.
       ONE-COLUMN MODE (layout == "one", long rules): change BOTH flex bases below to
       "1 1 100%" — the image and the Rules card then each take a full row, so the card
       falls below the image at full width instead of towering as a tall side column.
       Everything else (styles, the #ddf bar, rule blocks) stays identical. -->
  <div style="display: flex; flex-wrap: wrap; gap: 20px; align-items: stretch;">
    <div style="flex: 3 1 320px; text-align: center;">
      <a href="{{SUDOKUPAD_LINK}}"><img:{{IMAGE_ID}} width="420" style="max-width: 100%; display: block; margin: 0 auto;"></a>
      <div style="margin-top: 8px;"><a href="{{SUDOKUPAD_LINK}}" style="color: #557; font-weight: bold; text-decoration: none;">Play Now! &rarr;</a></div>
    </div>
    <aside style="flex: 2 1 280px; background: #eef; border: 1px solid #ddf; border-radius: 5px; overflow: hidden;">
      <div style="background: #ddf; padding: 8px 18px; font-weight: bold;">Rules</div>
      <div style="padding: 16px 18px;">
        <div style="margin-bottom: 14px; line-height: 1.5;"><strong style="display: block;">{{RULE_NAME}}</strong><span style="color: #444;">{{RULE_TEXT}}</span></div>
        <!-- one block per rule; last one uses margin-bottom: 0; -->
      </div>
    </aside>
  </div>
</section>
```
