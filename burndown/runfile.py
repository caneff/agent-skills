#!/usr/bin/env python3
"""One run's state, machine-readable, at `~/.cache/burndown/<run-id>.json`:

    python3 burndown/runfile.py start    <run-id> --repo <checkout> [--slots <k>] [--controller <agent>]
    python3 burndown/runfile.py clump    <run-id> --tickets 901,902 --workspace <path> --agent <name>
    python3 burndown/runfile.py job      <run-id> --clump 901 --cores 8 | --none | --done
    python3 burndown/runfile.py land     <run-id> --clump 901 --sha <sha>
    python3 burndown/runfile.py close    <run-id> --clump 901 --reason <text>
    python3 burndown/runfile.py pr-up    <run-id> --clump 901 --pr 950 | --clear
    python3 burndown/runfile.py leftover <run-id> --clump 901 --pr 950 --from <dispositions sidecar> --pr-body <path>
    python3 burndown/runfile.py check    --from <dispositions sidecar> --pr-body <path>
    python3 burndown/runfile.py sweep-check --ticket <sweep ticket body> --pr-body <path> --from <dispositions sidecar>
    python3 burndown/runfile.py round-1-empty --reviews-dir <dir> <ticket>
    python3 burndown/runfile.py show     <run-id>
    python3 burndown/runfile.py resume   <run-id> --live a,b [--controller <agent>]

It holds the run id, the slot budget, the controller's herdr agent name, the
**target repo** (the absolute path of the primary checkout of the repo the
run works on, which `loop.py dispatch` prints into every `implement-dispatch`
command and `sweep.py counts --repo` is checked against), and one entry per
clump — its ticket list, its workspace, its worker's **herdr agent name**, and
its squash sha once it lands — or, for a clump that closed with no landing
of its own, the reason it closed. It also holds the run's **leftovers**, copied at
landing from each PR's dispositions sidecar (`implement/SKILL.md` § Review)
rather than transcribed by hand. `resume`
reads it back and splits the clumps against the agents that are alive: the
live workers to re-announce the controller to, the vanished ones to
reconcile by hand, the landings already banked, and the clumps closed with no
landing. Only the controller writes.

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
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frontier  # noqa: E402

CACHE_DIR = "~/.cache/burndown"
# The one form of the PR-body fetch `leftover --pr-body` reads.
_FETCH_BODY = "gh pr view <pr> --repo <owner/name> --json body --jq .body"
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
# A clump's parallel-job state. `None` is "nothing on record" — only a #892-era
# file has it, since registration records `none` (#1311) — which is not
# the same fact as "no job": a worker that never declared and a worker that
# declared none read alike to a controller charging cores, and silence read
# as zero is the #351 dispatch into a box already at 25.8 load. Absent from
# a #892-era file, so it is filled in on load rather than demanded.
_JOB_STATES = ("running", "none", "done")
# What a clump registered for the first time records: its worker has launched
# nothing yet (#1311).
NEW_CLUMP_JOB = {"state": "none", "cores": 0}
# The keys a `leftover` sidecar line carries.
_SIDECAR_LEFTOVER_KEYS = ("id", "file", "title", "severity", "text")
# What one leftover entry holds: the clump that carried the finding, the
# full ticket list that clump closes, the PR it landed on, and the sidecar
# line's own fields untouched.
_LEFTOVER_KEYS = ("clump", "tickets", "pr", *_SIDECAR_LEFTOVER_KEYS)
# The five outcomes `implement/SKILL.md` § Review's dispositions sidecar can
# carry; why any other is refused, not skipped: `references/run-file.md`
# § Leftovers.
_SIDECAR_OUTCOMES = ("fixed", "disputed", "filed", "handed-back", "leftover")


def clean_git_env():
    # GIT_DIR and friends would repoint git at another repo whatever the path
    # says. The scrub `checkout_top` and `sweep.default_reviews_dir` share;
    # `closure.git_listing` has its own, wider one.
    return {k: v for k, v in os.environ.items()
            if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")}


def checkout_top(where):
    """The absolute path of the **primary checkout** of the repo `where` is
    in — `where` a checkout root, a linked worktree, or any directory inside
    either, a trailing slash included — or a `RunFileError` when `where` is
    not in a git checkout. Comparing primary checkouts, not spellings, is
    what makes a subdirectory, `path/` or a linked worktree the same target.
    A blank `where` is refused: `git -C ""` stays in the cwd, so an unset shell variable would
    record whatever repo the controller stands in."""
    if not isinstance(where, str) or not where.strip():
        raise RunFileError("no checkout named: the path is blank")
    try:
        done = subprocess.run(
            ["git", "-C", os.path.expanduser(where), "worktree", "list",
             "--porcelain"], capture_output=True, text=True, timeout=30,
            env=clean_git_env())
    except (OSError, subprocess.SubprocessError) as exc:
        raise RunFileError(f"{where} is not a git checkout: {exc}") from exc
    first = done.stdout.split("\n", 1)[0]
    if done.returncode != 0 or not first.startswith("worktree "):
        raise RunFileError(
            f"{where} is not a git checkout: {done.stderr.strip()}")
    return os.path.realpath(first[len("worktree "):])


def target_repo(run):
    """The checkout a run targets, or a `RunFileError` when its run file names
    none. A run file from before the field loads (as `job` and `leftovers`
    do), so the refusal is here, at each reader that needs the answer: a
    missing target read as "no check needed" is a `--repo`-less command
    aimed at whatever repo the cwd happens to be."""
    if run.get("repo") is None:
        raise RunFileError(
            f"run {run['run_id']} names no target repo — it was started "
            "before `runfile.py start --repo`; start a new run")
    return run["repo"]


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


def env_root():
    """The root a CLI passes down: `BURNDOWN_CACHE_DIR`, `~` expanded, or
    None for the default. Every burndown CLI resolves the environment here
    once and hands the result to in-process calls as `root`."""
    override = os.environ.get("BURNDOWN_CACHE_DIR")
    return os.path.expanduser(override) if override else None


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
            # Filled in the same way: the PR a worker's "PR up" named, or
            # `None` when none reached the controller (#1148).
            pr = entry.get("pr_up")
            entry["pr_up"] = None if pr is None else pr_number(pr)
            if entry["landed"] is not None:
                checked_sha(entry["landed"])
            # Filled in the same way: a clump closed with no landing (#1310).
            closed = entry.get("closed")
            entry["closed"] = None if closed is None else close_reason(closed)
            if entry["landed"] is not None and closed is not None:
                raise RunFileError(
                    f"has clump #{entry['tickets'][0]} both landed and closed")
        # Filled in rather than demanded, the same as `job` above: a run file
        # written before leftovers existed is still that controller's run.
        leftovers = run.get("leftovers", [])
        if not isinstance(leftovers, list):
            raise RunFileError(
                f"holds leftovers as {type(leftovers).__name__}, not a list")
        run["leftovers"] = [leftover_record(item) for item in leftovers]
        # Filled in with `None` the same way; `target_repo` refuses it.
        repo = run.get("repo")
        if repo is not None and (not isinstance(repo, str)
                                 or not os.path.isabs(repo)):
            raise RunFileError(
                f"holds a target repo that is not an absolute path: {repo!r}")
        run["repo"] = repo
    except RunFileError as exc:
        raise RunFileError(f"{target}: {exc}") from None
    return run


def start(run_id, slots=DEFAULT_SLOTS, controller=None, root=None, repo=None):
    slots = slot_budget(slots)
    if repo is None:
        raise RunFileError(
            "start needs --repo <checkout>: the run's target repo, which "
            "dispatch and the sweep's counts are checked against")
    repo = checkout_top(repo)
    if controller is not None:
        controller = named(controller, "herdr agent name")
    target = path(run_id, root)
    with locked(run_id, root):
        if os.path.exists(target):
            raise RunFileError(
                f"run {run_id} already has a file at {target} — resume reads "
                "it, and a second start would wipe it")
        run = {"run_id": run_id, "slots": slots, "controller": controller,
               "repo": repo, "clumps": [], "leftovers": []}
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
    in order, as `(line number, object)`. A line that is not a JSON object
    with one of the five sidecar outcomes is refused by file and line — why
    it is not skipped: `references/run-file.md` § Leftovers. So is a second
    line carrying an id an earlier line already used (#1124): every reader
    joins on the id, and one of the two would be dropped or counted twice."""
    try:
        with open(sidecar_path) as fh:
            raw_lines = fh.readlines()
    except OSError as exc:
        raise RunFileError(
            f"could not read {sidecar_path}: {exc.strerror}") from exc
    out = []
    seen = {}
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
        fid = obj.get("id")
        if not isinstance(fid, str) or not fid.strip():
            raise RunFileError(
                f"{sidecar_path}:{n} carries no finding id, or one that is "
                f"not a string: {fid!r}")
        if fid in seen:
            raise RunFileError(
                f"{sidecar_path}:{n} repeats finding id {fid!r} from "
                f"line {seen[fid]} — one line per finding")
        seen[fid] = n
        out.append((n, obj))
    return out


def read_leftover_lines(sidecar_path):
    """Every `leftover` line of a dispositions sidecar, in order; the other
    outcomes are skipped (`references/run-file.md` § Leftovers)."""
    out = []
    for n, obj in read_dispositions(sidecar_path):
        if obj["outcome"] != "leftover":
            continue
        missing = [key for key in _SIDECAR_LEFTOVER_KEYS if key not in obj]
        if missing:
            raise RunFileError(
                f"{sidecar_path}:{n} is a leftover missing "
                f"{', '.join(missing)}")
        out.append(obj)
    return out


# How a PR body's Decisions made cites a finding (`implement/SKILL.md`
# § The PR): ids leading a list item, grouped by commas or "and", or one
# named as `sidecar <id>` anywhere on the line.
_OUTCOME_WORD = r"(fixed|disputed|filed|handed[- ]back|leftover)"
_ID = r"[A-Za-z][A-Za-z0-9-]*[0-9][A-Za-z0-9]*"
_LIST_MARKER = re.compile(r"\s*(?:(?:[-*+]|\d+[.)])\s+)?")
# A sweep PR's controller cites an id file-qualified (`**e2e/scenarios.mjs
# S8**`, #1213): a path token before the id, optionally `:<line>` or `#L<line>`.
# The token carries a `/`, or is a bare file name in backticks: a dotted word
# (`Node.js`, `v1.2`) is prose.
_FILE_QUALIFIER = (r"(?P<file>[\w.\-/]*/[\w.\-/]*|[\w.\-/]+(?=`))"
                   r"(?::\d+|#L\d+)?[*_`]*\s+[*_`]*")
_FILE_QUALIFIER = r"(?:" + _FILE_QUALIFIER + r")?"
_LEAD_ID = re.compile(r"[*_`]*" + _FILE_QUALIFIER + r"(?P<id>" + _ID
                      + r")[*_`]*(?![\w-])")
_ID_SEPARATOR = re.compile(r"\s*,\s*(?:and\s+)?|\s+and\s+|\s*/\s*")
_TAIL_ID = re.compile(r"\bsidecar(?:\s+id)?:?\s+[*_`]*(" + _ID + r")",
                      re.IGNORECASE)
_HEADING = re.compile(r"(#{1,6})\s")
_DECISIONS = re.compile(r"(#{1,6})\s+Decisions made\b", re.IGNORECASE)


def decisions_made(body_lines):
    """The `(line number, text)` lines of the body's Decisions made section,
    or `None` when it has none."""
    out = None
    for n, line in enumerate(body_lines, start=1):
        heading = _HEADING.match(line)
        if out is not None and heading and len(heading.group(1)) <= level:
            break
        if out is not None:
            out.append((n, line))
        elif _DECISIONS.match(line):
            out, level = [], len(heading.group(1))
    return out


def _cites(line):
    """The `(file or None, id)` pairs the leading ids of a Decisions made
    line cite, and the position where the text after them starts."""
    pos = _LIST_MARKER.match(line).end()
    cites = []
    while True:
        token = _LEAD_ID.match(line, pos)
        if token is None:
            break
        cites.append((token.group("file"), token.group("id")))
        pos = token.end()
        sep = _ID_SEPARATOR.match(line, pos)
        if sep is None or _LEAD_ID.match(line, sep.end()) is None:
            break
        pos = sep.end()
    return cites, pos


def cited_ids(line):
    """`(ids, rest, cites)` of a Decisions made line: the ids it cites, the
    text after the leading ones, and the `(file or None, id)` pairs of the
    leading ones. `- S1, P2 and C1: fixed` cites all three. A file-qualified
    id (`**e2e/scenarios.mjs S8**`) cites the id alone; `cites` keeps its
    file."""
    cites, pos = _cites(line)
    ids = [fid for _, fid in cites]
    ids += [m.group(1) for m in _TAIL_ID.finditer(line)]
    return ids, line[pos:], cites


def qualified_id(file, fid):
    """The id a sweep item is recorded under, sidecar and body both:
    `<file> <id>`. `fid` alone repeats across a sweep's source PRs."""
    return f"{file} {fid}"


def split_qualified(key):
    """`(file or None, id)` of a finding id: the inverse of `qualified_id`.
    An id never holds a space, so the last one splits a `<file> <id>`."""
    file, _, fid = key.rpartition(" ")
    return (file or None), fid


def stated_outcome(rest):
    """The outcome a line states outright: the disposition word opening the
    text after its first colon outside parentheses, as in `S1 (hard):
    fixed`. `None` when that word is something else."""
    depth = 0
    for i, ch in enumerate(rest):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ":" and depth == 0:
            word = re.match(r"\s*[*_`]*" + _OUTCOME_WORD + r"\b", rest[i + 1:],
                            re.IGNORECASE)
            return word and normal_outcome(word.group(1))
    return None


def normal_outcome(word):
    return word.lower().replace(" ", "-")


def body_records(body_lines):
    """Every finding id Decisions made records, mapped to its records in
    order: `(line number, stated outcome or None, every outcome word on the
    line)`. A line naming an id with no outcome word at all records
    nothing."""
    records = {}
    for n, line in decisions_made(body_lines) or []:
        ids, rest, cites = cited_ids(line)
        words = {normal_outcome(w) for w in
                 re.findall(r"\b" + _OUTCOME_WORD + r"\b", rest, re.IGNORECASE)}
        if ids and words:
            # A file-qualified citation is recorded under its `<file> <id>`
            # as well as the bare id: a sweep item's sidecar line is keyed
            # by the qualified form, since a bare id repeats across files.
            keys = ids + [qualified_id(file, fid) for file, fid in cites
                          if file]
            for key in keys:
                records.setdefault(key, []).append(
                    (n, stated_outcome(rest), words))
    return records


def refuse_reused_ids(body_path, records, held):
    """A finding id the sidecar holds that the body records twice with two
    different stated outcomes is an id two review rounds both used (#1177):
    a round after the first prefixes its ids (`r2-S1`; the rule is in
    `multi-axis-code-review/SKILL.md` § 4), so a bare id names one finding.
    Only ids the sidecar holds are compared: a sweep PR's body cites sweep
    items whose ids repeat across their source PRs (#1213), and those are
    nobody's finding here."""
    for fid, found in records.items():
        if fid not in held:
            continue
        stated = {}
        for line_n, outcome, _ in found:
            if outcome is not None:
                stated.setdefault(outcome, line_n)
        if len(stated) > 1:
            (one, one_n), (two, two_n) = list(stated.items())[:2]
            raise RunFileError(
                f"{body_path}:{one_n} and :{two_n} record {fid} "
                f"more than once, as {one!r} and {two!r} — the "
                "id was reused across review rounds, which is not a "
                "stale sidecar. A review round after the first prefixes "
                "its ids with the round (r2-S1, r2-C3), and a sweep PR's "
                "own findings take r1-: rename the later round's ids in "
                "the sidecar and the body. A changed disposition is edited "
                "into its one line, not appended below the first")


def refuse_disagreeing_pr_body(sidecar_path, body_path):
    """A sidecar the PR body disagrees with predates a disposition change:
    the controller's fix read or ruling reaches the PR body and the sidecar
    in one step (`implement/SKILL.md` § The merge), so a line the body
    contradicts is one that step never touched (#1085). The comparison is
    by content, so a commit that changed no disposition refuses nothing
    (#1147). A line that states its outcome must match the sidecar's; one
    that only mentions outcome words disagrees when the sidecar's is not
    among them. The refusals and their reasons: `references/run-file.md`
    § Leftovers."""
    try:
        with open(body_path) as fh:
            body_lines = fh.read().splitlines()
    except OSError as exc:
        raise RunFileError(
            f"could not read the PR body {body_path}: {exc.strerror}"
        ) from exc
    if decisions_made(body_lines) is None:
        raise RunFileError(
            f"the PR body {body_path} has no Decisions made section — fetch "
            f"it with `{_FETCH_BODY}`")
    records = body_records(body_lines)
    lines = read_dispositions(sidecar_path)
    if lines and not any(obj["id"] in records for _, obj in lines):
        raise RunFileError(
            f"the PR body {body_path} cites none of {sidecar_path}'s finding "
            "ids — is it this PR's body?")
    held = {obj["id"] for _, obj in lines}
    refuse_reused_ids(body_path, records, held)
    for n, obj in lines:
        if obj["id"] not in records:
            continue
        body_n, stated, words = records[obj["id"]][-1]
        if stated is not None:
            agrees = stated == obj["outcome"]
            said = stated
        else:
            agrees = obj["outcome"] in words
            said = " or ".join(sorted(words))
        if not agrees:
            raise RunFileError(
                f"{body_path}:{body_n} records {obj['id']} as {said!r}, "
                f"but {sidecar_path}:{n} says {obj['outcome']!r} — rewrite "
                "the sidecar line; if the ruling genuinely divides a "
                "controller-only finding (never a round-1 finding's own "
                f"id), write it as two ids, one per half ({obj['id']}a, "
                f"{obj['id']}b — implement/SKILL.md § Review's split "
                "grammar), each with its own sidecar line; otherwise pass "
                "--allow-stale")
    # A sweep item's sidecar line is keyed `<file> <id>`; the bare id a
    # qualified citation is also recorded under is not a second finding, and
    # is skipped so the refusal names the qualified form (#1315). A bare cite
    # matches only a bare line: one held only as `<file> <id>` is refused,
    # naming those forms (#1343).
    shadowed = {(split_qualified(k)[1], found[-1][0])
                for k, found in records.items() if split_qualified(k)[0]}
    held_forms = {}
    for h in held:
        file, bare = split_qualified(h)
        if file:
            held_forms.setdefault(bare, []).append(h)
    for fid, found in records.items():
        body_n, stated, _ = found[-1]
        if stated != "leftover" or fid in held:
            continue
        file = split_qualified(fid)[0]
        if not file:
            if (fid, body_n) in shadowed:
                continue
            if fid in held_forms:
                # The file in backticks, then the id: the one form
                # `_FILE_QUALIFIER` reads for a root-level file too.
                cite = " or ".join(
                    f"`{split_qualified(h)[0]}` {fid}"
                    for h in sorted(held_forms[fid]))
                raise RunFileError(
                    f"{body_path}:{body_n} records {fid} as a leftover, but "
                    f"{sidecar_path} holds it only file-qualified — cite it "
                    f"as {cite}")
        keyed = " (its `id` is the `<file> <id>` form)" if file else ""
        raise RunFileError(
            f"{body_path}:{body_n} records {fid} as a leftover, but "
            f"{sidecar_path} has no line for it — append it in § "
            f"Review's leftover grammar{keyed}, or pass --allow-stale")


_SWEEP_FILE = re.compile(r"##\s+(.+?)\s*$")
_SWEEP_ITEM = re.compile(r"\s*[-*+]\s+\*\*(.+?)\*\*")


def sweep_items(ticket_text):
    """A sweep ticket's items as `<file> <id>`, in order: the grammar
    `sweep.py render_body` emits — one `## <file>` section per file, one
    `- **<id>**` bullet per item. A fenced block is skipped (`frontier.unfenced`), and the
    `## Blocked by` declaration is not a file. A bullet that kept its own
    file's prefix reads bare."""
    items, file = [], None
    for _, line in frontier.unfenced(ticket_text.splitlines()):
        heading = _SWEEP_FILE.match(line)
        if heading:
            file = heading.group(1).strip("`")
            if file.lower() == "blocked by":
                file = None
            continue
        item = _SWEEP_ITEM.match(line)
        if item and file:
            bare = item.group(1).removeprefix(f"{file} ")
            items.append(qualified_id(file, bare))
    return items


def refuse_unaccounted_sweep_items(ticket_path, body_path, sidecar_path):
    """A sweep PR's worker accounts for every item of the sweep ticket: a
    `leftover` line in the sidecar under its `<file> <id>`, or a
    Decisions made line in the PR body stating it `fixed` (#1259).
    An item in neither is one the next sweep never sees, since
    `leftover` harvests the sidecar and nothing else. Refused by item name."""
    try:
        with open(ticket_path) as fh:
            items = sweep_items(fh.read())
        with open(body_path) as fh:
            records = body_records(fh.read().splitlines())
    except OSError as exc:
        raise RunFileError(f"could not read {exc.filename}: {exc.strerror}"
                           ) from exc
    if not items:
        raise RunFileError(
            f"{ticket_path} holds no `## <file>` / `- **<id>**` sweep items "
            "— it is not a sweep ticket, or its body was not fetched whole")
    repeated = sorted({i for i in items if items.count(i) > 1})
    if repeated:
        raise RunFileError(
            "sweep item(s) named twice under one `<file> <id>`: "
            + ", ".join(repeated) + " — one sidecar line would account for "
            "both and the harvest would carry one; give each bullet its own id")
    held = set()
    if os.path.exists(sidecar_path):
        held = {obj["id"] for _, obj in read_dispositions(sidecar_path)}
    missing = []
    for item in items:
        if item in held:
            continue
        found = records.get(item)
        if found:
            if found[-1][1] == "fixed":
                continue
        missing.append(item)
    if missing:
        raise RunFileError(
            "sweep item(s) in neither the sidecar nor the PR body as done: "
            + ", ".join(missing) + f" — write each undone one as a "
            f"`leftover` line in {sidecar_path} under its `<file> <id>`, "
            "and cite it the same way in Decisions made "
            "(implement/SKILL.md § Review)")


_SIDECAR_NAME = re.compile(r"dispositions-([0-9]+)\.jsonl")


def dispositions_path(reviews_dir, lowest):
    """The sidecar `_SIDECAR_NAME` parses, for clump `<lowest>`."""
    return os.path.join(reviews_dir, f"dispositions-{lowest}.jsonl")


def findings_path(reviews_dir, axis, lowest):
    """Round 1's `findings-<axis>-<lowest>.jsonl` (`implement/SKILL.md`
    § Review), which `implement/verification-check.sh` also reads."""
    return os.path.join(reviews_dir, f"findings-{axis}-{lowest}.jsonl")


def round_1_found_nothing(reviews_dir, lowest):
    """True only when all three axes' findings sidecars exist, are readable
    and hold no non-blank line. This is the one home of the test:
    `implement/verification-check.sh` runs it through `runfile.py
    round-1-empty` to pass a clump without a verification pass. A missing,
    unreadable or undecodable one is not an empty round."""
    for axis in ("standards", "spec", "correctness"):
        try:
            with open(findings_path(reviews_dir, axis, lowest)) as fh:
                if fh.read().strip():
                    return False
        except (OSError, UnicodeDecodeError):
            return False
    return True


def refuse_foreign_sidecar(sidecar_path, tickets):
    """A sidecar is `dispositions-<n>.jsonl` for the ticket `<n>` its PR was
    dispatched for (`implement/SKILL.md` § Review). One whose `<n>` is not a
    ticket this clump closes is another PR's file: its leftovers would be
    attributed here for good, and one holding no leftover would record zero
    and exit clean, the same as a PR that left nothing (#1084)."""
    name = os.path.basename(sidecar_path)
    match = _SIDECAR_NAME.fullmatch(name)
    if match is None:
        raise RunFileError(
            f"{name} is not named dispositions-<n>.jsonl, so it names no "
            "ticket to check against this clump")
    if int(match.group(1)) not in tickets:
        raise RunFileError(
            f"{name} belongs to ticket #{match.group(1)}, not one of this "
            f"clump's tickets ({', '.join(f'#{t}' for t in tickets)})")


def leftover(run_id, lowest, pr, sidecar_path, root=None, pr_body=None):
    """Copy every `leftover` line of a landed PR's dispositions sidecar into
    the run file. The sidecar's `dispositions-<n>` must name one of the
    clump's tickets. Idempotent per PR and finding id; a finding already
    recorded under a different PR, or a clump with no recorded landing, is
    refused — the reasons are in `references/run-file.md` § Leftovers.

    Returns `(run, added)`, `added` being the finding ids this call
    actually appended, for a caller to report a copy count.

    `pr_body` is a file holding the PR's body, checked against the sidecar
    by `refuse_disagreeing_pr_body`: a contradicted outcome, a leftover the
    body records and the sidecar lacks, a body citing none of the sidecar's
    ids, and a body with no Decisions made section are refused. `None` skips
    the check; the CLI never passes it without `--allow-stale`."""
    pr = pr_number(pr)
    found = read_leftover_lines(sidecar_path)
    if pr_body is not None:
        refuse_disagreeing_pr_body(sidecar_path, pr_body)
    with locked(run_id, root):
        run = load(run_id, root)
        entry = clump_entry(run, lowest)
        if entry["landed"] is None:
            raise RunFileError(
                f"clump #{lowest} has not landed — `land` comes first")
        refuse_foreign_sidecar(sidecar_path, entry["tickets"])
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


def pr_up(run_id, lowest, pr, root=None):
    """Record the PR a clump's worker reported "PR up" on, which the sweep
    reads (`burndown/SKILL.md` § Liveness). It lives here and not in the
    controller's context, because a resumed controller's sweep has only this
    file. A later "PR up" naming another PR replaces it: unlike a squash sha,
    a PR number is not final — a worker can close one and open another.
    `pr=None` clears it, when the controller hands findings back: the PR
    stays open through a fix round, so only the clear makes a worker that
    stops mid-fix read `stalled` again."""
    pr = None if pr is None else pr_number(pr)
    with locked(run_id, root):
        run = load(run_id, root)
        clump_entry(run, lowest)["pr_up"] = pr
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
    clump — and reopens a closed one, which now has a worker again. A new clump
    records job `none`: its worker has launched nothing yet (#1311). A ticket
    that already sits in another clump is refused: one ticket in two clumps is
    two workers in the same files."""
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
                 # A closed clump registered again is dispatched again.
                 "closed": None,
                 # A re-registration keeps a declared job (#1311).
                 "job": same["job"] if same else NEW_CLUMP_JOB,
                 # A new agent has sent no "PR up" of its own.
                 "pr_up": same["pr_up"] if same and same["agent"] == agent
                 else None}
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
        if entry["closed"] is not None:
            raise RunFileError(
                f"clump #{lowest} is closed without a landing "
                f"({entry['closed']})")
        entry["landed"] = sha
        save(run, root)
        return run


def close_reason(reason):
    """Why a clump closed with no landing: one non-blank line, the hygiene a
    leftover's fields keep, since `render_resume` prints it on one line."""
    return leftover_field(reason, "close reason")


def close(run_id, lowest, reason, root=None):
    """Record that a clump closed with no landing of its own — its ticket
    found already fixed on the default branch, or handed to a nested spec run
    whose landings live in that run's own file (#1310). Distinct from `land`:
    no squash sha exists, and `main`'s tip recorded as one is a landing the
    sweep then looks for a sidecar behind. A closed clump holds no slot, has
    no worker to re-announce to, and has no sidecar for `sweep.py counts`.
    A landed clump is refused; closing again with the same reason is a no-op,
    with another reason is refused."""
    reason = close_reason(reason)
    with locked(run_id, root):
        run = load(run_id, root)
        entry = clump_entry(run, lowest)
        if entry["landed"] is not None:
            raise RunFileError(
                f"clump #{lowest} already landed at {entry['landed']}")
        if entry["closed"] not in (None, reason):
            raise RunFileError(
                f"clump #{lowest} is already closed: {entry['closed']}")
        entry["closed"] = reason
        save(run, root)
        return run


def settled(entry):
    """A clump that has finished in this run, landed or closed: no worker
    to reach, no workspace holding files, no slot held."""
    return bool(entry.get("landed") or entry.get("closed"))


def reconcile(run, live_agents):
    """Split a run's clumps four ways against the agents that are alive:
    the live workers to re-announce to, the vanished ones a controller has to
    reconcile by hand, the landings, and the clumps closed with no landing. A
    landed or closed clump is in neither working bucket however its worker
    looks — its slot is free and its outcome is final.
    """
    live = set(live_agents)
    announce, vanished, landed, closed = [], [], [], []
    for entry in run["clumps"]:
        if entry["landed"]:
            landed.append(entry)
        elif entry["closed"]:
            closed.append(entry)
        elif entry["agent"] in live:
            announce.append(entry)
        else:
            vanished.append(entry)
    # A vanished clump counts against the budget with the live ones: its
    # worker may still be holding its tickets, so refilling its slot before
    # anyone has reconciled it puts a second worker in the same files. Only a
    # landing or a close frees a slot for certain.
    held = len(announce) + len(vanished)
    return {"run_id": run["run_id"], "slots": run["slots"],
            "controller": run["controller"],
            "free": max(0, run["slots"] - held), "held": held,
            "announce": announce, "vanished": vanished, "landed": landed,
            "closed": closed}


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
    clump, landings marked with their sha and closes with their reason."""
    lines = [f"run {run['run_id']}  slots {run['slots']}  "
             f"controller {run['controller'] or '-'}  "
             f"repo {run.get('repo') or 'none recorded'}"]
    for entry in run["clumps"]:
        state = (f"landed {entry['landed']}" if entry["landed"]
                 else f"closed: {entry['closed']}" if entry["closed"]
                 else "in flight")
        lines.append(f"clump #{entry['tickets'][0]}  {tickets_of(entry)}  "
                     f"{entry['agent']}  {entry['workspace']}  {state}  "
                     f"{render_job(entry.get('job'))}  "
                     f"{render_pr_up(entry.get('pr_up'))}")
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


def render_pr_up(pr):
    return f"PR #{pr} up" if pr is not None else "no PR up"


def tickets_of(entry):
    return ",".join(f"#{n}" for n in entry["tickets"])


def render_resume(state):
    """What resume owes the controller: the slot budget it recovered, the live
    workers to re-announce itself to, the vanished ones to reconcile by hand,
    the landings already banked, and the clumps closed with no landing."""
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
    for entry in state["closed"]:
        lines.append(f"closed       {tickets_of(entry)}  {entry['closed']}")
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
    new.add_argument("--repo", required=True,
                     help="the target repo's checkout; the absolute path of its "
                          "primary checkout is recorded")

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

    shut = subs.add_parser(
        "close", help="record a clump that closed with no landing of its own")
    shut.add_argument("run_id")
    shut.add_argument("--clump", type=int, required=True,
                      help="the clump's lowest ticket")
    shut.add_argument("--reason", required=True,
                      help="why, on one line: e.g. already fixed on main as "
                           "#1202, or a nested spec run under its own run file")

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
    fresh = lo.add_mutually_exclusive_group(required=True)
    fresh.add_argument("--pr-body", metavar="PATH",
                       help=f"the PR's body, as `{_FETCH_BODY}` prints "
                            "it. Refused as stale: a sidecar line its "
                            "Decisions made contradicts, a leftover the body "
                            "records that the sidecar lacks, a body that "
                            "cites none of the sidecar's ids, and a body "
                            "with no Decisions made section "
                            "(references/run-file.md § Leftovers)")
    fresh.add_argument("--allow-stale", action="store_true",
                       help="skip the PR-body check")

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

    up = subs.add_parser("pr-up",
                         help="record the PR a worker reported \"PR up\" on")
    up.add_argument("run_id")
    up.add_argument("--clump", type=int, required=True,
                    help="the clump's lowest ticket")
    which = up.add_mutually_exclusive_group(required=True)
    which.add_argument("--pr", type=int)
    which.add_argument("--clear", action="store_true",
                       help="the controller handed findings back; the next "
                            "\"PR up\" records it again")

    chk = subs.add_parser(
        "check",
        help="the PR-body comparison `leftover` runs at harvest, with no run "
             "file: the worker's pre-\"PR up\" gate (#1214)")
    chk.add_argument("--from", dest="from_path", required=True,
                     metavar="PATH", help="the dispositions sidecar")
    chk.add_argument("--pr-body", required=True, metavar="PATH",
                     help="the PR's body")

    swp = subs.add_parser(
        "sweep-check",
        help="a sweep PR's pre-\"PR up\" gate (#1259): every item of the "
             "sweep ticket is a sidecar line or done in the PR body")
    swp.add_argument("--ticket", required=True, metavar="PATH",
                     help="the sweep ticket's body")
    swp.add_argument("--pr-body", required=True, metavar="PATH",
                     help="the PR's body")
    swp.add_argument("--from", dest="from_path", required=True,
                     metavar="PATH",
                     help="the dispositions sidecar; may be absent or empty")

    rnd = subs.add_parser(
        "round-1-empty",
        help="exit 0 only when ticket <n>'s three findings sidecars all "
             "exist and are empty (#1336)")
    rnd.add_argument("--reviews-dir", required=True, metavar="DIR")
    rnd.add_argument("ticket", type=int)

    out = subs.add_parser("show", help="print the run file")
    out.add_argument("run_id")

    back = subs.add_parser("resume", help="reconcile against the live agents")
    back.add_argument("run_id")
    back.add_argument("--live", default="",
                      help="comma-separated herdr agent names that are alive")
    back.add_argument("--controller", help="the controller's current name")

    args = parser.parse_args(argv[1:])
    # One seam per caller: in-process callers pass `root`, the CLI resolves the
    # environment once here and passes it down.
    root = env_root()
    try:
        if args.command == "start":
            print(render(start(args.run_id, args.slots, args.controller, root,
                               args.repo)))
        elif args.command == "clump":
            print(render(clump(args.run_id, parse_tickets(args.tickets),
                               args.workspace, args.agent, root)))
        elif args.command == "land":
            print(render(land(args.run_id, args.clump, args.sha, root)))
        elif args.command == "close":
            print(render(close(args.run_id, args.clump, args.reason, root)))
        elif args.command == "leftover":
            run, added = leftover(args.run_id, args.clump, args.pr,
                                  args.from_path, root, args.pr_body)
            print(render(run))
            print(f"copied {len(added)} leftover(s) from {args.from_path}")
        elif args.command == "check":
            if not read_dispositions(args.from_path):
                raise RunFileError(f"{args.from_path} has no lines — nothing "
                                   "to compare the PR body against")
            read_leftover_lines(args.from_path)
            refuse_disagreeing_pr_body(args.from_path, args.pr_body)
            print(f"{args.from_path} and {args.pr_body} agree")
        elif args.command == "sweep-check":
            refuse_unaccounted_sweep_items(args.ticket, args.pr_body,
                                           args.from_path)
            print(f"every sweep item in {args.ticket} is accounted for")
        elif args.command == "round-1-empty":
            if not round_1_found_nothing(args.reviews_dir, args.ticket):
                raise RunFileError(
                    f"round 1 of #{args.ticket} is not provably empty under "
                    f"{args.reviews_dir}")
            print(f"round 1 of #{args.ticket} found nothing")
        elif args.command == "job":
            state = ("running" if args.cores is not None
                     else "none" if args.none else "done")
            print(render(job(args.run_id, args.clump, state,
                             args.cores or 0, root)))
        elif args.command == "pr-up":
            print(render(pr_up(args.run_id, args.clump, args.pr, root)))
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
