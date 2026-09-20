# The include closure: what a change really touches

A **clump** is one connected component of a run's file-collision graph — one
worker, one workspace, one PR. The graph is built on each candidate's
**include closure**: the files a change to the candidate's target files
actually regenerates. Reading it is `burndown/closure.py` — `python3
burndown/closure.py <repo-root> <n>=<path>[,<path>]...`, or
`clumps(root, candidates)` in process.

Not on declared seams. A ticket's `## Seams under test` is prose typed by
whoever filed it, and the shared snippet nobody mentioned is exactly what two
workers collide over. On #781, ticket `#451` ("Line-kind gates cache the
repeats answer in both directions") named each component's `update` and
`validate` and nothing about skyscraper; its diff touched **41 files across
six example families**, including the component and four link artifacts a
second worker had already committed to. The cause was one shared
`#include ../_shared/line-kind.js`. The ticket's author could not reasonably
have listed those files, so no amount of care reading the ticket would have
found them. The cost was a forced rebase on an in-flight branch, a harness
denial, and a worker parked for hours.

## The declaration, in `AGENTS.md`

The repo says what its include lines look like and what regenerates from
them. The resolver follows that declaration rather than hardcoding one
repo's convention.

    ## Include closure

    - **Directive**: `#include <path>`
    - **Paths**: relative to the including file
    - **Generator**: `make examples`

- **The heading** is an ATX heading whose text is exactly `Include closure`,
  any level, any case, optional trailing colon. The section runs to the next
  heading of any level.
- **Directive** is a *template*, not a regex: everything but `<path>` is
  matched literally, so a repo writes the line its own files contain —
  `#include <path>`, `{% include "<path>" %}`, `<!-- include <path> -->`.
  `<path>` reaches to the next literal the template names, or to whitespace
  when the template ends there.
- **Paths** says what the reference is relative to: `relative to the
  including file` (the default, and what `../_shared/line-kind.js` means) or
  `repo-root`.
- **Generator** is the command that regenerates. It is **reported, never
  run** — see § Never empirically.
- **A fenced region is quoted, never declared.** Anything between ``` or ~~~
  fences is an example, closing CommonMark's way; this is #890's rule and
  #890's code, imported rather than reimplemented. A doc that shows the
  grammar in a fence — this one does, and so does `AGENTS.md` — has declared
  nothing by showing it.

## Three answers, and the run's opening report says which it got

| The repo's `AGENTS.md` | Mode | What a closure is |
|---|---|---|
| declares a directive | `closure` | the candidate's files, plus every file that includes one of them |
| states `None` | `no-include-graph` | the candidate's own files, and nothing else |
| has no such section | `subtree` | not resolvable; clumping falls back to directory subtree |

The opening report carries the announcement line for whichever it got, in
stated words:

- ``clumping: include closure, from AGENTS.md (directive `#include <path>`, generator `make examples`)``
- `clumping: include closure, from AGENTS.md (declared None: this repo has no include graph, so each candidate closes over its own files)`
- `clumping: conservative, by directory subtree — AGENTS.md declares no include closure, so any two candidates touching the same directory subtree are one clump`

A stated `None` and silence clump the same way on a repo that really has no
include graph, and they are still two different answers. Silence is a gap
somebody should close; `None` is the truth about that repo. A controller
reading "conservative" has to know which one it is looking at, so the report
never collapses them — the same rule #890 set for a ticket that states no
blockers versus one that says nothing at all.

## One hop

The closure is the target files plus every file that **includes** one of
them. One hop, and the second hop is not taken.

That is a stated cost ceiling, not an approximation of a transitive walk. A
second hop is where the graph flattens into most of the repo and stops
separating any two candidates, which is the same failure as clumping
everything together. A repo whose generator really does cascade states that
by naming the hub file as a target.

Forward edges are not followed either: changing a component that includes a
shared snippet does not regenerate the snippet, and does not reach the
snippet's other includers.

## The conservative fallback

With no declaration there is no graph, so two candidates collide when either
one's directory contains the other's — same directory, or one an ancestor of
the other. A candidate touching a file at the repo root therefore collides
with everything. That is the point: conservative means clumping too much,
never too little. Clumping too little is what #781 cost.

## Never empirically

No code path regenerates to find a closure. Touching a candidate's files and
running the declared generator would answer exactly, and it would cost one
regeneration per candidate per wave — the whole queue, re-explored on every
refill. The declaration exists so that one scan of the repo answers for every
candidate at once, and `closure.py` names `subprocess` nowhere, which a test
asserts against its own source.
