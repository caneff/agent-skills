# The whole process, redesigned (draft for Chris, 2026-10-04)

One page: every stage from idea to merged code, what it is today, what it
should be, what gets deleted. Evidence: `docs/research/2026-10-04-agent-workflow-prior-art.md`,
`docs/research/2026-10-04-agent-ticket-inflation.md`, the review ledger
baseline. Nothing here is applied yet except where marked.

## The principle

The process exists to get Chris's work built. Today 77% of tickets are about
the process itself. Every stage below is cut to the smallest thing that
still catches real failures, and the process changes only by removing a part
and measuring what breaks, never by adding a part per incident.

## Stage by stage

| Stage | Today | Proposed | Deleted or frozen |
|---|---|---|---|
| **1. Capture** | Reviews, controllers, workers and the weekly retro each file a ticket per observation. 295 filed in 14 days. | A ticket is something Chris wants built. Agents add to an open ticket for the same component rather than file (applied, 9599e2f). Friction goes in one log. The retro reports; it files nothing. | Prevention tickets; retro-filed tickets; per-PR sweeps. |
| **2. Plan** | Non-trivial work: grill, spec, slice into 5-7 tickets plus a closing ticket. | Most work is one ticket. A spec only when the work needs more than one session; slice only into pieces that touch different files and can run at once. The closing check runs in the last slice. | Closing tickets; slicing for its own sake. |
| **3. Dispatch** | A burn controller per repo: frontier, closure, clumping, tiering, box check, run file, herdr naming, alerts, adoption after restarts. | One agent per ticket in its own worktree, started by one command. A burn only when there are 5+ independent tickets, and its controller does not relay anything to Chris except a real decision. | Most of burndown's run-file and liveness machinery, after ablation. |
| **4. Build** | Worker does TDD in a worktree. | Unchanged. This part works. | Nothing. |
| **5. Review** | Up to five passes in sequence: three axes, verification, Codex, Codex again. Findings over a size bar become leftovers. | One wave: the axes, plus Codex on big PRs, in parallel. The worker fixes every finding. A script checks each fix is a real commit. The test suite is the last check. (Ruled; #1401.) | Verification pass; Codex pass 2; leftovers; sweeps; the adjacency checker; most of the review ledger. |
| **6. Merge** | Controller: labels, CLEAN, verification check, Codex, seam in a scratch worktree, squash, merge-cleanup. | The same gate minus the removed passes: CLEAN, the fix check, the seam, squash, cleanup. Chris reads `/landed` after. | The Codex-at-merge step (moves into the wave). |
| **7. Learn** | Weekly retro adds a rule per failure; ~4,700 words loaded every session until today's split. | A rule only on a failure's second occurrence (applied, e1a2644). Always-on text stays near today's ~2,800 words. Twice a month, switch one process part off and count what breaks. | Rule-per-incident. |
| **8. Harness** | Auto mode denials on any edit to settings, hooks or instruction files; workers dispatched into harness work stall. | Harness work happens in a session outside auto mode, with Chris approving each step. Auto mode's soft-deny list stays as set today. | Dispatching harness tickets to auto-mode workers. |

## What Chris sees

- Today: denials, stop alerts, decisions about the process, questions about cleanup.
- Proposed: a `/landed` read after merges, a decision only when a choice is contested or cannot be undone, and one short report when a burn closes.

## Order of work

1. Stages 1 and 7: done today; nothing more to build.
2. Stage 5: #1401 (already filed).
3. Stage 2: a one-paragraph change to `to-tickets` and `implement-spec`.
3a. Stage 3's everyday command is built: `drain/drain.py` (#1403) works the ready queue serially, one agent-chosen bundle of tickets per PR, and replaces the burn for everyday use.
4. Stage 3: ablate the burn machinery last, once stages 1, 2 and 5 have cut the ticket flow. What survives is kept.

## Ruled 2026-10-04 (Chris)

- Serial is acceptable: "a sensible way to address open issues automatedly without all this extra crap ... even if it is more serial and less parallel". Built as `drain`, #1403.
- The unit of work is a bundle, not a ticket (worker-chosen, ruled "y" 2026-10-04 over directory bundles): "serial is impossible if we keep filing nitpicky small tickets ... make sure all tickets are meaty enough". `drain` hands the agent the oldest ticket plus every ready title, and the agent takes up to 8 it would fix in the same PR, so small tickets are fine to file and are done together.
- Wording tests are deleted: "wording is shit tests" (#1414).
- Each merge runs only the tests for what it touched; one full suite per drain run: "yes" (#1415).
