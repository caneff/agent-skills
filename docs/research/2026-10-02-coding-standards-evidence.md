# Coding-standards evidence, PRs #1196–#1321

2026-10-02. Evidence sweep behind a `/extract-coding-standards 100` run on
this repo. The skill caps the range at 50, so it covers the last 50 merged
PRs: #1196 (merged 2026-09-27) to #1321 (merged 2026-10-02). This note holds
the evidence; the proposals made from it were put to Chris in chat, and no
`CODING_STANDARDS.md` existed at the repo root when the sweep ran.

## How the evidence was read

- These PRs carry no GitHub review comments (PR #1317: 0 comments, 0
  reviews). The review record is each PR body's `## Decisions made` section
  and the cached reviewer files under `~/.cache/agent-reviews/skills/`,
  keyed by the ticket the PR closes.
- A finding counts as **accepted** only when its disposition is `fixed` with
  a sha. `disputed` is a rejection; `leftover` and `filed` are deferrals.
- One `sonnet` agent did the sweep. All 50 PRs had a Decisions made section
  and cache files for their ticket.
- Not done: the agent grouped findings by reviewer title and disposition
  line, and read the full reviewer prose for only a few. It did not re-read
  each fix sha's diff. The controller spot-checked 23 cited findings against
  the saved records; 22 matched, and #1277 r1-S3's title was missing from
  the join (its sha, ef8237f, matched).
- Raw data: `.scratch/extract-standards-2026-10-02/` in the primary checkout
  (`pr-<n>.json` per PR, `joined.txt`, `cp-fixed.txt`, `measure.py`,
  `join.py`). That directory is git-ignored and is the only copy.

## Conventions with accepted corrections in two or more PRs

Counts are separate PRs with at least one accepted correction.

| Convention | Accepted | Disputed | Deferred | Adherence in the tree | Written home today |
|---|---|---|---|---|---|
| Delete or shrink what has no reader (unused params, imports, dead branches, parallel structures) | 27 PRs | 9 findings | 16 findings | Unused module-level imports: 496/497 conform (AST pass, tracked `.py`). Nothing else counted. | The over-engineering lens in `multi-axis-code-review/SKILL.md` |
| No stale claim: a doc, docstring, comment or message contradicting what the PR changed | 25 PRs | 0 | 6 findings | Not countable | Blocking kind (b), `implement/SKILL.md` § Review |
| Reuse the existing helper, constant or fixture instead of a second copy | 18 PRs | 8 findings | 20 findings | Sidecar JSONL readers 2/4; `GIT_*` env scrub 4/11; five separate non-test `git()` wrappers | Blocking kind (a), `implement/SKILL.md` § Review |
| Names say what the thing is or does | 10 PRs | 0 | 5 findings | Not countable | Mysterious Name, the smell baseline in `multi-axis-code-review/SKILL.md` |
| Messages state the true cause and offer only actions that exist | 8 PRs | 0 | 0 | Not countable | None. Some instances are defect class 1 or 2. |
| Wrap edited prose and comments to the surrounding width | 6 PRs | 2 findings | 4 findings | Proxy, lines at or under 100 columns: `.py` 99.1%, `.sh` 94.9%, `.rs` 94.2%, `.md` 93.3% | None |
| State a rule once; other places point to it | 5 PRs | 6 findings | 1 finding | Not countable | None |
| Delete an assertion already witnessed elsewhere or unable to fail | 5 PRs | 4 findings | 0 | Not countable | The over-engineering lens |
| Section cross-reference in the checked `<path> § <Heading>` form | 3 PRs | 0 | 0 | Checker not run in the sweep | `docs/agents/section-references.md`; `tests/check-section-references.py` |
| Tests do not read or write ambient or live state | 3 PRs | 0 | 0 | Sampled: 22 of 37 test files naming a HOME-like path redirect it; 7 of the other 15 were read and none touches the real one | None |
| Positional or tuple indexing becomes named unpacking or a keyed record | 3 PRs | 0 | 5 findings | Not counted | None |
| Place new prose inside the existing structure | 3 PRs | 0 | 0 | Not countable | None |
| Parse git path output with `-z` or `core.quotePath=false` | 2 PRs | 0 | 0 | 5/9 sites | None |

The three documented defect classes (`docs/agents/defect-classes.md`) also
recurred: class 1 in 19 PRs, class 2 in 10, class 3 titled in 2.

## The accepted corrections behind the conventions with no written home

**Messages state the true cause.** #1197 S1 8fc52cb ("report_blockers
prints 'blockers: none' when git worktree list fails"); #1203 SP2 06ef616;
#1241 S1 69533f0; #1246 S6 c044677 ("Reuse refusal asserts round reuse;
cannot tell it from an appended ruling"); #1255 S1 d4be687 ("Gate relays
refusal text advertising --allow-stale, which neither check nor the gate
accepts") and S2 48105e4 ("reports 'no dispositions sidecar' without having
looked"); #1291 N2 72be1b8; #1296 S1 f6b440d ("Not-owned push message still
says 'or ownership couldn't be verified — gh down?'"); #1299 S6 4ba600e
("refusal reason says 'no error line in the .out' when no .out exists").

**Tests and ambient state.** #1198 C1 a34e914 ("Test runs real --restore
and overwrites live Windows VS Code settings on every gate run"); #1294 C5
f23d80f ("Ceiling test inherits ambient CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS
and goes hollow when the shell exports it"); #1298 C7 38d9311 ("earlier
recipe runs keep real HOME and invoke the installed ~/.agents/skills
review_ledger.py").

**Wrap width.** Accepted: #1240 S1 f78250e, #1263 S5 b4880c5, #1277 r1-S5
3ef8aa2, #1283 S5 dda4e99, #1289 S2 2bee14c, #1290 S3 233f2cd. Disputed as
cosmetic: #1196 S2, #1253 S8. Leftover: #1246 S4, #1263 S6, #1272 S4, #1285
P1. Long lines today: `multi-axis-code-review/SKILL.md:135` (137 columns),
`:138` (322), `:154` (462); `flow/lane/src/atomic.rs:19` (144).

**State a rule once.** Accepted: #1202 S1 b23864a, #1203 S2 06ef616 ("Split
grammar stated in full three times"), #1246 S3 8f758ec ("Round ids rule
restated in four places despite 'one home' claim"), #1277 r1-S3 ef8237f,
#1289 S3 2bee14c ("Twin sweep-search prose diverges"). Disputed: #1196 S1
(a pasted brief must hold its own copy), #1199 S3, #1289 OE1 (twin tests pin
each clause), #1290 S4, #1245 S6, #1237 OE2. Leftover: #1321 S5.

**git `-z`.** #1250 C2 83e8efd ("workspace_diff returns C-quoted non-ASCII
paths that never intersect raw closure paths"); #1263 C4 b4880c5. Sites not
using it: `multi-axis-code-review/check_adjacent.py:70` and `:90`,
`all-audits/driver.py:149`, `landed/generate.py:180`. Two of those parse
`--numstat` and may not need it.

**Positional indexing.** #1202 S4 b23864a, #1246 S7 ca185f6, #1287 S2
a0d7e43.

**Prose placement.** #1203 S1 06ef616, #1281 S1 20cc107, #1295 S5 afd0d5d.

## Single sightings

- #1203 S4 129ac6d: f-string with no placeholder. 889/891 f-strings conform.
- #1298 S2 a84c625: `^...$` with `.match` accepts a trailing newline; use
  `fullmatch`.
- #1263 S2 b4880c5: a hand-kept `CASES` list lets an unlisted `test_` never
  run.
- #1253 S5 e8e84c9: a test passes `--repo` twice, relying on argparse
  last-wins.
- #1250 S4 064ecdb: a test helper took an in-band fake CLI flag.

## What a mechanical gate already enforces

- `§` section references: `tests/check-section-references.py`.
- The adjacent-fix size limit: `multi-axis-code-review/check_adjacent.py`.
- The verification pass and the dispositions sidecar:
  `implement/verification-check.sh`, `implement/pre-report-gate.sh`.
- A suite that exits 0 while printing a failure word: `tests/all.sh`.

No tracked linter or formatter config exists at the repo root, and no suite
checks line width, naming, unused imports, stale docs or duplication.

## Ruling

2026-10-02, Chris: write four rules into a new `CODING_STANDARDS.md` at the
repo root — honest messages and tests-and-live-state as rules, wrap width
and one-home-per-rule as contested. Not written: git `-z`, positional
indexing and prose placement (thin or uncountable evidence), and the stale
claim and second copy conventions, which stay stated once as the blocking
kinds in `implement/SKILL.md`.
