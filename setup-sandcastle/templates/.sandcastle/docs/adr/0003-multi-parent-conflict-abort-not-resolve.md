# Multi-parent base conflict: abort-and-surface, don't auto-resolve

## Status

accepted

## Context

An issue with ≥2 declared parents (a diamond) is built on a temp base merging every parent's branch (`buildMultiParentBase`, `.sandcastle/base-resolution.mts`). When two parents edit the same lines, that merge conflicts and the function returns `null`. Parent branches are static across the iterations of a run, so the merge conflicts *identically* every iteration; the planner re-selects the issue, the caller re-skips it, and the run burns every remaining iteration making zero progress (issue #64: #62 re-skipped 3/20, 4/20, 5/20…).

The conflict is a decision about the *parents*, not the child: #60 and #61 conflict with each other (both edit one `CLAUDE.md` bullet); #62 is only the downstream that needs both.

## Decision

On a deterministic multi-parent base conflict, **abort the issue for the rest of the run and surface it for a human** — do not attempt to auto-resolve the merge.

- **In-run block, no persistent state.** A `blockedThisRun` Set (host-side, authoritative) records the issue on the first `null` base; blocked ids are dropped from `work` after planning. A `BLOCKED_THIS_RUN` list is also fed to the planner (mirroring `COMPLETED_THIS_RUN`) so it stops re-selecting the issue — the Set is the hard gate, the planner list is the optimization. No GitHub label is written; the block evaporates next run.
- **Self-healing across runs.** One attempt per run. Once a human merges the conflicting parents into `main`, the base resolves to plain `main` and the child builds cleanly — no orchestrator change needed.
- **Human surface.** A distinct `blocked-parent-conflict` bucket in the end-of-run Run Summary (`reconcile.mts`) names the conflicting parents ("#62 blocked — parents #60, #61 conflict; merge upstream first"). The mid-run `console.error` stays as the trace; the summary is the durable, human-read surface.

## Consequences

- Trade-off is **autonomy vs. honesty**. We give up building the child this run in exchange for not inventing an unreviewed resolution.
- Rejected alternative — **auto-resolve the conflict** (hand the conflicted worktree to an agent, commit the merge on the temp base): the resolution is ephemeral (the base is rebuilt every run), so it fixes nothing durable — the *real* conflict still awaits a human when #60 and #61 merge into `main`. It also entangles an unrelated `CLAUDE.md` merge into the child's diff (defeating the rebase-not-merge discipline the child's branch relies on) and silently auto-edits project instructions with no human in the loop. Auto-resolve would only pay off for frequent, mechanical, *persisted* conflicts — none of which holds here.
- Rejected alternative — **persist a cached resolution** keyed on parent tips: every-run rebases move parent tips constantly, so the cache mostly misses; a stale key risks basing the child on wrong parents (the failure #128 hardened against). Not worth a caching layer whose main new risk is a silently-wrong base.
- Rejected alternative — **a persistent `blocked-needs-human` label**: the pathology is burning *iterations within a run*, not re-attempts across runs. A label needs an un-block rule (when do parent tips change enough to retry?) that in-run memory sidesteps entirely.
