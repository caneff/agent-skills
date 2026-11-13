# LMD image upload and puzzle submit forms

**Both forms were read logged in on 2026-11-06 (#1660).** The upload is a plain
multipart form. The new image's id is listed first on the upload page,
newest-first, under the name given at upload. The submit form has one required
question that the help page does not mention: whether the puzzle is a Sudoku. Its
tagging has two parts: 62 fixed label checkboxes and a free-tag text field.

Sources:
- The first pass (logged out) read the public help page,
  https://logic-masters.de/Raetselportal/Hilfe/einstellen.php.
- The second pass (#1660) read both forms in the stream browser over CDP on port
  9334. It opened one tab, read the pages, submitted nothing, and closed the tab.
  OBS was not running.
- The capture script is snapshotted at `2026-11-06-lmd-form-capture.mjs`
  (beside this note). Rerun it with Windows `node.exe <script> <out-dir>` while
  the stream browser is up with its port.
- Test fixtures: `create-lmd-page/fixtures/lmd-upload.html` and
  `create-lmd-page/fixtures/lmd-submit.html`. This repo is public, so the upload
  fixture's real file list was replaced with two made-up entries (`0099AB`
  `fixture-newer`, `0099AA` `fixture-older`) in the same markup. The submit
  fixture is the page as served.

The account in use is `ChinStrap`, and the site UI language is English.

## Image upload

- The page is https://logic-masters.de/Dateien/. The form POSTs to
  `/Dateien/index.php` as `multipart/form-data`.
- Fields:

  | Field | Type | Use |
  | --- | --- | --- |
  | `datei` | file | The image. |
  | `MAX_FILE_SIZE` | hidden | `4194304` (4 MiB). |
  | `name` | text | A label shown in the file list. Use the page slug. |
  | `anmerkung` | textarea | "Anmerkung". The page asks you to state that you made the file yourself, or that its maker gave you permission. Chris's ruling: "author created". |
  | `offen` | checkbox | "Die Datei darf auch von Anderen genutzt werden" (others may use the file). Unchecked by default. Chris's ruling: leave it unchecked. |
  | `dateiupload` | submit | Value "Hochladen". |

- A login is enough to upload. The "die benötigten Rechte" wording on the
  logged-out page did not block this account.
- The image id appears on the upload page. The page lists uploaded files
  newest first in `table.upload_list_gross`. Each row has
  `span.upload_list_gross_name` (the `name`), `span.upload_list_gross_data`
  (format, pixel size, KB) and `span.upload_list_gross_id` ("ID: 0015HL"). The
  row also links to `/Dateien/index.php?id=<id>`. Right after an upload,
  `/Dateien/` shows the file list with the new file as its first row and **no
  upload form** (seen 2026-11-06 in #1659's closing check: "check-in … PNG
  (800 x 800, 124KB) ID: 001626" on top, `input[name=datei]` absent). So a
  check after the upload looks for the list, not the form. The driver reads
  the newest row whose name matches the one it sent.
- The submit page (`Eigene/einstellen.php`) embeds a second copy of this upload
  form, with the same fields, posting to `/Raetselportal/Eigene/einstellen.php`.
- Chris's past uploads are mostly 800px wide. Heights run from 722 to 977, a
  few are 832×832 or 900×900, and file sizes run from 26 to 178 KB. The
  ruling for this skill is "fits inside 800×800".

### Image size limits (searched 2026-11-09)

**LMD publishes no pixel limit.** The only hard number is the form's
`MAX_FILE_SIZE` of 4194304 bytes (4 MiB). Browsers do not enforce that field;
PHP checks it on the server.

What was searched, and what each source says:
- LMD's upload help, https://logic-masters.de/Raetselportal/Hilfe/einstellen.php
  (German and English): it lists the formats and the six-character id. It
  states no pixel or byte limit.
- LMD's terms of use, https://logic-masters.de/nutzungsbedingungen.php: they
  list the formats. They state no size limit.
- The forum thread "Bilder hochladen : Datei zu groß" (2014-08,
  https://forum.logic-masters.de/archive/index.php?thread-1259.html): uploads
  of an 11 KB file and of a 436×436, 9 KB PNG were refused with "Bild zu
  groß", while a 653×883, 25 KB PNG went through. One poster called it a bug.
  The thread ends without a stated limit or a fix.
- Exa web search over logic-masters.de and its forum for image size, pixel and
  "zu groß" limits: nothing beyond the above.

Upper bounds seen to work on Chris's account: 900×900, 800×977, 832×852, and
230 KB (`000ZKY`, 800×808). Untested: anything wider or taller than 900 px,
or larger than 230 KB. Only an upload test can settle those.

## Puzzle submit

- The page is https://logic-masters.de/Raetselportal/Eigene/einstellen.php.
  The form POSTs to `einstellen.php` as `application/x-www-form-urlencoded`.
- Fields, in page order:

  | Field | Type | Label on the page | Notes |
  | --- | --- | --- | --- |
  | `Sudoku_JaNein` | radio `Ja` / `Nein`, required | "First things first: Ist your puzzle in essence a Sudoku (this includes variants)?" | Not in the help page. Neither choice is selected by default. |
  | `name` | text, required | Name | The title. |
  | `htmlcode` | textarea | Puzzle (German) | Left empty, by ruling. |
  | `codedescr` | textarea | Solution code description (German) | Left empty, by ruling. |
  | `htmlcode_en` | textarea | Puzzle (English) | The page HTML. |
  | `codedescr_en` | textarea | Solution code description (English) | |
  | `code` | text | Solution code | Hint on the page: "Allowed characters: Letters, numbers and ()<>~+-*= /\|!#$%&". |
  | `dif` | select | Difficulty | `1` very easy, `2` easy, `3` average (default), `4` hard, `5` very hard. |
  | `frei` | select | "Do you want to activate this puzzle at a certain point in time?" | `ja` ("Yes, on:"), `nein` ("No", default). Leave it at `nein`. |
  | `day` `month` `year` `hour` `min` `sec` | text | Date / Time | Used only with `frei=ja`. Leave them empty. |
  | `label_<n>` | checkbox, value `1` | Labels | The 62 fixed labels listed below. |
  | `freetags` | text, id `freetags` | "Additional tags" | Free tags from a list of 261 suggestions. The page autocompletes from the list in the page script (`freeRawTags`). |
  | `einstellen` | submit | Value "Create" | |

- The submit page's footnote says: "In order to publish the puzzle
  automatically you have to activate it on the puzzle page!" This agrees with
  the help page: "Create" saves the puzzle inactive.
- "Create" does not redirect. Seen 2026-11-06 in #1659's closing check
  (Check-In, puzzle 000VX4): the answer stays on
  `Raetselportal/Eigene/einstellen.php`. Its text begins "The puzzle has been
  saved. Edit Puzzle 000VX4 To the puzzle page", and the submit form shows
  again below, emptied. The id is in the "To the puzzle page" link
  (`Raetsel/zeigen.php?id=000VX4`) and in the "Edit Puzzle" text. The site
  menu also links `Raetsel/zeigen.php`, with no id.
- Editing a saved puzzle, seen 2026-11-06 fixing Check-In by hand: the edit
  page is `Raetselportal/Eigene/einstellen.php?id=<id>` (`bearbeiten.php` is
  only the list). It is the same form, pre-filled, without `Sudoku_JaNein`, and
  its one submit is `einstellen=Change`. It answers "The puzzle has been
  changed. Edit Puzzle <id> To the puzzle page".
- After `Sudoku_JaNein=Ja`, LMD added the free tag "Sudoku" itself; the post
  sent `freetags` empty.
- On the edit page the date fields come back pre-filled with the save time,
  while `frei` stays `nein`.
- A second upload the same day worked on `/Dateien/` (image 001627), and a
  reload read its id. Swapping `<img:001626>` for `<img:001627>` through the
  edit page changed the image the live page serves.
- The form's character hint and the help page list the same symbols. The
  form's hint also shows a space.

### Edit form (#1720)

**Source and gap.** Everything here is from the 2026-11-06 hand edit above
(Check-In, 000VX4) and 2026-11-13's hand edit (Hot Property, 000W0N: a
plain-version play link added to a live page). #1720's worker could not re-read
the live form over CDP: a `chrome-stream.exe` was running with no control port,
which only Chris closes (`create-lmd-page/SKILL.md` step 4). So no edit-form
fixture is a saved copy of the live page; the driver test derives its fake edit
page from the submit fixture by the differences below. Rerun
`2026-11-06-lmd-form-capture.mjs` on `?id=<id>` to settle the open questions.

- **URL:** `https://logic-masters.de/Raetselportal/Eigene/einstellen.php?id=<id>`.
  The form POSTs to `einstellen.php` (the `id` is in the query or a hidden
  field the driver does not need to know: it submits the form as the page
  serves it).
- **Fields:** the submit form's, minus `Sudoku_JaNein`, pre-filled with the
  puzzle's current values: `name`, `htmlcode`, `codedescr`, `htmlcode_en`,
  `codedescr_en`, `code`, `dif`, `frei`, `day` `month` `year` `hour` `min`
  `sec`, `label_<n>`, `freetags`. The page HTML is `htmlcode_en`.
- **Submit:** `einstellen` with value `Change` (the create form's is `Create`).
- **Answer:** stays on the edit page, "The puzzle has been changed. Edit Puzzle
  <id> To the puzzle page", the "To the puzzle page" link being
  `Raetsel/zeigen.php?id=<id>`.
- **Activation:** the `frei` select and the date fields are part of this form
  and come back pre-filled (`frei=nein`, the date fields the save time). The
  driver leaves all of them as served, so an edit never sets, clears or
  schedules activation. The "Aktivieren" button is on the puzzle page, which an
  edit never visits.
- **Open:** whether the edit page of an *active* puzzle serves `frei` and the
  date fields differently, or refuses a change to an active puzzle. Chris's
  2026-11-13 Hot Property edit was of a live page and worked by hand, so it
  does not refuse.

### Labels (`label_<n>`)

1 Standard puzzle, 2 Puzzle combination, 3 Puzzle variant, 4 Variant combination,
5 New, 11 German knowledge, 12 English knowledge, 13 Math knowledge, 14 Special
knowledge, 21 Beginners, 22 Solving hints, 23 Computer generated, 24 Computer
assistance, 25 Online solving tool, 26 Large, 27 Small, 31 Optimizer, 32 Meta
puzzle, 33 Mystery puzzle, 34 Cipher, 35 Sequence, 36 Instructionless, 41
Multi-grid puzzle, 42 Team puzzle, 43 Permaculture, 44 Geisterbahn, 45
Matchmaker, 51 Just one cell, 101 Hexagonal, 102 Triangular, 103 Irregular grid,
111 Wraparound, 112 Three-dimensional, 121 Filling puzzle, 122 Arithmetic
puzzle, 123 Path puzzle, 124 Placement puzzle, 125 Shading puzzle, 126
Dissection puzzle, 127 Maze, 128 Word puzzle, 129 Movement puzzle, 131 Latin
Square, 132 Euler Square, 141 Knapp daneben, 142 Coded puzzle, 143 Even/Odd
coded puzzle, 151 Dominoes, 152 Trominoes, 153 Tetrominoes, 154 Pentominoes, 155
Hexominoes, 156 Polyominoes, 157 SLICY, 158 Pentacubes, 161 Chess, 162 Playing
cards, 201 Neandertal, 202 Alien, 211 Multiple solutions, 221 2358, 222 Portal
Special.

### Free tags

The 261 suggestions sit in the submit fixture's `freeRawTags` array. Examples:
"Sudoku", "Killer (Variant)", "Little Killer (Variant)", "Arrows (Variant)",
"Region Sum Lines (Variant)", "Battenburg (Variant)". Whether a tag outside the
list is accepted is not known.

## Solution code (help page)

- Letters are uppercased automatically. Characters outside the allowed set are
  stripped silently, from the setter's code and from the solver's input alike.

## Other facts from the help page

- After "Create", the author opens `Raetsel/zeigen.php?id=…` and clicks
  "Aktivieren" in the right-hand box. A puzzle can be deactivated and edited
  later.
- The help recommends no more than 7 puzzles a week.
- The login form POSTs to `?` with `name`, `pwd`, `hiddenaction=login`, an
  optional `dauer` checkbox, and a submit named `login` with the value
  `Anmelden`. The skill never logs in itself, because the stream browser stays
  logged in.
