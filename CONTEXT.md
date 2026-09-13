# Agent skills

The skills, rules, and lane mechanics Chris's agents run under. One context; the terms below are the ones the `/implement` lane and its dispatch contract turn on.

## Language

**Dispatcher**:
The session on the primary checkout's default branch that runs `implement-dispatch` to claim a ticket, create its workspace, and start its worker; it then stays that worker's controller.
_Avoid_: coordinator, driver, parent session

**Worker**:
The interactive Claude session that builds one ticket inside its workspace, from dispatch until the ticket lands on the default branch.
_Avoid_: agent (ambiguous), task, builder

**Workspace**:
A git worktree under `<repo>/.claude/worktrees/<name>` on its own branch, holding exactly one worker.
_Avoid_: worktree (when the herdr pane is meant too)

**Brief**:
The single prefilled prompt a worker receives at start, `/implement <n> --tier light|heavy --controller "<name>"`; the skill supplies everything else.
_Avoid_: prompt, instructions, task description

**Controller**:
The session a worker reports to: the dispatcher that started it, named in its brief. It rules on the worker's questions and escalates to Chris only a spec-ruling change, a new dependency, an irreversible deletion, or a repo Chris does not own.
_Avoid_: coordinator, driver, parent session, owner

**Tier**:
How much process a ticket's build gets, set at dispatch by its `documentation` label: light (label present; the worker pushes to the default branch, no PR, no reviewer) or heavy (no label; TDD, one review round plus one verification pass, PR). A worker may raise light to heavy, never the reverse.
_Avoid_: lane (that is auto-ship vs code), mode, level

**Front end**:
Where Chris watches workers and their state; herdr. Not where dispatch happens.
_Avoid_: dashboard, viewer, rail

**Live-session guard**:
The refusal in `merge-cleanup` to remove a workspace while a session is alive in it.
_Avoid_: safety check, lock
