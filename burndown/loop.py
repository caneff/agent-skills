#!/usr/bin/env python3
"""The burn loop's mechanical steps, so the prose in `burndown/SKILL.md`
§ The loop has a reader behind it instead of a rule a controller applies from
memory:

    python3 burndown/loop.py seat
    python3 burndown/loop.py box [--processes <n>] --committed-gb <g> [--add-gb <g>]
    python3 burndown/loop.py sweep --workers <clumps.json>

The judgment steps stay in the skill. What lives here is what a run got wrong
by hand: which clumps are dispatchable once the live workspaces are excluded,
whether a landing was a hub landing, whether the box has room for one more
worker, which live slots still have a pane behind them, how many free slots a
declared parallel job leaves, and which live workers a resumed controller owes
a message.

Why each rule reads the way it does: `references/loop.md`.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time


class LoopError(Exception):
    """The loop cannot proceed as asked. One stderr line, never a traceback:
    a controller needs the reason it is refused, not a stack."""


def seat(run):
    """The branch the controller is sitting on, or a refusal saying why this
    seat is not a controller's.

    `run(args) -> stdout` is `git` with the arguments given. Three refusals:
    a linked worktree, a detached HEAD, and any branch other than this
    checkout's default. Why each, and why the checkout need not hold the
    target repo: `references/loop.md`.
    """
    git_dir = os.path.realpath(run(["rev-parse", "--absolute-git-dir"]).strip())
    common = run(["rev-parse", "--git-common-dir"]).strip()
    # `--git-common-dir` answers relative to the cwd in an older git, so it is
    # resolved rather than compared as text.
    common = os.path.realpath(common)
    if git_dir != common:
        raise LoopError(
            f"this is a linked worktree ({git_dir}) — inside one, /implement "
            "reads the session as a worker, not a controller. Run the loop "
            "from a primary checkout's default branch.")
    branch = run(["branch", "--show-current"]).strip()
    if not branch:
        raise LoopError(
            "detached HEAD — neither a controller's seat nor a worker's. "
            "Check out the default branch.")
    try:
        default = run(
            ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]).strip()
    except LoopError as exc:
        raise LoopError(
            f"{exc} — this checkout has no recorded default branch, and the "
            "loop will not assume `main`: record it with `git remote set-head "
            "origin -a`") from None
    default = default.split("/", 1)[1] if "/" in default else default
    if branch != default:
        raise LoopError(
            f"on {branch}, not this checkout's default branch ({default}) — "
            "a controller runs from the default branch.")
    return branch


def paths(clump):
    """The files a clump owns: its resolved closure where there is one, its
    named files where there is not. `closure.py` emits `closure` only in the
    two modes that resolved one — in subtree mode there is no closure, and the
    exclusion below still has to read something.

    A value that is not a non-empty list of non-empty strings is refused
    rather than read: `set("shared.py")` is a set of six letters, which
    intersects no real path set, so a malformed closure would read as a clump
    colliding with nobody and put a second worker in a file a live workspace
    holds. Fails closed, as `closure.py` does one layer down (#891).
    """
    for key in ("closure", "files"):
        value = clump.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or not value or not all(
                isinstance(p, str) and p.strip() for p in value):
            raise LoopError(
                f"clump #{key_of(clump)}: {key} is not a list of paths: "
                f"{value!r}")
        return set(value)
    raise LoopError(f"clump #{key_of(clump)} names no files")


def key_of(clump):
    """The clump's lowest ticket — the number its branch and workspace are
    named for."""
    return min(clump["tickets"])


def frontier(candidates, in_flight):
    """`(candidates, in_flight) -> {dispatchable, held}`: which clumps may be
    dispatched right now, and which are held by a live workspace and by what.

    `candidates` are already open, labelled, unclaimed and unblocked — that
    is `frontier.py`'s answer, not this one's — and already clumped by
    `closure.py`. What this adds is the rule neither of those can see: a
    clump whose closure intersects a **live workspace's** closure is off the
    frontier, because dispatching it puts two workers in one file. Held
    clumps carry the workspace and the intersecting files, so a controller
    can say which worker is holding what.
    """
    dispatchable, held = [], []
    for clump in sorted(candidates, key=key_of):
        # Read before the inner loop, so a clump whose closure failed to
        # resolve is refused with nothing in flight too — where there is no
        # live workspace to compare it against and the refusal would
        # otherwise never fire.
        own = paths(clump)
        collisions = []
        for live in in_flight:
            over = sorted(own & paths(live))
            if over:
                collisions.append({"clump": clump, "workspace": live["workspace"],
                                   "holder": key_of(live), "over": over})
        if collisions:
            held.extend(collisions)
        else:
            dispatchable.append(clump)
    return {"dispatchable": dispatchable, "held": held}


def picks(state, free):
    """`(picked, held)`: the clumps to dispatch, taken from a frontier
    already read — widest closure first, ties broken by lowest ticket, every
    free slot at once — and every clump the same-tick guard skipped, each
    naming the earlier pick it collided with. Sorted before the guard runs
    (#1026): why widest-first, and what it costs: `references/loop.md`.

    Split from `refill` so a caller that also reports what is holding the
    rest reads the frontier once: two reads of one question can disagree
    while a worker lands between them.
    """
    if free <= 0:
        return [], []
    picked, held = [], []
    # The tie-break is this sort's own key, not borrowed from `frontier`'s
    # pre-sort: a `state` built by some other caller must not silently lose
    # it (#1026 review, S1/C2).
    widest_first = sorted(state["dispatchable"],
                          key=lambda c: (-len(paths(c)), key_of(c)))
    for clump in widest_first:
        # A clump picked a moment ago is in flight by the time the next one
        # starts, so the same exclusion applies inside one tick. Candidates
        # that collide with each other are normally one clump already — this
        # is the guard for the case where they are not. Unlike a frontier
        # collision, there is no live workspace to name: the holder is
        # another candidate picked this same tick, so the held entry is
        # tagged `same_tick` explicitly rather than distinguished by which
        # keys it happens to carry (#971).
        blocker = next((earlier for earlier in picked
                        if paths(clump) & paths(earlier)), None)
        if blocker is not None:
            held.append({"clump": clump, "holder": key_of(blocker),
                        "over": sorted(paths(clump) & paths(blocker)),
                        "same_tick": True})
            continue
        # Past the free-slot cut the walk goes on so a collision with a pick
        # is still named (#1049); a clump that collides with nothing is only
        # out of slots, not held.
        if len(picked) < free:
            picked.append(clump)
    return picked, held


def refill(candidates, in_flight, free):
    """The clumps to dispatch into the free slots, widest closure first,
    ties broken by lowest ticket — every free slot at once, not one wave's
    worth.

    Recomputed at each landing and never held for another clump. Why no
    waves, and the two consequences a controller has to state out loud:
    `references/loop.md`.
    """
    picked, _ = picks(frontier(candidates, in_flight), free)
    return picked


def hubs(clumps):
    """The files two or more of these clumps' closures share — the hub files
    a landing has to touch for the whole queue's closures to have moved.

    A file in one closure is not a hub however central it looks: nothing else
    in the queue closes over it, so a landing that touches it changes no
    other candidate's answer.
    """
    seen, shared = set(), set()
    for clump in clumps:
        for path in paths(clump):
            if path in seen:
                shared.add(path)
            seen.add(path)
    return shared


def hub_landing(landed_files, hub_files):
    """Whether this landing's diff touched a hub, which is the one trigger
    for a **full** re-exploration.

    Every other landing gets the one-hop re-resolution of the next clump's
    own closure instead. Why one trigger and not a schedule:
    `references/loop.md`.
    """
    return bool(set(landed_files) & set(hub_files))


# The box's two caps, from `~/.claude/CLAUDE.md`'s memory rules, which is
# their source: this is the one place in the repo that holds the numbers, and
# the prose says what `loop.py box` enforces rather than restating them.
PROCESS_CAP = 28
# A slot's peak, not its steady state: the worker plus the three review axes
# `/multi-axis-code-review` runs at once, plus one for the verification pass.
# A slot charged at 1 while it peaks at 5 is how three slots put 20 processes
# on a box the check had read as 15 (#933). The one place the multiplier is
# stated: `box_check` and the status line both read it here.
SLOT_PEAK_PROCESSES = 5
VM_BUDGET_GB = 24


AGENT_COUNTER = "`ps -eo comm=` lines equal to claude"
HERDR_COUNTER = ("`herdr agent list` working panes plus claude pids no "
                "pane resolves to")
UNSTATED_COUNTER = "count supplied by the caller"


def _run_counted(cmd):
    """(status, stdout) for a counting command — `ps` or `herdr` — run with
    a 10s timeout; the default `ps`/`run` both counters take when the
    caller passes none. An `OSError` (the binary is missing) or a
    subprocess failure reads as a failed run, not a crash: the caller
    decides whether that is refusable."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{exc}"
    return done.returncode, done.stdout


def count_agent_processes(ps=None):
    """The agent processes on the box, counted by command name: one per
    `claude` session (subagents run inside it). Counting by name and not by
    argument (`pgrep -f claude`) keeps plugin scripts and hook shims, whose
    arguments merely mention a claude path, out of the count.

    A count that could not be taken raises: a failed or empty `ps` is not
    "0 agents, the box is wide open". `ps` takes the command and returns
    (exit status, stdout).
    """
    if ps is None:
        ps = _run_counted
    status, out = ps(["ps", "-eo", "comm="])
    names = [line.strip() for line in out.splitlines() if line.strip()]
    if status != 0 or not names:
        raise LoopError(
            "could not count the agent processes on the box (`ps -eo comm=` "
            "failed or listed nothing), and an unmeasured box is not an "
            "empty one: refusing to dispatch — pass --processes <n> with a "
            "count you took")
    agents = sum(1 for name in names if name == "claude")
    if agents == 0:
        # The controller running this is itself a claude session, so a
        # healthy listing with none means the name did not match (a wrapper,
        # a renamed launcher) and the cap would never fire.
        raise LoopError(
            f"`ps -eo comm=` listed {len(names)} processes and none named "
            "claude, yet this controller is one: the count cannot be "
            "trusted, so refusing to dispatch — pass --processes <n> with a "
            "count you took")
    return agents


def _proc_start(pid):
    """Field 22 of `/proc/<pid>/stat` — the kernel's own start-time
    fingerprint for that pid, the same field `agent-status.md`'s liveness
    check and `worker-alert-lib.sh`/`resolve-controller` compare a
    registry record's `procStart` against. `None` when the process is
    gone or `/proc` cannot be read.

    The `comm` field (2nd) is parenthesised and can itself contain spaces
    or parens, so this splits on the *last* `)` rather than on whitespace
    — the same reader `ps`'s own `comm=` parsing sidesteps by never
    touching this file at all.
    """
    try:
        with open(f"/proc/{pid}/stat") as fh:
            text = fh.read()
    except OSError:
        return None
    end = text.rfind(")")
    if end == -1:
        return None
    fields = text[end + 1:].split()
    return fields[19] if len(fields) > 19 else None


def _session_pids(sessions_dir=None, proc_start=None):
    """`{sessionId: pid}` off the live sessions registry
    (`~/.claude/sessions/<pid>.json`), the same file `agent-status.md`
    reads and `resolve-controller` resolves through — validated against
    `/proc/<pid>/stat`'s own start time the same way both of those do.
    A pid recycles: after a WSL restart or an ordinary pid reuse, a stale
    record can still name a pid that is alive again as a completely
    different process. Matching on the name alone let that stale record
    claim the live process's pid, dropping it out of
    `count_working_herdr_agents`'s `unlisted` bucket while the record's
    own (often idle) status added nothing for it — a live process
    silently uncounted (Codex gate finding on 9391bd8). A record whose
    `procStart` does not match is not a match; its pid stays unresolved.

    Read fresh on every call — a pane's session can end between ticks —
    and skipped rather than raised on a directory or file this run cannot
    read: a registry gap fails a session's *match*, which
    `count_working_herdr_agents` already fails closed on, not the whole
    count. `proc_start` takes a pid and returns field 22 or `None`
    (default `_proc_start`, reading `/proc` directly).
    """
    sessions_dir = sessions_dir or os.path.expanduser("~/.claude/sessions")
    if proc_start is None:
        proc_start = _proc_start
    mapping = {}
    try:
        names = os.listdir(sessions_dir)
    except OSError:
        return mapping
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(sessions_dir, name)) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        sid, pid = data.get("sessionId"), data.get("pid")
        if not (isinstance(sid, str) and sid and isinstance(pid, int)):
            continue
        if proc_start(pid) != data.get("procStart"):
            continue
        mapping[sid] = pid
    return mapping


def count_working_herdr_agents(ps=None, herdr=None, sessions=None):
    """(working, unlisted): the box's working agents, herdr's own way —
    herdr counts by pane, one entry per Claude session, a review
    fan-out's subagents folded into that one entry rather than listed on
    their own. `working` is every listed pane whose `agent_status` is
    not `idle` or `done` — those two are the only statuses read as not
    working; a missing, null or unrecognised status fails closed as
    working rather than vanishing from the count (Codex gate finding on
    7a6bedd) — plus every listed pane whose session cannot be resolved to
    a pid (a resolution failure fails closed the same way, counted as
    working rather than dropped). `unlisted` is every `claude` pid `ps`
    shows that no listed pane resolved to — a subagent or headless run
    herdr does not pane-list, which still burns a core and fails closed
    the same way (#1075 controller ruling, correcting the ticket's
    original premise that herdr lists a subagent as its own agent).

    `ps`/`herdr` take a command and return (status, stdout), the contract
    `count_agent_processes` uses; `sessions` takes nothing and returns
    `{sessionId: pid}` (default `_session_pids`). Raises when either `ps`
    or herdr cannot be asked or answers something unusable, or when the
    herdr listing is empty or resolves to none of the box's actual
    `claude` pids while `ps` shows some exist — herdr's registry read as
    broken, not the box read as idle, the same shape of refusal
    `count_agent_processes` gives an all-idle `ps` listing.
    """
    if ps is None:
        ps = _run_counted
    if herdr is None:
        herdr = _run_counted
    if sessions is None:
        sessions = _session_pids

    pid_status, pid_out = ps(["ps", "-eo", "pid,comm"])
    if pid_status != 0 or not pid_out.strip():
        raise LoopError(
            "could not list claude pids on the box (`ps -eo pid,comm` "
            "failed or listed nothing), and an unmeasured box is not an "
            "empty one: refusing to dispatch — pass --processes <n> with a "
            "count you took")
    claude_pids = set()
    for line in pid_out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].strip() == "claude":
            claude_pids.add(int(parts[0]))
    if not claude_pids:
        # The controller running this is itself a claude session, so a
        # healthy listing with none means the name did not match.
        raise LoopError(
            "`ps -eo pid,comm` listed processes and none named claude, yet "
            "this controller is one: the pid count cannot be trusted, so "
            "refusing to dispatch — pass --processes <n> with a count you "
            "took")

    status, out = herdr(["herdr", "agent", "list"])
    if status != 0:
        raise LoopError(
            f"herdr agent list failed: {(out or '').strip() or 'no output'}")
    try:
        answer = json.loads(out)
    except (TypeError, ValueError) as exc:
        raise LoopError(f"herdr agent list did not answer JSON: {exc}") from exc
    result = answer.get("result") if isinstance(answer, dict) else None
    agents = result.get("agents") if isinstance(result, dict) else None
    if not isinstance(agents, list):
        raise LoopError(
            f"herdr agent list answered {answer!r}, no agents list to count")

    sid_to_pid = sessions()
    working = 0
    matched_pids = set()
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        session = agent.get("agent_session")
        sid = session.get("value") if isinstance(session, dict) else None
        pid = sid_to_pid.get(sid) if isinstance(sid, str) else None
        if pid is None:
            working += 1  # unresolved: fail closed, counted working
            continue
        matched_pids.add(pid)
        # Only "idle" and "done" exclude a pane. A missing, null or
        # unrecognised status is not known idle, so it counts as working —
        # the same fail-closed reading an unresolved pane already gets;
        # equality against "working" alone let a wedged or unclassified
        # pane read as neither working nor unlisted and vanish from the
        # count (Codex gate finding, 7a6bedd).
        if agent.get("agent_status") not in ("idle", "done"):
            working += 1

    if not matched_pids:
        raise LoopError(
            f"herdr agent list named {len(agents)} agent(s) but none "
            f"resolved to any of the {len(claude_pids)} claude pid(s) `ps` "
            "shows on the box — herdr's registry reads as broken, not the "
            "box as idle; pass --processes <n> with a count you took")

    return working, len(claude_pids - matched_pids)


def projected_processes(processes, workers, live):
    """(reserve, projected): the one place the peak arithmetic lives, read by
    the gate and by the status line so they cannot disagree."""
    reserve = live * (SLOT_PEAK_PROCESSES - 1)
    return reserve, processes + reserve + workers * SLOT_PEAK_PROCESSES


def box_check(processes, committed_gb, add_gb=0, workers=1,
              counter=UNSTATED_COUNTER, live=0):
    """Whether the box has room for one more worker, and every reason it does
    not.

    `processes` is the agent processes on the box — Claude sessions, not OS
    processes, and not only this run's. The cap is Chris's "no more than 28
    cores TOTAL" on a box shared with other agents, so a dispatch that fits
    this run's own count can still be the 29th agent on the machine, while
    the ~190 OS processes of an idle box are not what it counts.
    `workers` is how many this tick would start: three picks are three
    processes and three `ulimit -v` caps, so asking about one more worker
    passes a tick that starts three.

    Each new worker is charged at its **peak**, `SLOT_PEAK_PROCESSES`, and
    each of the `live` workers already running keeps the headroom between
    the one process it holds now and that peak: its review fan-out is a
    schedule the controller does not see. A live worker mid-fan-out is
    already in `processes`, so this over-reserves by what it is running now;
    an early refusal is the safe error, a dispatch into a peak is not.
    """
    refusals = []
    reserve, projected = projected_processes(processes, workers, live)
    if projected > PROCESS_CAP:
        refusals.append(
            f"{processes} agent processes on the box already ({counter}), "
            f"plus {reserve} of review fan-out headroom for {live} live "
            f"workers, plus {workers} new at a peak of "
            f"{SLOT_PEAK_PROCESSES} each would pass the cap of "
            f"{PROCESS_CAP}, which "
            "counts agent processes — Claude sessions, subagents included "
            "— not OS processes")
    if committed_gb + add_gb * workers > VM_BUDGET_GB:
        refusals.append(
            f"{committed_gb} GB of ulimit -v caps committed plus {add_gb} GB "
            f"for each of {workers} workers is over the ~{VM_BUDGET_GB} GB "
            "budget")
    return {"ok": not refusals, "refusals": refusals}


def process_count(text):
    """A `--processes` override: 0 is a deliberate count, a negative one would
    sit under the cap and disarm the gate."""
    count = int(text)
    if count < 0:
        raise argparse.ArgumentTypeError(
            f"--processes {count} is negative; give the agent processes you "
            "counted, 0 or more")
    return count


def live_count(text):
    """A `--live` count: negative would subtract reserve and disarm the gate,
    the same typo `process_count` refuses."""
    count = int(text)
    if count < 0:
        raise argparse.ArgumentTypeError(
            f"--live {count} is negative; give the live workers you "
            "counted, 0 or more")
    return count


def agent_count(args, herdr=None, ps=None, sessions=None):
    """(count, counter label, working, unlisted): the override when one
    was passed, else herdr's (working panes + unlisted claude pids) —
    see `count_working_herdr_agents`, which a #1075 controller ruling
    corrected from a plain working-panes count once measurement showed
    herdr does not list a subagent as its own agent. `working`/`unlisted`
    are `None` when `count` did not come from that split — an override, or
    the process-count fallback — so the peak line prints a flat number
    rather than a fabricated one.

    A herdr or `ps`-pid failure falls back to the plain process count (all
    `claude` on the box, idle included) for `count` — an unmeasured box is
    not an empty one, so the fallback is a measurement, never a default
    that reads as zero — and the counter label names the fallback so a
    refusal says which counter it used.
    """
    if args.processes is not None:
        return args.processes, "passed by --processes", None, None
    try:
        working, unlisted = count_working_herdr_agents(
            ps=ps, herdr=herdr, sessions=sessions)
    except LoopError as exc:
        total = count_agent_processes(ps)
        return total, (f"herdr could not answer ({exc}); fell back to "
                       + AGENT_COUNTER), None, None
    return working + unlisted, HERDR_COUNTER, working, unlisted


def box_room(processes, committed_gb, add_gb, want,
             counter=UNSTATED_COUNTER, live=0):
    """How many of `want` workers the box has room for, and the refusals if
    that is none. Fewer than asked is the normal answer on a shared box, and
    holding the extra slots empty is the point."""
    for workers in range(want, 0, -1):
        verdict = box_check(processes, committed_gb, add_gb, workers, counter,
                            live)
        if verdict["ok"]:
            return workers, []
    return 0, box_check(processes, committed_gb, add_gb, 1, counter,
                        live)["refusals"]


def job_cores(key, record):
    """A live clump's outstanding parallel job, as cores to charge.

    `None` is not zero. A worker nobody recorded and a worker that declared it
    launched nothing read alike from here, and charging the first as the
    second is the #351 dispatch into a box already at 25.8 load — so the
    absent record is refused by name, one layer under the skill's own rule
    that silence is not zero.
    """
    if record is None:
        raise LoopError(
            f"#{key} is live with no job record — record what that worker has "
            "out with `runfile.py job` (its cores, or --none) before "
            "dispatching, because silence is not zero")
    if not isinstance(record, dict):
        raise LoopError(f"#{key}: not a job record: {record!r}")
    state, cores = record.get("state"), record.get("cores", 0)
    if state not in ("running", "none", "done"):
        raise LoopError(f"#{key}: not a job state: {state!r}")
    if isinstance(cores, bool) or not isinstance(cores, int) or cores < 0:
        raise LoopError(f"#{key}: not a core count: {cores!r}")
    if state != "running":
        return 0
    if cores < 1:
        raise LoopError(f"#{key}: a running job names at least one core")
    return cores


def core_room(free, in_flight):
    """The free slots a run really has, once every outstanding parallel job's
    declared cores are charged against them.

    A slot is one core's worth of machine until a worker says otherwise, so a
    worker that declares an 8-core job is holding eight slots' worth and the
    seven past its own come off the free ones. That is the bridge the trial
    had nothing for: the controller's budget was in slots, the contention was
    in cores, and a run with a free slot dispatched into a box already at
    25.8 load (#351).

    Each declaration is read off the **clump's own** `job` record, which the
    run file holds, so it survives the restart that a declaration living in
    one dispatch's argv would not.
    """
    held = []
    charged = 0
    for clump in sorted(in_flight, key=key_of):
        key = key_of(clump)
        cores = job_cores(key, clump.get("job"))
        if cores > 1:
            charged += cores - 1
            held.append((key, cores))
    return {"room": max(0, free - charged), "held": held, "charged": charged}


def render_cores(state, free):
    """The declared jobs as a controller's status line carries them, or
    nothing to say when no worker declared one."""
    if not state["held"]:
        return ""
    jobs = ", ".join(f"#{key} declared {cores} cores"
                     for key, cores in state["held"])
    return (f"cores: {jobs} — {state['charged']} of {free} free "
            f"{'slot' if free == 1 else 'slots'} held, room for "
            f"{state['room']}")


def render_peak(count, live, room, working=None, unlisted=None):
    """The peak arithmetic as a controller's status line carries it: the
    measured count, what each live worker may still add, and the workers
    the box can take at their peak. `working`/`unlisted` print the split
    beside it, when both are given, so a controller can see how many of
    the count are herdr-listed working panes versus unlisted claude pids
    (a subagent or headless run herdr does not pane-list) (#1075)."""
    reserve, projected = projected_processes(count, room, live)
    split = (f" ({working} working, {unlisted} unlisted)"
            if working is not None and unlisted is not None else "")
    return (f"peak: {count} agent processes measured{split}, {live} live "
            f"{'worker' if live == 1 else 'workers'} holding {reserve} of "
            f"fan-out headroom, cap {PROCESS_CAP} — {room} more at "
            f"{SLOT_PEAK_PROCESSES} each projects {projected}")


def resolve_via_binary(agent):
    """`resolve-controller <agent>` as `announce`'s default resolver: the
    worker's herdr agent name resolved to the live Claude session name
    `SendMessage` can reach — the same resolution `implement-dispatch` does
    for the controller (#923). Raises rather than guessing when the binary
    is missing, times out, or prints nothing.
    """
    try:
        done = subprocess.run(["resolve-controller", agent],
                              capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        raise LoopError(
            f"resolve-controller {agent} could not run: {exc}") from exc
    if done.returncode != 0:
        raise LoopError((done.stderr or done.stdout).strip()
                        or f"resolve-controller {agent} failed")
    name = done.stdout.strip()
    if not name:
        raise LoopError(f"resolve-controller {agent} printed nothing")
    return name


def announce(state, send, resolve=resolve_via_binary):
    """Tell every live, unlanded worker who its controller is now — exactly
    one message each, and nothing to anyone else.

    `state` is `runfile.reconcile`'s answer; `send(agent, message)` is the
    caller's messenger and `resolve(agent) -> session name` (default
    `resolve_via_binary`) is called immediately before each send, so `send`
    never sees the worker's durable herdr agent name. A name that does not
    resolve refuses by name. Why: `references/loop.md`.
    """
    sent = []
    for entry in state["announce"]:
        tickets = ", ".join(f"#{n}" for n in entry["tickets"])
        agent = entry["agent"]
        message = (f"Your controller is now {state['controller']} — before every "
                   f"send, resolve that name with `resolve-controller` and send "
                   f"your questions and finish notice to what it prints. Run "
                   f"{state['run_id']}, clump {tickets}, workspace "
                   f"{entry['workspace']}.")
        try:
            address = resolve(agent)
        except Exception as exc:
            reached = ", ".join(sent) or "none"
            raise LoopError(
                f"could not resolve {agent} ({tickets}) to a live session: "
                f"{exc} — already reached: {reached}, so a retry covers the "
                "rest and not these") from exc
        try:
            send(address, message)
        except Exception as exc:
            reached = ", ".join(sent) or "none"
            raise LoopError(
                f"could not re-announce to {agent} ({tickets}): "
                f"{exc} — already reached: {reached}, so a retry covers the "
                "rest and not these") from exc
        sent.append(agent)
    return sent


def questions(clump, outstanding):
    """The worker questions still unanswered for this clump, checked before
    anything is ordered around them.

    A bare string is refused rather than iterated: `"is it ok?"` is ten
    characters, so it would read as ten outstanding questions and answer
    none of them — the same fail-closed rule `paths` applies one layer down.
    A question is one line, because each step prints as one.
    """
    if isinstance(outstanding, str) or not isinstance(
            outstanding, (list, tuple)) or not all(
            isinstance(q, str) and q.strip() for q in outstanding):
        raise LoopError(
            f"clump #{key_of(clump)}: not a list of outstanding worker "
            f"questions: {outstanding!r}")
    for question in outstanding:
        if "\n" in question or "\r" in question:
            raise LoopError(
                f"clump #{key_of(clump)}: a question is one line, and this "
                f"one is not: {question!r}")
    return list(outstanding)


def landing_steps(clump, outstanding=()):
    """A landing's tail, in the order it runs: **answer** every outstanding
    worker question, then **merge**, then **cleanup**.

    Cleanup is the last act because cleanup is what closes the worker's
    pane. On #781 a controller merged `#454`, ran `merge-cleanup`, and then
    sent the ruling its worker had asked for in good faith — to an agent
    that no longer existed. Answering before the *merge* is not the rule and
    would write the same bug in a new place: a question answered between
    merge and cleanup is answered, and one answered after cleanup is lost.
    Why, with the rest of the merge tail: `references/merge-tail.md`.
    """
    return [{"step": "answer", "agent": clump["agent"], "question": q}
            for q in questions(clump, outstanding)] + [
        {"step": "merge"}, {"step": "cleanup"}]


def cleanup_ready(clump, outstanding=()):
    """True when nothing is owed this clump's worker, or the refusal naming
    what is — the gate immediately before `merge-cleanup`.

    It names the agent and the questions, not just the count: a controller
    that hits this refusal has to *send* the answers, and a refusal it has
    to go looking behind is a refusal it works around.
    """
    owed = questions(clump, outstanding)
    if owed:
        raise LoopError(
            f"clump #{key_of(clump)}: {clump['agent']} is still owed an "
            f"answer to "
            + "; ".join(repr(q) for q in owed)
            + " — cleanup closes its pane, so the answer goes first")
    return True


# The pane states `herdr agent get` reports that the sweep passes through as
# its verdict. A state herdr grows later reads as `unknown` and is reported
# with the word herdr used, rather than being silently folded into `working` —
# which is the reading that would let a stuck worker pass as healthy.
_AGENT_STATES = frozenset({"working", "idle", "blocked"})
# One deadline for the **whole** sweep, not one per probe. A per-probe bound
# composes: N hung panes would hold the controller inside one tool call for N
# timeouts, and a controller in a tool call hears no worker at all (#778). So
# the worst case is this constant, whatever the wave size; a slot the deadline
# did not reach is read on the next wake, which costs nothing because the
# sweep only ever runs on a wake the controller already had.
SWEEP_BUDGET = 10.0


def sweep(clumps, get, budget=SWEEP_BUDGET, clock=time.monotonic):
    """One probe per live slot: which workers herdr still has a pane for, and
    what each of those panes is doing.

    `get(agent, timeout) -> decoded herdr answer` is the caller's probe —
    `herdr agent get <name>`, which the controller runs itself. **Bounded**
    twice over: at most one call per live, unlanded clump, no retry and no
    wait, and the whole sweep inside one `budget` seconds however many slots
    there are. Each probe is handed the budget that is **left**, and a slot
    the deadline did not reach is `unswept` — a slot nobody asked about, read
    on the next wake, which is a different fact from a pane that answered.
    It is the backstop under the wake, not a substitute for it, and it is
    never a timer: a controller inside a tool call hears no worker at all
    (#778).

    A vanished pane — herdr has no agent by that name — is the one failure
    only this sweep can find, and it is reported as its own verdict rather
    than as an idle worker. What the sweep cannot see is the other shape: a
    pane that is present and busy looks `working` whatever it is busy with
    (#925). Nothing about one clump ends the sweep: a probe that fails, and a
    clump the run file left with no agent name, are each that one worker's
    verdict, so a herdr that answers for two workers and not the third still
    tells the controller about two.
    """
    workers = [c for c in clumps if not c.get("landed")]
    started = clock()
    calls = 0
    read = []
    for clump in workers:
        agent = clump.get("agent")
        if not isinstance(agent, str) or not agent.strip():
            read.append({"agent": "-", "tickets": clump["tickets"],
                         "workspace": clump.get("workspace", ""),
                         "verdict": "unnamed",
                         "detail": "the run file names no herdr agent for this "
                                   "clump, and the sweep probes by name"})
            continue
        left = budget - (clock() - started)
        if left <= 0:
            read.append({"agent": agent, "tickets": clump["tickets"],
                         "workspace": clump.get("workspace", ""),
                         "verdict": "unswept",
                         "detail": f"the sweep's {budget:g}s deadline expired "
                                   "before this slot — read on the next wake"})
            continue
        calls += 1
        try:
            answer = get(agent, left)
        except Exception as exc:
            verdict, detail = "unreachable", str(exc)
        else:
            verdict, detail = _verdict(answer)
        read.append({"agent": agent, "tickets": clump["tickets"],
                     "workspace": clump.get("workspace", ""),
                     "verdict": verdict, "detail": detail})
    return {"calls": calls, "workers": read,
            "vanished": [w for w in read if w["verdict"] == "vanished"]}


def _verdict(answer):
    """One herdr answer read as a verdict and the detail behind it."""
    if not isinstance(answer, dict):
        return "unknown", f"herdr answered {answer!r}"
    error = answer.get("error")
    if isinstance(error, dict):
        code = error.get("code", "")
        if code == "agent_not_found":
            return "vanished", error.get("message", code)
        return "unreachable", error.get("message", code) or "herdr errored"
    result = answer.get("result")
    if not isinstance(result, dict):
        return "unknown", f"herdr answered {answer!r}"
    nested = result.get("agent")
    status = nested.get("agent_status") if isinstance(nested, dict) else None
    if status is None:
        status = result.get("agent_status")
    if status in _AGENT_STATES:
        return status, str(status)
    return "unknown", f"herdr reports agent_status {status!r}"


def render_sweep(state):
    """The sweep as a controller reads it: one line per live slot, the
    vanished ones named as vanished and not as idle."""
    lines = [f"{w['verdict']:<9} #{key_of(w)}  {w['agent']}  {w['workspace']}"
             f"  {w['detail']}".rstrip()
             for w in state["workers"]]
    return "\n".join(lines) or "no live slots to sweep"


def admit(candidates, clump, stuck_on=None):
    """The frozen candidate set, plus the one ticket allowed to join it.

    A ticket filed while the run is going does not extend it. The one
    exception is a ticket filed *during* the run **because the run is stuck
    on what it fixes**; `stuck_on` names the clump it unblocks, which has to
    be one of this run's. Why the freeze and why the exception is narrow:
    `references/loop.md`. Returns a new list; the frozen set is never
    mutated in place.
    """
    if stuck_on is None:
        raise LoopError(
            f"the candidate set is frozen at this run's initial exploration, "
            f"so #{key_of(clump)} waits for the next run — unless the run is "
            "stuck on what it fixes, which is stated as stuck_on=<clump>")
    if not any(stuck_on in c["tickets"] for c in candidates):
        raise LoopError(
            f"#{stuck_on} is not a ticket of this run, so #{key_of(clump)} "
            "cannot be the ticket the run is stuck on")
    return list(candidates) + [clump]


def read_clumps(path, live=False, closure=True):
    """A clump list from a JSON file — `closure.py --json`'s output, each
    entry with the `workspace` an in-flight one sits in.

    `live=True` for the in-flight list, whose entries are also named in
    every held-clump line and so must carry a `workspace`. `closure=False`
    for the sweep's list, which is the run file's own entries: the sweep asks
    about panes and not about files, and a run file holds no closure.

    Validated field by field, as `runfile.py` validates its own state: a
    hand-built or half-written file is the normal case here, and it reaches
    this reader while a controller is recovering, which needs the reason and
    not a stack.
    """
    try:
        with open(path) as fh:
            clumps = json.load(fh)
    except (OSError, ValueError) as exc:
        raise LoopError(f"could not read {path}: {exc}") from exc
    if not isinstance(clumps, list):
        raise LoopError(f"{path} is not a list of clumps")
    for entry in clumps:
        if not isinstance(entry, dict):
            raise LoopError(f"{path} holds something that is not a clump: "
                            f"{entry!r}")
        tickets = entry.get("tickets")
        if not isinstance(tickets, list) or not tickets or not all(
                isinstance(n, int) and not isinstance(n, bool) and n > 0
                for n in tickets):
            raise LoopError(f"{path}: not a clump's ticket list: {tickets!r}")
        if live and not isinstance(entry.get("workspace"), str) or (
                live and not entry.get("workspace", "").strip()):
            raise LoopError(
                f"{path}: clump #{min(tickets)} names no workspace, and an "
                "in-flight clump is reported by the workspace holding it")
        if closure:
            paths(entry)
    return clumps


def herdr_get(agent, timeout):
    """`herdr agent get <name>` decoded — the sweep's probe as the controller
    runs it. herdr exits non-zero for an agent it has no pane for and still
    prints the `agent_not_found` answer, so the output is read either way and
    only an unparseable one is an error.

    `timeout` is what the sweep has left of its whole deadline, not a fresh
    allowance: "bounded" has to mean the wall clock too, and a herdr that
    never answers would otherwise hold the controller inside a tool call,
    where no worker can reach it at all."""
    try:
        done = subprocess.run(["herdr", "agent", "get", agent],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise LoopError(
            f"herdr agent get {agent} did not answer in {timeout:g}s"
        ) from None
    text = done.stdout.strip() or done.stderr.strip()
    try:
        return json.loads(text)
    except ValueError:
        raise LoopError(
            f"herdr agent get {agent} answered {text or '(nothing)'!r}"
        ) from None


def render_dispatch(picked, held):
    lines = [f"dispatch  #{key_of(c)}  "
             + ",".join(f"#{n}" for n in c["tickets"]) for c in picked]
    for entry in held:
        # `same_tick` names the other candidate this tick picked ahead of it;
        # otherwise the holder is a live workspace (#971).
        where = "this tick" if entry.get("same_tick") \
            else f"in {entry['workspace']}"
        lines.append(
            f"held      #{key_of(entry['clump'])}  by #{entry['holder']} "
            f"{where}  over {', '.join(entry['over'])}")
    return "\n".join(lines) or "nothing to dispatch"


def run(argv):
    parser = argparse.ArgumentParser(
        prog="loop.py", description=(
            "The burn loop's mechanical steps. `announce` has no subcommand: "
            "sending is SendMessage, which the controller calls itself — and "
            "so is `landing`'s answer step, which is why `landing` reports "
            "what is owed and gates cleanup rather than answering anything."))
    subs = parser.add_subparsers(dest="command", required=True)
    agent_help = ("Override for the agent count this run's cap check reads "
                  "(Claude sessions, subagents included), not OS processes; "
                  "never `ps | wc -l`. Default: " + HERDR_COUNTER +
                  ", falling back to " + AGENT_COUNTER +
                  " only when herdr cannot answer.")
    subs.add_parser("seat", help="refuse unless this is a controller's seat")
    box = subs.add_parser("box", help="room on the box for one more worker")
    box.add_argument("--processes", type=process_count,
                     help=agent_help)
    box.add_argument("--committed-gb", type=float, required=True)
    box.add_argument("--live", type=live_count, required=True,
                     help="workers already running, each held at its peak; "
                          "0 is a count you took, not a default")
    box.add_argument("--add-gb", type=float, default=0)
    dispatch = subs.add_parser(
        "dispatch", help="which clumps go into the free slots")
    dispatch.add_argument("--candidates", required=True)
    dispatch.add_argument("--in-flight", required=True,
                          help="the live clumps file; an empty list says no "
                               "worker is live, an omitted one is refused")
    dispatch.add_argument("--free", type=int, required=True)
    # Measured when omitted, so the box check cannot be skipped by a
    # controller who does not know what number to pass.
    dispatch.add_argument("--processes", type=process_count,
                          help=agent_help)
    dispatch.add_argument("--committed-gb", type=float, required=True)
    dispatch.add_argument("--add-gb", type=float, default=0)
    sweep_cmd = subs.add_parser(
        "sweep", help="one herdr probe per live slot, the backstop under the "
                      "wake")
    sweep_cmd.add_argument("--workers", required=True,
                           help="the run's clumps, as the run file holds them")
    hub = subs.add_parser(
        "hub", help="whether a landing asks for full re-exploration")
    hub.add_argument("--candidates", required=True)
    hub.add_argument("--landed", required=True,
                     help="comma-separated paths the landing's diff touched")
    landing = subs.add_parser(
        "landing", help="a landing's tail, and whether cleanup may run yet")
    landing.add_argument("--clump", type=int, required=True,
                         help="the clump's lowest ticket")
    landing.add_argument("--agent", required=True,
                         help="the worker's herdr agent name")
    landing.add_argument("--outstanding", action="append", default=[],
                         help="a worker question still unanswered; repeatable")
    args = parser.parse_args(argv[1:])
    try:
        if args.command == "seat":
            print(seat(git))
        elif args.command == "box":
            count, counter, _working, _unlisted = agent_count(args)
            verdict = box_check(count, args.committed_gb, args.add_gb,
                                counter=counter, live=args.live)
            if not verdict["ok"]:
                for refusal in verdict["refusals"]:
                    print(f"loop.py: {refusal}", file=sys.stderr)
                return 1
            print("box ok")
        elif args.command == "dispatch":
            candidates = read_clumps(args.candidates)
            in_flight = read_clumps(args.in_flight, live=True)
            free = max(args.free, 0)
            # Measured before any early return: a broken herdr or `ps` must
            # refuse here too, not hide behind "nothing to dispatch".
            count, counter, working, unlisted = agent_count(args)
            # A landed clump awaiting cleanup is not a live worker: it is
            # filtered out before the core accounting, the peak live count,
            # and the frontier all see it, so a run file that sets `landed`
            # without ever clearing `job` reads as a freed slot instead of
            # refusing the whole tick on a job record that will never be
            # recorded (#1003) — and its dead workspace (the change is on
            # `main`; the next worker branches from there) never blocks a
            # candidate sharing its closure (Codex gate, PR #1050).
            unlanded = [c for c in in_flight if not c.get("landed")]
            cores = core_room(free, unlanded)
            cores_line = render_cores(cores, free)
            if cores_line:
                print(cores_line)
            if cores["room"] == 0 and free:
                # The declared jobs hold every free slot. Said here rather
                # than left to the box check, whose refusal would name a
                # process cap that is not what is holding the slot — and with
                # the held-clump lines, which a controller reads to see which
                # live workspace holds which candidate whatever stopped the
                # dispatch.
                print("nothing to dispatch: every free slot is held by a "
                      "declared job")
                print(render_dispatch([], frontier(candidates, unlanded)["held"]))
                return 0
            live = len(unlanded)
            room, refusals = box_room(count, args.committed_gb,
                                      args.add_gb, cores["room"], counter,
                                      live)
            if refusals:
                for refusal in refusals:
                    print(f"loop.py: {refusal}", file=sys.stderr)
                return 1
            print(render_peak(count, live, room, working, unlisted))
            state = frontier(candidates, unlanded)
            picked, same_tick_held = picks(state, room)
            lines = render_dispatch(picked, state["held"] + same_tick_held)
            if room < cores["room"]:
                lines = f"box: room for {room} of {cores['room']}\n{lines}"
            print(lines)
        elif args.command == "landing":
            if args.clump < 1:
                raise LoopError(f"not a ticket number: {args.clump}")
            if not args.agent.strip():
                raise LoopError(
                    "no agent named — the refusal's whole job is to name the "
                    "worker that is owed an answer")
            clump = {"tickets": [args.clump], "agent": args.agent}
            owed = [step for step in landing_steps(clump, args.outstanding)
                    if step["step"] == "answer"]
            if owed:
                # The answers, and a refusal saying they are the whole list.
                # `merge` and `cleanup` are not printed here: an exit code
                # refuses, a printed step list does not, and anything reading
                # this list would be handed `cleanup` on the one path where
                # running it closes the pane the answer is owed on.
                print(f"refused: {len(owed)} answer"
                      f"{'' if len(owed) == 1 else 's'} owed before cleanup")
                for step in owed:
                    print(f"answer    {step['agent']}  {step['question']}")
            else:
                for step in landing_steps(clump, args.outstanding):
                    print(step["step"])
            cleanup_ready(clump, args.outstanding)
        elif args.command == "sweep":
            # Checked once, before any probe: without it every slot reads
            # `unreachable`, which is a dead roster and a missing tool telling
            # the same story — and § Parking would park the run on it.
            if shutil.which("herdr") is None:
                raise LoopError(
                    "herdr is not on PATH, so the sweep has nothing to ask — "
                    "this is a broken controller box, not a roster of dead "
                    "workers")
            budget = float(os.environ.get("BURNDOWN_SWEEP_BUDGET")
                           or SWEEP_BUDGET)
            print(render_sweep(
                sweep(read_clumps(args.workers, closure=False), herdr_get,
                      budget=budget)))
        elif args.command == "hub":
            landed = [p for p in args.landed.replace(",", " ").split() if p]
            hub_files = hubs(read_clumps(args.candidates))
            if hub_landing(landed, hub_files):
                print("re-explore: this landing touched "
                      + ", ".join(sorted(set(landed) & hub_files)))
            else:
                print("no hub touched: re-resolve the next clump's own "
                      "closure, one hop, and dispatch")
    except LoopError as exc:
        print(f"loop.py: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv):
    """`run`, plus the reader that closed early.

    A pipe makes stdout block-buffered, so `loop.py landing ... | head -1`
    usually breaks at the flush — which the interpreter does after `run` has
    returned, where no handler inside it can reach. Past the buffer it
    breaks inside `run` instead, on a `print`. Both are the same dead
    reader, so both are handled here, and pointing the fd at /dev/null keeps
    the interpreter's own exit-time flush off the dead pipe, where it would
    print the traceback this module promises never to print.

    The status is whatever `run` decided — stderr is a different fd, and a
    refusal printed there arrived whatever happened to stdout — or, when
    `run` never got to decide, the refusing one: a command whose output
    nobody read cleared nothing, and a caller reading the exit code must not
    take a dead pipe for permission.
    """
    status = 1
    try:
        status = run(argv)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return status


def git(args):
    """`git` as the seat check calls it, from the cwd the controller is in."""
    done = subprocess.run(["git", *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise LoopError(
            f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


if __name__ == "__main__":
    sys.exit(main(sys.argv))
