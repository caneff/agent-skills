# Where "I merge every code-lane PR" came from

Question (Chris, 2026-09-14): the code lane has Chris approving PRs and running
`merge-cleanup` by hand — was that an Orca restriction?

Answer: yes. The owner-merge step entered with the Orca workspace model and was
carried through the herdr rewrite because that ticket put the hard rules off
the table. No ruling ever chose it on its own merits.

| Date | Commit / issue | What changed |
| --- | --- | --- |
| 2026-08-30 | `1e71e22` (#465) | **Land lane.** On Chris's repos agents land code on `main` via `land`; review is after the fact (`/landed`, `git log -p`, revert). The hard rule becomes "agents never merge a PR" — scoped to *when a PR exists* ("If I say 'make this a PR' → `pushpr`, and I merge"). |
| 2026-09-01 | #489, `ec0c0bd` (#490) | **Orca.** `land`, `pushpr` and `require-worktree` deleted (#489). With no landing script, #490 rewrote Gate 2 so the code lane ends in "PR at the end, and I merge", and added the gotcha that Orca does not remove a workspace after merge. |
| 2026-09-12 | `4fbfd9e` (#699) | CLAUDE.md thinned; the owner-merge wording carried over unchanged. |
| 2026-09-13 | `f9eed03` (#728) | **Herdr.** Orca removed from the lane. #728's rulings list "the hard rules in `CLAUDE.md`" as off the table, so "Code lane: TDD, reviews and a PR I merge" survived. The light tier (documentation label) already lands without a PR. |

`merge-cleanup --help` still describes itself as "the tail Chris hand-ran after
every squash merge".
