# The include closure: what a change really touches

A **family** is one connected component of a run's file-collision graph,
and a **clump** — one worker, one workspace, one PR — is the family members
whose closures are identical (§ Families run as clumps). The graph is built
on each candidate's **include closure**: the files a change to the
candidate's target files actually regenerates. Reading it is
`burndown/closure.py` — `python3 burndown/closure.py [--json] <repo-root>
<n>=<path>[,<path>]...`, or `clumps(root, candidates)` in process.

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
- **`None`** is the stated way to say this repo has no include graph at all:
  the word, ending its clause — `None`, `None — nothing here is generated.`
  A sentence that merely *starts* with it, like `None of the docs are
  generated, but examples/ are`, states nothing this grammar can read, and is
  read as silence rather than as "no include graph". Reading it the other way
  clumps every candidate alone and puts two workers in the same files.
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

In `subtree` mode a clump carries **no closure at all** — only the files its
tickets named. Handing a consumer those files under the name `closure` would
hand back the declared seams this whole reader exists to stop trusting.

The opening report carries the announcement line for whichever it got, in
stated words:

- ``clumping: include closure, from AGENTS.md (directive `#include <path>`, generator `make examples`); each family runs as clumps of identical closures``
- `clumping: include closure, from AGENTS.md (declared None: this repo has no include graph, so each candidate closes over its own files); each family runs as clumps of identical closures`
- `clumping: conservative, by directory subtree — AGENTS.md declares no include closure, so any two candidates touching the same directory subtree are one clump, and a family is never split`

A stated `None` and silence clump the same way on a repo that really has no
include graph, and they are still two different answers. Silence is a gap
somebody should close; `None` is the truth about that repo. A controller
reading "conservative" has to know which one it is looking at, so the report
never collapses them — the same rule #890 set for a ticket that states no
blockers versus one that says nothing at all.

## Families run as clumps

A connected component proves one thing: two of its tickets that share a file
cannot hold live workspaces at the same time. It does not prove they ship
together. On `burn-2026-09-21-0930` the 27 remaining tickets chained through
hub files — `implement/SKILL.md`, `burndown/loop.py`, `AGENTS.md`,
`tests/all.sh` — into one component of 34 files. Read as one clump, the loop's
only move was one worker holding 27 tickets in one context, one branch and
one PR (#970).

So a component is a **family**, and it is split:

- A **clump** is the family members whose closures are **identical**, lowest
  ticket first, at most `MAX_CLUMP` (3) of them. Identical closures would
  only rebase onto each other, so one worker takes them. The cap keeps that
  worker inside one context: a heavy build is TDD plus three review axes, a
  verification pass and a Codex round per ticket. The 3 is a controller's
  guess from 2026-09-21 with no measurement behind it. A run that hits it
  should move it with evidence, not work around it. The render says
  `identical closures split at MAX_CLUMP=3` on any family it cut.
- Every other member is a clump of one.
- **Serializing needs no new mechanism.** `loop.py dispatch` already holds
  a clump whose closure intersects a live workspace's, and `picks` never
  takes two clumps sharing a file in one tick. So the loop dispatches the
  lowest free clump of a family, and those two keep back every clump that
  shares a file with it. Two family members that share no
  file can run together. The invariant is "no two live workspaces share a
  file", not "one live member per family".
- **A `subtree`-mode family is never split.** There, two tickets are in a
  family because their directories overlap, not their files. The dispatch
  hold compares files, so splitting would let two workers into one
  directory.

`--json` prints every family's clumps as one list, in the shape `loop.py
dispatch --candidates` reads, and the announcement on stderr. That way a
redirect into the candidates file leaves the report line on the terminal.

## What the scan reads

One scan of the repo answers for every candidate. In a Markdown file a fenced
block is quotation by definition, so a doc that *shows* the repo's include
line — this one does — registers no edge. Everywhere else every line counts:
a ``` line in source code means nothing in particular, and reading it as a
fence would hide the real directives after it, which is the under-clumping
direction. A file that does not read as text, and the directories in `SKIP_DIRS`
(`.git`, `node_modules`, `__pycache__`, `.claude`), hold no directives.

Everything else about the scan **fails closed**, because the direction it
would fail in is under-clumping — a missing edge, and two workers in the same
files. Every file is read whole, with no truncation: a repo's minified bundle
is a single enormous line megabytes long, so any cutoff lands somewhere
arbitrary with respect to content, and a directive past it would read as
absent. A file past the 32 MB memory ceiling, a file that cannot be opened,
and a directory that cannot be listed each **fail the resolve** and name
themselves, rather than dropping quietly out of it. A closure resolved from a
scan that partly failed is a precise-looking answer with a hole in it, and
the hole is where two workers meet.

A candidate's files get one spelling, whatever the ticket wrote: `./a/x.js`,
`a//x.js` and an absolute path inside the repo are all `a/x.js`. Two
spellings of one file collide with nobody, which is the same silent
under-clumping by another route. A path that leaves the repo is refused, not
guessed at.

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
