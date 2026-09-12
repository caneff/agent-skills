# Agent skills

The skills, rules, and lane mechanics Chris's agents run under. One context; the terms below are the ones the `/implement` lane and its dispatch contract turn on.

## Language

**Dispatcher**:
The session on the primary checkout's default branch that claims a ticket, creates its workspace, starts its worker, reports, and stops.
_Avoid_: coordinator, driver, parent session

**Worker**:
The interactive Claude session that builds one ticket inside its workspace, from dispatch until Chris merges and closes it.
_Avoid_: agent (ambiguous), task, builder

**Workspace**:
A git worktree under `<repo>/.claude/worktrees/<name>` on its own branch, holding exactly one worker.
_Avoid_: Orca workspace, worktree (when the herdr pane is meant too)

**Brief**:
The single prefilled prompt a worker receives at start, `/implement <n>`; the skill supplies everything else.
_Avoid_: prompt, instructions, task description

**Front end**:
Where Chris watches workers and their state; herdr. Not where dispatch happens.
_Avoid_: dashboard, viewer, rail

**Live-session guard**:
The refusal in `merge-cleanup` to remove a workspace while a session is alive in it.
_Avoid_: safety check, lock
