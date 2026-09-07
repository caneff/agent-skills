---
name: sm-link
description: Inspect and edit SudokuMaker puzzle links (sudokumaker.app) — report a link's size, givens, ring state, entered cells, constraints and verdict, or decode a link to JSON, edit it, and encode it back. Use when asked to decode, inspect, check, edit, or rebuild a SudokuMaker link, or to check whether a link is safe to share.
---

# SudokuMaker links

Two scripts in the **gridfind** checkout do this work. Run them from there.
Never write a fresh decoder — a hand-rolled lzstring round trip is how the same
eight scratch scripts get written again.

SudokuMaker only. SudokuPad links (`scl` prefix, a different app) are a
different format; `sudokupad-art/codec.py` handles those.

## Inspect a link

```
uv run --directory ~/src/gridfind python scripts/inspect_link.py '<link>' ['<link>' ...]
```

Takes links as arguments or on stdin, one per line. A batch costs one startup,
so pass them all at once. One line per link:

```
11x11 · 121 cells · 37 givens · ring: 27/40 · entered: 0 · types {0,1,301,1000,2000} · active: 301x2 · verdict: found
```

- **ring** — how much of the outer ring is filled. Edge-clue puzzles (Numbered
  Rooms, Skyscraper) keep their outside clues there, so a full ring means every
  outside clue is spelled out. Reported, not judged.
- **entered** — non-given cells holding a value or a pencil mark. **Anything
  above 0 means a shared link opens with work already done**, unless the ring
  holds the clues on purpose.
- **verdict** — gridfind's own solve result, not a share check.

## Edit a link

```
uv run --directory ~/src/gridfind python scripts/link_file.py decode '<link>' board.json
uv run --directory ~/src/gridfind python scripts/link_file.py encode board.json link.txt
```

`decode` also accepts a file holding a link. Either path may be `-` for stdin
or stdout.

The round trip preserves the **document**, not the link text: a link the app
wrote and a link written here can compress differently and still open the same
puzzle. Compare decoded documents, never link strings.

## Write the link to a file

When asked for a link, write it to a file and give the path. A link is hundreds
of characters; pasting one into a reply is unreadable and gets truncated.

## Before sharing a link

Check `entered: 0` and a ring that is not full. In
**sudokumaker-custom-constraints**, `just check` gates both across every shipped
`PUZZLE_LINK*.txt`, and `docs/share-checklist.md` carries the criteria a gate
cannot test. A non-given cell must never hold a solution digit or a hidden
clue — that ships a board with the answer typed in. Do not fill the whole
ring either; most outside-clue cells stay blank. Verify with a decode that
non-given cells are `{}` and the ring is sparse before calling a link
share-ready.

Two exceptions:

- Pencilmarks the owner asks for by name ("add the pencilmarks too") are
  candidates, not values, and are wanted.
- A ring carved to CP-SAT minimality is "mostly blank" by definition (owner
  ruling, sudokumaker-custom-constraints #286) — do not re-derive or thin it.

## Where the app and its wire format live

SudokuMaker lives at sudokumaker.app — sudokumaker.com is a parked domain. For
wire-format questions, read the app's `main-*.js` bundle (live fetch, or the
HAR under `examples/_shared` in **sudokumaker-custom-constraints**), and check
**gridfind**'s `docs/research/` for the recorded method before re-deriving it.

## Stripping a board for timing

`examples/_shared/probe_link.py` in **sudokumaker-custom-constraints** empties a
board so the app's solver actually searches:

```
uv run --with lzstring examples/_shared/probe_link.py empty|strip <src> <out>
```

`empty` clears inner non-given cells and keeps the ring (edge clues live there);
`strip` clears every non-given cell. Timing a board with entered values is not a
timing — the app reports a verdict "based on already entered values" instead of
solving.

## Swapping constraint code

Each example's own `build_link.py` does this, using
`examples/_shared/link_swap.py`. Edit the builder and re-run it; there is no
generic swap command.
