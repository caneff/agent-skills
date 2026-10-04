# The closing check: the seam, and what it cannot see

The policy is `implement-spec/SKILL.md` § The closing check;
`implement-spec/closing_ticket.py` generates the section appended to the last
slice's body. This file is the
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
The value ends at a blank line, a heading, a fence, a key line (nested or
not), or the first line at the item's own indent or shallower. Reading only
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
end-to-end test over the whole spec's acceptance criteria", named no seam,
and the worker stopped and asked. Naming one would not have been enough either. The seam
that existed was the headless solver bundle, and it had **already diverged
from the live editor inside that same spec**: `#367`'s no-ring header
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

## The shas, and the procedure that can actually run over them

The spec-level review is handed the run file's landings as a list. On #781
the range a reader would reach for — the spec's first slice to
`origin/main` — held the spec's three squash commits and ~17 unrelated
commits from other sessions.

The list alone is not enough, because `/multi-axis-code-review` pins **one**
fixed point and reads `<fixed point>...HEAD`: it cannot take disjoint
commits. A closing check that names the shas and stops states a procedure
nothing can carry out, and a worker handed one invents the range the list
exists to prevent. So the generated section carries the procedure that builds the
comparison out of those commits: a detached worktree at the first sha, the
rest cherry-picked on in landing order, and the review run against
`<first>~1`, with the worktree removed after. HEAD is then this spec's
commits and nothing else. Where a cherry-pick conflicts, the fallback is one
run per sha against its own parent — also written out, because "fall back to
per-sha" with no commands is the same unexecutable instruction one level
down.

An empty sha list is the one-slice spec: the slice has no earlier landings,
so the generated section omits the spec-level review and keeps the seam, the
blind spot and the surfaces. It is not a refusal, because a refusal would
leave every one-slice spec with no closing check at all.
