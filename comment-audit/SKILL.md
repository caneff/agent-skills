---
name: comment-audit
description: Ruthlessly audit a repo's comments — delete every one that doesn't earn its place, keep only what the code cannot say.
disable-model-invocation: true
argument-hint: "[path]"
---

Sweep the code in scope and cut every comment that does not earn its place. A
codebase full of comments that restate the code trains the reader to skip all
comments — so the one comment that matters goes unread. Ruthless deletion is
what buys the survivors their authority.

The default deliverable is a **report**, not applied edits. The sweep writes a
machine-readable findings log and a grouped HTML summary; it touches no code.
Applying the cuts is a separate, opt-in step the user asks for by name.

## The one test

**A comment earns its place only if it tells the reader something the code
cannot.** Default is CUT: the burden of proof is on the comment, so when you are
unsure whether one earns its place, it does not.

The code already says **what** it does. A comment earns its place by saying
**why** — the rationale, the constraint, the gotcha the code executes but cannot
explain.

Be ruthless about the *why*, because almost any comment can have one invented
for it. A why survives only if it passes both gates:

- **Not inferable.** A competent engineer reading this code and its names would
  not already know it. If the why is obvious from the code, the comment is
  restatement wearing a because-clause. Cut it.
- **Load-bearing absence.** Delete the comment in your head — does a reader now
  make a concrete mistake? If nothing breaks, nothing was holding it up. Cut it.

Reach for the whole cut first. Most comments in scope are whole deletions;
keepers are a minority, and a comment worth trimming down to a rescued clause is
rarer still. Ask **"does this whole comment go?"** before you ask "what part
earns its place?" — the first question is the one that clears a codebase, and
the second is the trapdoor that turns every deletion into a trim.

When only a fragment of a comment passes, you may keep that fragment — but
salvage clears a higher bar than a keeper does. Judge the surviving clause as if
you were typing it onto a blank line today: does it, standing alone, pass both
gates? If you would not write it into empty space, do not rescue it — delete the
whole comment. A comment that is one clause of real *why* wrapped in three of
restatement is a whole cut far more often than it is a rescue.

## Load-bearing — never touch

Some lines look like comments but change how code runs or how tools read it.
These are load-bearing. Leave them exactly as they are, always:

- Linter/type directives: `# type: ignore`, `# noqa`, `# pragma: no cover`,
  `// eslint-disable`, `// @ts-expect-error`, `# pyright: ignore`.
- Compiler/tooling pragmas: `//go:embed`, `//go:build`, `# -*- coding: utf-8 -*-`,
  shebang lines (`#!/usr/bin/env ...`).
- License/copyright headers the project's policy requires.
- Structured doc markers a generator consumes: `@param`/`@returns` in a JSDoc or
  docstring that feeds published API docs.

If a comment might be read by a tool rather than a human, treat it as
load-bearing and move on.

## Cut

Delete on sight — each of these says nothing the code doesn't already say, and
each rots into a lie the moment the code changes underneath it:

- **Restates the code.** `i += 1  // increment i`; `# loop over users`;
  `return total  // return the total`.
- **Narrates the obvious.** Section-divider banners, `# constructor`, `# imports
  below`, a comment on every line of a self-evident block.
- **Historical cruft.** `# changed from a list to a dict on 3/4`; `// used to
  call the old API`; a changelog living in the source. Git already holds this.
- **Bare issue/ticket/decision/spec citation.** `# see JIRA-4521`, `// fixes
  #88`, `// (issue #4, decision 3)`, `# spec #99`, a naked forward-ref
  `(#399)`, `(decisions #382, #385)`. A bare number counts even with no verb
  or keyword beside it — a lone `(#399)` is still a pointer to cut. Every such
  pointer sends the reader off to reconstruct a reason that belongs right here.
  Cut the *whole* citation, not one pointer out of it — dropping `#4` from
  `(issue #4, decision 3)` leaves a barer `decision 3`, worse than what you
  started with. If the citation carried a *why*, keep the *why* as plain prose
  and delete every number. **One exception — an `ADR-NNNN` reference stays.**
  An ADR is a durable, addressable decision record, not an ephemeral ticket,
  so the reason it points to genuinely lives elsewhere and stays reachable —
  keep it, the way a domain-rule keeper does. Still drop a bare number riding
  beside an ADR: `per ADR-0007 (#412)` → `per ADR-0007`.
- **The plausible-but-inferable why.** A because-clause a reader would already
  know from the code: `# use a set for fast lookup`, `# sort so output is
  stable`, `# cache to avoid recomputing`. It sounds like rationale, but the code
  and the names already say it. Cut it.
- **Filler and hedging.** `# helper function`, `# note:` with nothing after the
  note, `# this is a bit hacky` with no fix, `# TODO` with no actionable next
  step. A comment that gestures without informing is noise.
- **Commented-out code.** Delete it. Git remembers; a graveyard block does not.
- **Stale or wrong.** A comment the code has outgrown. If it no longer matches
  the code, it misleads — cut it (or fix it if the *why* is still true).

## Keep

These earn their place — each carries a *why* the code cannot. A keeper is not
exempt from editing: rewrite it to the fewest words that still read clearly.
Cut the throat-clearing, the restated code, the second sentence that repeats the
first. A good comment is a note, not a paragraph.

- **The why.** Why this approach over the obvious one; why this constant; why
  this order matters. `# retry 3x — upstream 404s the first cold read`.
- **The warning.** A non-obvious consequence, a sharp edge, a "do not touch
  unless you also change X."
- **The workaround and the reason for it.** The constraint that forces the
  code's shape, stated so the reader never leaves the file:
  `// upstream truncates payloads over 64KB — chunk first`. Keep the reason;
  never keep an issue number in its place — a `#123` promises the reason lives
  elsewhere, and this audit puts it here instead (a durable `ADR-NNNN` is the
  exception — keep it; see Cut).
- **The domain rule the code can't make self-evident.** A business constraint or
  legal requirement whose *why* lives outside the codebase.
- **Public API contract.** A docstring or doc-comment on a published interface,
  carrying what the signature cannot — the promise, the units, the failure modes
  callers depend on. A docstring that only restates the signature is no
  contract; cut it like any other restatement.

## The audit, worked

Eight comments guard this test; one earns its place. Each of the other seven
says what the code or the test's own name already says — so each is a whole cut,
not a trim.

```python
def test_white_kropki_decode():
    # --- type 200 white-kropki decode ---
    # arrange
    board = Board(size=9)  # default 9x9 grid
    # build a puzzle with one white dot
    puzzle = decode(WHITE_DOT_WIRE)
    # act
    result = puzzle.witness()
    # assert
    # white dot means the two cells differ by 1
    assert result.pairs == [(a, b)]
    # should have exactly one pair
```

The audited version keeps one line:

```python
def test_white_kropki_decode():
    board = Board(size=9)
    puzzle = decode(WHITE_DOT_WIRE)
    result = puzzle.witness()
    # white dot means the two cells differ by 1
    assert result.pairs == [(a, b)]
```

Eight comments in, one out. The `--- ... ---` banner and the arrange/act/assert
labels name blocks the reader already sees; `# default 9x9 grid`, `# build a
puzzle with one white dot`, and `# should have exactly one pair` each restate the
line beneath them. Only the domain rule survives — the code enforces that a white
dot means the two cells differ by 1, but nothing in it says why that pair is the
answer.

## Run

1. **Scope.** Audit `$ARGUMENTS` if given; with no argument, scope defaults
   per `~/.agents/skills/all-audits/SKILL.md`'s Scope section. Skip vendored, generated, and dependency trees
   (`node_modules`, `dist`, `.venv`, build output, lockfiles) and any `.git/` or
   `worktrees/` tree — a git worktree mirrors the whole repo, so scanning it
   multiplies every finding once per worktree.

2. **Sweep — every comment, not a sample.** Walk the files in scope and read
   every comment in the context of the code it sits on. Judgment needs the code
   beside the comment, so read them together; a grep of comment markers only
   tells you where to look. On a large tree, fan the sweep across subagents by
   directory — but every comment in scope gets judged, never sampled.

3. **Judge each into one bucket** against the one test: load-bearing (never
   touch), keep (earns its place), or cut (default). For every keeper, write one
   sentence naming the concrete mistake a reader makes once it is gone — a
   specific wrong action (*"a reader assumes the retry is optional and deletes
   it"*), not "adds context" or "explains the why." If you cannot name the
   mistake, the comment is not load-bearing — cut it.

4. **Write the findings log and render the summary — the default deliverable.**
   Write every judged cut and keeper to `findings.jsonl`, then draw a grouped
   summary `report.html` from it (see below). Touch no code. Print the one-line
   verdict and the summary's absolute path, nothing else.

   Before you write, hold up two mirrors — each catches a different way the
   sweep goes timid. Neither is a rule; both are a prompt to go back and re-judge.

   - **Salvage vs whole-delete.** If the salvages outnumber the whole deletes,
     you rationalized — re-ask each salvage whether you would write that clause
     onto a blank line today. Most are whole cuts you softened.
   - **Keep vs cut.** Keepers are a minority — a small one. If they run past a
     fraction of the comments judged, you rationalized the other way: you let
     "there might be a why" promote restatement to a keep. Re-ask each keeper
     the not-inferable gate — would a competent reader already know this from
     the code and its names? Over-keeping is over-salvaging one level up, and it
     is the easier miss to miss, because a keep leaves no trim to notice.

## Write the log and render the summary

Write the full record to `findings.jsonl` and a grouped summary to
`report.html`, following `~/.agents/skills/all-audits/harness/findings-schema.md`
for both — the JSONL schema, the grouped-overview shape, and why it's two
files instead of one card per comment.
Write both to `<tmpdir>/comment-audit-<timestamp>/` and deliver the summary per
`~/.agents/skills/all-audits/harness/HTML-REPORT.md` — tmpdir resolution,
opening, and handing off the path all live there.

- **Log** — one JSONL line per judged comment. `bucket` is `cut` / `keep` /
  `load-bearing`. `category` is the reason that named it — `restatement`,
  `banner`, `historical`, `citation`, `inferable-why`, `filler`,
  `commented-out-code`, `stale` for cuts; `why`, `warning`, `workaround`,
  `domain-rule`, `api-contract` for keepers. A cut carries `before`/`after`
  (`"— gone —"` for a whole delete, the tightened clause for a salvage).
- **Summary** — the verdict, the `N judged · M cut · K kept` metabar, and the
  findings grouped by bucket then category with counts (the shape a reader
  wants: "80 restatement, 21 banner, 11 citation"). No per-comment cards. Close
  with a `vt-callout` for the load-bearing lines left untouched (directives,
  pragmas, license headers), so the reader sees they were considered, not missed.

## Applying the cuts (opt-in)

Only when the user asks to apply — see `~/.agents/skills/all-audits/SKILL.md`'s
"Opt-in edits" section for the shared opt-in contract
(reviewable PR on its own branch, never a direct commit). Start from a clean
working tree — the comments-only guarantee below only holds when nothing else
is uncommitted.

Apply: delete the cuts. For every keeper, tighten the prose to the fewest
words that still read clearly, and correct any text that has gone stale while
its *why* stays true. Touch comments only — leave the code itself, its
formatting, and every keeper that already reads true exactly as they are.

Verify before the PR: the final diff must touch comments and nothing else —
confirm with `git diff`. Run the repo's build/lint/test so a load-bearing
line you misread turns the loop red before review, not after.

## When a comment props up unclear code

A comment that exists only because the code beneath it is confusing is a
different problem — cutting it silently loses the one thread the reader had. Do
not delete it as cruft. Flag it: the fix is a clearer name or a refactor, which
is a code change outside this audit's comments-only scope. Note it as a
follow-up and leave the comment until the code is fixed.
