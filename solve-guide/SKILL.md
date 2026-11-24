---
name: solve-guide
description: Turn one of Chris's puzzles (a SudokuPad link, or an image plus its rules text) into a short illustrated PDF solve guide.
disable-model-invocation: true
---

# Solve guide

`/solve-guide <SudokuPad link | image path> [rules text]`

sudoku-kit's command line does every proof: it imports the puzzle, checks it,
searches for steps and draws the guide. You write the words. A grid in the
guide never shows a step the command line did not prove, and the guide file
you write must cover its step record exactly (the Refusals section of
`$SUDOKU_KIT/docs/guide-file.md`), so every key idea names steps of the
record.

**A guide is a solution path.** It lives only under the work directory below
and the PDF destination, both outside every repo; it is never committed,
attached, pasted into a ticket or PR, or published (the Solution paths
section of sudoku-kit's `AGENTS.md`). `print_pdf.py` refuses a destination
inside a git work tree.

## Setup

Every command runs through `kit.sh`, which points `uv run` at the sudoku-kit
checkout `$SUDOKU_KIT` names (default `~/src/sudoku-kit`) and refuses one
without the guide library. Until sudoku-kit#127 reaches main, export
`SUDOKU_KIT` as a checkout of `origin/spec-127`. Pick a slug (the Logic
Masters id, such as `000HUJ`, else the title in kebab case) and work in its
directory:

```
export SUDOKU_KIT=~/src/sudoku-kit
mkdir -p ~/.cache/solve-guide/<slug> && cd ~/.cache/solve-guide/<slug>
```

`K=~/.agents/skills/solve-guide/kit.sh` below. Each command line call names
the puzzle input and `out` as its output directory; `out/steps.json`, the step
record, carries across calls, so every later call resumes from it. Every call
re-runs the checks and re-proves the record, so a `--time-limit` or
`--proof-limit` raised on one call is carried on every later call, the
render's included. The exit codes are `solve_guide.py`'s docstring's; the
sections below say what to do on each.

## 1. Import

- **A SudokuPad link.** Write it to `link.txt` with your file-write tool, never
  into a shell string. create-lmd-page's renderer draws SudokuPad's own
  picture of it, the original the checks compare against, and saves the
  puzzle's encoded string beside it as `original.scl.txt`. That file is the
  input: the command line reads a `.txt` file as an encoded string, never a
  link. Then run the checks without searching:

  ```
  uv run --project ~/src/sudokupad-art python ~/.agents/skills/create-lmd-page/board_png.py "$(cat link.txt)" original.png
  $K solve-guide original.scl.txt out --max-steps 0 --image original.png
  ```

  The input from here on is `original.scl.txt`. Exit 2 that names an item the
  importer does not read (a rule type it does not recognise) means you write
  the rules file yourself, as for an image: dump the puzzle JSON with
  `$K python -c 'import json, sys; from sudoku_kit import sudokupad_codec as c; json.dump(c.read_puzzle(sys.argv[1]), sys.stdout, indent=1)' original.scl.txt > puzzle.json`
  and translate it. Any other exit 2 message is the input's fault: report it
  and stop.
- **An image plus rules text.** Read the image, then write `rules.json` by
  hand in the format `$SUDOKU_KIT/src/sudoku_kit/rules_file.py`'s docstring
  defines, each clue's `rule` a key of `clue_rules.RULES` with the cell and
  value conventions that module's docstring gives. Put the rules text
  verbatim in `rules_text`. Then:

  ```
  $K solve-guide rules.json out --max-steps 0 --image <image path>
  ```

  The input from here on is `rules.json`.

A rule that no key of `clue_rules.RULES` expresses cannot be checked or
searched: stop and tell Chris which rule, so the library can gain it. A
`rules.json` you write is the input to every later call.

`--image` belongs to the import checks only: it puts the original beside the
render the checks compare. The search and the render run without it, so the
guide opens on the library's clean starting grid. Pass `--image` to them only
when Chris asks for the original beside the guide.

## 2. Checks

The command prints `unique:` and `solution fits:`.

- Exit 1: the puzzle is not unique, or the stored solution breaks a clue (it
  names which). Report it and stop: a guide needs a unique puzzle.
- Exit 5: the uniqueness check hit `--time-limit`. Offer a rerun with a higher
  `--time-limit`; nothing is searched until one gives a verdict.
- Exit 0: `out/render.html` holds the plain render beside the original.
  Screenshot it
  (`shot-scraper out/render.html -o render-check.png --silent`), open the
  image and compare the two clue by clue: every dot, line, cage and given in
  the original is in the render, and nothing else is. A difference goes back
  into the rules file you wrote, or to Chris when it is the importer's, and
  the checks run again.

**Image input stops here for Chris.** Open `out/render.html` for him in his
personal Chrome (`flow/claude/VISUAL-INSPECTION.md` § Showing me a file), say
what you compared, and end the turn asking him to approve the side-by-side.
The search starts only on his approval. A link's import is checked against
SudokuPad's own drawing, so it goes on to the search without asking.

## 3. Search

One background job on one core, so the turn ends while it runs:

```
job-run --name solve-guide-<slug> --timeout 0 -- ~/.agents/skills/solve-guide/kit.sh solve-guide <input> out
```

Launch it with `run_in_background` and end the turn; its completion wakes you.
It prints `search: <outcome> after <n> steps (<h> hard)`. Exit 0 is solved
(go to § 5 Read). Exit 3 is stuck: § 4. Exit 5 has two causes, told apart by
the message:

- `search: timeout` and `proofs hit --proof-limit`: the search found no step
  but some proof ran out of time. `out/steps.json` holds that stuck point.
  Offer Chris a rerun with a higher `--proof-limit`, and treat it as stuck
  (§ 4) until then.
- No `search:` line (a check or re-proving the record timed out): nothing was
  written. Run again with the limits the record was built under, raised if
  the message names one.

## 4. Stuck

Do § 5 to § 7 on the record as it stands: a partial guide. The library ends
the page with "The search is stuck here" over the stuck-point grid and its
candidates; a record with no steps takes an empty `entries` list, so that grid
is the whole guide. Hand Chris the PDF, say which cells are still open, and
offer the hint loop:

1. Chris gives a hint in chat ("r3c4 is 5 because of the black dot and box 2").
2. Translate it into a claim as the step record writes one, cells counted from
   0 (`{"cell": [2, 3], "digits": [5]}`, the cell's remaining digits), and the
   constraints it uses, each by its name in `rules.json` (`row 5`,
   `region 2`, a clue's `id`).
3. Run it as the search job of § 3, adding
   `--hint '<claim JSON>' --named '<name>'` (one `--named` per constraint).
   Exit 2 naming a constraint: that name is not in `rules.json`; fix it. Exit
   4: the hint was not proved; report the `witness:` line it prints (a
   filling that keeps the constraints and breaks the claim) and ask again.
   Otherwise the hint is appended as a step and the search goes on from it:
   back to § 3's outcomes.

A step whose `by` is `hint` in `out/steps.json` came from Chris; the guide
credits him for it.

## 5. Read

```
$K solve-deductions out
```

prints the step record grouped into deductions, one line each:
`D<k> (steps <numbers>): <claims>, from <constraints>.` Read every line. The
numbers are the step numbers the guide file's `first`, `last` and `explains`
use.

## 6. Write

Write `guide.json` in the format `$SUDOKU_KIT/docs/guide-file.md` defines.
Its entries cover every step once, in order, as key ideas and fill stretches.

- **A key idea is one move a solver would name.** It ends in a placed digit or
  a narrowed set, its `heading` names the move, and its explanation runs about
  three short sentences. Use `explains` to draw only the steps the move is
  about when its run also holds routine ones.
- **The break-in is flagged** (`break_in: true`): the first key idea a solver
  needs to get anywhere.
- **A "suppose" argument** ("if this cell were 4, then ... clash") gets a
  `supposition` diagram: the assumed digit, the digits it forces in order,
  and the clash cells. Setup the supposition leans on is its own key idea
  first. Check the chain before you write it: every digit it forces is among
  that cell's candidates at that point (the guide's grid for the idea, the
  candidates `solve-deductions` left there), each forced digit follows from
  the clue's rule given the digits before it, and the chain stops at the
  first clash, which really breaks the clue or house it names. A chain that
  passes through a digit a clue cannot hold beside its partner is false even
  when its conclusion is right: rewrite it, never ship it.
- **A fill stretch is one sentence** for a run of routine steps (singles,
  house completion) between key ideas. It says what the stretch achieved,
  in plain words ("the 9s are placed", "row 7 is finished"), and lists no
  removals: the stretch's collapsed step list carries the detail.
- **Name a clue as the picture draws it.** Two diagonal clues that the
  rules file holds as two ids but the picture draws as one dot at a corner
  are one dot in the words: "the black dot where r1c1, r1c2, r2c1 and r2c2
  meet", never "the black dots r1c1-r2c2 and r1c2-r2c1".
- **A clue whose digits are forced is a key idea.** When a dot, cage or
  line can hold only one pair or set (a two-cell cage of 3 holds 1 and 2), say
  so in the key idea whose steps depend on it, with the counting that proves
  it. The record rarely states such a fact, because the search proves the
  same steps cell by cell, so look for it in the clues themselves: for each
  clue, list the digit sets its rule allows on its cells and ask whether the
  houses it sits in cut them down to one.
- **Words ahead of the record go in `early_removals`.** When a key idea's
  words rule out a digit the record has not removed by the end of that
  idea's steps, list it in the entry's `early_removals`
  (`{"cell": "r7c8", "digits": [9]}`), so its grid strikes the digit and
  every later grid starts without it. Write no label for it. Exit 2 naming
  a digit already gone means the record removed it first: drop the entry.
  Exit 2 naming the cell's solution digit means the words are wrong: fix
  them.
- Every claim the words make is a step of the record, or true reasoning
  from the puzzle's clues that proves one; a claim no step makes is not
  written.

## 7. Render

```
$K solve-guide <input> out --max-steps 0 --guide guide.json
python3 ~/.agents/skills/solve-guide/print_pdf.py out/guide.html <destination>
```

`--max-steps 0` draws the record as it stands: the render never searches, so
a stuck record keeps its stuck point. It exits 0 when it drew the page,
whether the record is solved or stuck. Exit 2 names what the guide file gets
wrong; fix it and run again. Exit 5 is § 3's second cause.

The destination is the path Chris names, else
`~/.cache/solve-guide/<slug>/guide.pdf`; `print_pdf.py` refuses a path inside
a git work tree, so a named path inside a repo goes back to him. Give each
round a fresh file name. Look at every key idea before handing it over: the
PDF prints `out/guide.html`, so screenshot that
(`shot-scraper out/guide.html -o guide-check.png --silent`) and open the image
(`flow/claude/VISUAL-INSPECTION.md` § Judging visual work). Then open the PDF
for Chris with `wslview <destination>` and say which key ideas it has.
