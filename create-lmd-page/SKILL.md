---
name: create-lmd-page
description: Post a Logic Masters Deutschland puzzle from a SudokuPad link: render the image, create the inactive puzzle through the driver, archive it, and hand back the puzzle page link.
disable-model-invocation: true
---

# Create LMD Page

Make a Logic Masters Deutschland puzzle page from a SudokuPad link: render the board
image, post the puzzle to LMD as an inactive draft, write the page HTML, archive the
puzzle, and hand Chris the puzzle page link. **Chris reviews the page and clicks
"Aktivieren" himself; the skill never does.**

**A failure stops the skill.** Any step that fails (the extractor after its one
fallback, the stream gate, the stream browser, the render, the driver, a check on its
output, the archive) stops the run, and the failure is reported to the user with the
command's output. Once Output step 1 has run, the report also names the page file it
wrote, `~/lmd-pages/work/<slug>/page.html` (its image id still the literal
`{{IMAGE_ID}}`), for reference. There is no fallback to the manual flow: do not hand over
a page to paste, and never say the puzzle is posted or archived after a failure. Facts
about the LMD forms and the driver's contract:
`docs/research/2026-11-06-lmd-upload-and-submit-forms.md`, `create-lmd-page/lmd_driver.mjs`.

This is the one statement of the failure rule; the steps below say what counts as a
failure, never how to report it.

## Inputs

Collect from the user **one at a time**, each in its own message, waiting for the reply
before asking the next. Skip any input the user already supplied. Order:

1. **SudokuPad link** — e.g. `https://sudokupad.app/abc123`. It *also supplies the
   ruleset*: run the extractor (below) and show the rules for the user to correct.
   When the extractor's `title` is `null` (or it failed), ask for the **title** next,
   in one message of its own, before the notes.
2. **Notes** (optional) — intro/flavor text shown at the *top* of the page, above the
   image, with no header. If not given, omit the intro block entirely.
3. **Solution code description** — what the code is, e.g. "row 5, left to right".
4. **Difficulty** — 1 to 5 (default 3).

There is no image id to ask for: the driver reads it from LMD.

**Linking a setter's name in the notes.** When the user says "link to <name>'s LMD page"
(or asks to link a name mentioned in the notes), wrap that name in an anchor to their LMD
user page: `https://logic-masters.de/Raetselportal/Benutzer/eingestellt.php?name=<NAME>`
(substitute the name, URL-encoding it if needed). Don't ask for the URL.

### Auto-extract rules and solution from the link

After the link, run:

```
~/.agents/skills/create-lmd-page/extract_puzzle.py "<sudokupad-url-or-id>"
```

(needs `uv`, shebang pulls `lzstring`). It prints JSON `{title, author, rules, solution,
layout}` pulled from the puzzle's `metadata`. `rules` is the ruleset — one named rule per
paragraph, `\n\n`-separated. `solution` is the puzzle's embedded solution (digits,
row-major), or `null` when it carries none. `layout` (`"two"`/`"one"`) picks the template
column count — see the Template section.

If the script errors (fetch failed, unknown blob format, no rules field), ask the user
for the ruleset as plain text, and judge `layout` by eye: one column if the rules would
run taller than the ~450px image. That one fallback is the extractor's only; `solution`
and `title` are then `null`.

### Solution code

The code is what the solver enters on LMD. Derive it, then show it for confirmation:

- The description is a plain readout (a row, a column or a diagonal, in a stated
  direction) and `solution` is not `null`: read those cells off `solution` and show the
  code. Chris confirms or corrects it.
- Anything else, or `solution` is `null`: ask the user for the code.

The driver refuses a code with a character LMD would strip; the allowed set is its
`CODE_ALLOWED`.

### Tags, and the Sudoku question

Propose all three from the ruleset and show them in **one** message for the user to
confirm or change (tag list and field names: the research note's *Labels* and *Free
tags*):

- **Labels** — the fixed checkboxes `label_<n>` (62 of them, e.g. `3` Puzzle variant,
  `131` Latin Square). Send the numbers.
- **Free tags** — the `freetags` text, suggestions from the research note's list
  (e.g. `Sudoku`, `Killer (Variant)`).
- **Sudoku_JaNein** — "Is your puzzle in essence a Sudoku (this includes variants)?"
  Default `Ja`; the user may flip it to `Nein`.

## Output

Work in `~/lmd-pages/work/<slug>/`; `<slug>` comes from the puzzle/rule name, e.g.
`scell-squish`. Create the directory. Then, in order:

1. **Fill the template** (§ Template, formatting rules below) with `{{IMAGE_ID}}` left as
   the literal text `{{IMAGE_ID}}`, and write it to `~/lmd-pages/work/<slug>/page.html`.
2. **Render the board image** that fits inside 800×800. The `<img:ID>` display width stays
   420 (two-column) or 600 (one-column), whatever the file's size:

   ```
   uv run --project ~/src/sudokupad-art python ~/.agents/skills/create-lmd-page/board_png.py "<sudokupad-link>" ~/lmd-pages/work/<slug>/board.png
   ```

   It runs sudokupad-art's `render_real.js` on the puzzle and shrinks the PNG when a side
   is over 800 px. A non-zero exit is a failure, and it leaves no PNG.
3. **Stream gate.** Before any driver call, run the rig's own check and stop on a
   non-zero exit, showing its stderr as it stands:

   ```
   node ~/src/twitch-rules-scroller/layout/install-preflight.mjs obs
   ```

   Exit 0 (it prints `open` or `closed`) means OBS is neither streaming nor recording.
   It refuses when OBS is streaming or recording, when OBS's status cannot be read, and
   when the websocket is unreachable while `obs64.exe` is running. Its message starts
   "Refusing to install"; in this skill the refusal is the stream gate's, so say so and
   show the output unchanged.
4. **Stream browser endpoint.** The driver needs the stream browser's control port. Ask
   it, through Windows `node.exe` (WSL cannot reach a Windows loopback port); the last
   argument is how many seconds to keep trying:

   ```
   node.exe -e "const end=Date.now()+1000*Number(process.argv[1]);(async()=>{for(;;){try{if((await fetch('http://127.0.0.1:9334/json/version')).ok)process.exit(0)}catch{}if(Date.now()>=end){console.error('nothing answers on 127.0.0.1:9334');process.exit(1)}await new Promise(r=>setTimeout(r,500))}})()" 0
   ```

   Exit 0: go on. Otherwise list the running stream browsers:
   `tasklist.exe /FI "IMAGENAME eq chrome-stream.exe" /NH`. Any `chrome-stream.exe` line
   is a refusal: a stream browser that is already running keeps the command line it
   started with, so it has no control port until it is closed once (the e2e Chrome runs
   the same exe, so name the pids and say that). With none running, launch it with the
   rig's own arguments (twitch-rules-scroller `StreamBrowser.cs` `LaunchStreamBrowser`,
   read at 3784974; the rig lives in `C:\Users\canef\stream-rig`):

   ```
   powershell.exe -NoProfile -Command "Start-Process -FilePath 'C:\Users\canef\stream-rig\chrome-stream\chrome-stream.exe' -WorkingDirectory 'C:\Users\canef\stream-rig\chrome-stream' -ArgumentList '--remote-debugging-port=9334','--user-data-dir=C:\Users\canef\stream-rig\stream-profile','--no-first-run','--no-default-browser-check','--hide-crash-restore-bubble','https://logic-masters.de/Raetselportal/Einstellungen/listen.php?list=beobachtung'"
   ```

   then rerun the endpoint check above with `20` in place of `0`. A non-zero exit there
   is a failure.
5. **Write the driver values** to `~/lmd-pages/work/<slug>/values.json`, from what the
   user confirmed, with the keys and types the header of `lmd_driver.mjs` lists. `title`
   is the extractor's, or the one Chris gave; `codedescr_en` is the description the user
   gave.
6. **Post.** Run the driver through Windows `node.exe`, against the stream browser on
   9334. It uploads the image, fills the template's image id, fills the English-only form
   and clicks "Create", which saves the puzzle inactive. The command first refuses when
   `driver.json` already holds an earlier run's output, naming that run's puzzle id, so
   a rerun never posts a second puzzle over a first or overwrites its id:

   ```
   cd ~/lmd-pages/work/<slug> && python3 -c 'import json,os,sys; t=open("driver.json").read() if os.path.exists("driver.json") else ""; d=json.loads(t) if t.strip() else {}; d and sys.exit("refusing to post: driver.json already holds puzzle %s from an earlier run" % d["puzzle_id"] if d.get("puzzle_id") else "refusing to post: an earlier run failed after uploading image %s%s: %s; check LMD before posting again" % (d.get("image_id"), ", Create clicked" if d.get("submitted") else "", d.get("failed")))' && node.exe "$(wslpath -w ~/.agents/skills/create-lmd-page/lmd_driver.mjs)" --endpoint http://127.0.0.1:9334 --png "$(wslpath -w board.png)" --template "$(wslpath -w page.html)" --values "$(wslpath -w values.json)" > driver.json
   ```

   A non-zero exit is a failure. A failure after the upload still leaves a record in
   `driver.json` (the image id, and whether "Create" was clicked), so the guard refuses a
   rerun and names what already reached LMD; report it so Chris checks LMD first.
7. **Check the driver's output.** Exit 0 is not enough: `driver.json` must carry a
   non-empty `puzzle_id`, `puzzle_url` and `html`. This prints the puzzle id, or exits
   non-zero naming what is missing, which is a failure:

   ```
   cd ~/lmd-pages/work/<slug> && python3 -c 'import json,sys; t=open("driver.json").read(); d=json.loads(t) if t.strip() else {}; miss=[k for k in ("puzzle_id","puzzle_url","html") if not d.get(k)]; sys.exit("driver.json lacks " + ", ".join(miss)) if miss else print(d["puzzle_id"])'
   ```
8. **Write the page file.** Write `html` from `driver.json` to `~/lmd-pages/<slug>.html`
   and load it onto the clipboard: `clip.exe < FILE` (WSL). State the file path.
9. **Archive** (§ Archive), with the puzzle id from `driver.json`.
10. **Hand-off.** Give Chris `puzzle_url` from `driver.json`, the puzzle page link, bare on
   its own line. Say the puzzle is saved inactive; he reviews the page and clicks
   "Aktivieren" himself.

**Never have the user copy the HTML out of the terminal.** Drag-selecting long soft-wrapped
lines in the TUI silently drops chunks mid-line. **Never print the HTML to the terminal at
all** — not even in a code block for review. The page file and the clipboard copy are for
reference; the post itself carries the page.

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
- Use `%`/`px` units like the site does, not `rem` (site font-size is 90%, so rem values don't line up).
- `.rp_html IMG` already gets `max-width: 100%` from site CSS.
- The whole post sits in a thin frame: `background: #fafaff; border: 1px solid #ddf; border-radius: 8px; padding: 26px 30px` on the `<section>` (both layouts). Same `#ddf`/`5px`-family hairline as the Rules card; the `#fafaff` fill is a barely-there lavender tint, deliberately lighter than the `#eef` card so the card still reads as the darker inner panel. Frame widths: 820px two-column, 840px one-column (a wide single column filled by a large centered image up top and a wide rules card below — see the gutter gotcha above for why the card can be wide).

**LMD embeds pasted HTML verbatim — there is no sanitizer.** Verified by extracting a live puzzle's source (search the page source for `HTML-Code des Raetsels: Anfang`; the raw HTML follows). Divs, inline styles, `<hr>`, headings all pass through untouched. If the rendered page loses tags or text, the paste was corrupted (see Output section) — do not redesign the HTML around it. LMD's own docs recommend `<div style="clear:both;text-align:center">` as the image wrapper.

The image is referenced with LMD's custom syntax `<img:XXXXXX>` where XXXXXX is the uploaded file's id, which the driver fills in for `{{IMAGE_ID}}` — beware stray spaces inside it. Extra attributes are passed through to the rendered `<img>` tag: `width="420"` (two-column) / `width="600"` (one-column) sets the display size; `max-width: 100%` keeps it from overflowing (it shrinks to full width when the columns stack on mobile).

Layout — pick by the `layout` field (see the two variants under Template):
- **Two-column** (`"two"`, shorter rulesets): a centered italic epigraph on top, then a flex row — image left (`flex: 3`), Rules card right (`flex: 2 1 280px`, `#eef`/`#ddf` with a `#ddf` header bar). The ~3:2 split keeps short rules beside the image.
- **One-column** (`"one"`, long rulesets): epigraph, then a large centered image, then a wide full-width Rules card below — so a verbose ruleset runs across the page instead of towering as a tall side column.

`flex-wrap` stacks the columns vertically on narrow screens. **Flexbox on LMD is unverified — check a real preview; if it doesn't hold, the wrap makes it degrade to stacked blocks anyway.**

## Archive

Back the puzzle up once, with its LMD id from the driver (the user's ruling, sudokupad-art
`docs/research/2026-09-30-lmd-archive-facts.md`, rulings 13 and 18). `<slug>` is the page
file's name without `.html`; `<sudokupad-link>` is the link exactly as the page uses it,
any `?setting-...` query included; `<id>` is `puzzle_id` from `driver.json`.

```
uv run --project ~/src/sudokupad-art ~/src/sudokupad-art/lmd_archive.py archive "<sudokupad-link>" --archive ~/src/lmd-archive --slug <slug> --lmd <id>
```

That archives the puzzle and its LMD page and names the folder by the id. A non-zero exit,
or any `FAILED` line on stderr, is a failure. The puzzle is already posted, so a failed
archive does not undo it: say that too.

## Template

One shared skeleton with four values that differ by `layout` — see
`~/.agents/skills/create-lmd-page/reference/template.md` for the HTML and the
two-column/one-column delta table.
