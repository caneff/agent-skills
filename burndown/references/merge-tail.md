# The merge tail: two branches in the same files

The include closure ([`closure.md`](closure.md)) exists so that two workers
are never dispatched into one file. This file is the tail for when that
failed anyway — a collision found at merge time, after both branches exist.
Until a merge conflicts, the loop's landing step is all there is.

Nothing here is a second review. Both diffs were reviewed on their own
branches; what follows moves one of them onto the other's base without
changing what it says.

## First PR to land wins

The **first PR to land wins**, whichever ticket is lower and whichever branch
started first. The other rebases onto the default branch and catches up. Not
the reverse, and not a negotiation: the landed branch is on `main`, where
undoing it is a revert everybody sees, and the unlanded one is a branch its
own worker can move.

The loser's worker runs it, in its own workspace:

1. `git fetch origin && git rebase origin/<default>`.
2. Resolve each conflict — **generated artifacts by regenerating** (below),
   everything else by hand, keeping both sides' intent.
3. Check the result against what was reviewed:
   `git diff origin/<default>...HEAD` says the same thing the reviewed diff
   said, plus the landed branch's changes, and nothing else. A rebase that
   silently drops a hunk is the failure mode here.
4. Run the tests, then `git push --force-with-lease origin <branch>` — the
   lease refuses if anyone else pushed, and an `implement-*` branch is
   disposable by design.
5. Report the new tip to the controller, with every commit past the last
   reviewed sha named and classed, the same as any "PR up".

Two harness notes, because both cost a worker hours on #781: finishing a
rebase already under way is sanctioned, as is `--force-with-lease` to the
worker's own `implement-*` branch. Neither is a history rewrite that needs
Chris, and a worker parked mid-rebase waiting to ask is the outcome that
carve-out exists to stop.

## Generated artifacts are regenerated, never hand-merged

An artifact conflict is **not resolved by reading it**. Take the default
branch's side of the file and then **regenerate** it from the sources on the
rebased branch:

```
git checkout --ours -- <generated paths>
<the repo's declared Generator command>
git add -A && git rebase --continue
```

The Generator command is the one declared in the repo's `AGENTS.md` § Include
closure, never one remembered from another repo.

`--ours` is the confusing half and it is the right one: **inside a rebase the
sides are inverted**, because git is replaying your commits onto the upstream
— `--ours` is `origin/<default>`, the branch that already landed, and
`--theirs` is the commit being replayed. Taking `--ours` is not the answer to
the merge; it is how the tree gets clean enough to run the generator, which
is the answer.

Hand-merging a generated file produces a tree that no generator run would
produce, and the next run of that generator reverts it — silently, in someone
else's PR. On #781 four link artifacts conflicted this way and regenerating
them took one command; reading them would have taken an afternoon and shipped
a diff nobody could check.

A repo that declares no generator has nothing to regenerate, and its
conflicts are all hand-merges.

## An escaped collision is a defect in the include grammar

A collision that reached the merge tail **escaped the closure**, and that is
a defect in the repo's declared include grammar, not bad luck. File it against
the repo with `/file-ticket` — never an ad hoc `gh issue create`, which leaves
it with no routing role — naming the two files, the two tickets, and which of
the three shapes it was:

- **No declaration.** The repo has no `## Include closure` section in its
  `AGENTS.md`, so the run clumped conservatively by directory subtree and the
  two files were in different subtrees. The ticket adds the section.
- **A directive that missed.** The section exists and the real include line
  does not match its template — a second spelling the repo also uses, or a
  generator that resolves paths some other way. The ticket fixes the
  template.
- **A hub past the one-hop ceiling.** The edge was real and two hops away.
  One hop is a stated cost ceiling, so the fix is not a deeper walk: the
  ticket names the hub file as a target on the tickets that reach it.

Without the ticket the same two files collide on every run, the closure never
learns, and each run pays this tail again.

## Answer, then merge, then cleanup

Every outstanding worker question is answered **before cleanup**, and
**cleanup is the last act** of a landing. The order is exactly that:
answer, then merge, then cleanup. `loop.landing_steps` returns it, and
`python3 burndown/loop.py landing --clump <n> --agent <name> [--outstanding
<question>]` prints what is owed and refuses cleanup while anything is.

The rule is **not merely before the merge**. Merging with a question
outstanding is survivable; `merge-cleanup` is not, because cleanup **closes
its pane** and with it the only channel the answer had. An answer sent
between the merge and cleanup arrives. An answer sent after cleanup is
`No agent named 'implement-454-12' is reachable`, which is exactly what #781
got: `#454`'s worker asked for a ruling in good faith, the controller merged,
cleaned up, and then sent the ruling into a closed pane. Nothing was lost
materially that time. On a longer-lived worker, a question asked and never
answered is a worker that stops asking.

"Outstanding" means asked and not yet answered, whatever the controller
intends to say — including a question the controller means to refuse, and a
question whose answer is "this is filed, build it as it stands". A ruling the
worker never receives is not a ruling.

The same ordering is the single-ticket lane's, at the step that runs cleanup:
[`implement/SKILL.md`](~/.agents/skills/implement/SKILL.md) § The merge.
