# Friction log

One line per friction point a controller or worker hits, instead of a prevention ticket (ADR 0005). Format: date, repo, what happened, what it cost. Read at retro; a point promoted from here becomes a ticket only on its second occurrence.

- 2026-10-04, agent-skills: the frontier's cross-repo parent line drops the repo (#1288's `--spec 259` names no owner/repo), so the printed handoff command would run against the wrong repo. Cost: a hand check per cross-repo slice.
- 2026-10-04, agent-skills: `loop.py dispatch` prints the plain `implement-dispatch` verb for a spec clump; the controller had to switch to `--spec <n>` by hand. Cost: one wrong dispatch avoided by reading.
- 2026-10-04, agent-skills: a `!` command Chris runs in the controller pane clears the pane's herdr name and session binding; `resolve-controller` then fails until the pane is renamed and the SessionStart hook replayed. Cost: two unreachable-controller episodes.
- 2026-10-04, agent-skills: nothing stops a merge on a non-CLEAN `mergeStateStatus`; the controller merged PR #1376 while it read UNKNOWN. Cost: one unchecked merge (it was clean).
