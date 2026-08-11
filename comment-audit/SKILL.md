---
name: comment-audit
description: Ruthlessly audit a repo's comments — delete every one that doesn't earn its place, keep only what the code cannot say. Slash-only.
disable-model-invocation: true
argument-hint: "[path]"
---

Sweep the code in scope and cut every comment that does not earn its place. A
codebase full of comments that restate the code trains the reader to skip all
comments — so the one comment that matters goes unread. Ruthless deletion is
what buys the survivors their authority.

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
- **Issue/ticket/ADR/decision citation.** `# see JIRA-4521`, `# per ADR-012`,
  `// fixes #88`, `// (issue #4, decision 3)`. Every such pointer sends the
  reader off to reconstruct a reason that belongs right here. Cut the *whole*
  citation, not one pointer out of it — dropping `#4` from `(issue #4, decision
  3)` leaves a barer `decision 3`, worse than what you started with. If the
  citation carried a *why*, keep the *why* as plain prose and delete every
  number.
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
  elsewhere, and this audit puts it here instead.
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

1. **Start clean, scope tight.** Confirm a clean working tree first
   (`git status`) — the comments-only guarantee in step 5 only holds when nothing
   else is uncommitted. Then scope: audit `$ARGUMENTS` if given; with no
   argument, default to the current branch's diff against its base
   (`git diff --name-only main...HEAD`), not the whole tree — a repo-wide sweep is
   an explicit opt-in the user asks for by name. Either way, skip vendored,
   generated, and dependency trees (`node_modules`, `dist`, `.venv`, build
   output, lockfiles).

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

4. **Apply the changes.** Delete the cuts. For every keeper, tighten the prose
   to the fewest words that still read clearly, and correct any text that has
   gone stale while its *why* stays true. Touch comments only — leave the
   code itself, its formatting, and every keeper that already reads true exactly
   as they are.

5. **Verify, then open a PR for review.** The final diff must touch comments and
   nothing else — confirm with `git diff`. Run the repo's build/lint/test so a
   load-bearing line you misread turns the loop red before review, not after.
   Then commit the audit on its own branch, with nothing else in the commit, and
   open a pull request. Every cut is a judgment call, so a human reads the sweep
   before it merges — and the isolated commit means the whole audit reverts in
   one step if a call proves wrong.

   Before you commit, count whole deletions against salvage-trims. This is a
   mirror, not a rule: if the salvages outnumber the whole deletes, you
   rationalized — go back and re-ask each salvage whether you would write that
   clause onto a blank line today. Most of them are whole cuts you softened.

## When a comment props up unclear code

A comment that exists only because the code beneath it is confusing is a
different problem — cutting it silently loses the one thread the reader had. Do
not delete it as cruft. Flag it: the fix is a clearer name or a refactor, which
is a code change outside this audit's comments-only scope. Note it as a
follow-up and leave the comment until the code is fixed.
