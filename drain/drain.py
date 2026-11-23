#!/usr/bin/env python3
"""`drain.py [--repo <path>] [--once] [--max <n>] [--bundle-max <k>]
[--anchor <n>]`: work the `ready-for-agent` queue unattended, serially, one PR
at a time.

The **anchor** is the oldest unblocked ready ticket (`implement-spec/frontier.py`)
or clear spec parent, whichever has the lower number, or, for the first bundle
drain picks, the ticket or spec `--anchor <n>` names (refused unless `<n>` is
open, ready, unblocked and without a kept workspace; a resumed bundle goes
first and the anchor waits for the next pick). Tickets numbered
below the anchor never join its bundle, because the worker's branch and herdr
agent are named for the lowest ticket of a bundle.

`drain` leaves a `drain anchor:` comment on it, has one headless one-turn
`claude -p` session choose the **bundle** (the other unblocked ready tickets
it would naturally fix in the same PR, at most `--bundle-max` in all; the
anchor alone, with a `drain chooser:` comment saying why, when the session
fails), records the choice in a `drain bundle: <tickets> (of <k> candidates)`
comment, singles included, and starts the bundle through `implement-dispatch`,
the one dispatch path: claim, worktree, an interactive worker in a herdr pane
named `<repo-short>-<anchor>` that shows in `herdr agent list` (#1415). A headless build cannot wait on its reviewers,
which is an exit in `-p` mode, so the worker is an ordinary interactive one
and `drain` waits for it: its PR appears and its pane goes idle, under a
three-hour wall clock. A worker that sits idle or blocked with no PR for half
an hour is a failed build (the ticket's own evidence of a healthy wait on a
reviewer is 22 minutes), unless it is idle beside a live `job-run` job of its
own, which restarts the half hour (#1715). `drain` does no directory or closure grouping.

A **spec parent** is a bundle of its own (#1477). The frontier's `spec` bucket
holds the parents `implement-dispatch --spec` accepts (`ready-for-agent`, not
claimed, not blocked), so only they anchor: a spec without the ready label, or
one a session already runs, leaves its slices unbuilt, as a slice never is built as
a lone ticket. `drain` starts it with `implement-dispatch --spec <n>` (that
command's own slot default) and no chooser, since the spec's slices are its
bundle. A spec with no unblocked slice on the frontier (none at all, or every one blocked, a
blocker in another repo included) never anchors: it is a `passed over:` line naming its blocked
slices and their blockers, since its run would open with nothing to build and end idle with no
PR (#1974). So does a spec with any open slice labelled `ready-for-human`, blocked or not and
with or without `ready-for-agent` (`--anchor` on it included): that slice's PR needs Chris's
merge and `drain` has no controller session to hand it to, so the run would idle and be handed
to Chris as a failed build. It is a `passed over: #<spec> slice #<n> is ready-for-human` line
(`slices #<n>, #<m> are ready-for-human` for several; #2006). Waiting on Chris's merge would hold
the serial queue on a person. When nothing else is startable, a `waiting:` line names each spec
whose slices are ready but which `drain` cannot start. The spec
run is the worker: pane `<repo-short>-spec-<n>`, workspace and branch
`spec-<n>`, and it drives its slices itself (`implement-spec/SKILL.md`). Its
stop is the integration PR up and the pane idle, and the wait differs in three
ways: the half-hour idle grace does not run while a slice worker is `working`, a run idle past it with
no PR is prompted once through herdr (a `resumed:` line) and gets the grace again, and idle
again is a failed build with no second nudge (#1710),
the wall clock is twelve hours (`SPEC_WALL_CLOCK_SECONDS`), and the PR must
close the spec and may close any number of its slices (a ticket whose parent is
the spec), with no `--bundle-max` cap, since the spec's size is its own. A
failed spec run is handed to Chris with the spec, its claimed slices and every
pane of theirs closed. A spec with one slice has no integration branch and no
`spec-<n>` PR: its run lands the slice itself, and `drain` reports the spec as
landed with no PR, its own PR check never having run.
`--max` stops the loop after that many tickets (a bundle counts all of its
tickets); `--once` stops after one bundle.

Then it checks (the PR is not draft, CLEAN once `implement/pr_settle.py` has
waited out UNKNOWN and running checks (#1526), closes the anchor within the
bundle cap, and the repo's per-change command passes on the PR merged into
current main), squash-merges, runs `merge-cleanup` (which closes the worker's
pane), and returns any ticket the worker claimed but the PR did not close to
the queue. The per-change command is what `implement/selector_check.py
command` reads from current main's `AGENTS.md` § End-to-end seam, never the
merged tree's, so a PR that edits that section does not choose its own gate:
its `Narrowed` command, else its `Seam` (#1597). It runs on every merge
but one the worker's green run already covered: the PR body's `Seam run at:
<sha>` line names the head, current main is in that head, and the seam
section is unchanged and declares a command. That merge skips the run with a
`seam rerun skipped:` comment on the PR, the lane's merge step's #1616 skip
(#1949). A main that moved by the fetch before the merge is checked again. A
run that happens has `TESTS_JOBS` at most `SEAM_JOBS`, and a repo that
declares a `Narrowed` line gets that run's listing as one `selector:` comment
on the PR, posted before the command, as the lane's merge step does (#1593).
A section that declares no command merges nothing. No full seam runs in
drain: the nightly backstop (`backstop/`) is the only full run.
After each merge, before the next bundle starts, a repo that declares a
`- **Deploy**: `<command>`` line in that section (#1726; `{before}` is
current main's sha just before the merge) has the primary checkout
fast-forwarded and the command run there, read from main after the merge.
`deploy <tickets>: `<command>` -> exit <n>` and the last 15 output lines
(`deploy output: ...`) go to the progress file. A non-zero exit, a timeout, a
checkout that cannot fast-forward or a declaration that cannot be read ends the
drain with `stopped: deploy ...` naming the merged PR; merges already made stay
merged. An output line starting with the repo's `- **Owed marker**: `<text>``
(backticked, any number) or the default `owed:` is carried into the summary
as `    deploy: <line>` under its merged ticket. A repo with no `Deploy` line runs
nothing and prints nothing more.
A bundle that fails is given one more try by prompting the same worker with
the reason (waiting for it to start working before it looks again); a second
failure closes the worker's pane, labels the anchor and every claimed ticket
`ready-for-human` with a one-line comment, keeps the worktree, and the loop
moves on. A ticket whose workspace is kept is never picked again until that
workspace is removed. Two bundles in a row handed to Chris stop the loop
instead: that is the environment failing (auth, quota, herdr), not the tickets.
The worker's brief names the controller `drain`, which no session bears;
`implement/SKILL.md` § Control says what a worker does then (no messages, no
job notices, "PR up" is its stop), and `drain` waits for that stop.

Progress is one flushed line per event on stdout, which `job-run` copies into
the run's progress file as it happens: `bundle started: #<n> <title>; ...
pane <repo-short>-<anchor>` when a bundle's worker exists, `bundle ended: #<n>
... merged <pr> <sha>` or `... handed to Chris: <reason>` or `... stopped:
<reason>` when it ends, then the summary. Before the first bundle, one
`unresolved at start: #<n> <title>  <why>` per ready ticket with no
readable `Blocked by`, worded as its `passed over:` line; the run goes on
without it. A ticket the worker closed with no
PR is recorded as what closed it, from its `closed` event: `(landed on main,
no PR)` with that commit's sha, or with the sha of the main commit whose
message says `Closes #<n>` when a hand closed it after the trailer did not
fire; `moot (closed, no PR)` with no sha when neither exists; or an unverified
close with the reason, never as main's tip. This drain's last lines are one
`passed over: #<n> <why>` per ready ticket it did not build (human-held,
claimed, blocked, a kept workspace, not started), read fresh when a limit ends
the drain, and one
`ended: <cause>`: `queue empty`, `no startable ticket` (every queued ticket has
a kept workspace), `--once reached`, `--max <n> reached`, or `stopped` beside
its `stopped:` line. `ended:` is no `stopped:` line and leaves the exit code
alone. A queue read that comes back empty is read once more after 45 s, since
GitHub's label listing lags a relabel. `drain/SKILL.md`
reads these lines for its same-turn print, its status and its completion
report.

State lives in GitHub, git and herdr, nowhere else. An open, in-progress
ticket carrying drain's own `drain anchor:` comment is resumed (a worker
started by `implement-dispatch` outside drain has none, so it is never taken)
and its worker or open PR is waited on and checked rather than rebuilt. Only
repos whose origin owner is the `gh` login or on the owned-owners list
(`common/owners.py`, #2005).
"""
import argparse
import collections
import contextlib
import ctypes
import fcntl
import os
import re
import resource
import shlex
import signal
import subprocess
import sys
import time

for _dir in ("implement-spec", "implement", "common"):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", _dir))

import frontier  # noqa: E402
import pr_settle  # noqa: E402
import scratch_run  # noqa: E402
import selector_check  # noqa: E402
import shellcmd  # noqa: E402
import owners  # noqa: E402  (#2005)
import tracker  # noqa: E402
from scratch_run import one_line  # noqa: E402
from selector_check import UNDECLARED  # noqa: E402

READY, HUMAN, CLAIMED = "ready-for-agent", "ready-for-human", frontier.CLAIMED_LABEL
# What opens the reason `barren_specs` / `human_held_specs` give a spec read_queue passed over.
HELD_SPEC_REASONS = ("spec with no dispatchable slice", "slice #", "slices #")
ANCHOR_NOTE, BUNDLE_NOTE, HANDED_NOTE = "drain anchor:", "drain bundle:", "drain could not land"
CHOOSER_NOTE = "drain chooser:"  # never `BUNDLE_NOTE`: its digits would read as tickets
# The count a `drain bundle:` note ends with, which is not a ticket.
# `count_note` writes it and `CANDIDATES` strips it: change the two together.
CANDIDATES = re.compile(r"\(of \d+ candidates\)")


def count_note(k):
    return f"(of {k} candidates)"
BUNDLE_MAX = 8
MAX_CONSECUTIVE_FAILURES = 2


def consecutive_failure_stop(ctx, failures):
    """The stop reason once `failures` bundles in a row went to Chris, else `None`."""
    if failures < MAX_CONSECUTIVE_FAILURES:
        return None
    return (f"{failures} bundles in a row went to Chris; the environment is the likelier "
            f"cause (auth, quota, herdr, implement-dispatch). Check `herdr agent list` and the "
            f"logs in {ctx.log_dir}.")


# The caps, stated here and nowhere else: the equivalent of `ulimit -v 32G`
# (address space, not resident memory, hence generous) on the one-shot bundle
# chooser, and a three-hour wall clock for a worker to finish and for the seam.
# TERM and ctrl-C kill a subprocess's whole group; SIGKILL of drain kills only
# the chooser itself (PR_SET_PDEATHSIG). A worker is an interactive herdr
# session of its own: drain waits for it and never kills it.
MEMORY_CAP_BYTES = 32 << 30
WALL_CLOCK_SECONDS = 3 * 60 * 60
# A spec run builds every slice and reviews the whole, so its clock is longer.
SPEC_WALL_CLOCK_SECONDS = float(os.environ.get("DRAIN_SPEC_WALL_CLOCK_SECONDS", 12 * 60 * 60))
# Never a permission-skipping flag: the bundle chooser runs in the mode the
# harness already trusts for unattended work. (A worker's own mode is
# `implement-dispatch`'s.)
PERMISSION_MODE = "auto"
# How the wait on a worker is paced. Test hooks, not options: seconds between
# looks at the worker, and how long its pane may sit idle with no PR before the
# build counts as failed (an idle worker with a PR is done; one with none is
# usually waiting on a reviewer, which is why it is not failed at the first idle
# look; the ticket's evidence is a 22-minute wait, so the grace is longer).
POLL_SECONDS = float(os.environ.get("DRAIN_POLL_SECONDS", 15))
IDLE_GRACE_SECONDS = float(os.environ.get("DRAIN_IDLE_GRACE_SECONDS", 30 * 60))
CHOOSER_SECONDS = float(os.environ.get("DRAIN_CHOOSER_SECONDS", 15 * 60))
# Characters of each candidate's body and comments the chooser's prompt carries;
# the chooser may still open a ticket in full.
EXCERPT_CHARS = 400
# How long an empty queue read waits before it is read once more: GitHub's label
# listing lags a relabel by about 30 s, so a ticket readied just before the drain
# starts is not listed yet.
FRONTIER_RETRY_SECONDS = float(os.environ.get("DRAIN_FRONTIER_RETRY_SECONDS", 45))
# How long one `herdr agent get` may take: a herdr that hangs would otherwise stall
# an unattended drain with no message. Test hook, not an option.
HERDR_SECONDS = float(os.environ.get("DRAIN_HERDR_SECONDS", 30))
# Where `job-run` keeps one directory per run; a test points it elsewhere.
JOBS_DIR = os.environ.get("DRAIN_JOBS_DIR", os.path.expanduser("~/.cache/agent-jobs"))
IDLE = ("idle", "done")
# `blocked` is a permission or question dialog nobody here can answer.
STALLED = ("blocked",)
# Consecutive failed looks at a worker (a `gh` or `herdr` call) before the wait
# gives up, so one transient error is not a failed build or a stopped drain.
LOOK_ERRORS = 5
# The controller named in every brief. No session bears it: the worker's "PR up"
# send to it finds nobody and the worker stops idle, which is what drain waits
# for. A question the worker would put to a controller goes unanswered the same
# way and shows as an idle worker with no PR, a failed build.
CONTROLLER = "drain"

# `tracker` is the repo's issue tracker (`tracker.GhTracker`; a test gives `MemoryTracker`).
Ctx = collections.namedtuple("Ctx", "root repo default log_dir bundle_max want tracker")
# What an anchor is: a ticket built by a worker, or a spec parent built by a spec run.
TICKET, SPEC = "ticket", "spec"


class DrainError(Exception):
    """A step failed; the message is the reason handed to Chris."""


class DrainStop(Exception):
    """The loop cannot go on, and no ticket is at fault."""


class WorkerGone(DrainError):
    """The worker's herdr agent is gone and its build has no PR."""


class IdleAfterResume(DrainError):
    """A spec run was still idle or blocked with no PR a grace after drain's one resume
    prompt: no second try."""


def refs(tickets):
    """`#1 #2`: tickets as they are written in a line of output."""
    return " ".join(f"#{n}" for n in tickets)


def git(args, cwd, ok=(0,)):
    """`git <args>` in `cwd`: its stripped stdout; an exit outside `ok` is a `DrainError`."""
    try:
        return shellcmd.git(args, cwd=cwd, ok=ok).stdout.strip()
    except shellcmd.CmdError as exc:
        raise DrainError(str(exc)) from None


def labels_of(issue):
    """The label names of a REST or `gh issue view` issue, the one parser (`tracker.labels`)."""
    try:
        return tracker.labels(issue)
    except tracker.TrackerError as exc:
        raise DrainError(str(exc)) from exc


def asked(call, *args):
    """`call(*args)`, a call on `ctx.tracker`; a tracker that cannot answer is a `DrainError`."""
    try:
        return call(*args)
    except tracker.TrackerError as exc:
        raise DrainError(str(exc)) from None


def issue_view(ctx, n, fields):
    """`gh issue view`'s object for ticket `n` with the comma-separated `fields`."""
    return asked(ctx.tracker.issue_view, n, fields)


def relabel(ctx, n, add):
    """Move ticket `n` from in-progress to `add` and drop drain's assignment."""
    asked(ctx.tracker.relabel, n, [add], [CLAIMED], "@me")


def run_group(cmd, cwd, timeout, preexec=None):
    """`scratch_run.run_group`'s `(exit code, output)`; its wall clock is a `DrainError`."""
    try:
        return scratch_run.run_group(cmd, cwd, timeout, preexec=preexec)
    except scratch_run.ScratchError as exc:
        raise DrainError(str(exc)) from None


def _cap_session():
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_CAP_BYTES, MEMORY_CAP_BYTES))
    ctypes.CDLL(None).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG: die with drain


def origin_slug(root):
    """`owner/name` of `root`'s origin; a remote that is not github.com is a `DrainError`."""
    try:
        slug = shellcmd.origin_slug(root)
    except shellcmd.CmdError as exc:
        raise DrainError(str(exc)) from None
    if slug is None:
        raise DrainError(f"origin of {root} is not a github.com repo")
    return slug


def read_frontier(ctx, retry=True):
    """`read_queue`, read once more after `FRONTIER_RETRY_SECONDS` when the
    queue came back empty (GitHub's label listing lags a relabel). A queue
    that is still empty is the answer: one retry, never a loop."""
    got = read_queue(ctx)
    if retry and not got[0]:
        time.sleep(FRONTIER_RETRY_SECONDS)
        got = read_queue(ctx)
    return got


def read_queue(ctx):
    """`(queue, waiting, stranded, passed)`. `queue` is
    `[(number, title, kind)]`: the unblocked
    ready tickets and the clear spec parents, oldest first; the anchor is the
    first. A slice is neither: it is built inside its spec's run. `waiting` is
    the numbers of specs that have a ready slice and are not in the queue
    (not ready-for-agent, claimed, blocked), which drain cannot start.
    `stranded` is `[(number, why)]`: slices whose spec is closed or in another
    repo, which no spec run can build (#1485). `passed` is `[(number, why)]`:
    the other open ready tickets, which a drain passes over (human-held,
    claimed, blocked, unresolved, or carrying a non-dispatchable label)."""
    listing = asked(ctx.tracker.issues, READY)
    issues = {i["number"]: i for i in listing}
    try:
        buckets = frontier.frontier(ctx.repo, READY, tracker=Listed(ctx.tracker, listing))
    except tracker.TrackerError as exc:
        raise DrainError(f"frontier: {exc}") from exc
    queue = [(t["number"], t["title"], kind) for kind, bucket in ((TICKET, "unblocked"), (SPEC, "spec"))
             for t in buckets[bucket]]
    queue = sorted((t for t in queue if HUMAN not in labels_of(issues[t[0]])), key=lambda t: t[0])
    specs = {n for n, _, k in queue if k == SPEC}
    barren = human_held_specs(ctx, specs)
    barren.update(barren_specs(ctx, issues, buckets, specs - set(barren)))
    queue = [t for t in queue if t[0] not in barren]
    waiting = {t["spec"] for t in buckets["slice"]} - {t[0] for t in queue} - set(barren)
    stranded = [(t["number"], t["why"]) for t in buckets["stranded"]]
    return queue, sorted(waiting), stranded, sorted(passed_over(issues, buckets) + list(barren.items()))


def barren_specs(ctx, issues, buckets, specs):
    """`{spec: why}` for each of `specs` (clear spec parents) with no unblocked slice on the
    frontier, so a spec run would open with nothing to build and end idle with no PR (#1974).
    The decision rests on the `slice` bucket alone. The `why` names the spec's blocked slices
    and their blockers when their parents can be read; a read that fails only shortens it, and
    never keeps a barren spec in the queue."""
    ready = {t["spec"] for t in buckets["slice"]}
    barren = [n for n in sorted(specs) if n not in ready]
    if not barren:
        return {}
    blocked = {t["number"]: (name, t) for name in ("blocked", "unresolved") for t in buckets[name]}
    held, unread = {n: [] for n in barren}, []
    for n, (name, entry) in blocked.items():
        try:
            parent = frontier.fetch_parent(ctx.tracker, issues[n])
        except tracker.TrackerError:
            unread.append(n)
            continue
        if parent and parent["number"] in held:
            held[parent["number"]].append((n, name, entry))
    why = {}
    for spec in barren:
        named = "; ".join(f"#{n} " + held_reason(name, e, native_blockers(ctx, issues[n]) if name == "blocked" else ())
                          for n, name, e in held[spec])
        if named:
            why[spec] = f"spec with no dispatchable slice: {named}"
        elif unread:
            why[spec] = ("spec with no dispatchable slice found (the parent of " + refs(unread)
                         + " could not be read, so its blocked slices are not named)")
        else:
            why[spec] = "spec with no dispatchable slice (it has no ready slice)"
    return why


def human_held_specs(ctx, specs):
    """`{spec: why}` for each of `specs` (clear spec parents) with an open `ready-for-human`
    slice. Its slice PR needs Chris's merge, and `drain` has no controller session to hand that
    to, so the spec run would idle past its one resume and be handed to Chris as a failed build
    (#2006). Read from the `ready-for-human` listing, not the frontier: a human slice usually
    lacks `ready-for-agent`, and a blocked one waits in a frontier bucket the run unblocks
    mid-run. A read that fails stops the drain, since a spec not known to be clear of a human
    slice must not anchor."""
    if not specs:
        return {}
    held = collections.defaultdict(list)
    try:
        for issue in ctx.tracker.issues(HUMAN):
            parent = None if issue.get("pull_request") else frontier.fetch_parent(ctx.tracker, issue)
            if parent and parent["number"] in specs:
                held[parent["number"]].append(issue["number"])
    except tracker.TrackerError as exc:
        raise DrainError(f"{HUMAN} slices: {exc}") from exc
    return {spec: (f"slice #{ns[0]} is {HUMAN}" if len(ns) == 1 else
                   f"slices {', '.join(f'#{n}' for n in ns)} are {HUMAN}")
            for spec, ns in ((spec, sorted(ns)) for spec, ns in held.items())}


def native_blockers(ctx, issue):
    """The open native blockers of `issue` that sit in this repo, `()` when the tracker cannot
    list them (a blocker in another repo raises): the reason then stays unnamed, not wrong."""
    try:
        return ctx.tracker.native_blockers(issue)
    except tracker.TrackerError:
        return ()


class Listed:
    """`inner` with `issues(label)` answering the one listing drain already read, so the frontier
    classifies the very issues `passed_over` names rather than a second read that could differ.
    Every other call goes to `inner`, which is never changed."""

    def __init__(self, inner, listing):
        self._inner, self._listing = inner, listing

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def issues(self, label):
        return list(self._listing)


UNRESOLVED = "blocker state unresolved:"  # opens `held_reason`'s wording for an `unresolved` entry


def held_reason(bucket, entry, native=()):
    """Why a `blocked` or `unresolved` frontier entry is held, the one wording `passed_over`
    and `barren_specs` share. `native` is the open native blockers read for an entry whose
    own list is empty (a native dependency)."""
    if bucket == "unresolved":
        return f"{UNRESOLVED} {entry['why']}"
    named = entry["blockers"] or list(native)
    if named:
        return "blocked by " + ", ".join(f"#{n}" for n in named)
    return f"blocked: {entry['why']}"


def passed_over(issues, buckets):
    """`[(number, why)]` for each open ready ticket that is not in the queue and
    not a slice (its spec run builds it, or `waiting:` / `stranded:` name it)."""
    why = {}
    for name in ("blocked", "unresolved"):
        for t in buckets[name]:
            why[t["number"]] = held_reason(name, t)
    placed = {t["number"] for bucket in buckets.values() for t in bucket}
    for n, issue in issues.items():
        labels = labels_of(issue)
        if issue.get("pull_request") or (n in placed and n not in why and HUMAN not in labels):
            continue
        if HUMAN in labels:
            why[n] = HUMAN
        elif n not in why:
            held = labels & frontier.NON_DISPATCHABLE_LABELS
            if CLAIMED in labels:
                why[n] = f"claimed ({CLAIMED})"
            elif issue.get("assignees"):
                why[n] = "claimed (assigned)"
            elif held:
                why[n] = f"label {', '.join(sorted(held))}"
            else:
                why[n] = "left off the frontier, reason not read"
    return sorted(why.items())


def pick(ctx):
    return read_frontier(ctx)[0]


def branch_of(n, kind):
    """The branch and workspace name `implement-dispatch` gives an anchor."""
    return f"{'spec' if kind == SPEC else 'implement'}-{n}"


def workspace_of(ctx, branch):
    return os.path.join(ctx.root, ".claude", "worktrees", branch)


def workspace_path(ctx, n, kind):
    return workspace_of(ctx, branch_of(n, kind))


def anchors(ctx, queue):
    """The queue's tickets that may anchor a bundle: those with no kept
    workspace. A ticket drain handed to Chris keeps its workspace, and
    `implement-dispatch` refuses to start where one exists, so a re-readied one
    would stop every later drain at it."""
    return [t for t in queue if not os.path.isdir(workspace_path(ctx, t[0], t[2]))]


def put_first(queue, want):
    """`queue` with ticket `want` first; refused when it is not in it. The
    queue is the unblocked ready tickets, so `want` is open, ready and unblocked
    exactly when it is there."""
    chosen = [t for t in queue if t[0] == want]
    if not chosen:
        raise DrainError(f"--anchor #{want} is not an open, ready, unblocked ticket without a kept workspace")
    return chosen + [t for t in queue if t[0] != want]


@contextlib.contextmanager
def claim_lock(ctx):
    """The lock `implement-dispatch` holds around its own claims, so a spec
    run dispatching at the same moment cannot claim the same ticket."""
    path = os.path.expanduser("~/.implement-dispatch-claim-" + ctx.repo.replace("/", "__") + ".lock")
    with open(path, "a") as lock:
        for _ in range(30):
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                time.sleep(1)
        else:
            raise DrainStop(f"could not get {path} in 30s")
        yield


_ANCHOR_NOTE = re.compile(re.escape(ANCHOR_NOTE) + r" (implement|spec)-(\d+)")


def anchor_kind(note, n):
    """`SPEC` or `TICKET` for the issue `n`'s own anchor note, `None` for a note
    that is not exactly what `note_anchor` writes: an unreadable note is never
    resumed as a ticket by default."""
    m = _ANCHOR_NOTE.fullmatch(note.strip())
    return {"implement": TICKET, "spec": SPEC}[m.group(1)] if m and int(m.group(2)) == n else None


def note_anchor(ctx, anchor, kind):
    """True when the anchor is still ready and drain left its `drain anchor:`
    note, False when another claim took it since the pick (read again under the
    lock, as `implement-dispatch` does). The claim itself is `implement-dispatch`'s
    and comes after: the note first, so a kill between the two leaves a ready
    ticket with a stray note, which the next pick simply notes again, where the
    other order leaves an in-progress ticket no rerun resumes."""
    with claim_lock(ctx):
        view = issue_view(ctx, anchor, "state,labels")
        if view["state"].lower() != "open" or READY not in labels_of(view) or CLAIMED in labels_of(view):
            return False
        asked(ctx.tracker.comment, anchor, f"{ANCHOR_NOTE} {branch_of(anchor, kind)}")
    return True


def claimed_issues(ctx):
    """The open in-progress tickets, lowest first, with pull requests and human-held tickets
    dropped: the one claimed-queue read `resumable` and `claimed_slices` share."""
    claimed = asked(ctx.tracker.claimed)
    return sorted((i for i in claimed if not i.get("pull_request") and HUMAN not in labels_of(i)),
                  key=lambda i: i["number"])


def resumable(ctx, ended):
    """`(number, kind)` of the lowest open in-progress ticket or spec whose
    latest drain comment is its anchor note, or `None`. A worker
    `implement-dispatch` started has none, and a ticket drain handed to Chris
    ends in `HANDED_NOTE`, so neither is taken.
    The open list can still carry a ticket just closed, so each candidate's
    state and labels are read again, and an anchor this drain already took up
    (`ended`) is never taken twice."""
    for issue in claimed_issues(ctx):
        if issue["number"] in ended:
            continue
        view = issue_view(ctx, issue["number"], "state,labels,comments")
        if view["state"].lower() != "open" or CLAIMED not in labels_of(view):
            continue
        marks = [c["body"] for c in view["comments"] if c["body"].startswith((ANCHOR_NOTE, HANDED_NOTE))]
        kind = anchor_kind(marks[-1], issue["number"]) if marks and marks[-1].startswith(ANCHOR_NOTE) else None
        if kind:
            return issue["number"], kind
    return None


def noted(ctx, anchor):
    """The numbers in `drain bundle:` comments posted after the anchor's latest
    claim: what the agent says it took. Digits are read with `findall`, so a
    note that wraps lines or ends in punctuation still parses; the
    `(of <k> candidates)` count is cut first, since it is not a ticket."""
    comments = issue_view(ctx, anchor, "comments")["comments"]
    start = max((i for i, c in enumerate(comments) if c["body"].startswith(ANCHOR_NOTE)), default=-1)
    return {int(x) for c in comments[start + 1:] if c["body"].strip().startswith(BUNDLE_NOTE)
            for x in re.findall(r"\d+", CANDIDATES.sub("", c["body"]))} - {anchor}


_PARENTS = {}  # (repo, number) -> parent number or None; a ticket's parent does not change mid-drain


def parent_number(ctx, issue):
    """The number of the parent `issue` (a dict with `number` and `body`) names
    by the sub-issue link or a `Part of` line, or `None`. Read once per ticket:
    the idle wait asks every poll."""
    key = (ctx.repo, issue["number"])
    if key not in _PARENTS:
        try:
            parent = frontier.fetch_parent(ctx.tracker, issue)
        except tracker.TrackerError as exc:
            raise DrainError(f"parent of #{issue['number']}: {exc}") from exc
        _PARENTS[key] = parent and parent["number"]
    return _PARENTS[key]


def is_slice_of(ctx, n, spec):
    """Whether ticket `n` (read live) has `spec` as its parent."""
    body = issue_view(ctx, n, "body")["body"]
    return parent_number(ctx, {"number": n, "body": body}) == spec


def claimed_slices(ctx, spec):
    """The in-progress tickets whose parent is `spec`: the slices its run holds.
    Read live, since the spec run claims them, not drain."""
    held = []
    for i in claimed_issues(ctx):
        if i["number"] == spec:
            continue
        try:
            if parent_number(ctx, i) == spec:
                held.append(i["number"])
        except DrainError:  # an unrelated ticket whose parent cannot be read is not this spec's, and not a reason to fail it
            continue
    return sorted(held)


def bundle_of(ctx, anchor, branch, kind):
    """The anchor plus the tickets it is still holding: those the agent named
    and those an open PR closes, each read live, so a closed, human-held or
    unclaimed one is not the bundle's. A spec's are the slices its run holds."""
    if kind == SPEC:
        return [anchor] + claimed_slices(ctx, anchor)
    hint = noted(ctx, anchor)
    if open_pr(ctx, branch):
        view = asked(ctx.tracker.pr_view, branch, "closingIssuesReferences")
        hint |= {r["number"] for r in view["closingIssuesReferences"]} - {anchor}
    held = []
    for n in sorted(hint):
        view = issue_view(ctx, n, "state,labels")
        if view["state"].lower() == "open" and CLAIMED in labels_of(view) and HUMAN not in labels_of(view):
            held.append(n)
    return [anchor] + held


def agent_name(ctx, lead, kind):
    """The herdr agent `implement-dispatch` names its worker: the checkout's
    directory name cut to fit 32 characters with `-<lead>` (`-spec-<lead>` for a
    spec run), as that command does (`implement_dispatch.rs`)."""
    suffix = f"-spec-{lead}" if kind == SPEC else f"-{lead}"
    return os.path.basename(ctx.root)[:32 - len(suffix)] + suffix


def agent_info(name):
    """The worker's herdr record (`agent_status`, `pane_id`, ...), or `None` when
    herdr has no such agent. Any other herdr failure is a `DrainStop`: a herdr
    that cannot be asked is not a worker that is gone."""
    try:
        return shellcmd.herdr_agent(name, timeout=HERDR_SECONDS)
    except shellcmd.CmdError as exc:
        raise DrainStop(str(exc)) from None


def agent_status(name):
    info = agent_info(name)
    return info and info["agent_status"]


def stop_worker(name):
    """Close the worker's pane, so a bundle handed to Chris does not keep working
    beside the next one. The workspace stays for inspection; the session's
    transcript stays with claude. Best effort: a worker already gone is fine."""
    with contextlib.suppress(DrainStop, DrainError, KeyError, OSError, shellcmd.CmdError):
        info = agent_info(name)
        if info:
            shellcmd.herdr(["pane", "close", info["pane_id"]], timeout=HERDR_SECONDS)


def excerpt(ctx, n):
    """A candidate's body and comments, read live and cut to `EXCERPT_CHARS`, so
    the chooser judges from text and the log shows what it judged from. A ticket
    that cannot be read says so: a blank excerpt would read as an empty ticket.
    A ticket unblocked by GitHub's native dependencies alone may have no body and
    no comments, and says so rather than rendering blank."""
    try:
        view = issue_view(ctx, n, "body,comments")
    except DrainError as exc:
        return f"(body not read: {one_line(exc, 80)})"
    text = " ".join([view["body"] or "", *(c["body"] or "" for c in view["comments"])])
    return one_line(text, EXCERPT_CHARS) or "(empty body, no comments)"


def chooser_prompt(anchor, others, bundle_max):
    """`others` is `(number, title, excerpt)` per candidate."""
    listing = "\n".join(f"- #{n} {title}: {text}" for n, title, text in others) or "- (none)"
    return (f"Bundle choice for an unattended drain. #{anchor} is the anchor ticket to build next. Other unblocked "
            f"ready tickets, each with the start of its body and comments:\n{listing}\n"
            f"Open any that look related to #{anchor} in full (`gh issue view <n>`, body and comments) and pick those "
            f"you would naturally fix in the same PR, at most {bundle_max - 1} of them. Change nothing. "
            f"Your last line is exactly `{BUNDLE_NOTE} <numbers, the anchor first>`, with no other numbers; "
            f"`{BUNDLE_NOTE} {anchor}` when none belong.")


def choose_bundle(ctx, anchor, others, log):
    """`([anchor, ...], why)`: the tickets one headless session picks from the
    other unblocked ready ones, read from its last `drain bundle:` line, and a
    reason when it did not answer. It is one turn with no reviewer to wait for,
    so `-p` is safe here. A chooser that fails, times out or answers with nothing
    usable gives the anchor alone and the reason: bundling is an optimization,
    never a reason not to build, and the reason is left on the ticket."""
    if not others:
        return [anchor], None
    prompt = chooser_prompt(anchor, [(n, t, excerpt(ctx, n)) for n, t in others], ctx.bundle_max)
    with open(log, "w") as out:  # the prompt first, so a chooser that fails still leaves what it was given
        out.write(prompt + "\n\n--- chooser output ---\n")
    try:
        code, text = run_group(["claude", "-p", prompt, "--permission-mode", PERMISSION_MODE], ctx.root, CHOOSER_SECONDS,
                               preexec=_cap_session)
    except DrainError as exc:
        return [anchor], one_line(exc, 120)
    with open(log, "a") as out:
        out.write(text)
    lines = [x for x in text.splitlines() if x.strip().startswith(BUNDLE_NOTE)]
    if code or not lines:
        return [anchor], f"the chooser exited {code} and gave no `{BUNDLE_NOTE}` line (log {log})"
    allowed = {n for n, _ in others}
    picked = []
    for n in (int(x) for x in re.findall(r"\d+", CANDIDATES.sub("", lines[-1]))):
        if n in allowed and n not in picked:
            picked.append(n)
    return [anchor] + picked[:ctx.bundle_max - 1], None


def dispatch(ctx, bundle, kind):
    """Start the bundle's worker through `implement-dispatch`, the one dispatch
    path: claim, worktree, herdr pane, brief. A refusal claims and creates
    nothing, so it is the environment's (herdr down, onboarding) and stops the
    drain rather than looping over one ticket. A failure after the claim (herdr
    failing once the workspace exists) leaves the claim and the workspace in
    place: that is this bundle's failed build, not the environment's."""
    # Several numbers are one clump only when the caller says so (#1701).
    if kind == SPEC:
        which = ["--spec", str(bundle[0])]
    else:  # a clump is several numbers and says so
        which = (["--clump"] if len(bundle) > 1 else []) + [str(n) for n in bundle]
    out = subprocess.run(["implement-dispatch", "--repo", ctx.root, "--controller", CONTROLLER, *which],
                         capture_output=True, text=True)
    if out.returncode:
        reason = "implement-dispatch failed: " + one_line(out.stderr or out.stdout, 250)
        view = issue_view(ctx, bundle[0], "labels")
        if CLAIMED in labels_of(view):
            raise DrainError(reason)
        raise DrainStop(reason.replace("failed", "refused", 1))


def slices_working(ctx, spec):
    """Whether any slice worker of `spec` is `working`: the spec run's pane sits
    idle while it waits on them, which is no failed build."""
    for n in claimed_slices(ctx, spec):
        status = agent_status(agent_name(ctx, n, TICKET))
        if status is not None and status not in IDLE and status not in STALLED:
            return True
    return False


def live_job(workspace):
    """The name of a `job-run` job still alive whose wrapper runs in `workspace` (or below
    it), else `None`. A worker that started one and ended its turn to wait for it sits idle
    with no PR, which is no failed build (#1715). `job-run` records no directory of its own,
    so the wrapper's pid is asked for its cwd. A run with an `exit` record, no readable pid, a
    dead pid, a pid that is no `job-run` process (a run killed with no `exit` record keeps its
    directory for days, and its pid may be reused) or a cwd we may not read is not live."""
    root = os.path.realpath(workspace)
    try:
        names = sorted(os.listdir(JOBS_DIR))
    except OSError:
        return None
    for name in names:
        run = os.path.join(JOBS_DIR, name)
        if os.path.exists(os.path.join(run, "exit")):
            continue
        try:
            with open(os.path.join(run, "pid")) as f:
                pid = int(f.read().strip())
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                if b"job-run" not in f.read():
                    continue
            cwd = os.path.realpath(os.readlink(f"/proc/{pid}/cwd"))
        except (OSError, ValueError):
            continue
        if cwd == root or cwd.startswith(root + os.sep):
            return name
    return None


def wait_for_worker(ctx, branch, agent, bundle, spec=None, resumed=None):
    """`"pr"` once the branch has an open PR and its worker has gone idle (or is
    gone), `"closed"` when it went idle with every ticket closed and no PR
    (the light tier lands on main itself, or a ticket was closed as moot). A
    worker idle or blocked with no PR past the grace, a vanished one with
    neither, and the wall clock are failed builds. A look that errors (`gh`,
    herdr) is tried again; `LOOK_ERRORS` in a row end the wait. `spec` is the spec number when the worker is a spec run:
    its wall clock is `SPEC_WALL_CLOCK_SECONDS`, and a slice worker at work
    restarts its idle grace, as does a live `job-run` job in the workspace of an
    idle worker (`live_job`): the wall clock still ends the wait. A spec run idle past
    the grace with no PR is prompted once (`resume`) and its grace restarts; idle again
    past it, or blocked, is an `IdleAfterResume` (#1710). `resumed` is the set of agents already
    resumed, which a bundle's waits share so the run is resumed once, not once per wait.
    A ticket's worker is never resumed."""
    limit = SPEC_WALL_CLOCK_SECONDS if spec else WALL_CLOCK_SECONDS
    deadline, stalled_since, errors = time.monotonic() + limit, None, 0
    resumed = set() if resumed is None else resumed  # the agents resumed so far, shared by a bundle's waits
    while True:
        try:
            status = agent_status(agent)
            outcome, busy = None, False
            if status is None or status in IDLE:
                if open_pr(ctx, branch):
                    outcome = "pr"
                elif all(issue_view(ctx, n, "state")["state"].lower() == "closed" for n in bundle):
                    outcome = "closed"
                elif status is None:
                    raise WorkerGone(f"the worker {agent} is gone and the build has no PR")
            if not outcome and status is not None and (status in IDLE or status in STALLED):
                if spec:
                    busy = slices_working(ctx, spec)
                if status in IDLE and not busy:
                    busy = live_job(workspace_of(ctx, branch)) is not None
            errors = 0
        except WorkerGone:
            raise
        except (DrainError, DrainStop):
            errors += 1
            if errors >= LOOK_ERRORS:
                raise
        else:
            if outcome:
                return outcome
            if (status in IDLE or status in STALLED) and not busy:
                stalled_since = stalled_since or time.monotonic()
                if time.monotonic() - stalled_since >= IDLE_GRACE_SECONDS:
                    if spec and status in IDLE and agent not in resumed:
                        resumed.add(agent)  # before the prompt: one that failed was still the one
                        stalled_since = None
                        resume(ctx, agent)
                    elif agent in resumed:
                        raise IdleAfterResume(f"the worker {agent} is {status} with no PR, and drain's one "
                                              "resume prompt did not help")
                    else:
                        raise DrainError(f"the worker {agent} is {status} with no PR")
            else:
                stalled_since = None
        if time.monotonic() > deadline:
            raise DrainError(f"the worker {agent} passed the {limit}s wall clock")
        time.sleep(POLL_SECONDS)


def open_pr(ctx, branch):
    prs = asked(ctx.tracker.open_prs, branch)
    return prs[0] if prs else None


def run_in_scratch_tree(ctx, cmd, log, head, main):
    """`scratch_run.run_in_scratch_tree` on `main` (current main's sha) with
    `head` merged in, under the worker's wall clock; any failure there is a
    `DrainError`."""
    try:
        scratch_run.run_in_scratch_tree(ctx.root, main, cmd, log, WALL_CLOCK_SECONDS, head=head)
    except scratch_run.ScratchError as exc:
        raise DrainError(str(exc)) from None


SELECTOR_CHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "implement", "selector_check.py")
# What the run writes to its log before the per-change command, so a failure
# names the command that ran, not the shell around it.
RUNNING = "per-change command: "


# The most `TESTS_JOBS` the run gets: `tests/all.sh`'s `linked_cap`, the
# width an undeclared run in a linked worktree gets (#1808). The scratch
# tree's run is no declared job either (#1949). A test holds the two equal.
SEAM_JOBS = 4
# How many times main may move under the merge's check before drain gives up:
# each move means the checked tree is not the one the merge would land.
BASE_CHECKS = 3
# The PR body line a worker under drain writes for the commit its green run
# covered (#1949).
SEAM_RUN_AT = re.compile(r"^Seam run at: ([0-9a-f]{40})\s*$", re.MULTILINE)


def seam_jobs():
    """`TESTS_JOBS` for the run: drain's own `TESTS_JOBS` when it is a smaller
    positive number, else `SEAM_JOBS`. The cap only ever lowers the width."""
    try:
        asked = int(os.environ.get("TESTS_JOBS", ""))
    except ValueError:
        return SEAM_JOBS
    return asked if 0 < asked < SEAM_JOBS else SEAM_JOBS


def worker_ran_on(body):
    """The full sha every `Seam run at:` line of the PR body names, else
    `None`: no line, a line that is no full sha, or two lines naming
    different shas all keep the rerun."""
    shas = set(SEAM_RUN_AT.findall(body or ""))
    return shas.pop() if len(shas) == 1 else None


def skip_reason(ctx, head, body, main):
    """The `seam rerun skipped:` comment when the rerun would repeat the
    worker's green run, else `None`. These are #1616's three checks
    (`implement/SKILL.md` § The merge step 3): current main (`main`, read
    after the fetch) is in `head`, the body's `Seam run at:` sha is `head`,
    and the seam section is the same at both. A fourth keeps the module
    docstring's rule that a section declaring no command merges nothing:
    main's section must resolve a command. Any check that cannot answer
    keeps the rerun."""
    if worker_ran_on(body) != head:
        return None
    try:
        if shellcmd.git(["merge-base", "--is-ancestor", main, head], cwd=ctx.root, ok=(0, 1)).returncode:
            return None
    except shellcmd.CmdError:
        return None
    tool = [sys.executable, SELECTOR_CHECK]
    same = subprocess.run(tool + ["seam-section", "--root", ctx.root, "--base-rev", main, "--head-rev", head],
                          capture_output=True, text=True)
    if same.returncode or same.stdout.strip() != "same":
        return None
    if subprocess.run(tool + ["command", "--root", ctx.root, "--rev", main], capture_output=True).returncode:
        return None
    return f"seam rerun skipped: {ctx.default} {main} is in the head {head}, worker's run at {head}"


def seam(ctx, head, log, pr, body):
    """The merge's run, as the module docstring states it, on the PR head
    merged into current main in a throwaway worktree; returns the main sha
    it checked against. The command's own exit status is what comes out,
    never the `selector:` comment's; a resolver refusal raises with its
    reason, before anything runs. Skipped, with its comment on the PR, when
    `skip_reason` finds the worker's run covered this tree; a comment that
    cannot be posted runs it anyway, so no merge lands with neither
    record."""
    git(["fetch", "-q", "origin"], cwd=ctx.root)
    main = git(["rev-parse", ctx.default], cwd=ctx.root)
    skipped = skip_reason(ctx, head, body, main)
    if skipped:
        try:
            ctx.tracker.comment(pr, skipped)
            return main
        except tracker.TrackerError:
            pass
    log = os.path.abspath(log)  # the commands run in the scratch tree, not in drain's cwd
    with contextlib.suppress(FileNotFoundError):
        os.remove(log)  # a conflict writes no log, and an earlier drain's must not answer for it
    state = shlex.quote(os.path.splitext(log)[0] + "-selector.json")
    tool = f"{shlex.quote(sys.executable)} {shlex.quote(os.path.normpath(SELECTOR_CHECK))}"
    base = f"--root . --rev {shlex.quote(main)}"
    cmd = (f"export TESTS_JOBS={seam_jobs()}; cmd=$({tool} command {base}) || exit 1; "
           f"printf '{RUNNING}%s\\n' \"$cmd\"; "
           f"if {tool} list {base} --state {state}; then "
           f"{tool} comment {base} --state {state} --pr {pr} --repo {shlex.quote(ctx.repo)}; fi; "
           'sh -c "$cmd"')
    try:
        run_in_scratch_tree(ctx, cmd, log, head, main)
    except DrainError as exc:
        raise DrainError(f"seam {seam_failure(log) or exc} on the PR merged into main") from exc
    return main


def seam_failure(log):
    """What a failed `seam` run's log says failed: the resolver's reason, the
    per-change command that ran, or `None` when neither got that far (a
    conflict, an install), whose own error then stands."""
    try:
        with open(log, errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith(UNDECLARED):
            return "the repo declares no per-change command: " + line[len(UNDECLARED):]
    ran = [x[len(RUNNING):] for x in lines if x.startswith(RUNNING)]
    return f"`{ran[-1]}` failed (output in {log})" if ran else None


def repo_slug(ctx):
    """`owner__name`: the repo as one file-name component."""
    return ctx.repo.replace("/", "__")


def verify_pr(ctx, branch, anchor, kind):
    """The PR's settled view: not draft and CLEAN, waited for rather than
    refused on UNKNOWN or a check still running (`pr_settle.py` has the
    limits), then its closures and the seam."""
    try:
        view = pr_settle.settle(pr_settle.gh_reader(branch, ctx.repo, "number,url,closingIssuesReferences,body",
                                                    tracker=ctx.tracker))
    except pr_settle.SettleError as exc:
        url = (exc.view or {}).get("url")
        raise DrainError(f"{url} {exc}" if url else str(exc)) from exc
    closed = {r["number"] for r in view["closingIssuesReferences"]}
    if anchor not in closed:
        raise DrainError(f"{view['url']} does not close the anchor #{anchor}")
    if kind == SPEC:  # the spec and its slices are one bundle, whatever their number
        foreign = [n for n in sorted(closed - {anchor}) if not is_slice_of(ctx, n, anchor)]
        if foreign:
            raise DrainError(f"{view['url']} closes " + ", ".join(f"#{n}" for n in foreign)
                             + f" which is not a slice of spec #{anchor}")
    else:
        unrecorded = closed - {anchor} - noted(ctx, anchor)
        if unrecorded:
            raise DrainError(f"{view['url']} closes " + ", ".join(f"#{n}" for n in sorted(unrecorded))
                             + f" which no {BUNDLE_NOTE} comment on #{anchor} names")
        if len(closed) > ctx.bundle_max:
            raise DrainError(f"{view['url']} closes {len(closed)} tickets, over --bundle-max {ctx.bundle_max}")
    view["closes"] = sorted(closed)
    check_merge(ctx, branch, view)
    return view


def check_merge(ctx, branch, view):
    """`seam` on the PR, then again each time main has moved by the last
    fetch before the merge, as the lane's merge step re-runs on a moved
    base: a check of an older main is no check of the tree the merge
    lands. Main moving under `BASE_CHECKS` checks in a row is a
    `DrainError`."""
    log = os.path.join(ctx.log_dir, f"{branch}-seam.log")
    for _ in range(BASE_CHECKS):
        checked = seam(ctx, view["headRefOid"], log, view["number"], view.get("body"))
        git(["fetch", "-q", "origin"], cwd=ctx.root)
        if git(["rev-parse", ctx.default], cwd=ctx.root) == checked:
            return
    raise DrainError(f"{ctx.default} moved under each of {BASE_CHECKS} merge checks of {view['url']}")


def cleanup_notes(ctx, branch):
    """`merge-cleanup`, closing the worker's pane and removing its workspace; a
    failure is a note, never a reason to build again."""
    try:
        cleanup = subprocess.run(["merge-cleanup", "--repo", ctx.root, branch], capture_output=True, text=True)
    except OSError as exc:
        return [f"merge-cleanup: {exc}"]
    if cleanup.returncode:
        return ["merge-cleanup failed: " + one_line(cleanup.stderr or cleanup.stdout, 150)]
    return []


# What a result is: a PR drain merged (or a commit that landed on main), or a
# close with no PR that no sha stands behind.
MERGED, CLOSED, UNVERIFIED = "merged", "closed", "unverified"
LANDED_LABEL, MOOT_LABEL = "(landed on main, no PR)", "moot (closed, no PR)"


def closing_commit(ctx, n):
    """The sha of the commit that closed ticket `n`, `None` when it was closed
    by hand, as read from its last `closed` event. Raises `DrainError` when
    GitHub cannot say."""
    events = asked(ctx.tracker.closed_events, n)
    if not events:
        raise DrainError("it has no closed event")
    if "commit_id" not in events[-1]:
        raise DrainError("its closed event carries no commit_id field")
    return events[-1]["commit_id"]


def closes_commit(ctx, n):
    """The sha of the newest commit on the default branch whose message says
    `Closes #<n>` (or Fixes, Resolves), `None` when there is none. The light
    tier's worker closes by hand when the trailer did not fire, so a close
    with no commit on its event is moot only when no landed commit says it
    closed the ticket either. Raises `DrainError` when git cannot say."""
    pattern = rf"\b(closes|fixes|resolves) #{n}([^0-9]|$)"
    try:
        found = git(["log", "-n1", "--format=%H", "-i", "-E", f"--grep={pattern}", ctx.default], cwd=ctx.root)
    except DrainError as exc:
        raise DrainError(f"git log on {ctx.default} failed: {one_line(exc, 100)}") from None
    return found or None


def close_outcome(ctx, n):
    """`(label, sha)` for ticket `n`, closed with no PR: landed on main with
    the commit that closed it, moot when nothing but a hand closed it, or
    unverified with the reason, which carries no sha. An answer that cannot be
    read is never read as either of the others."""
    try:
        commit = closing_commit(ctx, n)
    except (DrainError, KeyError, TypeError, ValueError) as exc:
        return f"closed, no PR (landing not verified: {one_line(exc, 100)})", None
    if commit is None:
        try:
            commit = closes_commit(ctx, n)
        except DrainError as exc:
            return f"closed, no PR (landing not verified: {one_line(exc, 100)})", None
        return (LANDED_LABEL, commit) if commit else (MOOT_LABEL, None)
    try:
        on_main = shellcmd.git(["merge-base", "--is-ancestor", commit, ctx.default], cwd=ctx.root, ok=(0, 1))
    except shellcmd.CmdError as exc:
        return (f"closed, no PR (landing not verified: could not check closing commit {commit[:8]}: "
                f"{one_line(exc, 80)})"), None
    if on_main.returncode == 1:
        return f"closed, no PR (landing not verified: closing commit {commit[:8]} is not on {ctx.default})", None
    return LANDED_LABEL, commit


def finish_closed(ctx, branch, tickets):
    """The worker closed every ticket and opened no PR: `merge-cleanup` is all
    that is left, the controller's step in a spec run. Each ticket is recorded as
    what closed it (`close_outcome`), never as main's current tip: a ticket
    closed as moot has no landing, and the tip is another ticket's commit.
    One result per distinct outcome; the cleanup note rides on the first."""
    notes = cleanup_notes(ctx, branch)
    try:
        git(["fetch", "-q", "origin"], cwd=ctx.root)
    except DrainError as exc:
        notes.append(f"fetch failed: {one_line(exc, 100)}")
    groups = {}
    for n in sorted(tickets):
        groups.setdefault(close_outcome(ctx, n), []).append(n)
    def outcome_of(label, sha):
        return MERGED if sha else CLOSED if label == MOOT_LABEL else UNVERIFIED

    results = [{"tickets": ts, "via": label, "sha": sha or "", "note": "", "outcome": outcome_of(label, sha)}
               for (label, sha), ts in groups.items()]
    results[0]["note"] = "; ".join(notes)
    return results


def finish(ctx, anchor, branch, view, kind):
    """After the merge: the squash sha, `merge-cleanup`, and the tickets the
    agent claimed that the PR did not close back to the queue. A step that
    fails is a note on a merged PR, never a reason to build again."""
    notes, sha = [], view["headRefOid"]
    try:
        sha = asked(ctx.tracker.pr_view, view["number"], "mergeCommit")["mergeCommit"]["oid"]
    except (DrainError, KeyError, TypeError) as exc:
        notes.append(f"squash sha unread, head shown: {one_line(exc, 100)}")
    notes += cleanup_notes(ctx, branch)
    try:
        for n in set(bundle_of(ctx, anchor, branch, kind)) - set(view["closes"]):
            relabel(ctx, n, READY)
    except DrainError as exc:
        notes.append("releasing unclosed tickets failed: " + one_line(exc, 150))
    return [{"tickets": view["closes"], "via": view["url"], "sha": sha, "note": "; ".join(notes), "outcome": MERGED,
             "deploy": deploy_after_merge(ctx, view["before"])}]


# How long a deploy may run, and how many of its last output lines the progress
# file keeps.
DEPLOY_SECONDS = 1800
DEPLOY_TAIL = 15


def deploy_after_merge(ctx, before):
    """`None` when the repo declares no `Deploy` line (#1726); else a dict
    `{command, status, tail, owed, failed, why}`: main fast-forwarded in the
    primary checkout, then the command run there with `{before}` (main's sha
    just before this merge) substituted. `owed` is every output line starting
    with one of the repo's markers. A section that cannot be read, a checkout
    that cannot fast-forward and a deploy that exits non-zero or times out are
    all `failed` with the reason in `why`, never "no deploy" (class 1). Read
    from main after the merge, as the seam's command is read from current
    main."""
    def failed(why, command="", status=None, tail=(), owed=()):
        return {"command": command, "status": status, "tail": list(tail), "owed": list(owed), "failed": True,
                "why": why}

    try:
        git(["fetch", "-q", "origin"], cwd=ctx.root)
        deploy, why = selector_check.deploy_of(ctx.root, ctx.default)
        if why:
            return failed(f"the deploy declaration cannot be read: {why}")
        if deploy is None:
            return None
        local = ctx.default.split("/", 1)[-1]  # `ctx.default` is `origin/<branch>`
        if git(["branch", "--show-current"], cwd=ctx.root) != local:
            return failed(f"the primary checkout is not on {local}, so it was not fast-forwarded", deploy.command)
        git(["merge", "--ff-only", "-q", ctx.default], cwd=ctx.root)
    except DrainError as exc:
        return failed(f"could not fast-forward the primary checkout: {one_line(exc, 150)}")
    command = deploy.command.replace("{before}", before)
    try:
        ran = subprocess.run(command, shell=True, cwd=ctx.root, capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=DEPLOY_SECONDS, errors="replace")
    except subprocess.TimeoutExpired:
        return failed(f"timed out after {DEPLOY_SECONDS} s", command)
    lines = (ran.stdout + ran.stderr).splitlines()
    owed = [x.strip() for x in lines if x.strip().lower().startswith(tuple(m.lower() for m in deploy.markers))]
    return {"command": command, "status": ran.returncode, "tail": lines[-DEPLOY_TAIL:], "owed": owed,
            "failed": bool(ran.returncode), "why": f"exited {ran.returncode}" if ran.returncode else ""}


def say_deploy(result):
    """The deploy's command, exit status and output tail as progress lines,
    and the stop reason when it failed, else `None`."""
    deploy = result.get("deploy")
    if not deploy:
        return None
    say(f"deploy {refs(result['tickets'])}: `{deploy['command']}` -> "
        + ("not run" if deploy["status"] is None else f"exit {deploy['status']}") + f"  ({deploy['why']})" * bool(deploy["why"]))
    for line in deploy["tail"]:
        say(f"deploy output: {line}")
    return f"deploy {deploy['why']} after merging {result['via']} ({refs(result['tickets'])})" if deploy["failed"] else None


def resume(ctx, agent):
    """Prompt an idle spec run once to continue or say what blocks it, and say so (#1710)."""
    prompt_agent(ctx, agent, RESUME_TEXT)
    say(f"resumed: {agent} was idle with no integration PR; sent it one prompt and restarted the idle grace")


RESUME_TEXT = ("Unattended drain, no controller: you are idle with no integration PR. Continue /implement-spec "
               "for this spec now, or report what blocks you and stop. Send no messages.")


def nudge_text(reason, pr_up, kind):
    head = "Unattended drain, no controller: "
    if pr_up:
        return (head + f"the PR is up but drain's check of it failed: {reason} Fix that, push to the PR branch, "
                "and send no messages.")
    if kind == SPEC:
        return head + (f"the PR is not up yet ({reason}). Finish /implement-spec for this spec now, the slices, "
                       "the spec-level review and the integration PR, and send no messages.")
    return head + (f"the PR is not up yet ({reason}). Finish /implement for this ticket now, the build, the "
                   "review wave and the PR, and send no messages.")


def nudge(ctx, agent, branch, reason, kind):
    """Prompt the worker with why the first try failed and wait for it to start
    working, so the next look at it is not the idle it was in before the prompt."""
    prompt_agent(ctx, agent, nudge_text(reason, bool(open_pr(ctx, branch)), kind))


def prompt_agent(ctx, agent, text):
    """Send `text` to `agent` through herdr and wait for it to start working or block."""
    if agent_status(agent) is None:
        raise WorkerGone(f"the worker {agent} is gone; nothing to prompt")
    code, out = run_group(["herdr", "agent", "prompt", agent, text,
                           "--wait", "--until", "working", "--until", "blocked", "--timeout", "30000"],
                          ctx.root, 60)
    if code:
        raise DrainError(f"herdr agent prompt {agent} failed: {one_line(out, 150)}")


def say(text):
    """One progress line, flushed: `job-run` copies drain's stdout into the run's
    progress file, and a buffered line would reach it only at exit."""
    print(text, flush=True)


def title_of(ctx, n):
    try:
        return one_line(issue_view(ctx, n, "title")["title"], 100)
    except (DrainError, KeyError, TypeError):
        return "(title unread)"


def announce(ctx, anchor, tickets, kind):
    """The `bundle started:` line: every ticket with its title and the worker's
    herdr pane, said the moment the bundle's worker exists."""
    say("bundle started: " + "; ".join(f"#{n} {title_of(ctx, n)}" for n in tickets)
        + f"  pane {agent_name(ctx, anchor, kind)}")


def work(ctx, anchor, others, resumed, started, kind):
    """`([result, ...], None)` or `(None, the second failure's one-line reason)`;
    appends the bundle's tickets to `started` once its worker exists.
    Attempt 1 starts the worker (a resumed bundle finds it or its PR already
    there); attempt 2 prompts the same worker with the first failure's reason,
    since its workspace exists and a second dispatch would refuse it."""
    branch, agent, reason, bundle = branch_of(anchor, kind), agent_name(ctx, anchor, kind), "", [anchor]
    resumed_agents = set()
    # The worker's branch and agent are named for the lowest ticket in the
    # bundle, so every ticket bundled with the anchor is a higher number.
    others = [t for t in others if t[0] > anchor]
    for attempt in (1, 2):
        try:
            if attempt == 2:
                nudge(ctx, agent, branch, reason, kind)
            elif not resumed:
                if kind == TICKET:  # a spec's slices are its bundle: nothing to choose
                    bundle, why = choose_bundle(ctx, anchor, others, os.path.join(ctx.log_dir, f"{repo_slug(ctx)}-{branch}-choose.log"))
                    if why:
                        asked(ctx.tracker.comment, anchor, f"{CHOOSER_NOTE} #{anchor} alone: {why}")
                    asked(ctx.tracker.comment, anchor, f"{BUNDLE_NOTE} {' '.join(str(n) for n in bundle)} {count_note(len(others))}")
                dispatch(ctx, bundle, kind)
            tickets = [anchor] + (sorted(noted(ctx, anchor)) if kind == TICKET else [])
            if attempt == 1:
                announce(ctx, anchor, tickets, kind)
                started[:] = tickets
            if wait_for_worker(ctx, branch, agent, tickets, spec=anchor if kind == SPEC else None,
                               resumed=resumed_agents) == "closed":
                return finish_closed(ctx, branch, tickets), None
            view = verify_pr(ctx, branch, anchor, kind)
            git(["fetch", "-q", "origin"], cwd=ctx.root)
            view["before"] = git(["rev-parse", ctx.default], cwd=ctx.root)  # `{before}` of the deploy (#1726)
            try:
                pr_settle.merge(pr_settle.gh_reader(view["number"], ctx.repo, tracker=ctx.tracker),
                                pr_settle.gh_merger(view["number"], ctx.repo, tracker=ctx.tracker), view["headRefOid"])
            except pr_settle.SettleError as exc:
                raise DrainError(f"{view['url']} {exc}") from exc
        except DrainError as exc:
            reason = one_line(exc)
            if not started:  # a failure before the announce (a dispatch that failed after the claim): the bundle was still worked
                announce(ctx, anchor, bundle, kind)
                started[:] = bundle
            if isinstance(exc, IdleAfterResume):  # the resume was the second try
                return None, reason
        else:
            return finish(ctx, anchor, branch, view, kind), None
    return None, reason


def hand_to_chris(ctx, anchor, reason, kind):
    branch = branch_of(anchor, kind)
    stop_worker(agent_name(ctx, anchor, kind))
    bundle = bundle_of(ctx, anchor, branch, kind)
    if kind == SPEC:  # the spec run's slice workers would otherwise keep working with nobody to merge them
        for n in bundle[1:]:
            stop_worker(agent_name(ctx, n, TICKET))
    for n in bundle:
        relabel(ctx, n, HUMAN)
        asked(ctx.tracker.comment, n, f"{HANDED_NOTE} this ticket (bundle {refs(bundle)}) after two attempts. "
           f"Last failure: {reason} The worktree {branch} is kept for inspection and its worker's "
           "pane is closed; drain skips this ticket until that worktree is removed.")
    return bundle


Result = collections.namedtuple("Result", "merged closed handed stop ended passed unread")


def survey(ctx, retry=True):
    """`(queue, waiting, stranded, candidates, passed)`: one read of the queue.
    `candidates` is the queue's tickets that may anchor a bundle; `passed`
    also names the queued ones whose workspace is kept."""
    queue, waiting, stranded, passed = read_frontier(ctx, retry)
    candidates = anchors(ctx, queue)
    kept = sorted({t[0] for t in queue} - {t[0] for t in candidates})
    return queue, waiting, stranded, candidates, passed + [(n, "workspace kept") for n in kept]


def say_unresolved(ctx, prog, passed):
    """Once per drain, before its first bundle: one `unresolved at start:` line per ready
    ticket `passed` holds as unresolved, with the same reason its `passed over:` line gives."""
    if prog.preflight:
        return
    prog.preflight = True
    for n, why in passed:
        if why.startswith(UNRESOLVED):
            say(f"unresolved at start: #{n} {title_of(ctx, n)}  {why}")


def preflight_for_resume(ctx, prog):
    """A resumed bundle starts before any queue read, so the preflight reads the queue
    itself first. A failed read is said, never taken for an empty list."""
    if prog.preflight:
        return
    try:
        passed = read_frontier(ctx, retry=False)[3]
    except DrainError as exc:
        prog.preflight = True
        say(f"unresolved at start: not read ({one_line(exc, 150)})")
        return
    say_unresolved(ctx, prog, passed)


def say_waiting(waiting):
    for spec in waiting:
        say(f"waiting: ready slices of spec #{spec}, which drain cannot start (it is not "
            "ready-for-agent, is claimed, or is blocked)")


class Progress:
    """What one drain has done and seen so far: the state `next_anchor` and
    `record_bundle` read and write, so the loop body holds none of it."""

    def __init__(self, want):
        self.merged, self.closed, self.handed = [], [], []
        self.failures, self.done, self.want = 0, 0, want
        self.preflight = False  # the `unresolved at start:` lines are out
        self.started = []  # the tickets of a bundle whose start line is out and whose end line is not
        self.told = set()  # stranded slices already named this drain
        self.ended = set()  # the anchors this drain has taken up: added before `work()`, so none is taken twice
        self.cause, self.seen = None, None  # the cause the drain ended on, and the last queue read `(queue, waiting, passed)`


def next_anchor(ctx, prog):
    """`(anchor, kind, resumed, others)` for the next bundle, or `None` when the
    queue holds nothing startable (`prog.cause` then says which). A resumable
    anchor comes first; otherwise the queue is read, `--anchor` is put first and
    the head is noted."""
    while True:
        taken = resumable(ctx, prog.ended)
        if taken is not None:
            preflight_for_resume(ctx, prog)
            anchor, kind = taken
            return anchor, kind, True, []
        queue, waiting, stranded, candidates, passed = survey(ctx)
        prog.seen = (queue, waiting, passed)
        say_unresolved(ctx, prog, passed)
        for n, why in stranded:
            if n not in prog.told:  # every exit names them, once
                prog.told.add(n)
                say(f"stranded: #{n}, {why}")
        if not candidates:
            say_waiting(waiting)
            prog.cause = "queue empty" if not queue else "no startable ticket"
            prog.seen = (queue, [], passed)  # named just above
            return None
        if prog.want:
            if not any(t[0] == prog.want for t in candidates):
                raise DrainStop(f"--anchor #{prog.want} left the ready queue before drain reached it")
            candidates, prog.want = put_first(candidates, prog.want), None
        anchor, _, kind = candidates[0]
        others = [(n, title) for n, title, k in queue if k == TICKET and n != anchor]
        if note_anchor(ctx, anchor, kind):
            return anchor, kind, False, others


def record_bundle(ctx, prog, anchor, kind, results, reason):
    """Say how the bundle ended and file it: its results as merged or closed, or,
    when it failed, hand it to Chris. Returns the stop reason when the failures
    in a row reach the limit, else `None`."""
    if results:
        for result in results:
            if result["outcome"] == MERGED:
                say(f"bundle ended: {refs(result['tickets'])}  merged  {result['via']}  {result['sha']}")
            else:
                say(f"bundle ended: {refs(result['tickets'])}  {result['via']}")
            (prog.merged if result["outcome"] == MERGED else prog.closed).append(result)
        prog.started.clear()
        prog.done, prog.failures = prog.done + sum(len(r["tickets"]) for r in results), 0
        # A failed deploy stops the run after the merges already made (#1726).
        return next((stop for stop in map(say_deploy, results) if stop), None)
    bundle = hand_to_chris(ctx, anchor, reason, kind)
    say(f"bundle ended: {refs(bundle)}  handed to Chris: {reason}")
    prog.started.clear()
    prog.handed.append((bundle, reason))
    prog.done, prog.failures = prog.done + len(bundle), prog.failures + 1
    return consecutive_failure_stop(ctx, prog.failures)


def drain(ctx, limit, limit_name):
    """`Result`: what merged, what closed with no PR, what was handed over,
    the stop reason or `None`, the cause the drain ended on, and the ready tickets it
    passed over as `[(number, why)]`. `passed` is `None` when no queue could be
    read for it, and `unread` then says why. `limit` counts tickets;
    `limit_name` is how a reached limit is worded, e.g. `--max 3`. Each pass of
    the loop picks an anchor, works its bundle and records the result."""
    prog, stop = Progress(ctx.want), None
    try:
        if prog.want:  # refuse before any work, and not only when the loop gets there
            queue, waiting, _, candidates, passed = survey(ctx)
            prog.seen = (queue, waiting, passed)
            say_unresolved(ctx, prog, passed)
            if not any(t[0] == prog.want for t in candidates) and dict(passed).get(prog.want, "").startswith(HELD_SPEC_REASONS):
                raise DrainError(f"--anchor #{prog.want} is passed over: {dict(passed)[prog.want]}")
            put_first(candidates, prog.want)
        while prog.done < limit:
            pick = next_anchor(ctx, prog)
            if pick is None:
                break
            anchor, kind, resumed, others = pick
            prog.ended.add(anchor)
            results, reason = work(ctx, anchor, others, resumed, prog.started, kind)
            stop = record_bundle(ctx, prog, anchor, kind, results, reason)
            if stop:
                break
        else:
            prog.cause = f"{limit_name} reached"
    except (DrainStop, DrainError) as exc:  # a refusal or a tracker failure, said as it is
        stop = str(exc)
    except Exception as exc:  # noqa: BLE001 - the summary of what landed must still print
        stop = f"unexpected {type(exc).__name__}: {one_line(exc)}"
    if prog.started:
        say(f"bundle ended: {refs(prog.started)}  stopped: {stop}")
    if stop:
        prog.cause = "stopped"
    return Result(prog.merged, prog.closed, prog.handed, stop, prog.cause,
               *passed_at_exit(ctx, prog))


def passed_at_exit(ctx, prog):
    """`(passed, unread)`: the ready tickets this drain passed over, read fresh at
    an exit that left work behind (a limit, or no queue read yet) so a list
    from the start of an hours-long drain is not reported as current; a stopped
    drain, whose environment may be failing, keeps its last read. Ready tickets
    this drain never started carry the cause as their reason."""
    cause, seen = prog.cause, prog.seen
    worked = set(prog.ended) | {n for r in prog.merged + prog.closed for n in r["tickets"]} | {n for b, _ in prog.handed for n in b}
    fresh = cause != "stopped" and (seen is None or cause.endswith("reached"))
    unread = None
    if fresh:
        try:
            queue, waiting, _, _, passed = survey(ctx, retry=False)
        except DrainError as exc:
            seen, unread = None, f"not read (the queue could not be listed at exit: {one_line(exc, 150)})"
        else:
            seen = (queue, waiting, passed)
    if seen is not None:  # specs the loop's own break did not already name
        say_waiting(seen[1])
    if seen is None:
        return None, unread or "not read (the drain stopped before the queue was listed)"
    queue, _, passed = seen
    listed = {n for n, _ in passed}
    return passed + [(n, f"ready, not started ({cause})") for n, _, _ in queue
                     if n not in worked and n not in listed], None


def summary(result):
    """The result lines, `passed over:` for each ready ticket left, and the
    closing `ended:` line. It is not a `stopped:` line and does not change the
    exit code."""
    lines = []
    if result.merged:
        for m in result.merged:
            lines += (["merged:"] if m is result.merged[0] else []) + [
                f"  {refs(m['tickets'])}  {m['via']}  {m['sha']}" + (f"  ({m['note']})" if m["note"] else "")]
            lines += [f"    deploy: {x}" for x in (m.get("deploy") or {}).get("owed", [])]
    if result.closed:
        lines += ["closed, no PR:"] + [f"  {refs(m['tickets'])}  {m['via']}"
                                        + (f"  ({m['note']})" if m["note"] else "") for m in result.closed]
    if result.handed:
        lines += ["handed to Chris:"] + [f"  {refs(b)}  {r}" for b, r in result.handed]
    if result.stop:
        lines.append(f"stopped: {result.stop}")
    if not (result.merged or result.closed or result.handed or result.stop):
        lines.append("nothing to drain")
    if result.passed is None:
        lines.append(f"passed over: {result.unread}")
    else:
        lines += [f"passed over: #{n} {why}" for n, why in result.passed]
    lines.append(f"ended: {result.ended}")
    return "\n".join(lines)


def positive(text):
    if int(text) < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return int(text)


def main(argv):
    parser = argparse.ArgumentParser(description="work the ready-for-agent queue, one bundle at a time")
    parser.add_argument("--repo", default=".", help="the repo's primary checkout")
    parser.add_argument("--once", action="store_true", help="one bundle, then stop")
    parser.add_argument("--max", type=positive, default=None, help="stop after this many tickets")
    parser.add_argument("--bundle-max", type=positive, default=BUNDLE_MAX)
    parser.add_argument("--anchor", type=positive, default=None,
                        help="start the first bundle from this ticket, not the oldest ready one")
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        # The primary checkout, even when --repo is a linked worktree: workers,
        # their herdr agent names and `merge-cleanup` are all keyed on it.
        common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=args.repo)
        root = os.path.dirname(common)
        repo = origin_slug(root)
        issues = tracker.GhTracker(repo)
        login = asked(issues.viewer_login)
        try:
            owned = owners.is_owned(repo.split("/")[0], login)
        except owners.OwnersError as exc:
            raise DrainError(f"{repo}: {exc}; drain only runs on the caller's own repos") from exc
        if not owned:
            raise DrainError(f"{repo} is not owned by {login} nor on the owned-owners list; "
                             "drain only runs on the caller's own repos")
        default = shellcmd.default_branch(root)
        log_dir = os.environ.get("DRAIN_LOG_DIR") or os.path.expanduser("~/.cache/drain")
        os.makedirs(log_dir, exist_ok=True)
    except (DrainError, shellcmd.CmdError) as exc:
        print(f"drain.py: {exc}", file=sys.stderr)
        return 1
    limit = 1 if args.once else (args.max or sys.maxsize)
    limit_name = "--once" if args.once else f"--max {args.max}"
    run_ = drain(Ctx(root, repo, default, log_dir, args.bundle_max, args.anchor, issues), limit, limit_name)
    say(summary(run_))
    return 1 if run_.stop else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
