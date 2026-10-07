# The closing check: the seam, and what it cannot see

The policy is `implement-spec/SKILL.md` § The closing check;
`implement-spec/closing_ticket.py` generates the section for the spec's
integration PR, or for the only slice of a one-slice spec. This file is the
declaration grammar and the evidence.

## The declaration

A repo states its end-to-end seam in `AGENTS.md`, beside its include-closure
declaration:

```
## End-to-end seam

- **Seam**: `npm run test:e2e` over the headless solver bundle
- **Blind to**: the live editor — grid rendering at 4x4 and 6x6
```

A value may wrap onto continuation lines indented deeper than its item, as a
Markdown list item does; they are joined onto it with single spaces (#1243).
Under a list item, a blank line followed by a deeper-indented paragraph does
not end it, as in a loose list item (#1406); under a key line with no list
marker, a blank line ends the value, since an indented block after it is
code. The value ends at a heading, a fence, a key line (nested or not), or
the first line at the item's own indent or shallower. Reading only
the first line would state a partial blind spot as the whole one; reading
past these would pad it with text the author never wrote there.

Both keys are required, and a value of nothing but emphasis markers is
refused as naming nothing: `- **Seam**:**` reads as the value `**` (#1104).
A repo that declares nothing is not a repo with no seam: the exploration pass supplies both halves instead (`--seam`,
`--blind-to`), and a spec run that can supply neither has found something
worth telling the controller before it writes the closing check at all.

**The declaration outranks the exploration pass.** The pass fills only what
the declaration omits, and where both are present and differ the generator
refuses, naming both. A declaration an inferred value may silently override
is not a declaration: a stale exploration result would replace the repo's
canonical seam with nothing said about it. Where the two disagree, either the
pass is stale or the declaration is wrong, and the repo's own file is where
the second gets fixed.

Where the declaration belongs is the repo's own `AGENTS.md`, so the answer
sits where every later reader of that repo — not only this run — will find
it.

## Why a seam with no blind spot is refused

On #781's spec run the spec's separate final ticket said "write one
end-to-end test over the whole spec's acceptance criteria", named no seam, and
the worker stopped and asked. Naming one would not have been enough either.
The seam that existed was the headless solver bundle, and it had **already
diverged from the live editor inside that same spec**: `#367`'s no-ring header
verified green headless and broke 4×4 and 6×6 in the real app.

So the generator refuses a seam with no stated blind spot. A worker told only
where to drive the spec reads a green run as coverage; a worker told what the
seam cannot see knows what its green run does not mean.

## A worked blind spot

This repo's own declaration is `AGENTS.md` § End-to-end seam, the canonical
copy, kept there so a seam change is one edit, not two. The sharpest
instance in it is a worker spinning on identical no-op tool calls — healthy
on every signal the suite can check, and an hour gone before a human
noticed.

A blind spot reads like that: not "the tests are incomplete", but the class of
failure the seam structurally cannot witness.

## One open of the real thing

Where the spec puts a user-visible surface beyond the seam's reach, the
closing check says so and its acceptance carries one open of the shipping
surface per surface. This is the end-of-spec form of the standing rule that a
ruling about runtime behaviour is checked against the thing that ships, not
against a proxy for it.

## The range, and the sha list it replaced

The spec-level review reads `origin/<default>...spec-<n>`, the spec's
integration branch against the default branch (#1461). That range is the
review's own because the integration branch holds the spec's slices and
merges of `<default>`, nothing else, and three-dot compares against the
merge-base, so `<default>`'s own commits stay out.

Before #1461, slices landed on `main` one by one, and the range a reader
would reach for there — on #781, the spec's first slice to `origin/main` —
held the spec's three squash commits and ~17 unrelated commits from other
sessions. The closing check therefore carried the run file's merge shas as a
list, and a procedure that built a comparison out of them: a detached
worktree at the first sha, the rest cherry-picked on, the review against
`<first>~1`, and one run per sha where a cherry-pick conflicted. The
integration branch removed the problem that procedure solved, so the
generator no longer writes it.

A one-slice spec has no integration branch (ruling 3a of #1457): its slice
lands on the default branch with its own review wave. `--one-slice` makes a
section for that slice's body that keeps the seam, the blind spot and the
surfaces and names no spec-level review. It is not a refusal, because a
refusal would leave every one-slice spec with no closing check at all.
