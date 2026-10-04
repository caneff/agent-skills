# Friction log

One line per friction point a controller or worker hits, instead of a prevention ticket (ADR 0005). Format: date, repo, what happened, what it cost. Read at retro; a point promoted from here becomes a ticket only on its second occurrence.

- 2026-10-04, agent-skills: the frontier's cross-repo parent line drops the repo (#1288's `--spec 259` names no owner/repo), so the printed handoff command would run against the wrong repo. Cost: a hand check per cross-repo slice.
- 2026-10-04, agent-skills: `loop.py dispatch` prints the plain `implement-dispatch` verb for a spec clump; the controller had to switch to `--spec <n>` by hand. Cost: one wrong dispatch avoided by reading.
- 2026-10-04, agent-skills: a `!` command Chris runs in the controller pane clears the pane's herdr name and session binding; `resolve-controller` then fails until the pane is renamed and the SessionStart hook replayed. Cost: two unreachable-controller episodes.
- 2026-10-04, agent-skills: nothing stops a merge on a non-CLEAN `mergeStateStatus`; the controller merged PR #1376 while it read UNKNOWN. Cost: one unchecked merge (it was clean).
- 2026-10-04, agent-skills: drain's headless `claude -p` build exits when `/implement` ends its turn to wait on a background reviewer; #1219's build died at 22 minutes with no PR and drain retried into the same failure. Stopping the run (`kill` on the drain job this session launched) was denied by auto mode as [Interfere With Workloads]. Cost: about 25 minutes of build, and a kill handed to Chris. Fix in #1415.
- 2026-10-04, sudokumaker-custom-constraints: block-dangerous-git.sh refused `git -C .scratch/mutation-m1 checkout -q -- .` inside a throwaway mutation worktree during #668's mutation check (spec-649-smcc). The worker parked; #659, #660 and #673 sat behind it. Cost: about 20 hours of wall clock until Chris ruled fresh-worktree-per-mutation; the hook change is ticketed separately.
- 2026-10-04, sudokumaker-custom-constraints: loop.py dispatch's live-workspace check compares files only, so three times (spec-649-smcc) a clump whose candidate list named whole directories was offered a slot beside a live worker editing files inside them; #666 and #655 ended up sharing five files. Cost: four hand diffs of live workspaces and six overlap notices to workers. Already #1406 C1 (evidence comment added).
- 2026-10-04, sudokumaker-custom-constraints: implement/SKILL.md and runfile.py changed mid-run (#1401): verification-check.sh and `runfile.py leftover` vanished between one merge and the next in spec-649-smcc, and 46 leftovers recorded under the old rule are now swept by nothing. Cost: two refused commands at merge time and an orphaned-findings decision for Chris.

Commit each line on its own with the subject `friction: <what happened>`.
A burn's closing report counts them by that subject; the rule is
`burndown/SKILL.md` § The friction log.
