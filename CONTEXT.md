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
The single prefilled prompt a worker receives at start, `/implement <n>... --tier light|heavy --controller "<name>"` — every ticket of the clump, lowest first — plus `--chris-merges` when one of them is a `ready-for-human` ticket; the skill supplies everything else.
_Avoid_: prompt, instructions, task description

**Controller**:
The session a worker reports to: the dispatcher that started it, named in its brief by its herdr agent name when it has one (else its session name). A worker resolves that name to the controller's current session name with `resolve-controller` before every send; the session name is never stored, because a restart renames it. It rules on the worker's questions, merges the worker's PR and runs `merge-cleanup` on a repo Chris owns (a `ready-for-human` ticket's merge goes to Chris instead), and escalates to Chris only six things: a spec-ruling change, a new dependency, an irreversible deletion, a repo Chris does not own, a spec gap (the spec is silent on something the user needs), and a lane-mandated step the harness refuses. The last is the one escalation where the controller structurally cannot act. Everything else it rules on itself, against `burndown/SKILL.md` § Before a controller rules.
_Avoid_: coordinator, driver, parent session, owner

**Run**:
One controller session driving N workers, each in its own workspace via `implement-dispatch`, until its queue is empty or it stops. A burn (`/burndown`) and a spec run (`/implement-spec`) are the two kinds.
_Avoid_: burn (one kind of run), batch, session

**Slot**:
One live worker a run may hold. `--slots` caps a run's slots; the box rule bounds the sum across every run on the machine. A nested spec run's slots are debited from the burn that dispatched it.
_Avoid_: builder, lane, parallelism

**Family**:
The tickets of one connected component of a run's file-collision graph. It proves only that clumps sharing a file cannot be live at the same time, not that they ship together: a family runs as its clumps, each held off the frontier while a live workspace shares a file with it. In subtree mode a family is one clump.
_Avoid_: component (the graph term), cluster

**Clump**:
The tickets inside one family whose closures are identical, at most three (`MAX_CLUMP` in `burndown/closure.py`); any other family member is a clump of one. One worker, one workspace, one PR that closes every ticket in it.
_Avoid_: batch, group, cluster

**Tier**:
How much process a ticket's build gets, set at dispatch by its `documentation` label: light (label present; the worker pushes to the default branch, no PR, no reviewer) or heavy (no label; TDD, one review round plus one verification pass, PR). A worker may raise light to heavy, never the reverse.
_Avoid_: lane (that is auto-ship vs code), mode, level

**Front end**:
Where Chris watches workers and their state; herdr. Not where dispatch happens.
_Avoid_: dashboard, viewer, rail

**Wake**:
A worker's report reaching an idle controller as the controller's next turn, about a second after the worker sends it. A controller inside a tool call is not woken; the report waits for the call to return.
_Avoid_: notification, ping, callback

**Live-session guard**:
The refusal in `merge-cleanup` to remove a workspace while a session is alive in it.
_Avoid_: safety check, lock

**Reap**:
`merge-cleanup --reap`: tearing down every workspace of one repo whose ticket landed and whose worker is gone, without anyone naming a branch. A dead controller's leftovers, not a merge's tail.
_Avoid_: sweep (that is every repo under a root), clean up, garbage collect

**Run file**:
One JSON file per run at `~/.cache/burndown/<run-id>.json` holding that run's whole state: run id, slot budget, controller, and per clump its tickets, workspace, herdr agent name and squash sha. What a resumed controller reads instead of its own context.
_Avoid_: progress file, state file, log
