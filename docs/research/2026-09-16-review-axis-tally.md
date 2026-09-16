# Review-axis tally: what standards, spec, and correctness actually earn (#854)

Summary: correctness earns its tokens clearest — it raises the fewest but
densest-hard findings (87 hard out of 188, a 46% hard-rate) and the highest
hard-finding confirm rate (84%). Standards raises by far the most volume
(270 of 592 findings, 46% of everything raised) but 92% of that volume is
judgement calls, a quarter of which get disputed away — it's not earning
nothing, but it's the axis to trim first if token budget gets tight. Spec
sits in between: lower volume than standards, a 64% overall confirm rate,
and a 94% confirm rate on its (few) hard findings. The Codex adversarial
pass, run separately from these three axes at merge time, is the clearest
keep: across its 5-ticket trial it raised 10 codex-only confirmed findings
against only 3 that overlapped a Claude axis — it is finding a different
class of bug, not re-covering the same ground.

## Method

Two passes, kept separate because free prose can't be tallied by regex
alone:

1. **Mechanical** (`tally_review_axes.py`, tested in
   `tally_review_axes_test.py`): walks `~/.cache/agent-reviews`, parses each
   `review-*.md` filename into (round1|verify, axis or axes, issue number),
   folds `agent-skills`→`skills` (same repo, two checkout names) and
   `verify`/`verification` (two names for the same round) together, and
   joins round-1 reports to their verify report and merged PR by issue
   number (PR match: `Closes #<n>` text, falling back to the PR's
   `implement-<n>`/`issue-<n>` branch name — see below).
2. **Judgement**: reading each round-1 finding's text, its matching
   verify-pass text, and its PR body's "Decisions made" section, and
   classifying severity (hard violation / judgement call / clean-no-finding)
   and outcome (confirmed / disputed / filed-as-follow-up / unclear-no-
   disposition-found). Done by three parallel Sonnet subagent passes — one
   per repo/batch — each independently briefed with the same taxonomy and
   file layout. I spot-checked each batch's output against the source
   reports rather than re-reading all 592 records myself; spot checks were
   consistent with the source text. Batch-to-batch calibration drift on
   borderline judgement-call severity is the main residual risk in this
   step, not a claimed exact count.

PR matching had to fall back to branch name: `gh pr list --json
closingIssuesReferences` came back empty for essentially every PR in this
dataset (GitHub didn't compute the link even where the body said "Closes
#N"), so the join uses a regex over the PR body/title for `closes/fixes/
resolves #N`, and where that's absent, the PR's `headRefName` matching
`implement-<n>` or `issue-<n>`. This got 57 of 58 substantive issues
matched to a PR (see below for the one exception).

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
  `review-standards-853.md`, both timestamped today) with no correctness
  report yet — a round-1 review still in progress on a live, concurrently-
  written cache. I excluded #853 entirely as incomplete rather than tally
  a partial round.

That leaves **58 issues** with at least one complete round-1 set: 40 in
`skills` (folding in `agent-skills`'s 3), 17 in `sudokumaker-custom-
constraints`, 1 in `twitch-rules-scroller`.

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

- **`twitch-rules-scroller#274`** is the repo's only reviewed ticket, and
  the issue is still **open** — no merged PR, no verify pass exists yet.
  All 10 of its findings are "unclear" by construction: there's nothing to
  dispute yet, not a gap in the join. N=1 issue is too small to say
  anything about how this repo's axes behave; it's reported for
  completeness only, not compared to the other two repos.
- **17 of the 58 issues have no verify-pass report file at all**
  (`skills#751,764,784,785,793,805,819*,823,824,844`,
  `sudokumaker#428,429,435,445,469`, plus `#274` above; `*` = #819 has
  non-standard-named verify files, counted separately above as present).
  For those, disposition came only from the PR body's "Decisions made"
  section, or was marked unclear if that section didn't mention the
  finding either.
- **42 of 592 findings (7%) are "unclear"** — no verify report and no
  clear PR-body mention. Confirm/dispute rates below are best read as
  **lower/upper bounds**, not exact rates, because of this residual.
- **5 findings are `clean`** — a report that raised zero findings
  (`skills#751` spec, `#793` and `#835` correctness; `sudokumaker#435` and
  `#469` correctness). These are counted as one record each, not folded
  into the finding totals below.

## Per-axis table (all repos, 587 findings across 58 issues, excludes the 5 clean-report records)

| Axis | Findings | Confirmed | Disputed | Filed | Unclear | Confirm rate* | Hard findings | Hard confirm rate* |
|---|---|---|---|---|---|---|---|---|
| Standards | 270 | 163 | 73 | 5 | 29 | 60% | 22 | 91% |
| Spec | 134 | 86 | 37 | 1 | 10 | 64% | 18 | 94% |
| Correctness | 188 | 127 | 39 | 9 | 13 | 68% | 87 | 84% |

\*Confirm rate = confirmed / (confirmed + disputed + filed), i.e. excluding
the unclear residual from the denominator — a lower bound given 7% overall
unclear.

Reading it: correctness has the fewest total findings but by far the
highest **share** that are hard (87/188 = 46%, vs. 22/270 = 8% for
standards and 18/134 = 13% for spec) and the highest hard-confirm rate.
Standards produces roughly 2x correctness's volume, almost entirely
judgement calls (248/270 = 92%), and a quarter of those get disputed away.
Spec is the smallest and cleanest by confirm rate, but also the axis most
likely to report "clean" (satisfied AC, nothing to flag).

## Per-repo split

| Repo | Issues | Axis | Findings | Confirmed | Disputed | Filed | Unclear |
|---|---|---|---|---|---|---|---|
| skills (+ agent-skills) | 40 | standards | 154 | 96 | 49 | 3 | 6 |
| | | spec | 83 | 51 | 29 | 1 | 2 |
| | | correctness | 120 | 83 | 30 | 6 | 1 |
| sudokumaker-custom-constraints | 17 | standards | 111 | 67 | 24 | 2 | 18 |
| | | spec | 49 | 35 | 8 | 0 | 6 |
| | | correctness | 65 | 44 | 9 | 3 | 9 |
| twitch-rules-scroller | 1 | all | 10 | 0 | 0 | 0 | 10 |

Sudokumaker's standards axis has a notably higher unclear share (18/111 =
16%, vs. skills' 6/154 = 4%) — it has 5 of the 17 issues with no verify
pass at all (`#428,429,435,445,469`), all correctness-report-absent too;
this repo's smaller review volume means missing verify passes hit its
denominator harder. Its confirm rate (67/(67+24+2)=72%) and volume-per-
issue pattern otherwise track skills' closely — nothing suggests the two
codebases need different axis treatment.

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

- **Keep correctness as-is.** Fewest findings, highest hard-density,
  highest hard-confirm-rate. It is the axis catching the bugs that would
  actually ship.
- **Keep spec as-is.** Smallest volume, highest overall confirm rate, and
  the axis most likely to report a genuinely clean PR — it isn't padding
  findings to justify its run.
- **Standards is the trim candidate, not a drop candidate.** It earns real
  confirms (60%, and 91% on its hard findings), but it's also the single
  largest source of judgement-call volume in the whole review system
  (248 judgement-call findings, more than spec and correctness's judgement
  calls combined). If token budget forces a cut, this is where a stricter
  "hard violations and settled-standard breaches only, defer the
  over-engineering/style nits to a lighter pass" scope would recover the
  most tokens for the least confirmed-finding loss.
- **Keep the Codex pass, and treat this tally as independent evidence for
  the controller's pending keep/drop call** — 10 codex-only confirmed
  findings in 5 tickets is not noise.
- **Confidence:** the confirm/dispute rates above are lower bounds; 42 of
  587 findings (7%) had no traceable disposition, concentrated in the 17
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
explicitly said not to touch `multi-axis-code-review/SKILL.md`, so the
fix is out of scope here. I filed
**caneff/agent-skills#861** ("multi-axis-code-review: give every finding a
stable id so future tallies don't require a reading pass") to track it.
