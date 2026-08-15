---
name: extract-coding-standards
description: Mine a repo's recent history — merged PRs, review comments, commits, and the current code — for the conventions the team actually enforces, and write them into CODING_STANDARDS.md in the house rule format. Slash-only.
disable-model-invocation: true
argument-hint: "[N | all]"
---

Read what a repo's history reveals about how its people write code, and turn the
conventions the team actually enforces into rules a future contributor — human
or agent — can follow. The output is a `CODING_STANDARDS.md` that `/code-review`
reads as its Standards axis, so every rule you write becomes a check on future
diffs.

`$ARGUMENTS` sets the scope: a number `N` looks at the last N merged PRs (or the
last N commits if the repo has no PR history), and `all` scans the whole history.
Default when empty: **20**.

## The core problem: one fix is not a rule

A review comment fixes **one spot**. A coding standard governs **every future
spot**. The whole risk of this skill is inventing a broad rule from one narrow
fix — a standard nobody agreed to. That false rule is worse than a missed one:
it churns future reviews, gets copied blindly, and teaches the reader to
distrust the whole doc. So aim for **precision over recall** — write fewer rules,
and only ones the evidence forces.

Two ideas keep you honest, both drawn from how convention-mining tools work:

- **Descriptive, not prescriptive.** Only write down what the code *already
  does*, not what one comment wishes it did. A rule the current code does not
  keep is not a rule.
- **Acceptance is the signal.** A review comment counts only if it was
  **accepted** — it produced a follow-up commit. A comment that was rebutted,
  ignored, or left open is noise, not a line the team drew.

## The promotion gate: three tiers

For each convention you spot, sort it into one of three tiers.

**Write it as a rule** when either test passes:

- **Corrected and kept** — an accepted review correction asked for it, **and**
  the current code conforms. The correction shows a person cared; the code shows
  the fix stuck and spread. This is the strongest evidence — two independent
  signals at once.
- **Repeated correction** — the same kind of accepted correction appears in
  **two or more separate PRs**. Two deliberate human acts, not one preference.

**Write it, but mark it "contested"** when the code mostly follows it but not
cleanly — roughly 60–90% of the sites conform, with real counter-examples. Say
so in the rule; do not assert a contested pattern as settled.

**Report it as a candidate, do not write it** — everything below the bar: a
single sighting, a correction the current code does not keep, or consistency
without any human signal behind it. Surface these to the user so a person can
promote them by hand. This is the holding pen for doubt — record it, never
graduate it.

Score conformance by **adherence ratio across the call-sites, not one example**:
near-100% → clean rule; 60–90% → contested; below that → candidate at most.

## Skip what a tool already enforces

Do not encode anything a linter, formatter, type checker, or test gate already
catches — line length, import order, quote style, trailing commas. Restating a
mechanical rule as prose is noise, and it teaches the reader to skim past the
rules that matter. First check the repo for those gates (`ruff`, `prettier`,
`eslint`, `tsc`, pre-commit config, CI). A convention a gate enforces is the
gate's job, not this doc's. Keep only the rules **no tool catches** — the ones
that break something silently.

## Steps

### 1. Set the scope and gather evidence

Resolve `$ARGUMENTS` to a range. Then gather, in one read-only sweep — delegate
it to a sub-agent so the raw output stays out of your context and you keep only
the findings:

- **PR review comments** — the richest source; about a third of review comments
  are about conventions. `gh pr list --state merged --limit N`, then for each PR
  its review comments and threads (`gh pr view --comments`, or `gh api`). For
  each comment that asked for a change, record what was wrong, what was asked
  instead, and **whether a later commit in that PR applied it** (accepted) or not
  (noise).
- **Commit history** — `git log` over the range. Flag fixup/revert/"address
  review"/"lint" commits: each marks a mistake the team corrected.
- **The current code** — for every candidate rule, measure how much of the
  current code actually follows it. This is what sorts rule from contested from
  candidate.

### 2. Distill candidates into tiers

Group the evidence into distinct conventions. Drop anything a tool already
enforces (the filter above). Run each survivor through **the promotion gate** and
label it **rule**, **contested**, or **candidate**.

### 3. Write CODING_STANDARDS.md

Choose the target so the output slots into what `/code-review` already reads:

- If the repo already documents standards in `CODING_STANDARDS.md` or
  `CONTRIBUTING.md`, append there.
- Otherwise create `CODING_STANDARDS.md` at the repo root.
- Never create a second competing standards file.

Write each rule in the house format — a bold one-line claim as an imperative,
then the *why* and the concrete thing that breaks silently when it is ignored:

```
N. **The claim as an imperative.** The reason it exists, and the concrete
   thing that breaks silently when someone ignores it — the failure no
   mechanical gate catches.
```

Mark a contested rule as contested in its own text (e.g. "Most of the code does
X; a few places still do Y — prefer X"). Keep the doc short: cite the evidence in
your report to the user, not in the doc. If the range gave you three real rules,
write three; do not pad to look thorough.

If the target file already exists, **merge, don't clobber**: keep every existing
rule, add only new ones. Where the recent history now **contradicts** a written
rule, do not edit or delete it — **flag the drift** in your report (e.g. "rule N
says X, but the last 8 PRs do Y") and leave the call to the user.

### 4. Report

Hand the user:

- The rules written or added, each with the evidence behind it — the PR or commit
  that proves the team enforces it, and its tier (rule or contested).
- The candidates you did **not** write, and why (thin evidence).
- Any drift you flagged against existing rules.
- Anything a tool already enforces that you deliberately left out.
