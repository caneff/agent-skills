#!/usr/bin/env python3
"""One run's state, machine-readable, at `~/.cache/burndown/<run-id>.json`:

    python3 burndown/runfile.py start    <run-id> [--slots <k>] [--controller <agent>]
    python3 burndown/runfile.py clump    <run-id> --tickets 901,902 --workspace <path> --agent <name>
    python3 burndown/runfile.py land     <run-id> --clump 901 --sha <sha>
    python3 burndown/runfile.py leftover <run-id> --clump 901 --pr 950 --from <dispositions sidecar>
    python3 burndown/runfile.py show     <run-id>
    python3 burndown/runfile.py resume   <run-id> --live a,b [--controller <agent>]

It holds the run id, the slot budget, the controller's herdr agent name, and
one entry per clump — its ticket list, its workspace, its worker's **herdr
agent name**, and its squash sha once it lands. It also holds the run's
**leftovers**, copied at landing from each PR's dispositions sidecar
(`implement/SKILL.md` § Review) rather than transcribed by hand. `resume`
reads it back and splits the clumps against the agents that are alive: the
live workers to re-announce the controller to, the vanished ones to
reconcile by hand, and the landings already banked. Only the controller
writes.

Why one file per run, why `~/.cache`, why the herdr agent name and why each
write replaces the file in one step: `references/run-file.md`, which is where
those reasons live rather than being restated here.
"""
import contextlib
import fcntl
import json
import math
import os
import re
import sys
import time

CACHE_DIR = "~/.cache/burndown"
# How long a writer waits for the run file's lock before refusing, matching the
# `flock -w 30` the dispatch lane already waits with.
LOCK_TIMEOUT = 30.0

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
# ASCII digits, and no other kind. `str.isdigit()` is true for `²`, which
# `int()` then rejects with a traceback, and for `٩`, which `int()` accepts
# as 9 — so `٩01` would register a ticket the brief never named.
_TICKET = re.compile(r"[0-9]+\Z")

# What a run file must carry to be read as one at all, top level and per
# clump. The file outlives the code that wrote it, so a shape this module does
# not recognise says so here rather than raising a KeyError three calls later,
# inside the first read a resumed controller does.
_KEYS = ("run_id", "slots", "controller", "clumps")
_CLUMP_KEYS = ("tickets", "workspace", "agent", "landed")
# A clump's parallel-job state. `None` is "nothing on record", which is not
# the same fact as "no job": a worker that never declared and a worker that
# declared none read alike to a controller charging cores, and silence read
# as zero is the #351 dispatch into a box already at 25.8 load. Absent from
# a #892-era file, so it is filled in on load rather than demanded.
_JOB_STATES = ("running", "none", "done")
# What one leftover entry holds: the clump that carried the finding, the
# full ticket list that clump closes, the PR it landed on, and the sidecar
# line's own fields untouched.
_LEFTOVER_KEYS = ("clump", "tickets", "pr", "id", "file", "title",
                  "severity", "text")
# The five outcomes `implement/SKILL.md` § Review's dispositions sidecar can
# carry; why any other is refused, not skipped: `references/run-file.md`
# § Leftovers.
_SIDECAR_OUTCOMES = ("fixed", "disputed", "filed", "handed-back", "leftover")


class RunFileError(Exception):
    """The run file could not be read or written as asked. One stderr line,
    never a traceback: a resumed controller needs the reason, not a stack."""


def env_number(name, default):
    """A non-negative, finite number from the environment, or `default` when
    the variable is unset or empty (`VAR=` is the shell's way to clear an
    override). Every environment read in this module goes through here: an
    unguarded `float()` turns a value inherited from a parent shell into a
    traceback, and the one moment these are read is a controller recovering
    from a restart, which needs the diagnostic. `inf` parses and would wait
    forever; `nan` parses and compares false against every deadline, which is
    the same wait with no name."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise RunFileError(f"{name} is not a number: {raw!r}") from None
    if not math.isfinite(value) or value < 0:
        raise RunFileError(f"{name} is not a non-negative, finite number: {raw!r}")
    return value


DEFAULT_SLOTS = 5


def slot_budget(slots):
    """A run's slot budget: a positive count, and not a bool."""
    if isinstance(slots, bool) or not isinstance(slots, int) or slots < 1:
        raise RunFileError(f"not a slot budget: {slots!r}")
    return slots


def checked_run_id(run_id):
    if not isinstance(run_id, str) or not _RUN_ID.match(run_id) or ".." in run_id:
        raise RunFileError(f"not a run id: {run_id!r}")
    return run_id


def cache_root(root=None):
    return root or os.path.expanduser(CACHE_DIR)


def path(run_id, root=None):
    return os.path.join(cache_root(root), f"{checked_run_id(run_id)}.json")


@contextlib.contextmanager
def locked(run_id, root=None):
    """Hold the run file's advisory lock across a read-modify-replace. Without
    it two commands racing both read, both replace, and the second writes back
    a run that never saw the first — a landing's sha overwritten by a stale
    `landed: null`, and a resumed controller re-dispatching work that already
    landed. `flock`, the same lock the dispatch lane waits on.

    The lock lives beside the run file as `<run-id>.json.lock`, because the run
    file itself does not exist yet when `start` takes the lock."""
    lock_path = path(run_id, root) + ".lock"
    timeout = env_number("BURNDOWN_RUNFILE_LOCK_TIMEOUT", LOCK_TIMEOUT)
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        raise RunFileError(f"could not open the lock {lock_path}: {exc}") from exc
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RunFileError(
                        f"timed out after {timeout:g}s waiting for the lock "
                        f"{lock_path} — another writer is holding it") from None
                time.sleep(0.05)
        # Only ever set by a test, to hold this critical section open past
        # another writer's read: nothing else can witness the lock rather than
        # pass on how two processes happen to interleave.
        delay = env_number("BURNDOWN_RUNFILE_DELAY_MS", 0)
        if delay:
            time.sleep(delay / 1000)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def save(run, root=None):
    """Replace the run file in one step. The machine going down mid-write is
    the event this file exists to survive, and a half-written run file reads
    as a run with no clumps — so the new state is written beside the old one,
    flushed to disk, and moved over it with `os.replace`. A reader sees the
    old file or the new one, never a torn one."""
    target = path(run["run_id"], root)
    directory = os.path.dirname(target)
    tmp = f"{target}.tmp.{os.getpid()}"
    try:
        os.makedirs(directory, exist_ok=True)
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
    fsync_dir(directory)


def fsync_dir(directory):
    """Make the rename itself durable, best effort. The file is already
    written and moved by the time this runs, so nothing here may raise: a
    directory that cannot be opened or synced (mode 0300, a filesystem that
    refuses it) must not report a write that landed as a write that failed —
    the caller would retry and meet "already has a file"."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
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
    if not isinstance(run["clumps"], list):
        raise RunFileError(
            f"{target} holds clumps as {type(run['clumps']).__name__}, "
            "not a list")
    # Every field, not just the keys: a resumed controller meeting a run file
    # the code no longer recognises needs a diagnostic, and a `slots` that is
    # a string reaches arithmetic in `reconcile` two calls later.
    try:
        if run["run_id"] != run_id:
            raise RunFileError(
                f"{target} says it is run {run['run_id']!r}, not {run_id!r}")
        slot_budget(run["slots"])
        if run["controller"] is not None:
            named(run["controller"], "herdr agent name")
        for entry in run["clumps"]:
            if not isinstance(entry, dict):
                raise RunFileError(
                    f"holds a clump as {type(entry).__name__}")
            absent = [key for key in _CLUMP_KEYS if key not in entry]
            if absent:
                raise RunFileError(f"has a clump missing {', '.join(absent)}")
            if not isinstance(entry["tickets"], list):
                raise RunFileError("has a clump whose tickets are not a list")
            ticket_numbers(entry["tickets"])
            named(entry["workspace"], "workspace path")
            named(entry["agent"], "herdr agent name")
            # Filled in rather than demanded: a run file written before jobs
            # were recorded is still that controller's run.
            entry["job"] = job_record(entry.get("job"))
            if entry["landed"] is not None:
                checked_sha(entry["landed"])
        # Filled in rather than demanded, the same as `job` above: a run file
        # written before leftovers existed is still that controller's run.
        leftovers = run.get("leftovers", [])
        if not isinstance(leftovers, list):
            raise RunFileError(
                f"holds leftovers as {type(leftovers).__name__}, not a list")
        run["leftovers"] = [leftover_record(item) for item in leftovers]
    except RunFileError as exc:
        raise RunFileError(f"{target}: {exc}") from None
    return run


def start(run_id, slots=DEFAULT_SLOTS, controller=None, root=None):
    slots = slot_budget(slots)
    if controller is not None:
        controller = named(controller, "herdr agent name")
    target = path(run_id, root)
    with locked(run_id, root):
        if os.path.exists(target):
            raise RunFileError(
                f"run {run_id} already has a file at {target} — resume reads "
                "it, and a second start would wipe it")
        run = {"run_id": run_id, "slots": slots, "controller": controller,
               "clumps": [], "leftovers": []}
        save(run, root)
    return run


def positive_int(value, what):
    """A whole number of at least one, never a bool (`True` is an `int`)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RunFileError(f"not a {what}: {value!r}")
    return value


def clump_entry(run, lowest):
    """The run's clump keyed by its lowest ticket, or a refusal naming it."""
    for entry in run["clumps"]:
        if entry["tickets"][0] == lowest:
            return entry
    raise RunFileError(f"run {run['run_id']} has no clump #{lowest}")


def ticket_numbers(tickets):
    """A clump's ticket list: at least one positive integer, sorted. The
    lowest is the clump's key — the same one its branch is named for."""
    if not tickets:
        raise RunFileError("a clump names at least one ticket")
    out = []
    for ticket in tickets:
        out.append(positive_int(ticket, "ticket number"))
    return sorted(set(out))


def job_record(value):
    """A clump's job state as the run file holds it: `None` when nothing is
    on record, else `{"state": <running|none|done>, "cores": <n>}`. A running
    job names at least one core; the other two states name none."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RunFileError(f"not a job record: {value!r}")
    state, cores = value.get("state"), value.get("cores", 0)
    if state not in _JOB_STATES:
        raise RunFileError(
            f"not a job state: {state!r} — one of {', '.join(_JOB_STATES)}")
    if isinstance(cores, bool) or not isinstance(cores, int) or cores < 0:
        raise RunFileError(f"not a core count: {cores!r}")
    if state == "running" and cores < 1:
        raise RunFileError("a running job names at least one core")
    if state != "running" and cores:
        raise RunFileError(
            f"a {state} job holds no cores, so it names none, not {cores}")
    return {"state": state, "cores": cores}


def pr_number(value):
    return positive_int(value, "PR number")


def leftover_field(value, what):
    """A leftover's id, file, title, severity or text: a non-blank string
    with no line break (a CommonMark line ends at LF or a lone CR) — the
    same hygiene `dispositions_fixture_test.py` holds the sidecar line to.
    `render` prints one line per leftover, and an embedded break would split
    that line in two."""
    if (not isinstance(value, str) or not value.strip()
            or "\n" in value or "\r" in value):
        raise RunFileError(f"not a {what}: {value!r}")
    return value


def leftover_record(value):
    """A leftover as the run file holds it: the clump and the full ticket
    list it closes, the PR it landed on, and the sidecar line's own `id`,
    `file`, `title`, `severity` and `text`, each checked."""
    if not isinstance(value, dict):
        raise RunFileError(f"not a leftover: {value!r}")
    missing = [key for key in _LEFTOVER_KEYS if key not in value]
    if missing:
        raise RunFileError(f"a leftover is missing {', '.join(missing)}")
    return {
        "clump": positive_int(value["clump"], "clump ticket"),
        "tickets": ticket_numbers(value["tickets"]),
        "pr": pr_number(value["pr"]),
        "id": leftover_field(value["id"], "finding id"),
        "file": leftover_field(value["file"], "file"),
        "title": leftover_field(value["title"], "title"),
        "severity": leftover_field(value["severity"], "severity"),
        "text": leftover_field(value["text"], "finding text"),
    }


def read_dispositions(sidecar_path):
    """Every line of a dispositions sidecar (`implement/SKILL.md` § Review),
    in order, each a JSON object with one of the five sidecar outcomes. A
    line that is not is refused by file and line, never skipped: a skipped
    line reads as a PR that genuinely left nothing, and `sweep.py counts`
    would report the same low count with a clean exit."""
    try:
        with open(sidecar_path) as fh:
            raw_lines = fh.readlines()
    except OSError as exc:
        raise RunFileError(
            f"could not read {sidecar_path}: {exc.strerror}") from exc
    out = []
    for n, raw in enumerate(raw_lines, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except ValueError as exc:
            raise RunFileError(
                f"{sidecar_path}:{n} is not readable JSON: {exc}") from exc
        outcome = obj.get("outcome") if isinstance(obj, dict) else None
        if outcome not in _SIDECAR_OUTCOMES:
            raise RunFileError(
                f"{sidecar_path}:{n} is not a dispositions sidecar line — "
                f"its outcome is {outcome!r}, not one of "
                f"{', '.join(_SIDECAR_OUTCOMES)}")
        out.append((n, obj))
    return out


def read_leftover_lines(sidecar_path):
    """Every `leftover` line of a dispositions sidecar, in order. The other
    four outcomes are not this command's to transcribe, and are skipped."""
    out = []
    for n, obj in read_dispositions(sidecar_path):
        if obj["outcome"] != "leftover":
            continue
        missing = [key for key in ("id", "file", "title", "severity", "text")
                   if key not in obj]
        if missing:
            raise RunFileError(
                f"{sidecar_path}:{n} is a leftover missing "
                f"{', '.join(missing)}")
        out.append(obj)
    return out


def leftover(run_id, lowest, pr, sidecar_path, root=None):
    """Copy every `leftover` line of a landed PR's dispositions sidecar into
    the run file. Idempotent per PR and finding id; a finding already
    recorded under a different PR, or a clump with no recorded landing, is
    refused — the reasons are in `references/run-file.md` § Leftovers.

    Returns `(run, added)`, `added` being the finding ids this call
    actually appended, for a caller to report a copy count."""
    pr = pr_number(pr)
    found = read_leftover_lines(sidecar_path)
    with locked(run_id, root):
        run = load(run_id, root)
        entry = clump_entry(run, lowest)
        if entry["landed"] is None:
            raise RunFileError(
                f"clump #{lowest} has not landed — `land` comes first")
        clump_prs = {item["id"]: item["pr"] for item in run["leftovers"]
                     if item["clump"] == lowest}
        added = []
        for obj in found:
            if clump_prs.get(obj["id"]) == pr:
                continue
            if obj["id"] in clump_prs:
                raise RunFileError(
                    f"finding {obj['id']} is already recorded under PR "
                    f"#{clump_prs[obj['id']]}, not #{pr}")
            record = leftover_record({
                "clump": lowest, "tickets": entry["tickets"], "pr": pr,
                "id": obj["id"], "file": obj["file"], "title": obj["title"],
                "severity": obj["severity"], "text": obj["text"],
            })
            run["leftovers"].append(record)
            clump_prs[obj["id"]] = pr
            added.append(obj["id"])
        save(run, root)
    return run, added


def job(run_id, lowest, state, cores=0, root=None):
    """Record what parallel job a clump's worker has out: `running` with its
    core count, `none` when the worker declared it launched none, or `done`
    when it reports the job finished.

    The declaration lives here and not in a dispatch's argv, because a
    controller that restarts mid-run has only this file: a hold that lived in
    one command line is a hold a resume cannot recover, and the free slot it
    then dispatches into is the contention #351 produced."""
    record = job_record({"state": state, "cores": cores})
    with locked(run_id, root):
        run = load(run_id, root)
        clump_entry(run, lowest)["job"] = record
        save(run, root)
        return run


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
    with locked(run_id, root):
        run = load(run_id, root)
        same = next(
            (c for c in run["clumps"] if c["tickets"][0] == tickets[0]), None)
        for other in run["clumps"]:
            shared = sorted(set(other["tickets"]) & set(tickets))
            if other is not same and shared:
                raise RunFileError(
                    f"ticket(s) {', '.join(f'#{n}' for n in shared)} are "
                    f"already in clump #{other['tickets'][0]}")
        if same:
            dropped = sorted(set(same["tickets"]) - set(tickets))
            if dropped:
                raise RunFileError(
                    f"clump #{tickets[0]} already holds "
                    f"{', '.join(f'#{n}' for n in dropped)} — re-registering "
                    "may grow a clump, never drop a ticket out of the run")
        entry = {"tickets": tickets, "workspace": workspace, "agent": agent,
                 "landed": same["landed"] if same else None,
                 "job": same["job"] if same else None}
        run["clumps"] = sorted(
            [c for c in run["clumps"] if c is not same] + [entry],
            key=lambda c: c["tickets"][0])
        save(run, root)
    return run


def checked_sha(sha):
    if not isinstance(sha, str) or not _SHA.match(sha):
        raise RunFileError(f"not a squash sha: {sha!r}")
    return sha


def land(run_id, lowest, sha, root=None):
    """Record a clump's squash sha. The sha is final: a second, different one
    is a stale writer, not a correction."""
    checked_sha(sha)
    with locked(run_id, root):
        run = load(run_id, root)
        entry = clump_entry(run, lowest)
        if entry["landed"] not in (None, sha):
            raise RunFileError(
                f"clump #{lowest} already landed at {entry['landed']}")
        entry["landed"] = sha
        save(run, root)
        return run


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
    # A vanished clump counts against the budget with the live ones: its
    # worker may still be holding its tickets, so refilling its slot before
    # anyone has reconciled it puts a second worker in the same files. Only a
    # landing frees a slot for certain.
    held = len(announce) + len(vanished)
    return {"run_id": run["run_id"], "slots": run["slots"],
            "controller": run["controller"],
            "free": max(0, run["slots"] - held), "held": held,
            "announce": announce, "vanished": vanished, "landed": landed}


def resume(run_id, live_agents, controller=None, root=None):
    """Read the run back and reconcile it against the live agents. Given the
    controller's current herdr agent name, record it: the address every live
    worker's brief carries is the one the restart just invalidated."""
    if controller is not None:
        named(controller, "herdr agent name")
    with locked(run_id, root):
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
                     f"{entry['agent']}  {entry['workspace']}  {state}  "
                     f"{render_job(entry.get('job'))}")
    for item in run.get("leftovers", []):
        lines.append(
            f"leftover  clump #{item['clump']}  {tickets_of(item)}  "
            f"PR #{item['pr']}  {item['id']}  {item['severity']}  "
            f"{item['file']}  {item['title']!r}")
    return "\n".join(lines)


def render_job(record):
    """A clump's job state as a controller reads it back, including the state
    that is not a fact: nothing on record."""
    if record is None:
        return "job: not declared"
    if record["state"] == "running":
        return f"job: {record['cores']} cores"
    return ("job: no parallel job" if record["state"] == "none"
            else "job: done")


def tickets_of(entry):
    return ",".join(f"#{n}" for n in entry["tickets"])


def render_resume(state):
    """What resume owes the controller: the slot budget it recovered, the live
    workers to re-announce itself to, the vanished ones to reconcile by hand,
    and the landings already banked."""
    lines = [f"run {state['run_id']}  slots {state['slots']}  "
             f"held {state['held']}  free {state['free']}  "
             f"controller {state['controller'] or '-'}"]
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
    """`901,902` or `901 902`. ASCII digits only: `int()` reads `9_01` and
    `+901` as 901, and a run file that says #901 where the brief said `9_01` is
    a wrong answer rather than a lenient one."""
    parts = text.replace(",", " ").split()
    if not parts or not all(_TICKET.match(part) for part in parts):
        raise RunFileError(f"not a ticket list: {text!r}")
    return [int(part) for part in parts]


def main(argv):
    import argparse

    parser = argparse.ArgumentParser(
        prog="runfile.py",
        description="One burn run's state at ~/.cache/burndown/<run-id>.json")
    subs = parser.add_subparsers(dest="command", required=True)

    new = subs.add_parser("start", help="create the run file")
    new.add_argument("run_id")
    new.add_argument("--slots", type=int, default=DEFAULT_SLOTS,
                     help=f"slot budget, a positive integer (default {DEFAULT_SLOTS})")
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

    lo = subs.add_parser(
        "leftover",
        help="copy a landed PR's leftover findings from its dispositions "
             "sidecar")
    lo.add_argument("run_id")
    lo.add_argument("--clump", type=int, required=True,
                    help="the clump's lowest ticket")
    lo.add_argument("--pr", type=int, required=True)
    lo.add_argument("--from", dest="from_path", required=True,
                    metavar="PATH", help="the dispositions sidecar to copy from")

    work = subs.add_parser("job", help="record a clump's parallel-job state")
    work.add_argument("run_id")
    work.add_argument("--clump", type=int, required=True,
                      help="the clump's lowest ticket")
    size = work.add_mutually_exclusive_group(required=True)
    size.add_argument("--cores", type=int,
                      help="cores of the job this worker has out")
    size.add_argument("--none", action="store_true",
                      help="the worker declared it launched no parallel job")
    size.add_argument("--done", action="store_true",
                      help="the worker reports its job finished")

    out = subs.add_parser("show", help="print the run file")
    out.add_argument("run_id")

    back = subs.add_parser("resume", help="reconcile against the live agents")
    back.add_argument("run_id")
    back.add_argument("--live", default="",
                      help="comma-separated herdr agent names that are alive")
    back.add_argument("--controller", help="the controller's current name")

    args = parser.parse_args(argv[1:])
    # One seam per caller: in-process callers pass `root`, the CLI resolves the
    # environment once here and passes it down (`cost.py` does the same).
    override = os.environ.get("BURNDOWN_CACHE_DIR")
    root = os.path.expanduser(override) if override else None
    try:
        if args.command == "start":
            print(render(start(args.run_id, args.slots, args.controller, root)))
        elif args.command == "clump":
            print(render(clump(args.run_id, parse_tickets(args.tickets),
                               args.workspace, args.agent, root)))
        elif args.command == "land":
            print(render(land(args.run_id, args.clump, args.sha, root)))
        elif args.command == "leftover":
            run, added = leftover(args.run_id, args.clump, args.pr,
                                  args.from_path, root)
            print(render(run))
            print(f"copied {len(added)} leftover(s) from {args.from_path}")
        elif args.command == "job":
            state = ("running" if args.cores is not None
                     else "none" if args.none else "done")
            print(render(job(args.run_id, args.clump, state,
                             args.cores or 0, root)))
        elif args.command == "show":
            print(render(load(args.run_id, root)))
        elif args.command == "resume":
            live = args.live.replace(",", " ").split()
            print(render_resume(resume(args.run_id, live, args.controller,
                                       root)))
    except RunFileError as exc:
        print(f"runfile.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
