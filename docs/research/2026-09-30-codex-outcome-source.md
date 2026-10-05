# Where Codex pass outcomes are recorded (#1267)

Measured 2026-09-30 by running `review_ledger.py harvest` on the real review cache
(`~/.cache/agent-reviews/`), with an empty transcripts tree so only Codex rows were under test.

## Finding

The only place a Codex finding's outcome is recorded in a form a script can join is the
**dispositions sidecar**: a line `codex-<phase>-<label>` in `dispositions-<n>.jsonl`. By the rule in
`implement/SKILL.md` § The merge step 3 the controller writes such a line only for a `leftover`, so the
known outcomes skew to leftover (zero value) and most findings are `unknown`.

The harvest reads findings from the `.out` (`- [severity] title (file:lines)`), wall clock from the
`.json` record, and outcomes from that sidecar. The PR body is not read.

## Evidence

| Source | What it holds | Usable? |
|---|---|---|
| `codex-adversarial-<n>-<phase>.json` | status, shas, `started`, `completed` (303 records) | wall clock and refusal only |
| `codex-adversarial-<n>-<phase>.out` | findings as free text, severity as written; no id | findings |
| `codex-body-<n>*.md` | the prompt sent to Codex (ticket, comments, controller appendix) | no: input, not outcome |
| `dispositions-<n>.jsonl` | 14 distinct `codex-*` ids on 29 lines in 14 files, all repos | yes: outcomes |
| `pr-body-<n>.md` | 42 of the 84 bodies in `skills` mention Codex, as prose: "Codex gate finding 1 (high) — fixed, `bed18e8`", "codex-gate-1: fixed at …", "Codex gate H1 …" | not joined: no stable id or grammar |

Result on the real cache: 303 records give 296 Codex rows (218 gate, 70 second, 8 third). 39 are
refusals (usage limit), 257 read a diff, and 6 `early` records (retired in #1015) are listed, not harvested.
The 257 rows hold 222 findings (121 high, 101 medium). Outcomes: 195 `unknown`, 16 leftover, 6 fixed,
4 disputed, 1 filed.

## Not solved here

- The PR body's free-text Codex dispositions are not parsed, so most backfilled Codex outcomes stay
  `unknown`. `report` counts them in `unknown outcomes` and never as zero value.
- Split ids (`codex-second-1a` / `-1b`) and drifted ids (`codex-gate-1-obs-session`) do not join; they
  are listed under "Dispositions with no finding" in the review file.

## Correction, 2026-10-04 (#1406, sweep item P5)

The finding above, that a Codex outcome is joinable only for a `leftover`, held for passes run
before #1401. It no longer holds for forward gate passes:

- **The rule changed.** Since 82f5d39 (#1401, 2026-10-04) the worker writes one dispositions line
  per finding, Codex's included, as `codex-gate-<k>` for the k-th finding of the `.out`
  (`implement/SKILL.md` § Review, step 3). The harvest joins that id by number.
- **Something enforces it.** `implement/fix_check.py` (`codex_findings`) reads the gate's `.out` with
  the ledger's own parser and requires a dispositions line for every `codex-gate-<k>`, so a
  missing line fails the worker's pre-report gate instead of reading as `unknown`.
- **Split ids now join.** A finding disposed as two ids, `codex-<phase>-<label>a` and `-b`, joins
  as one: halves that agree give their outcome, one valued half gives a partial
  (`review_ledger.py` `_split_outcome`, #1406). Drifted ids such as `codex-gate-1-obs-session`
  still do not join and are still listed under "Dispositions with no finding".

What is still unknown: the share of forward Codex findings that actually carry a known outcome.
This correction does not measure it; it reads the rule and its gate, not a harvest. The
second pass is gone (ADR 0004), so the gate is the only forward Codex phase. Backfilled passes
(the 195 `unknown` above) stay unjoinable: their fixed and disputed outcomes exist only as PR-body
prose.

**Follow-up, recorded here because ADR 0005 freezes new tickets against this machinery:** after
the next burn, run `review_ledger.py harvest` and `report`, and count, over `codex-gate` rows whose
record `started` after 2026-10-04, the findings with a known outcome. Under the new rule that
should be all of them; any `unknown` there names a worker that skipped a line and a fix-check that
let it through, which is a bug that blocks the measurement and may be filed as one.
