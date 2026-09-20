# The three defect classes this repo keeps shipping

Not a style guide. Three specific shapes that have each been caught more than
four times in this repo since 2026-09-14, every one of them in code written
to prevent the thing it failed at. They are listed here so a worker and a
review axis can check for them by name instead of rediscovering them.

Each entry gives the shape, the check that finds it, and the instances. The
instance lists are the point: this is not a theory about what might go wrong.

## 1. An absent or malformed answer read as a benign one

The most expensive class by a wide margin. A value that is missing, empty,
unreadable, or the wrong type takes the code's happy path instead of its
error path, and the result looks like a clean answer.

**The check.** For every input that can be absent or malformed, ask what the
code does with it, and require that the answer is *refuse and name it*, not
*continue with a default*. Zero, empty, `None`, `""`, exit status discarded,
and "no matches found" are the values to hunt. Ask specifically: **could this
success have been produced by the thing not running at all?**

**Instances.**

- `#892` — a vanished clump counted as a free slot, so a resumed controller
  refilled into a slot whose worker might still hold its tickets.
- `#893` — `paths()` called `set()` on any truthy closure, so a malformed
  string became a set of its characters and intersected no real path set:
  the clump read as colliding with nobody.
- `#894` — `--declared` defaulted to `""`, so a missing core declaration was
  charged as zero cores. One layer up, the same skill's Liveness section
  says it in words: *silence is not zero*.
- `#897` — one invalid `built_by` raised on the first entry, so a single
  malformed decision suppressed every real contradiction.
- `#899` — the lane sweep discarded `grep`'s exit status: a tree with 380
  unreadable files printed "409 files swept" and a clean lane.
- `#899` — the reachability assertion was a substring search over
  concatenated prose, and the doc names the module paths itself, so it
  passed with all three modules deleted.
- `#937` — the capture guard tested for *absence* when the hazard was
  *wrongness*: a replaced-but-non-empty patch read as valid.
- `#944` — the cross-reference gate for section headings prints real misses
  and exits 0, so `tests/all.sh` counts it green.
- `#946` — an unreadable ignored directory could read as "holds nothing",
  which would approve a destructive removal on a permission error.
- `#950` — the retry that runs *because* the early pass degraded was the one
  path with no exit-status capture, no record and no validation.
- `#951` — `codex-companion.mjs` advertises `--background` on reviews,
  parses it, and never reads it: a documented flag accepted and ignored.

## 2. A stated fallback with no mechanism behind it

A doc, ticket or comment states a rule, and nothing can carry it out. It
reads as policy and is decoration. These survive review because the sentence
is true-sounding and nobody runs it.

**The check.** For every "otherwise", "falls back to", "if absent", and
"every run must" — find the code path that does it. If the answer is a
paragraph rather than a line of code or a test, it is this class.
**A rule is not shipped until something can carry it out.**

**Instances.** `#888` (a rule justified only incidentally), `#877` (a guard
that cannot tell a citation from a use), `#911` (a `--blocked-by` fallback no
code path reached), `#897` (a closing ticket naming a review procedure no
skill could execute), `#950` ("every run records its duration" stated three
lines above the block that could not).

## 3. A test that passes for a reason other than the one it claims

The witness check exists for this, and the check itself is subject to it. A
mutation turning a suite red proves *something* broke, not that *your*
assertion caught it.

**The check.** When a mutation goes red, read the failure message and confirm
it is the assertion you meant. When one goes green, confirm the test could
ever have failed. Ask whether the fixture was built from the answer.

**Instances.**

- `#932` — the `cp -a` mutation went red because the recipe extraction keyed
  on the line the mutation deleted, so the block was never found. True
  status, false reason, one step from being reported as proof.
- `#932` — the ordering fixture named its shas in the answer's own order, so
  replacing the sort with `cat` stayed green.
- `#932` — a refusal guard whose only witness requires root, so the case it
  guards cannot be reached in the test environment.
- `#869` — a merge-commit refusal test passed because a different guard
  ("changes no files") caught it first.
- `#899` — see class 1: the first reachability draft.

## Why these three and not a longer list

Each has recurred after being fixed somewhere else in the same tree, which is
what distinguishes a class from a bug. Two of them have been reintroduced by
their own fixes (`#890`'s fence fix, `#892`'s F3 fix), which is why the
two-round review ceiling earns its cost on re-introduction rather than on
first discovery.

Filed from the map #776 build and its follow-up wave, 2026-09-14 to 09-20.
