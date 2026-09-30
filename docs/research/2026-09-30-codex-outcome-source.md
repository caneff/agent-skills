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
