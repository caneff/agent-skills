# The loop: why each rule reads the way it does

`burndown/SKILL.md` § The loop: that is the step list. This file is the evidence
behind it — what a run got wrong by hand, and what the rule costs when it is
read the other way. `burndown/loop.py` is the reader that applies the
mechanical half.

## Where the controller sits

The loop refuses to run from a linked worktree, and says so. Inside one,
`/implement`'s front-door rule reads the session as a **worker**: the same
prompt that starts a controller starts a build instead, on the branch that
worktree holds. The check is `--absolute-git-dir` against `--git-common-dir`,
not the path's spelling, and the branch is checked against
`refs/remotes/origin/HEAD` rather than against `main` — a repo whose default
branch is `trunk` is a checkout, not an exception.

The checkout the controller sits in need not hold the repo the run targets. A
run against `caneff/sudokumaker-custom-constraints` is driven perfectly well
from `agent-skills`'s default branch; every tracker call carries `--repo`. The
seat is about which door the session came in by, nothing else.

## Why the candidate set is frozen

The initial exploration covers the **whole queue** — every open, labelled
ticket the run can reach, not the first wave's worth. That is the expensive
step, and it is the step that makes the closures comparable: a clump resolved
against one repo scan can be checked against every other candidate, and a
candidate explored later cannot.

So the set is frozen once it is explored. A ticket filed while the run is
going does not join it; the run drains what it explored, and the next run
takes the rest. Growing the set mid-run means re-resolving every closure
against a new member, which is the full re-exploration below, for a ticket
nobody is waiting on.

The one exception is a ticket filed **during** the run *because the run is
stuck on what it fixes* — a blocker discovered by a worker, filed so it can
be built. That one is dispatched into the run, and `loop.admit` will not take
it without naming the clump it unblocks: the exception exists for a run that
cannot finish otherwise, and an unnamed `stuck_on` is how it would quietly
become "any ticket filed today".

## Why refill is continuous

A wave holds slots empty waiting for its slowest member. On #781 a clump
parked for hours mid-rebase, and every slot behind it in that wave sat idle
until someone noticed. Continuous refill has no wave to belong to: at each
landing the frontier is recomputed and every free slot is filled from it.

## Closure freshness, and the hub landing

At each dispatch the closures are re-resolved against current `main` —
**one hop**, `closure.py`'s declared ceiling — the candidate's own and every
in-flight clump's, since the run file stores a clump's tickets and workspace
but no closure, and a closure stored at claim time is exactly what goes
stale. The two are what `loop.py dispatch` reads as `--in-flight`. That is cheap and it is enough for the one
question a dispatch asks: does *this* clump collide with anyone live?

A **full** re-exploration is a different question, and it fires on one
trigger: a landing whose diff touched a **hub** — a file two or more
candidates' closures share. That is when other candidates' closures change,
because the file they all close over just moved. A landing that touched no
hub changes no other candidate's answer, so re-exploring after it spends the
exploration budget for an answer that is already on file.

`loop.hubs` reads a hub as a file in two or more closures. A file in exactly
one closure is not a hub however central it looks: nothing else in the queue
closes over it.

## The exclusion rule, and what it costs

A clump whose closure intersects a live workspace's closure is **off the
frontier**. A controller reading only "open, unblocked, unclaimed" would
dispatch straight into a collision — two workers editing one file, which is a
merge conflict the controller caused.

Among what is left, `picks` offers the free slots **widest closure first**
(#1026, grill Q12): a sweep ticket touching many files would otherwise go out
mid-run, once the frontier finally admits it, and hold most of the queue's
files for its whole run. Sorted before the same-tick guard walks the list, so
a wide clump is offered a slot ahead of narrower ones instead of sitting
behind them in ticket order.

The cost: a slot can go unfilled that ticket order would have filled. Two
free slots, nothing in flight, a wide clump sharing a file with two narrower
ones — widest-first picks the wide one, and the same-tick guard then holds
both narrower ones over its file, leaving the second slot idle until the
next landing. Ticket order would have filled it from whichever narrower
clump came first. That is the same-tick guard's ordinary behaviour, not a
bug in the sort — the run drains a slot behind schedule rather than into a
collision.

Both consequences are stated in the skill because neither is visible from the
frontier's own definition:

- **A run drains out of ticket order.** From the #781 burn: after `#453`
  landed, the obvious next candidates were `#452`, `#457` and `#458` — all
  three in the `examples/_shared/line-kind.js` include family, the same
  family holding parked `#455`. The slot went to `#501` instead, outside
  `examples/` entirely. A reader who expects ascending ticket numbers reads
  that as a bug.
- **One parked worker can hold a whole family.** On a repo with one hot
  shared file, every candidate in that family stays off the frontier until
  the worker holding it lands. That is starvation, it is the correct
  behaviour, and the fix is to land or park-and-reconcile the holder — never
  to dispatch into it.

## The box check

Two readings, `uptime` and `free -g`, before **every** dispatch, against the
two caps `~/.claude/CLAUDE.md`'s memory rules set and `loop.box_check` holds
as its constants — a process count over the shared box, and the sum of the
per-process `ulimit -v` caps. The numbers live there, once. Two WSL crashes
forced PC restarts when the caps summed to nearly three times the budget.
`box_check` returns every refusal, not the first, so a controller fixes one
thing and is not refused twice, and `loop.py dispatch` requires both readings
rather than taking them as optional flags: an optional one is the step a
controller forgets.

The process cap charges a slot at its **peak** — one worker plus its review
fan-out, `SLOT_PEAK_PROCESSES` (5) — not the one process it is between
reviews (#933): each new worker costs 5, each live worker keeps 4 in reserve.

The count that gates the cap is herdr's **working panes plus unlisted
claude pids** (`herdr agent list`; every `agent_status` counts except
`idle` and `done`, so a pane with no status or one herdr hasn't grown a
name for yet fails closed as working rather than reading as neither —
equality against the literal `"working"` let such a pane vanish from the
count, a Codex gate finding), not every `claude` process on the box read
as one flat total: an idle or done pane costs no cores, and counting it
held a run to fewer live workers than the box actually had room for
(#1075). Like `ps`, herdr counts by pane — one
entry per Claude session, a review fan-out's subagents folded into that
entry rather than listed on their own — so a *foreign* controller's own
review fan-out is not visible as extra herdr entries. What the first
version of this fix (#1075's original build) missed is that those
subagents are still real `claude` processes `ps` sees: `count_working_
herdr_agents` matches each herdr pane to a pid through the sessions
registry (`~/.claude/sessions/<pid>.json`, the same resolution
`resolve-controller` does), validated against `/proc/<pid>/stat`'s own
start time the same way `worker-alert-lib.sh` and `resolve-controller`
do — a pid recycles, so a registry record surviving a WSL restart or an
ordinary pid reuse can name a pid now held by a live, unrelated process,
and a match on the name alone let that stale record silently claim the
live process's pid, dropping it out of `unlisted` while the record's own
(often idle) status counted nothing for it (Codex gate finding on
9391bd8) — and adds every `claude` pid that matches no pane — a subagent
or a headless run — to the count, fail-closed, the same
way a herdr pane whose own session cannot be resolved is. A herdr listing
that is empty, or that resolves to none of the box's actual pids while
`claude` processes exist, is not read as an idle box: herdr's registry
reads as broken, and the count refuses the same way an all-idle `ps`
listing does. `loop.py` falls back to a flat process count (`ps -eo comm=
| grep -cx claude`, by command name, never a substring of the command line,
which overcounted 2x) only when herdr or the pid match cannot be taken at
all, and the refusal names which counter it used. The `peak:` line prints
the working and unlisted split beside the total, so a controller can see
what came from panes and what came from unlisted pids.

Before every dispatch, not once at the start: the box is shared, and the
process that puts it over the cap is as likely to be another agent's as this
run's.

## What resume owes each worker

A WSL restart renames every Claude session, and every worker's brief
names its controller in `--controller "<name>"`, a session name that a restart invalidates when the controller had no herdr agent name. So on resume the controller re-announces
itself — **exactly one message per live, unlanded worker**, which is
`runfile.reconcile`'s `announce` bucket and only that one. A landed clump's
worker is finished however its agent looks. A vanished one is reconciled or
parked by hand; messaging an agent nobody can find is not reconciliation.

`loop.announce` takes the messenger as an argument because sending is
`SendMessage`, which a Python module cannot call, and it raises rather than
returning a partial list when a send fails: a worker that was not reached is
a worker still addressing a controller that no longer exists.

The run file keys each worker by its **herdr agent name**. That name is the
durable key and not an address — `loop.announce` resolves it to a session
`send` can reach itself, at **send time**, through its `resolve`
argument (default: `resolve_via_binary`, which shells out to
`resolve-controller <herdr agent name>`, the same resolution
`implement-dispatch` does for the controller, #923). The caller's `send`
never sees the durable name, only the resolved one — `announce`'s own test
used to pass a permissive callback that accepted anything, so nothing
witnessed a resolved recipient, and a resumed controller's re-announcement
never reached a worker (#1013). A name that does not resolve refuses,
naming the worker, rather than sending to a guess. A resolved address
written into the run file is what aged and broke the last trial.
