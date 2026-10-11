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

## Round two (2026-10-11): the #207 sentences cannot be recovered

Plan: find the four false sentences twitch-rules-scroller #207 shipped across
four review rounds, and test whether the reading list contains them. It could
not be run.

- PR #211 (the #207 fix) and PR #208 (the #135 fix) each hold one commit and
  no GitHub review comments. The rounds were amended away.
- `git fsck --unreachable` lists 288 commits. One, 5cb0fd0, is an earlier
  copy of the #211 commit; `git range-diff` against the merged 50abe76 shows
  it differs only by a rebase onto a newer main.
- No Claude transcript for that repo predates 2026-09-06. The second-brain
  digest of 2026-09-06 describes the claims and quotes none.

What the surviving record says about them, from the #207 issue body and its
2026-09-04 comment: they were code comments. "A comment claiming the editor
page was the only writer", then "two comments still asserted
`writeScrollerSettings` was a live writer". The prototype reads Markdown
only, so it would not have seen any of them.

`comment-audit/SKILL.md` has a "Stale or wrong" category. Its 2026-09-23 run
on this repo produced the stale-comment list in issue #392 (at least 25
rows read; the list was cut at 3,000 characters), fixed by PR #414.

Not established: whether stale claims in Markdown docs are a recurring class
in any repo. No instance was found; the search was the four core docs at
77544f5 by token lookup, and 6 relation lines by hand.
