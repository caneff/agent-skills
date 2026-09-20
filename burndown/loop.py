#!/usr/bin/env python3
"""The burn loop's mechanical steps, so the prose in `burndown/SKILL.md`
§ The loop has a reader behind it instead of a rule a controller applies from
memory:

    python3 burndown/loop.py seat
    python3 burndown/loop.py box --processes <n> --committed-gb <g> [--add-gb <g>]

The judgment steps stay in the skill. What lives here is what a run got wrong
by hand: which clumps are dispatchable once the live workspaces are excluded,
whether a landing was a hub landing, whether the box has room for one more
worker, and which live workers a resumed controller owes a message.

Why each rule reads the way it does: `references/loop.md`.
"""
import argparse
import json
import os
import subprocess
import sys


class LoopError(Exception):
    """The loop cannot proceed as asked. One stderr line, never a traceback:
    a controller needs the reason it is refused, not a stack."""


def seat(run):
    """The branch the controller is sitting on, or a refusal saying why this
    seat is not a controller's.

    `run(args) -> stdout` is `git` with the arguments given. Three refusals:
    a linked worktree, where `/implement`'s front-door rule would read the
    session as a *worker*; a detached HEAD, which is neither door; and any
    branch other than this checkout's default — read from
    `refs/remotes/origin/HEAD`, never assumed to be `main`. The repo this
    checkout holds need not be the repo the run targets: the loop addresses
    that one with `--repo`.
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
    default = run(
        ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]).strip()
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
    exclusion below still has to read something."""
    for key in ("closure", "files"):
        if clump.get(key):
            return set(clump[key])
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
        collisions = []
        for live in in_flight:
            over = sorted(paths(clump) & paths(live))
            if over:
                collisions.append({"clump": clump, "workspace": live["workspace"],
                                   "holder": key_of(live), "over": over})
        if collisions:
            held.extend(collisions)
        else:
            dispatchable.append(clump)
    return {"dispatchable": dispatchable, "held": held}


def refill(candidates, in_flight, free):
    """The clumps to dispatch into the free slots, lowest ticket first — every
    free slot at once, not one wave's worth.

    Recomputed at each landing and never held for another clump: a wave holds
    slots empty waiting for its slowest member. The consequence, stated out
    loud because it looks like a bug from outside: a run drains **out of
    ticket order**, and on a repo with one hot shared file a single parked
    worker can hold a whole family of tickets off the frontier until it
    lands.
    """
    if free <= 0:
        return []
    picked = []
    for clump in frontier(candidates, in_flight)["dispatchable"]:
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
    own closure instead. Re-exploring the whole queue after every landing
    spends the exploration budget several times over for an answer that has
    not changed; skipping it after a hub landing dispatches against closures
    that have.
    """
    return bool(set(landed_files) & set(hub_files))


# The box's two rules (`~/.claude/CLAUDE.md`'s memory rules): at most 28
# processes on the shared WSL box counting every process on it, and the sum of
# the per-process `ulimit -v` caps under about 24 GB. Two WSL crashes forced PC
# restarts when the caps summed to 66 GB.
PROCESS_CAP = 28
VM_BUDGET_GB = 24


def box_check(processes, committed_gb, add_gb=0,
              cap=PROCESS_CAP, budget_gb=VM_BUDGET_GB):
    """Whether the box has room for one more worker, and every reason it does
    not.

    `processes` is every process on the box, not this run's — the readings
    come from `uptime` and `free -g` and the process table before each
    dispatch, because the box is shared with other agents and a dispatch that
    fits this run's own count can still be the 29th process on the machine.
    """
    refusals = []
    if processes + 1 > cap:
        refusals.append(
            f"{processes} processes on the box already, and the cap is {cap} "
            "counting every process on it, not this run's")
    if committed_gb + add_gb > budget_gb:
        refusals.append(
            f"{committed_gb} GB of ulimit -v caps committed plus {add_gb} GB "
            f"for this worker is over the ~{budget_gb} GB budget")
    return {"ok": not refusals, "refusals": refusals}


def announce(state, send):
    """Tell every live, unlanded worker who its controller is now — exactly
    one message each, and nothing to anyone else.

    `state` is `runfile.reconcile`'s answer and `send(agent, message)` is the
    caller's messenger, because sending is `SendMessage` and a Python module
    cannot call it. The bucket is `announce` and only that one: a landed
    clump's worker is done however its agent looks, and a vanished one is
    reconciled or parked by hand rather than messaged.

    The agent named is the worker's **herdr agent name**, which is the durable
    key and not an address: resolving it to the session a message can reach is
    the caller's, at send time (#923). A resolved address written into the run
    file is what aged and broke the last trial.
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
            raise LoopError(
                f"could not re-announce to {entry['agent']} "
                f"({tickets}): {exc}") from exc
        sent.append(entry["agent"])
    return sent


def admit(candidates, clump, stuck_on=None):
    """The frozen candidate set, plus the one ticket allowed to join it.

    The set is frozen at the initial exploration — which covers the **whole
    queue**, not the first wave's worth — so a ticket filed while the run is
    going does not extend it: the run drains what it explored and a later run
    takes the rest. The one exception is a ticket filed *during* the run
    **because the run is stuck on what it fixes**; `stuck_on` names the
    clump it unblocks, which has to be one of this run's, and that ticket is
    dispatched into this run. Returns a new list; the frozen set is never
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


def read_clumps(path):
    """A clump list from a JSON file — `closure.py`'s own `clumps` entries,
    each with the `workspace` an in-flight one sits in."""
    try:
        with open(path) as fh:
            clumps = json.load(fh)
    except (OSError, ValueError) as exc:
        raise LoopError(f"could not read {path}: {exc}") from exc
    if not isinstance(clumps, list):
        raise LoopError(f"{path} is not a list of clumps")
    return clumps


def render_dispatch(picked, state):
    lines = [f"dispatch  #{key_of(c)}  "
             + ",".join(f"#{n}" for n in c["tickets"]) for c in picked]
    for held in state["held"]:
        lines.append(
            f"held      #{key_of(held['clump'])}  by #{held['holder']} in "
            f"{held['workspace']}  over {', '.join(held['over'])}")
    return "\n".join(lines) or "nothing to dispatch"


def main(argv):
    parser = argparse.ArgumentParser(
        prog="loop.py", description=(
            "The burn loop's mechanical steps. `announce` has no subcommand: "
            "sending is SendMessage, which the controller calls itself."))
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
    hub = subs.add_parser(
        "hub", help="whether a landing asks for full re-exploration")
    hub.add_argument("--candidates", required=True)
    hub.add_argument("--landed", required=True,
                     help="comma-separated paths the landing's diff touched")
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
            in_flight = read_clumps(args.in_flight) if args.in_flight else []
            picked = refill(candidates, in_flight, args.free)
            print(render_dispatch(picked, frontier(candidates, in_flight)))
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


def git(args):
    """`git` as the seat check calls it, from the cwd the controller is in."""
    done = subprocess.run(["git", *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise LoopError(
            f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


if __name__ == "__main__":
    sys.exit(main(sys.argv))
