# Friction log

One line per friction point a controller or worker hits, instead of a prevention ticket (ADR 0005). Format: date, repo, what happened, what it cost. Read at retro; a point promoted from here becomes a ticket only on its second occurrence.

- 2026-10-04, agent-skills: the frontier's cross-repo parent line drops the repo (#1288's `--spec 259` names no owner/repo), so the printed handoff command would run against the wrong repo. Cost: a hand check per cross-repo slice.
- 2026-10-04, agent-skills: `loop.py dispatch` prints the plain `implement-dispatch` verb for a spec clump; the controller had to switch to `--spec <n>` by hand. Cost: one wrong dispatch avoided by reading.
- 2026-10-04, agent-skills: a `!` command Chris runs in the controller pane clears the pane's herdr name and session binding; `resolve-controller` then fails until the pane is renamed and the SessionStart hook replayed. Cost: two unreachable-controller episodes.
- 2026-10-04, agent-skills: nothing stops a merge on a non-CLEAN `mergeStateStatus`; the controller merged PR #1376 while it read UNKNOWN. Cost: one unchecked merge (it was clean).
- 2026-10-04, agent-skills: drain's headless `claude -p` build exits when `/implement` ends its turn to wait on a background reviewer; #1219's build died at 22 minutes with no PR and drain retried into the same failure. Stopping the run (`kill` on the drain job this session launched) was denied by auto mode as [Interfere With Workloads]. Cost: about 25 minutes of build, and a kill handed to Chris. Fix in #1415.

Commit each line on its own with the subject `friction: <what happened>`.
A burn's closing report counts them by that subject; the rule is
`burndown/SKILL.md` § The friction log.
