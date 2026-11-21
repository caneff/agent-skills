# Friction log audit, 2026-11-21

Every entry in `docs/agents/friction-log.md` at f93c1ca6 (202 entries, 2026-10-04 to 2026-11-21) was checked against current code, git history and the trackers. Four read-only agents each took a quarter of the file and wrote one row per entry, with a status and the evidence for it. The rows are in `2026-11-21-friction-log-audit.jsonl` beside this note. A row's `line` is its line in the log at f93c1ca6.

## Bottom line

- **60% is history.** 122 of 202 entries describe a failure that can no longer happen as written. The log keeps them all; nothing removes or marks an entry once it is fixed.
- **36 entries are live and on no ticket.** About 20 of them are repeats of 8 problems, which is exactly what the log's own rule (ADR 0005: promote on the second occurrence) should have turned into tickets. The promotion step has no mechanism, so it did not happen.
- **What did get ticketed is stuck.** Of 32 `TICKETED` rows, the open agent-skills tickets they name are all `needs-info`: #1619 (7 entries), #1708 (9; split today into #1969), #1906, #1703, #1697, #1699, #1710, #1709, #1905. They have waited on grilling since 2026-10-31 to 2026-11-16. A few `TICKETED` rows cite a closed ticket (#1658, #1618, #1606, #1539) for a part that is done. Those rows are partly fixed.
- **6 one-offs** (box load, a mid-run skill change, a test flake) and **6 unverified**. Three of the unverified are one cluster: the frontier still read landed slices as blockers after #1469's fix, and the cause was never traced.

| Status | Entries |
|---|---|
| FIXED | 122 |
| TICKETED | 32 |
| LIVE-UNTICKETED | 36 |
| UNVERIFIED | 6 |
| ONE-OFF | 6 |

Not fixed, by repo: sudokupad-scripts 24, twitch-rules-scroller 18, agent-skills 12, sudokumaker-custom-constraints 7, sudokupad-art 6, grid-hunts 5, sudoku-kit 4, penpa-edit 4.

## Live with no ticket, grouped

Log line numbers in brackets. Repeats come first.

1. **Undeclared or uncapped parallel test runs load the box** [109, 124, 144, 150, 158]. #1808 capped only agent-skills' `tests/all.sh`. twitch-rules-scroller's `run-tests.mjs` and sudokupad-scripts' `npm test` still default to every core unless a cap is set, and "declare a job before a parallel run" is prose with no check behind it.
2. **Spec runs started with nothing to dispatch, and no wake source** [84, 205, 206, 135, 139]. drain anchors a spec parent without checking that any slice is dispatchable, including a slice blocked by another repo's issue. A run refused at its first box check has no wake source, and nothing wakes a run when a cross-repo blocker lands.
3. **The merge-rerun skip rule reads only the AGENTS.md seam section** [199, 210, 201, and 172 unverified]. sudokupad-scripts' `live/README.md` requires extra live runs (for `.github/` and for unnamed files) that the skip rule never sees. Separately, a prose-only edit to the seam section reads as "differs" and forces a rerun.
4. **Frontier treats landed slices as open blockers** [36, 40, 55, unverified]. This recurred three times after #1469's landed-blocker rule. Controllers built dispatch input by hand.
5. **fanout-brief refuses valid input** [82, 165, 187]. A finding can't be split across two workers, and its no-test check misses `python3 x_test.py`.
6. **The git guard refuses cd-led chains ending in a push** [167, 209]. #1900 accepts only the exact `cd <abs> &&` form, and line 209 recurred the day after it landed.
7. **Ledger and runfile accept unchecked input** [108 caller-supplied seconds, 125 a hand-typed sha that does not exist, 189 a binary file crashes `escapes`, 160 a fixture row in the live ledger (unverified)].
8. **Controller and dispatch resolution** [7 a `!` command clears the pane binding (unverified), 196 a controller name collides with a worker name, 63 a 502 leaves a half claim, 198 a dispatch stalls under load with the brief typed and the ticket claimed].
9. **Include closure** [31 Python imports unread, 37 the closure hold makes a flat ES-module repo near-serial, 56 the closing-ticket check ignores a Miss ruling].
10. **One-line repo config or doc gaps** [43 twitch e2e stale userscript on a spec branch, 166 grid-hunts browser check has no setup, 171 `uvx radon` unpinned and denied, 208 OBS covers the e2e Chrome again after twitch-rules-scroller#1185, 212 twitch-rules-scroller has no `**Discardable**:` line, 152 `tests/all.sh` stops at the first red, 202 PR up before CI on a box-only recording, 93 OPERATIONS.md notify-when-idle rule, 68 a docs push to main skips the seam by design].

## What this says about the log

The log works as capture: entries are specific, dated and checkable, and the agents could verify 196 of 202. It fails as a pipeline. Nothing promotes a repeat, nothing retires a fixed entry, and the tickets it does feed wait on grilling. Its cross-repo content also broke this repo's section-reference check five times (#1970).
