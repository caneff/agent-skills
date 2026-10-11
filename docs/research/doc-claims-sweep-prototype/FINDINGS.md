# doc-claims-sweep prototype: findings (#604)

Throwaway. Run 2026-10-11 against twitch-rules-scroller at 77544f5.

Question: what does "verify a claim about code" mean as a procedure, and how
much of it is a mechanical lookup?

Procedure tried: every inline backticked token in a doc is a claim that the
name exists; look it up in the tracked non-Markdown tree; absent means FALSE
candidate. Lines relating two tokens with a verb, and counts, go to a reader.

## Core docs (README, AGENTS, GLOSSARY, CODING_STANDARDS): `run-core-docs.txt`

- 519 tokens, 31 mechanical FALSE candidates, 23 relation lines, 3 counts.
- 0 of the 31 candidates is a false claim. 8 were checked against the tree
  and are true: the doc writes the name in another form than the code
  (`OBS_ITEM=Puzzle` for `OBS_ITEM`, `--only "server restart"`, `STICKER_*`,
  `{collectionReady, reason}`), or the token is a dated observation
  (`sync v89`, code now `sync v101`, sentence dated 2026-09-20). The other 23
  were classed by reading the token only: URLs, Windows paths, shell
  commands, names from other tools, and one backtick-pairing artifact.
- 6 of the 23 relation lines were checked by hand (AGENTS.md:17, 73, 81,
  193; GLOSSARY.md:14, 227). All 6 hold. 17 were not checked.
- The "tests only" list is wrong: the heuristic counted `e2e.mjs` and
  `e2e/*.mjs`, the harness, as tests.

## docs/obs-layout.md: `run-obs-layout.txt`

1999 tokens, 158 candidates. Not judged. The doc's stated root is a Windows
folder outside the repo, so most paths are absent by design.

## What it shows

1. Presence of a name is the wrong test. It produced 31 flags and no finding
   on the repo where the stale claims were reported.
2. Absence often confirms the sentence ("#548 renamed `OBS_MONITOR` to ...",
   "#124 retired `PUZZLE_CROP`"). The verdict depends on what the sentence
   says about the name, which a lookup does not read.
3. The claims the ticket names (callers, imports, counts, restart behaviour)
   are sentences. A line-based extractor cuts them: AGENTS.md:73 names two
   files, and the thing they import is on line 74.
4. What the mechanical pass did deliver: a bounded reading list. 23 relation
   lines and 3 counts out of about 1,000 doc lines, each with file:line.
