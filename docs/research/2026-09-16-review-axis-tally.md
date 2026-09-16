# Review-axis tally: what standards, spec, and correctness actually earn (#854)

Summary: all three axes earn real confirmed findings — correctness at 69%,
spec at 65%, standards at 62% — and all three raise hard findings at a
90%+ confirm rate on the hard subset (spec 94%, standards 91%, correctness
85%). Correctness stands out on **hard-finding density**: 87 of its 184
findings (47%) are hard violations, vs. 22/270 (8%) for standards and
18/133 (14%) for spec. Standards is the volume axis — 270 of 587 findings
(46% of everything raised), 92% of it judgement calls, more than a quarter
of which get disputed. The Codex adversarial pass, run separately from
these three at merge time, is the clearest keep: across its 5-ticket trial
it raised 10 codex-only confirmed findings against only 3 that overlapped a
Claude axis.

*Revision note: this note went through one round of multi-axis review
(round 1) which found real arithmetic errors (mismatched totals, a
backwards hard-confirm-rate claim) and real script bugs (dead/unreachable
regex branch, an untested fallback path, a scratch-dir filter that
wouldn't actually catch `scratch-421`, a missing `gh` call the ticket asked
for). All of it is fixed below; every number in this revision was
recomputed from the underlying classification data after the fixes, not
hand-patched to look consistent. The disposition list is in the PR body.*

## Method

Two passes, kept separate because free prose can't be tallied by regex
alone:

1. **Mechanical** (`tally_review_axes.py`, tested in
   `tally_review_axes_test.py`, 19 tests): walks `~/.cache/agent-reviews`,
   parses each `review-*.md` filename into (round1|verify, axis or axes,
   issue number), folds `agent-skills`→`skills` (same repo, two checkout
   names) and `verify`/`verification` (two names for the same round)
   together, and joins round-1 reports to their verify report and merged PR
   by issue number. **The PR join calls `gh` directly** (`gh pr list
   --state merged --json number,body,title,headRefName`) and matches each
   PR to an issue by a `Closes #N`-shaped keyword in the body/title,
   falling back to the PR's `implement-<n>`/`issue-<n>` branch name when
   neither has one — which is the common case in this dataset: `gh`'s
   `closingIssuesReferences` came back empty for nearly every PR here even
   where the body literally said "Closes #N". An `--issue-to-pr <file>`
   flag replays a pre-built map offline for testing/reproducibility without
   a live `gh` call.
2. **Judgement**: reading each round-1 finding's text, its matching
   verify-pass text, and its PR body's "Decisions made" section, and
   classifying severity (hard violation / judgement call / clean-no-finding)
   and outcome (confirmed / disputed / filed-as-follow-up / unclear-no-
   disposition-found). Done by three parallel Sonnet subagent passes — one
   per repo/batch — each independently briefed with the same taxonomy and
   file layout, plus one issue (`twitch-rules-scroller#274`) reclassified
   by hand after it went from open to merged partway through this ticket
   (see below). I spot-checked each batch's output against the source
   reports rather than re-reading all 587 records myself; spot checks were
   consistent with the source text. Batch-to-batch calibration drift on
   borderline judgement-call severity is the main residual risk in this
   step, not a claimed exact count.

Run it yourself: `python3 docs/research/tally_review_axes.py` prints the
full round-1/verify/PR join as JSON (live `gh` lookup, ~10s). The
classification JSON this note's tables are computed from is not committed
(it's a one-off reading-pass artifact, not reusable mechanical output) —
the numbers below are reproducible from the same source reports by
re-running the classification pass, not from a checked-in cache.

## Inventory, as actually found (2026-09-16, ~08:00 ET)

A live `find ~/.cache/agent-reviews -name "review-*.md" -not -path
"*/scratch*"` returned **221** files at the time I ran the tally script,
not the ticket's stated 218 — two discrepancies, both explained, not a
missing-file problem:

- The ticket's own per-axis breakdown (60 standards + 59 spec + 60
  correctness + 31 verify + 9 verification) sums to **219**, not 218 — an
  arithmetic slip in the ticket text itself.
- Between the ticket being written and this script running, `skills#853`
  gained two round-1 reports (`review-spec-853.md`,
  `review-standards-853.md`) with no correctness report yet — a round-1
  review still in progress on a live, concurrently-written cache. I
  excluded #853 entirely as incomplete rather than tally a partial round.

That leaves **58 issues** with at least one complete round-1 set: 40 in
`skills` (folding in `agent-skills`'s 3), 17 in `sudokumaker-custom-
constraints`, 1 in `twitch-rules-scroller`.

**The cache kept moving under this ticket.** `twitch-rules-scroller#274`
was open with no PR when I first classified it (10 findings, all
"unclear" — nothing to dispute yet on an unmerged ticket). By the time
round-1 review came back on this note, #274 had a verification pass and a
merged PR (#294) in the live cache. I re-read the verify pass and PR body
and reclassified all 10 of its findings against their real dispositions
(6 confirmed/fixed, 4 disputed) rather than leave a now-false "still open"
claim in a finished note. Everything else in the tally is frozen at the
classification pass's original snapshot; only #274 was updated, because it
was the one place where "unclear" had gone from *no disposition exists
yet* to *actively wrong*.

Filename anomalies handled explicitly by the parser (all covered by
`tally_review_axes_test.py`):

- `skills#790`: verify pass is split across `review-correctness-790-
  verify.md` (one axis) and `review-standards-spec-790-verify.md` (two axes
  in one file) — both folded into #790's single verify pass.
- `sudokumaker#368`: verify pass is three separate axis-specific files
  (`review-standards-368-verify.md`, `-spec-`, `-correctness-`) instead of
  one combined file — folded the same way.
- `skills#819`: has non-`review-`-prefixed verify files
  (`verify-standards-819.md`, `verify-spec-819.md`,
  `verify-correctness-819.md`) alongside the normal naming. The mechanical
  script correctly does not count these as `review-*.md` reports (they
  aren't), but the classification pass used their content for #819's
  disposition since it exists and is real verify-pass prose.

## What couldn't be counted

- **15 of the 58 issues have no verify-pass report file at all**:
  `skills#751,764,784,785,793,805,819*,823,824,844`,
  `sudokumaker#428,429,435,445,469` (`*` = #819 has non-standard-named
  verify files, counted separately above as present). For those,
  disposition came only from the PR body's "Decisions made" section, or
  was marked unclear if that section didn't mention the finding either.
- **40 of 587 findings (6.8%) are "unclear"** — no verify report and no
  clear PR-body mention. Confirm rates below are best read as **lower
  bounds**, not exact rates, because of this residual.
- **5 findings are `clean`** — a report that raised zero findings
  (`skills#751` spec, `#793` and `#835` correctness; `sudokumaker#435` and
  `#469` correctness). These are counted as one record each, excluded from
  the 587-finding total below (587 = 592 committed records − 5 clean).

## Per-axis table (all repos, 587 findings across 58 issues)

| Axis | Findings | Confirmed | Disputed | Filed | Unclear | Confirm rate | Hard findings | Hard confirm rate |
|---|---|---|---|---|---|---|---|---|
| Standards | 270 | 167 | 74 | 5 | 24 | 62% | 22 | 91% |
| Spec | 133 | 87 | 37 | 1 | 8 | 65% | 18 | 94% |
| Correctness | 184 | 127 | 40 | 9 | 8 | 69% | 87 | 85% |
| **Total** | **587** | **381** | **151** | **15** | **40** | | **127** | |

Confirm rate = confirmed / total findings for that axis (one formula,
used consistently in every table and in the prose below — round 1 review
caught three different formulas sharing the same label in the prior
draft). Row totals sum to 587, matching every other total in this note
(round 1 review caught the prior draft's table summing to 592 while its
own prose said 587 — a clean/finding double-count, fixed by consistently
excluding the 5 clean-report records everywhere).

Reading it: correctness has the fewest total findings but by far the
highest **share** that are hard (87/184 = 47%, vs. 22/270 = 8% for
standards and 18/133 = 14% for spec) — it's finding fewer things, but a
much higher fraction of what it finds is a real violation, not a style
nit. On the hard subset specifically, **spec has the highest confirm rate
(94%), then standards (91%), then correctness (85%)** — correctness is not
the highest here, a claim the prior draft got backwards. Standards
produces roughly double correctness's volume, almost entirely judgement
calls (248/270 = 92%), and nearly 30% of those get disputed away.

## Per-repo split

| Repo | Issues | Axis | Findings | Confirmed | Disputed | Filed | Unclear |
|---|---|---|---|---|---|---|---|
| skills (+ agent-skills) | 40 | standards | 154 | 96 | 49 | 3 | 6 |
| | | spec | 82 | 50 | 29 | 1 | 2 |
| | | correctness | 118 | 81 | 30 | 6 | 1 |
| sudokumaker-custom-constraints | 17 | standards | 111 | 67 | 24 | 2 | 18 |
| | | spec | 49 | 35 | 8 | 0 | 6 |
| | | correctness | 63 | 44 | 9 | 3 | 7 |
| twitch-rules-scroller | 1 | standards | 5 | 4 | 1 | 0 | 0 |
| | | spec | 2 | 2 | 0 | 0 | 0 |
| | | correctness | 3 | 2 | 1 | 0 | 0 |

Sudokumaker's standards axis has a notably higher unclear share (18/111 =
16%, vs. skills' 6/154 = 4%) — 5 of its 17 issues have no verify pass at
all (`#428,429,435,445,469`), all correctness-report-absent too; this
repo's smaller review volume means missing verify passes hit its
denominator harder. Its confirm rate (67/111 = 60%) otherwise tracks
skills' standards rate (96/154 = 62%) closely — nothing here suggests the
two codebases need different axis treatment. `twitch-rules-scroller` has
only 1 reviewed issue; its row is reported for completeness, not compared
against the other two repos — n=1 is too small to say anything about how
this repo's axes behave, even though #274's own findings happen to be
fully resolved now.

## Codex adversarial pass

Separate from the three axes above; see
`docs/research/2026-09-14-codex-review-trial.md` for the full trial log.
Across the 5-ticket trial (the row count Chris set as the trial's length):
**10 codex-only confirmed findings**, **3 also found by a Claude axis**,
**2 disputed**. Every trial ticket produced at least one codex-only
confirmed finding; two tickets (#817, #821) produced three each with zero
overlap. This is the strongest signal in the dataset that a pass is
earning its tokens outright rather than restating another axis — the
controller hit the trial's row-5 cutoff at #819 and owes Chris the
keep/drop call the note describes, which this tally doesn't override.

## Recommendation

- **Keep correctness as-is.** Fewest findings, by far the highest
  hard-finding density (47% of its findings are hard, more than 3x either
  other axis's share), and a strong 85% hard-confirm-rate. It is the axis
  catching the fewest but most consequential things.
- **Keep spec as-is.** Smallest volume, a 65% overall confirm rate, and the
  highest hard-confirm-rate of the three (94%) — when spec calls something
  a hard violation, it's very rarely wrong.
- **Standards is the trim candidate, not a drop candidate.** It earns real
  confirms (62%, and 91% on its hard findings), but it's also the single
  largest source of judgement-call volume in the whole review system
  (248 judgement-call findings — more than spec and correctness's
  judgement calls combined, 115+97=212). If token budget forces a cut,
  this is where a stricter "hard violations and settled-standard breaches
  only, defer the over-engineering/style nits to a lighter pass" scope
  would recover the most tokens for the least confirmed-finding loss.
- **Keep the Codex pass, and treat this tally as independent evidence for
  the controller's pending keep/drop call** — 10 codex-only confirmed
  findings in 5 tickets is not noise.
- **Confidence:** the confirm/dispute rates above are lower bounds; 40 of
  587 findings (6.8%) had no traceable disposition, concentrated in the 15
  issues with no verify pass. If a stronger signal is needed later, closing
  that verify-pass gap (running verify even on "everything looked clean"
  round-1s, or at minimum keeping the PR body's Decisions section
  exhaustive) would tighten this the most, of anything.

## Follow-up: report format is unmeasurable-by-machine (filed)

The reports are intentionally free prose (findings as numbered items,
headed sections, or bullets, with no consistent finding-id or disposition
tag), so this tally required an actual reading pass — three parallel Sonnet
agents burned roughly 600K combined tokens reading and classifying 587
findings that a one-line-per-finding machine-readable format
(`<finding-id> <axis> <severity> <one-line>`, disposed later by ID in the
verify pass and the PR body) would make near-free to tally. This ticket
explicitly said not to touch `multi-axis-code-review/SKILL.md`, so the fix
is out of scope here. I filed
**caneff/agent-skills#861** ("multi-axis-code-review: give every finding a
stable id so future tallies don't require a reading pass") to track it.
