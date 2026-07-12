---
name: create-lmd-page
description: Generate a Logic Masters Deutschland puzzle page (HTML) from a ruleset, a SudokuPad link, and an image id. Use when the user wants to create/format an LMD puzzle post, says "create lmd page", "/create-lmd-page", or gives a new ruleset + sudokupad link for a puzzle page.
disable-model-invocation: true
---

# Create LMD Page

Generate the HTML for a Logic Masters Deutschland puzzle post from three inputs.

## Inputs

Collect from the user (ask for any that are missing):

1. **Ruleset** — the puzzle rules, usually as plain text with one named rule per paragraph (e.g. "Double Arrows: Digits along a purple line...")
2. **SudokuPad link** — e.g. `https://sudokupad.app/abc123`
3. **Image id** — e.g. `001344`, used in the `<img:ID>` placeholder
4. **Notes** (optional) — flavor text for the Notes section. If not given, leave the placeholder comment.

## Output

Fill the template below, then:

1. Write it to `~/lmd-pages/<puzzle-slug>.html` (create the dir if needed; slug from the puzzle/rule name, e.g. `scell-squish.html`).
2. Load it onto the clipboard: `clip.exe < FILE` (WSL) / `pbcopy < FILE` (macOS) / `xclip -selection clipboard < FILE` (Linux).
3. Tell the user it's on the clipboard AND state the file path, so they can re-copy it later without regenerating.

**Never have the user copy the HTML out of the terminal.** Drag-selecting long soft-wrapped lines in the TUI silently drops chunks mid-line (screen-cell copy during redraws) — this corrupted rule text and tags repeatedly before the clipboard workflow was adopted. Also show the HTML in a code block for review, but the clipboard is the source of truth.

Formatting rules:

- Each named rule becomes one `<li>` with the rule name in `<strong>` followed by a colon. Last `<li>` gets `margin-bottom: 0;`, all others `margin-bottom: 10px;`.
- Escape special characters as HTML entities (`&ouml;`, `&deg;`, `&amp;`, etc.).
- Fix obvious typos in rule text (e.g. "sum the the" → "sum to the"), but never change rule meaning. Mention any fix you made.
- Rule text is deliverable prose — write it normally, never compress it.
- The SudokuPad link goes in **both** the image anchor and the caption anchor.

The template is styled to blend into the Logic Masters Deutschland site (logic-masters.de), whose CSS the page inherits:

- No `font-family` — the site sets `sans-serif` at 90% on the page; inheriting matches the surrounding text.
- Background `#eef` and border `#ddf` match LMD's sidebar boxes and image borders; `border-radius: 5px` matches LMD's `.box`.
- Headings at `font-size: 120%` match LMD's in-box `H2` sizing; the caption's `80%`/`#888` matches LMD metadata lines (e.g. "eingestellt von...").
- Use `%`/`px` units like the site does, not `rem` (site font-size is 90%, so rem values don't line up).
- `.rp_html IMG` already gets `max-width: 100%` from site CSS.

**LMD embeds pasted HTML verbatim — there is no sanitizer.** Verified by extracting a live puzzle's source (search the page source for `HTML-Code des Raetsels: Anfang`; the raw HTML follows). Divs, inline styles, `<hr>`, headings all pass through untouched. If the rendered page loses tags or text, the paste was corrupted (see Output section) — do not redesign the HTML around it. LMD's own docs recommend `<div style="clear:both;text-align:center">` as the image wrapper.

The image is referenced with LMD's custom syntax `<img:XXXXXX>` where XXXXXX is the uploaded file's id — beware stray spaces inside it. Extra attributes are passed through to the rendered `<img>` tag: `width="600"` sets the display size, matching the 600px Rules/Notes block so image and text align flush; `max-width: 100%` keeps it from overflowing on mobile.

Layout: the Rules/Notes block is capped at 600px and auto-centered (text left-justified) so it sits on the same center line as the image; image and caption are centered by the LMD-recommended div wrapper.

## Template

```html
<section style="max-width: 720px; margin: 20px auto; padding: 15px; background: #eef; border: 1px solid #ddf; border-radius: 5px;">
  <div style="clear: both; text-align: center;">
    <a href="{{SUDOKUPAD_LINK}}"><img:{{IMAGE_ID}} width="600" style="max-width: 100%;"></a>
    <br>
    <span style="font-size: 80%; color: #888;"><a href="{{SUDOKUPAD_LINK}}">Click on the image to play</a></span>
  </div>

  <div style="max-width: 600px; margin: 20px auto 0; padding-top: 12px; border-top: 1px solid #ccd;">
    <p style="margin: 0 0 10px; font-size: 120%; font-weight: bold;">Rules</p>
    <ol style="margin: 0; padding-left: 20px;">
      <li style="margin-bottom: 10px;">
        <strong>{{RULE_NAME}}:</strong> {{RULE_TEXT}}
      </li>
      <!-- one <li> per rule; last one uses margin-bottom: 0; -->
    </ol>
  </div>

  <div style="max-width: 600px; margin: 20px auto 0; padding-top: 12px; border-top: 1px solid #ccd;">
    <p style="margin: 0 0 10px; font-size: 120%; font-weight: bold;">Notes</p>
    <p style="margin: 0; line-height: 1.5;">
      {{NOTES or <!-- notes here -->}}
    </p>
  </div>
</section>
```
