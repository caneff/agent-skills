#!/usr/bin/env python3
"""One run's state, machine-readable, at `~/.cache/burndown/<run-id>.json`:

    python3 burndown/runfile.py start  <run-id> --slots <k> [--controller <agent>]
    python3 burndown/runfile.py clump  <run-id> --tickets 901,902 --workspace <path> --agent <name>
    python3 burndown/runfile.py land   <run-id> --clump 901 --sha <sha>
    python3 burndown/runfile.py show   <run-id>
    python3 burndown/runfile.py resume <run-id> --live a,b [--controller <agent>]

It holds the run id, the slot budget, the controller's herdr agent name, and
one entry per clump — its ticket list, its workspace, its worker's **herdr
agent name**, and its squash sha once it lands. `resume` reads it back and
splits the clumps against the agents that are alive: the live workers to
re-announce the controller to, the vanished ones to reconcile by hand, and the
landings already banked.

One file per run, not one per repo: on #781 a per-repo append-only log already
held five earlier burns before that run wrote its first line, so "is this run
finished" was a question answered by eye. And `~/.cache`, not `/tmp` or a
session scratchpad, because a WSL restart wipes those and a restart is the
event this file exists for — the same restart renamed every Claude session
(controller `spectest-1a` to `spectest-f3`), which is why a worker is
addressed here by its herdr agent name and never by a session name.

Only the controller writes. Every write replaces the file in one step, so a
reader after a crash sees the old state or the new one, never a torn one. The
contract and the resume procedure: `references/run-file.md`.
"""
import json
import os
import re
import sys

CACHE_DIR = "~/.cache/burndown"

# A run id becomes a filename, so it is letters, digits, dash, dot and
# underscore, starting with a letter or a digit: a `/` or a `..` would write
# the run's state outside the cache dir, and a leading dot hides it from the
# reader coming back after a restart. `\Z` and not `$`, which also matches
# before a trailing newline — a run id with a newline in it is a filename with
# a newline in it.
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
# An abbreviated or full git object name. `HEAD`, a branch name or a sha with
# a stray space or newline is not a landing: the run file is what a later
# reader checks a landing against, and a name that moves answers a different
# question.
_SHA = re.compile(r"[0-9a-f]{7,40}\Z")

# What a run file must carry to be read as one at all. The file outlives the
# code that wrote it, so a shape this module does not recognise says so here
# rather than raising a KeyError three calls later.
_KEYS = ("run_id", "slots", "controller", "clumps")


class RunFileError(Exception):
    """The run file could not be read or written as asked. One stderr line,
    never a traceback: a resumed controller needs the reason, not a stack."""


def checked(run_id):
    if not isinstance(run_id, str) or not _RUN_ID.match(run_id) or ".." in run_id:
        raise RunFileError(f"not a run id: {run_id!r}")
    return run_id


def cache_root(root=None):
    return root or os.path.expanduser(
        os.environ.get("BURNDOWN_CACHE_DIR") or CACHE_DIR)


def path(run_id, root=None):
    return os.path.join(cache_root(root), f"{checked(run_id)}.json")


def save(run, root=None):
    """Replace the run file in one step. The machine going down mid-write is
    the event this file exists to survive, and a half-written run file reads
    as a run with no clumps — so the new state is written beside the old one,
    flushed to disk, and moved over it with `os.replace`. A reader sees the
    old file or the new one, never a torn one."""
    target = path(run["run_id"], root)
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)
    tmp = f"{target}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w") as fh:
            json.dump(run, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except OSError as exc:
        raise RunFileError(f"could not write {target}: {exc}") from exc
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    fd = os.open(directory, os.O_RDONLY)  # the rename itself, made durable
    try:
        os.fsync(fd)
    except OSError:
        pass  # not every filesystem allows fsync on a directory
    finally:
        os.close(fd)


def load(run_id, root=None):
    target = path(run_id, root)
    try:
        with open(target) as fh:
            run = json.load(fh)
    except OSError as exc:
        raise RunFileError(f"no run file at {target}: {exc.strerror}") from exc
    except ValueError as exc:
        raise RunFileError(f"{target} is not readable JSON: {exc}") from exc
    if not isinstance(run, dict):
        raise RunFileError(f"{target} holds {type(run).__name__}, not a run")
    missing = [key for key in _KEYS if key not in run]
    if missing:
        raise RunFileError(f"{target} is missing {', '.join(missing)}")
    return run


def start(run_id, slots, controller=None, root=None):
    if isinstance(slots, bool) or not isinstance(slots, int) or slots < 1:
        raise RunFileError(f"not a slot budget: {slots!r}")
    target = path(run_id, root)
    if os.path.exists(target):
        raise RunFileError(
            f"run {run_id} already has a file at {target} — resume reads it, "
            "and a second start would wipe it")
    run = {"run_id": run_id, "slots": slots, "controller": controller,
           "clumps": []}
    save(run, root)
    return run


def ticket_numbers(tickets):
    """A clump's ticket list: at least one positive integer, sorted. The
    lowest is the clump's key — the same one its branch is named for."""
    if not tickets:
        raise RunFileError("a clump names at least one ticket")
    out = []
    for ticket in tickets:
        if isinstance(ticket, bool) or not isinstance(ticket, int) or ticket < 1:
            raise RunFileError(f"not a ticket number: {ticket!r}")
        out.append(ticket)
    return sorted(set(out))


def named(value, what):
    """A workspace path or a herdr agent name. Blank is not an answer: the
    agent name is the only way to reach that worker after a restart, and the
    workspace path the only way to read what it did."""
    if not isinstance(value, str) or not value.strip():
        raise RunFileError(f"not a {what}: {value!r}")
    return value


def clump(run_id, tickets, workspace, agent, root=None):
    """Register a clump under its lowest ticket: its ticket list, its
    workspace, and the **herdr agent name** its worker answers to. A session
    name does not survive a restart; the herdr agent name does.

    Registering the same lowest ticket again moves the workspace and the agent
    and keeps the landing sha — a clump redispatched after a park is the same
    clump. A ticket that already sits in another clump is refused: one ticket
    in two clumps is two workers in the same files."""
    tickets = ticket_numbers(tickets)
    workspace = named(workspace, "workspace path")
    agent = named(agent, "herdr agent name")
    run = load(run_id, root)
    same = next((c for c in run["clumps"] if c["tickets"][0] == tickets[0]), None)
    for other in run["clumps"]:
        shared = sorted(set(other["tickets"]) & set(tickets))
        if other is not same and shared:
            raise RunFileError(
                f"ticket(s) {', '.join(f'#{n}' for n in shared)} are already "
                f"in clump #{other['tickets'][0]}")
    entry = {"tickets": tickets, "workspace": workspace, "agent": agent,
             "landed": same["landed"] if same else None}
    run["clumps"] = sorted(
        [c for c in run["clumps"] if c is not same] + [entry],
        key=lambda c: c["tickets"][0])
    save(run, root)
    return run


def land(run_id, lowest, sha, root=None):
    """Record a clump's squash sha. The sha is final: a second, different one
    is a stale writer, not a correction."""
    if not isinstance(sha, str) or not _SHA.match(sha):
        raise RunFileError(f"not a squash sha: {sha!r}")
    run = load(run_id, root)
    for entry in run["clumps"]:
        if entry["tickets"][0] != lowest:
            continue
        if entry["landed"] not in (None, sha):
            raise RunFileError(
                f"clump #{lowest} already landed at {entry['landed']}")
        entry["landed"] = sha
        save(run, root)
        return run
    raise RunFileError(f"run {run_id} has no clump #{lowest}")


def reconcile(run, live_agents):
    """Split a run's clumps three ways against the agents that are alive:
    the live workers to re-announce to, the vanished ones a controller has to
    reconcile by hand, and the landings. A landed clump is in neither working
    bucket however its worker looks — its slot is free and its sha is final.
    """
    live = set(live_agents)
    announce, vanished, landed = [], [], []
    for entry in run["clumps"]:
        if entry["landed"]:
            landed.append(entry)
        elif entry["agent"] in live:
            announce.append(entry)
        else:
            vanished.append(entry)
    return {"run_id": run["run_id"], "slots": run["slots"],
            "controller": run["controller"],
            "free": max(0, run["slots"] - len(announce)),
            "announce": announce, "vanished": vanished, "landed": landed}


def resume(run_id, live_agents, controller=None, root=None):
    """Read the run back and reconcile it against the live agents. Given the
    controller's current herdr agent name, record it: the address every live
    worker's brief carries is the one the restart just invalidated."""
    run = load(run_id, root)
    if controller is not None and controller != run["controller"]:
        run["controller"] = controller
        save(run, root)
    return reconcile(run, live_agents)


def render(run):
    """The run as the controller reads it back: one header line, one line per
    clump, landings marked with their sha."""
    lines = [f"run {run['run_id']}  slots {run['slots']}  "
             f"controller {run['controller'] or '-'}"]
    for entry in run["clumps"]:
        state = f"landed {entry['landed']}" if entry["landed"] else "in flight"
        lines.append(f"clump #{entry['tickets'][0]}  {tickets_of(entry)}  "
                     f"{entry['agent']}  {entry['workspace']}  {state}")
    return "\n".join(lines)


def tickets_of(entry):
    return ",".join(f"#{n}" for n in entry["tickets"])


def render_resume(state):
    """What resume owes the controller: the slot budget it recovered, the live
    workers to re-announce itself to, the vanished ones to reconcile by hand,
    and the landings already banked."""
    lines = [f"run {state['run_id']}  slots {state['slots']}  "
             f"free {state['free']}  controller {state['controller'] or '-'}"]
    for entry in state["announce"]:
        lines.append(f"re-announce  {entry['agent']}  {tickets_of(entry)}  "
                     f"{entry['workspace']}")
    for entry in state["vanished"]:
        lines.append(f"vanished     {entry['agent']}  {tickets_of(entry)}  "
                     f"{entry['workspace']}")
    for entry in state["landed"]:
        lines.append(f"landed       {entry['landed']}  {tickets_of(entry)}")
    return "\n".join(lines)


def parse_tickets(text):
    try:
        return [int(part) for part in text.replace(",", " ").split()]
    except ValueError:
        raise RunFileError(f"not a ticket list: {text!r}") from None


def main(argv):
    import argparse

    parser = argparse.ArgumentParser(
        prog="runfile.py",
        description="One burn run's state at ~/.cache/burndown/<run-id>.json")
    subs = parser.add_subparsers(dest="command", required=True)

    new = subs.add_parser("start", help="create the run file")
    new.add_argument("run_id")
    new.add_argument("--slots", type=int, required=True)
    new.add_argument("--controller", help="the controller's herdr agent name")

    reg = subs.add_parser("clump", help="register or re-register a clump")
    reg.add_argument("run_id")
    reg.add_argument("--tickets", required=True, help="e.g. 901,902")
    reg.add_argument("--workspace", required=True)
    reg.add_argument("--agent", required=True,
                     help="the worker's herdr agent name, not its session name")

    done = subs.add_parser("land", help="record a clump's squash sha")
    done.add_argument("run_id")
    done.add_argument("--clump", type=int, required=True,
                      help="the clump's lowest ticket")
    done.add_argument("--sha", required=True)

    out = subs.add_parser("show", help="print the run file")
    out.add_argument("run_id")

    back = subs.add_parser("resume", help="reconcile against the live agents")
    back.add_argument("run_id")
    back.add_argument("--live", default="",
                      help="comma-separated herdr agent names that are alive")
    back.add_argument("--controller", help="the controller's current name")

    args = parser.parse_args(argv[1:])
    try:
        if args.command == "start":
            print(render(start(args.run_id, args.slots, args.controller)))
        elif args.command == "clump":
            print(render(clump(args.run_id, parse_tickets(args.tickets),
                               args.workspace, args.agent)))
        elif args.command == "land":
            print(render(land(args.run_id, args.clump, args.sha)))
        elif args.command == "show":
            print(render(load(args.run_id)))
        elif args.command == "resume":
            live = [name for name in args.live.replace(",", " ").split()]
            print(render_resume(
                resume(args.run_id, live, args.controller)))
    except RunFileError as exc:
        print(f"runfile.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
