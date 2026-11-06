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
  row also links to `/Dateien/index.php?id=<id>`. What the page shows right
  after the POST is not yet seen. The driver should read the newest row whose
  name matches the one it sent.
- The submit page (`Eigene/einstellen.php`) embeds a second copy of this upload
  form, with the same fields, posting to `/Raetselportal/Eigene/einstellen.php`.
- Chris's past uploads are mostly 800px wide. Heights run from 722 to 977, a
  few are 832×832 or 900×900, and file sizes run from 26 to 178 KB. The
  ruling for this skill is "fits inside 800×800".

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
- Where the new puzzle id appears after "Create" is not yet seen. It shows on
  the first real post (#1662 closing check).
- The form's character hint and the help page list the same symbols. The
  form's hint also shows a space.

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
