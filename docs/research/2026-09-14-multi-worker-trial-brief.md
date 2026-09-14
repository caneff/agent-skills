# Multi-worker trial: controller briefs

Hand-written run briefs for the trial on the herdr lane ([agent-skills #781](https://github.com/caneff/agent-skills/issues/781)), written from the map's decisions ([#776](https://github.com/caneff/agent-skills/issues/776)) because `burndown` and `implement-spec` are still parked. Each brief is pasted whole into a fresh Claude session opened on the target repo's primary checkout, on its default branch. Chris watches in herdr and merges.

Order: the spec run first; the burn once `implement-dispatch --spec` ([#787](https://github.com/caneff/agent-skills/issues/787)) has landed and the spec run has settled.

## Brief 1: spec run

```
You are the Controller of a spec run: /implement-spec by hand, before the skill is written. Terms (Run, Slot, Clump, Worker, Controller, Wake, Workspace) are in ~/.agents/skills/CONTEXT.md; read it first. Read ~/.agents/skills/implement/SKILL.md § Dispatch, § Control and § The PR so you know what a worker does and sends. Record what hurts as you go: every rough edge is a comment on https://github.com/caneff/agent-skills/issues/781, one per comment, as it happens, not at the end.

Target: spec #366 (Up to N) in caneff/sudokumaker-custom-constraints. Primary checkout: /home/caneff/src/sudokumaker-custom-constraints (you are in it, on the default branch). Slots: 5.

1. Exploration pass, once, before any dispatch. Run one in-process Explore subagent (Agent tool, subagent_type Explore, model sonnet). Its brief: read the spec and every open child ticket end to end plus every "Settled:" comment on them; for each ticket list the files it would touch (by name), its size tag (docs-only, one-file, multi-file) and its collisions (a file two tickets both touch); check every settled decision that asserts runtime behaviour against the code and quote the implementing line anchored on a name, never a bare line number; write the whole thing to ~/.cache/burndown/sudokumaker-custom-constraints.notes.md with one section per ticket whose heading starts exactly `## #<n>` and one section headed exactly `## Collisions`; return a summary under 40 lines. A decision the code contradicts is a ruling for Chris: post it on the ticket before dispatching that ticket, and wait for his answer.

2. Clump. Draw the collision graph over the open children and take its connected components. Each component is one Clump: one worker, one workspace, one PR closing every ticket in it. Write the clumps under `## Collisions` in the notes file, each with its tickets in number order and the union of their files.

3. Closing ticket. Create one more child of the spec now, titled "Spec close: end-to-end test and spec-level review", labelled ready-for-agent, blocked by every other open child (native blocked-by edges; the tracker doc at ~/.agents/skills/docs/agents/issue-tracker.md has the gh api call). Its body: write one end-to-end test over the whole spec's acceptance criteria if none exists, run the repo's full test seam, review the whole landed range since the spec's first slice with /multi-axis-code-review, fix or file every finding, and close the spec issue in the PR body. It is a ticket like any other; the loop reaches it last.

4. The loop. The frontier is: open children of the spec, labelled ready-for-agent, with no open blocker and no assignee, grouped by clump, lowest ticket number first. While there is a frontier clump and a free slot:
   - Run `uptime` and `free -g`. If the 1-minute load is above 24 or free memory is under 6 GB, dispatch nothing and record it as a hurt.
   - `implement-dispatch --repo /home/caneff/src/sudokumaker-custom-constraints <lowest ticket in the clump>` (add `--model opus` when the notes tag it multi-file). Relay its report line. If the clump has more than one ticket, immediately SendMessage the new worker (its agent name is in the dispatch report) with: the other ticket numbers in number order, one commit per ticket carrying that ticket's `Closes #<n>`, the clump's own files, and the notes file path with the `## #<n>` headings to read. Record whether that message was enough as a hurt or a non-hurt.
   - Append `burning #<n>` for each ticket in the clump to ~/.cache/burndown/sudokumaker-custom-constraints.progress.
   Then end your turn. Your wait is going idle. Never sit in a long tool call, a sleep, a blocking wait or `herdr agent wait` while workers are out: their messages are held until the call returns.

5. On every wake (a worker's message is your next turn):
   - A question: rule on it yourself under the Controller entry in CONTEXT.md; escalate to Chris in your terminal only a spec-ruling change, a new dependency, an irreversible deletion. Answer the worker by SendMessage to its name.
   - "PR up": print the worker's two `! ` lines to Chris exactly as sent, append `#<n> pr <url>` for each of its tickets to the progress file, then run `python3 ~/.agents/skills/burndown/cost.py <workspace path>` and append `<n> <builder> <review> - 0` to ~/.cache/burndown/sudokumaker-custom-constraints.cost (first ticket of the clump gets the numbers, the rest get 0).
   - After Chris says merged (or `gh pr view <pr> --json state` shows MERGED on a later wake): append `#<n> landed <sha>`, then re-run step 4.
   - Before ending any turn with workers out, check each live worker with `herdr agent get <agent>`. One that is gone with no report is parked: comment on its ticket what was found, swap in-progress to ready-for-human, append `#<n> parked: <why>`, and tell Chris in your terminal. Two consecutive parks with no landing in between stop the run: append `done`, report, end.

6. When the closing ticket's PR is merged: append `done`, post a final comment on https://github.com/caneff/agent-skills/issues/781 with the tally (tickets landed, parked, dispatches, wakes, box checks that refused, and the hurt list in one place), and stop.

Rules that stand throughout: you never merge; you never edit code in /home/caneff/src/sudokumaker-custom-constraints; every question a worker asks that times out is the worker's to answer safely, not yours to chase; a worker's report that arrives cut off is read from the file it names.
```

## Brief 2: burn

Written after brief 1 has run and #787 has landed. The burn is brief 1's loop over a mixed `ready-for-agent` queue with a ticket cap of 15, plus: a ready ticket whose parent carries the `spec` label is dispatched as `implement-dispatch --spec <parent> --slots <k>` with k debited from the burn's free slots, counts against the cap as its number of open slices, and reports back as one unit.
