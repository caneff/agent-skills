# LMD image upload and puzzle submit forms

**Both forms sit behind login; their field names are unverified.** The public
help page gives the field order, labels and solution-code rules. The next step is
to dump `document.forms` on both pages from a logged-in Chrome.

Gathered 2026-11-06 for the create-lmd-page automation grill (drive the stream
Chrome, upload the screenshot, fill the submit form). Fetched logged out with
curl and WebFetch. No LMD form facts existed locally: sudokupad-art
`docs/research/2026-09-30-lmd-archive-facts.md` covers read-only scraping of
puzzle pages only.

## Image upload

- Page: https://logic-masters.de/Dateien/ (the portal's "Eigene" menu links to it
  as "Dateien hochladen"). Logged out it says: "Um Dateien hochladen zu können
  müssen Sie eingeloggt sein und die benötigten Rechte besitzen." The words "die
  benötigten Rechte" may mean that upload needs a permission beyond a login.
  Unverified.
- From https://logic-masters.de/Raetselportal/Hilfe/einstellen.php:
  - A successful upload yields a six-digit id, used as `<img:xxxxxx>`. A space
    inside the tag breaks it.
  - Accepted formats: PNG, JPEG, GIF, BMP, TIFF, XCF, PS, EPS. A PDF uploads but
    cannot be used in the portal.
  - The upload offers a choice of "geheim" or "öffentlich".
- Unverified: the file input's name, the submit button, and where the id appears
  after upload.

## Puzzle submit

- Page: https://logic-masters.de/Raetselportal/Eigene/einstellen.php. Neighbouring
  pages: `Eigene/bearbeiten.php`, `kommentare.php`, `loeschen.php`,
  `statistik.php`.
- Field order and labels, from the help page:
  1. Name (the title).
  2. Rätsel (HTML).
  3. Beschreibung des Lösungscodes (HTML is allowed but the help advises
     against it).
  4. Lösungscode.
  5. An optional English copy of the puzzle and the code description, shown
     behind the flag.
  6. Schwierigkeit (difficulty).
  7. An optional fixed activation time: a date and time plus a "Ja" choice.
  8. Eigenschaften (tags). Tag ids appear as `tag_id` in
     `Suche/erweitert.php?tag_id=N`, for example Sudoku 1001 and Killer
     (Variante) 9201.
- The submit button reads "Rätsel einstellen". The help describes no preview
  step.
- **Submitting does not publish.** The puzzle is saved inactive. The author
  then opens `Raetsel/zeigen.php?id=…` and clicks "Aktivieren" in the
  right-hand box. A puzzle can be deactivated and edited later.
- Posting needs a login and several profile fields filled in. The help
  recommends no more than 7 puzzles a week.
- Unverified: the real field names and which fields are required.

## Solution code

- Allowed characters: letters without umlauts, digits, and
  `! $ % & / ( ) = \ + - * # ~ < > |`.
- Letters are uppercased automatically. Other characters are stripped silently,
  from the setter's code and from the solver's input alike.

## Login form (seen on /Dateien/)

It POSTs to `?` with `name`, `pwd`, `hiddenaction=login`, an optional `dauer`
checkbox, and a submit named `login` with the value `Anmelden`.
