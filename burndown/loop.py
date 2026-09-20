#!/usr/bin/env python3
"""The burn loop's mechanical steps, so the prose in `burndown/SKILL.md`
§ The loop has a reader behind it instead of a rule a controller applies from
memory:

    python3 burndown/loop.py seat
    python3 burndown/loop.py box --processes <n> --committed-gb <g> [--add-gb <g>]
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
    """The clumps to dispatch, taken from a frontier already read — lowest
    ticket first, every free slot at once.

    Split from `refill` so a caller that also reports what is holding the
    rest reads the frontier once: two reads of one question can disagree
    while a worker lands between them.
    """
    if free <= 0:
        return []
    picked = []
    for clump in state["dispatchable"]:
        if len(picked) == free:
            break
        # A clump picked a moment ago is in flight by the time the next one
        # starts, so the same exclusion applies inside one tick. Candidates
        # that collide with each other are normally one clump already — this
        # is the guard for the case where they are not.
        if any(paths(clump) & paths(earlier) for earlier in picked):
            continue
        picked.append(clump)
    return picked


def refill(candidates, in_flight, free):
    """The clumps to dispatch into the free slots, lowest ticket first — every
    free slot at once, not one wave's worth.

    Recomputed at each landing and never held for another clump. Why no
    waves, and the two consequences a controller has to state out loud:
    `references/loop.md`.
    """
    return picks(frontier(candidates, in_flight), free)


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
VM_BUDGET_GB = 24


def box_check(processes, committed_gb, add_gb=0, workers=1):
    """Whether the box has room for one more worker, and every reason it does
    not.

    `processes` is every process on the box, not this run's — the readings
    come from `uptime` and `free -g` and the process table before each
    dispatch, because the box is shared with other agents and a dispatch that
    fits this run's own count can still be the 29th process on the machine.
    `workers` is how many this tick would start: three picks are three
    processes and three `ulimit -v` caps, so asking about one more worker
    passes a tick that starts three.
    """
    refusals = []
    if processes + workers > PROCESS_CAP:
        refusals.append(
            f"{processes} processes on the box already, {workers} more would "
            f"pass the cap of {PROCESS_CAP}, which counts every process on "
            "it and not this run's")
    if committed_gb + add_gb * workers > VM_BUDGET_GB:
        refusals.append(
            f"{committed_gb} GB of ulimit -v caps committed plus {add_gb} GB "
            f"for each of {workers} workers is over the ~{VM_BUDGET_GB} GB "
            "budget")
    return {"ok": not refusals, "refusals": refusals}


def box_room(processes, committed_gb, add_gb, want):
    """How many of `want` workers the box has room for, and the refusals if
    that is none. Fewer than asked is the normal answer on a shared box, and
    holding the extra slots empty is the point."""
    for workers in range(want, 0, -1):
        verdict = box_check(processes, committed_gb, add_gb, workers)
        if verdict["ok"]:
            return workers, []
    return 0, box_check(processes, committed_gb, add_gb, 1)["refusals"]


def cores_of(key, cores):
    """A declared job's core count: a positive integer, and not a bool or a
    string. A count read loosely is a hold that silently does not happen."""
    if isinstance(cores, bool) or not isinstance(cores, int) or cores < 1:
        raise LoopError(f"#{key}: not a job's core count: {cores!r}")
    return cores


def parse_declared(text):
    """`351=8,412=4` — the declarations a controller reads off its workers'
    reports — as `{clump: cores}`."""
    declared = {}
    for item in (text or "").replace(",", " ").split():
        key, sep, cores = item.partition("=")
        if not sep or not key.strip().isdigit() or not cores.strip().isdigit():
            raise LoopError(
                f"not a core declaration: {item!r} — one <clump>=<cores> per "
                "worker that declared a parallel job")
        key = int(key)
        if key in declared:
            # Last-wins would drop the larger declaration silently, which is
            # the hold that does not happen — the #351 dispatch into a loaded
            # box, with the reader reporting nothing wrong.
            raise LoopError(
                f"#{key} is declared twice ({declared[key]} and {cores}) — a "
                "clump has one outstanding job's core count, and the larger "
                "one would be dropped without a word")
        declared[key] = cores_of(key, int(cores))
    return declared


def core_room(free, in_flight, declared):
    """The free slots a run really has, once every outstanding parallel job's
    declared cores are charged against them.

    A slot is one core's worth of machine until a worker says otherwise, so a
    worker that declares an 8-core job is holding eight slots' worth and the
    seven past its own come off the free ones. That is the bridge the trial
    had nothing for: the controller's budget was in slots, the contention was
    in cores, and a run with a free slot dispatched into a box already at
    25.8 load (#351). A declaration names a clump this run has in flight;
    one that names anything else is a report read wrong, and is refused
    rather than quietly charged to nobody.
    """
    live = {key_of(clump) for clump in in_flight}
    held = []
    charged = 0
    for key in sorted(declared):
        cores = cores_of(key, declared[key])
        if key not in live:
            raise LoopError(
                f"#{key} declared a {cores}-core job but is not in flight — "
                "a declaration is charged to the clump that is running it")
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


def announce(state, send):
    """Tell every live, unlanded worker who its controller is now — exactly
    one message each, and nothing to anyone else.

    `state` is `runfile.reconcile`'s answer and `send(agent, message)` is the
    caller's messenger. The bucket is `announce` and only that one, and the
    agent it names is the worker's herdr agent name, which the caller
    resolves to an address itself. Why each of those three:
    `references/loop.md`.
    """
    sent = []
    for entry in state["announce"]:
        tickets = ", ".join(f"#{n}" for n in entry["tickets"])
        message = (f"Your controller is now {state['controller']} — re-address "
                   f"every question and your finish notice there. Run "
                   f"{state['run_id']}, clump {tickets}, workspace "
                   f"{entry['workspace']}.")
        try:
            send(entry["agent"], message)
        except Exception as exc:
            reached = ", ".join(sent) or "none"
            raise LoopError(
                f"could not re-announce to {entry['agent']} ({tickets}): "
                f"{exc} — already reached: {reached}, so a retry covers the "
                "rest and not these") from exc
        sent.append(entry["agent"])
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
# A probe that has not answered in this long is a probe the controller stops
# waiting on: the sweep is the backstop, and a controller blocked inside it is
# the one state the primary path cannot survive (#778).
HERDR_TIMEOUT = 10.0


def sweep(clumps, get):
    """One probe per live slot: which workers herdr still has a pane for, and
    what each of those panes is doing.

    `get(agent) -> decoded herdr answer` is the caller's probe — `herdr agent
    get <name>`, which the controller runs itself. **Bounded**: exactly one
    call per live, unlanded clump, no retry and no wait. It is the backstop
    under the wake, not a substitute for it, and it is never a timer: a
    controller inside a tool call hears no worker at all (#778).

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
        calls += 1
        try:
            answer = get(agent)
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
    """A clump list from a JSON file — `closure.py`'s own `clumps` entries,
    each with the `workspace` an in-flight one sits in.

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


def herdr_get(agent):
    """`herdr agent get <name>` decoded — the sweep's probe as the controller
    runs it. herdr exits non-zero for an agent it has no pane for and still
    prints the `agent_not_found` answer, so the output is read either way and
    only an unparseable one is an error.

    Time-bounded, because "bounded" has to mean the wall clock too: a herdr
    that never answers would otherwise hold the controller inside a tool call,
    where no worker can reach it at all."""
    try:
        done = subprocess.run(["herdr", "agent", "get", agent],
                              capture_output=True, text=True,
                              timeout=HERDR_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise LoopError(
            f"herdr agent get {agent} did not answer in {HERDR_TIMEOUT:g}s"
        ) from None
    text = done.stdout.strip() or done.stderr.strip()
    try:
        return json.loads(text)
    except ValueError:
        raise LoopError(
            f"herdr agent get {agent} answered {text or '(nothing)'!r}"
        ) from None


def render_dispatch(picked, state):
    lines = [f"dispatch  #{key_of(c)}  "
             + ",".join(f"#{n}" for n in c["tickets"]) for c in picked]
    for held in state["held"]:
        lines.append(
            f"held      #{key_of(held['clump'])}  by #{held['holder']} in "
            f"{held['workspace']}  over {', '.join(held['over'])}")
    return "\n".join(lines) or "nothing to dispatch"


def run(argv):
    parser = argparse.ArgumentParser(
        prog="loop.py", description=(
            "The burn loop's mechanical steps. `announce` has no subcommand: "
            "sending is SendMessage, which the controller calls itself — and "
            "so is `landing`'s answer step, which is why `landing` reports "
            "what is owed and gates cleanup rather than answering anything."))
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("seat", help="refuse unless this is a controller's seat")
    box = subs.add_parser("box", help="room on the box for one more worker")
    box.add_argument("--processes", type=int, required=True)
    box.add_argument("--committed-gb", type=float, required=True)
    box.add_argument("--add-gb", type=float, default=0)
    dispatch = subs.add_parser(
        "dispatch", help="which clumps go into the free slots")
    dispatch.add_argument("--candidates", required=True)
    dispatch.add_argument("--in-flight")
    dispatch.add_argument("--free", type=int, required=True)
    # Required, not optional: the box check runs before *every* dispatch, and
    # an optional flag is the step a controller forgets.
    dispatch.add_argument("--processes", type=int, required=True)
    dispatch.add_argument("--committed-gb", type=float, required=True)
    dispatch.add_argument("--add-gb", type=float, default=0)
    dispatch.add_argument(
        "--declared", default="",
        help="<clump>=<cores> per worker that reported a parallel job")
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
            verdict = box_check(args.processes, args.committed_gb, args.add_gb)
            if not verdict["ok"]:
                for refusal in verdict["refusals"]:
                    print(f"loop.py: {refusal}", file=sys.stderr)
                return 1
            print("box ok")
        elif args.command == "dispatch":
            candidates = read_clumps(args.candidates)
            in_flight = (read_clumps(args.in_flight, live=True)
                         if args.in_flight else [])
            free = max(args.free, 0)
            cores = core_room(free, in_flight, parse_declared(args.declared))
            cores_line = render_cores(cores, free)
            if cores_line:
                print(cores_line)
            if cores["room"] == 0 and free:
                # The declared jobs hold every free slot. Said here rather
                # than left to the box check, whose refusal would name a
                # process cap that is not what is holding the slot.
                print("nothing to dispatch: every free slot is held by a "
                      "declared job")
                return 0
            room, refusals = box_room(args.processes, args.committed_gb,
                                      args.add_gb, cores["room"])
            if refusals:
                for refusal in refusals:
                    print(f"loop.py: {refusal}", file=sys.stderr)
                return 1
            state = frontier(candidates, in_flight)
            lines = render_dispatch(picks(state, room), state)
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
            print(render_sweep(
                sweep(read_clumps(args.workers, closure=False), herdr_get)))
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
