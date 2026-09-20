# The closing ticket: the seam, and what it cannot see

The policy is `implement-spec/SKILL.md` § The closing ticket;
`implement-spec/closing_ticket.py` generates the body. This file is the
declaration grammar and the evidence.

## The declaration

A repo states its end-to-end seam in `AGENTS.md`, beside its include-closure
declaration:

```
## End-to-end seam

- **Seam**: `npm run test:e2e` over the headless solver bundle
- **Blind to**: the live editor — grid rendering at 4x4 and 6x6
```

Both keys are required. A repo that declares nothing is not a repo with no
seam: the exploration pass supplies both halves instead (`--seam`,
`--blind-to`), and a spec run that can supply neither has found something
worth telling the controller before it writes a closing ticket at all.

Where the declaration belongs is the repo's own `AGENTS.md`, so the answer
sits where every later reader of that repo — not only this run — will find
it.

## Why a seam with no blind spot is refused

On #781's spec run the closing ticket said "write one end-to-end test over
the whole spec's acceptance criteria", named no seam, and the closing worker
stopped and asked. Naming one would not have been enough either. The seam
that existed was the headless solver bundle, and it had **already diverged
from the live editor inside that same spec**: `#367`'s no-ring header
verified green headless and broke 4×4 and 6×6 in the real app.

So the generator refuses a seam with no stated blind spot. A worker told only
where to drive the spec reads a green run as coverage; a worker told what the
seam cannot see knows what its green run does not mean.

## One open of the real thing

Where the spec puts a user-visible surface beyond the seam's reach, the
closing ticket says so and its acceptance carries one open of the shipping
surface per surface. This is the end-of-spec form of the standing rule that a
ruling about runtime behaviour is checked against the thing that ships, not
against a proxy for it.

## The shas, not a range

The spec-level review is handed the run file's landings as a list. On #781
the range a reader would reach for — the spec's first slice to
`origin/main` — held the spec's three squash commits and ~17 unrelated
commits from other sessions, and `/multi-axis-code-review` takes one fixed
point. The generator refuses an empty sha list: a closing ticket with nothing
to review is a review that will be invented at the last minute.
