# Agent skills

The skills, rules, and lane mechanics Chris's agents run under. One context; the terms below are the ones the `/implement` lane and its dispatch contract turn on.

## Language

**Dispatcher**:
The session on the primary checkout's default branch that runs `implement-dispatch` to claim a ticket, create its workspace, and start its worker; it then stays that worker's controller unless its session exits, when another session may adopt the worker (`controller-adopt`).
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
The session a worker reports to: the dispatcher that started it, or the session that adopted it once that dispatcher's process exited (`controller-adopt`, #1098), named in its brief by its herdr agent name when it has one (else its session name). A worker resolves that name to the controller's current session name with `resolve-controller` before every send — the two-hop mechanism is `implement/SKILL.md` § Control, the one place that states it. It rules on the worker's questions, merges the worker's PR and runs `merge-cleanup` on a repo Chris owns (a `ready-for-human` ticket's merge goes to Chris instead), and escalates to Chris only six things: a spec-ruling change, a new dependency, an irreversible deletion, a repo Chris does not own, a spec gap (the spec is silent on something the user needs), and a lane-mandated step the harness refuses. The last is the one escalation where the controller structurally cannot act.
Everything else it rules on itself, against `implement-spec/SKILL.md` § Before a controller rules.
_Avoid_: coordinator, driver, parent session, owner

**Run**:
One controller session driving N workers, each in its own workspace via `implement-dispatch`, until its queue is empty or it stops. A spec run (`/implement-spec`) is the only kind; `drain` works unrelated tickets serially and is no run.
_Avoid_: burn (retired), batch, session

**Slot**:
One live worker a run may hold. `--slots` caps a run's slots; the box rule bounds the sum across every run on the machine.
_Avoid_: builder, lane, parallelism

**Family**:
Retired with the grouping code (spec #1634, ruling 1): `closure.py` no longer computes connected components. Prose that says "family" means the clumps one hot file holds off the frontier together.
_Avoid_: component (the graph term), cluster

**Clump**:
One slice's slot in a run: `closure.py` makes each candidate its own clump in every mode. One worker, one workspace, one PR; a ticket-list clump from an older run file may still hold several tickets.
_Avoid_: batch, group, cluster

**Anchor**:
The oldest unblocked `ready-for-agent` ticket or clear spec parent (or the one `--anchor` names), which `drain` (`drain/drain.py`) builds first. A one-turn session adds the other ready tickets it would naturally fix in the same PR, and `drain` starts the bundle through `implement-dispatch`.
_Avoid_: seed, lead ticket

**Bundle**:
The anchor plus the tickets the agent chose to fix with it, at most `--bundle-max` (8): one agent, one worktree, one PR that closes every one, one review wave. A one-turn session chooses it after reading the queue; `drain` groups nothing by directory or closure. A spec parent is a bundle of its own: the spec and all its slices, built by one `implement-dispatch --spec` run. Unlike a clump, which is one slice's slot in a spec run.
_Avoid_: clump (a spec run's term), batch

**Tier**:
How much process a ticket's build gets, set at dispatch by its `documentation` label: light (label present; the worker pushes to the default branch, no PR, no reviewer) or heavy (no label; TDD, one review wave and the fix round, PR). A worker may raise light to heavy, never the reverse.
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

**Integration branch**:
`spec-<n>`, the branch a spec run with more than one slice builds its spec on: cut from `origin/<default>` by `implement-dispatch --spec <n>`, the spec run's own workspace branch. Its slices branch from it and merge into it with no review wave; the default branch is merged in, never rebased; one review and one fix round run on it; one integration PR takes it to the default branch, closing every slice and the spec (ADR 0006).
_Avoid_: feature branch, spec branch, staging branch

**Run file**:
One JSON file per run at `~/.cache/spec-run/<run-id>.json` holding that run's whole state: run id, slot budget, controller, and per clump its tickets, workspace, herdr agent name and squash sha. What a resumed controller reads instead of its own context.
_Avoid_: progress file, state file, log

**Sweep**:
One pass of `all-audits/driver.py` over one repo: the audits it plans and runs, collected under one run folder with an `index.html`. A `--multi` pass is one sweep per repo, each from a fresh worktree of that repo's `origin/main`. The glossary reserves **Run** for a spec run, so a sweep is never called a run.
_Avoid_: run, scan, batch

**Stored sweep**:
A finished sweep copied to `~/.local/share/all-audits/<repo>/<sweep-id>/` (its `collection/` and `logs/`), outside the cache that prunes run folders after three days. The only form of a sweep that outlives the cache.
_Avoid_: archive, saved run, cached sweep

**Audit record**:
The GitHub issue a `--multi` sweep opens in the swept repo, labelled with its triage label, holding every finding and every fact about the sweep as text (body, then ordered comments past GitHub's length limit). One per repo per sweep, and only when the sweep found something or an audit failed. Its stored sweep keeps the issue number in `audit-record.json`; closing it, which `/all-audits triage` does, frees that stored sweep for deletion.
_Avoid_: report (one audit's HTML), manifest (one audit's `claude -p` answer), finding (one row inside a record)
