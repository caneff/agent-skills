# Another prose rule against coined labels in Quill replies

Quill replies sometimes coin a short label ("forced 7 vs any 7", "low options") and use it without saying what it means. `flow/claude/output-styles/quill.md` already requires a gloss on a coined label's first mention. The request was to tighten that prose: always use the literal description, or define the label every time it appears.

## Why this is out of scope

The request's own evidence is that the existing prose rule did not change behaviour. A stricter wording of the same rule is the same kind of fix, and nothing suggests it would land where the first did not. A rule here is worth shipping only with a mechanism behind it (`AGENTS.md` § Recurring defect classes, class 2). No one has named a check that could detect a coined label in a reply.

A future request should name that mechanism, such as a hook or a review pass that flags a reply's undefined label. Without one, it repeats this rejection.

## Prior requests

- #1706 — "Quill: stop unexplained coined labels"
