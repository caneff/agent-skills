# Parent liveness is gated on issue state, not branch content

## Status

accepted

## Context

Base resolution asked one question about each declared parent: does `sandcastle/issue-<n>` exist locally with commits not already in `main` (`branchExistsWithWork`, `.sandcastle/base-resolution.mts`)? A parent that answers yes is merged into the child's base — for a diamond, into the temp base `buildMultiParentBase` builds.

A closed issue can answer yes forever. In the run of 2026-08-09 (issue #127), #107's parent #101 was closed and shipped, but its branch survived and its tip `ff2f3b6` matched nothing on `main` by content: the feature had landed as a **from-scratch reimplementation**, not a squash of that branch. `git cherry main sandcastle/issue-101` reported `+ ff2f3b6`, and patch-id had nothing to match. So the predicate called #101 live, the base absorbed a superseded implementation of the layers feature, and at PR assembly that base collided with the real implementation on `main`. #107 produced zero PRs, and would have on every subsequent run until the branch was deleted by hand.

Content is the wrong evidence here. Unmerged-by-content is exactly what a superseded branch and a live branch both look like; no comparison of commits can separate them.

## Decision

**A parent whose issue is closed is never live work, whatever its branch's commits say** — and a closed issue's branch is garbage-collected so the question stops arising.

- **State is asked first.** `isLiveParent` is `!issueIsClosed(id) && branchExistsWithWork(id)`, applied in both the 1-parent path and the diamond's `present` filter. A closed parent drops out and the child bases on `main`, which is where that parent's work actually lives.
- **GC at run start.** `staleClosedBranches` names the local `sandcastle/issue-<n>` refs whose issue is closed, and the orchestrator deletes them before any branch is cut. Local refs only: base resolution reads local refs, and deleting someone's remote branch is a human's call.
- **The state query fails OPEN.** If `gh` cannot list closed issues, the closed set is empty and liveness falls back to branch content for that run. Failing closed would call every parent dead and base the whole forest on `main` — a wrong answer for every issue, to avoid a wrong answer for one.

## Consequences

- Two mechanisms guard one bug, deliberately. GC clears the branches that exist at run start; the predicate catches a parent closed *during* a run, which GC cannot see.
- The orchestrator now spends one `gh issue list --state all` per run on issue state, memoised and shared with the spent-parent check.
- Rejected alternative — **match by patch-id / `git cherry`**: the two implementations of the layers feature differ, so there is no patch to match. This fails precisely in the case that caused the bug.
- Rejected alternative — **GC alone**. It would have unblocked #107, but a parent closed mid-run still slips through, and any run against a repo whose branches were never swept starts poisoned.
