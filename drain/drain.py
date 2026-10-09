#!/usr/bin/env python3
"""`drain.py [--repo <path>] [--once] [--max <n>] [--bundle-max <k>]
[--anchor <n>]`: work the `ready-for-agent` queue unattended, serially, one PR
at a time (#1403).

The **anchor** is the oldest unblocked ready ticket (`burndown/frontier.py`)
or clear spec parent, whichever has the lower number, or, for the first bundle
drain picks, the ticket or spec `--anchor <n>` names (refused unless `<n>` is
open, ready, unblocked and without a kept workspace; a resumed bundle goes
first and the anchor waits for the next pick). Tickets numbered
below the anchor never join its bundle, because the worker's branch and herdr
agent are named for the lowest ticket of a clump.

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
reviewer is 22 minutes). `drain` does no directory or closure grouping.

A **spec parent** is a bundle of its own (#1477). The frontier's `spec` bucket
holds the parents `implement-dispatch --spec` accepts (`ready-for-agent`, not
claimed, not blocked), so only they anchor: a spec without the ready label, or
one a burn already runs, leaves its slices unbuilt, as a slice never is built as
a lone ticket. `drain` starts it with `implement-dispatch --spec <n>` (that
command's own slot default) and no chooser, since the spec's slices are its
bundle. When nothing else is startable, a `waiting:` line names each spec whose
slices are ready but which `drain` cannot start. The spec
run is the worker: pane `<repo-short>-spec-<n>`, workspace and branch
`spec-<n>`, and it drives its slices itself (`implement-spec/SKILL.md`). Its
stop is the integration PR up and the pane idle, and the wait differs in three
ways: the half-hour idle grace does not run while a slice worker is `working`,
the wall clock is twelve hours (`SPEC_WALL_CLOCK_SECONDS`), and the PR must
close the spec and may close any number of its slices (a ticket whose parent is
the spec), with no `--bundle-max` cap, since the spec's size is its own. A
failed spec run is handed to Chris with the spec, its claimed slices and every
pane of theirs closed. A spec with one slice has no integration branch and no
`spec-<n>` PR: its run lands the slice itself, and `drain` reports the spec as
landed with no PR, its own PR check never having run.
`--max` stops the loop after that many tickets (a bundle counts all of its
tickets); `--once` stops after one bundle.

Then it checks (the PR is not draft, CLEAN, closes the anchor within the
bundle cap, and the repo's seam passes on the PR merged into current main,
narrowed to what the PR touched; the check is skipped when main has not moved
past the PR's base, because the worker ran the same suite on that exact tree),
squash-merges, runs `merge-cleanup` (which closes the worker's pane), and
returns any ticket the worker claimed but the PR did not close to the queue.
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
<reason>` when it ends, then the summary. `drain/SKILL.md` reads these lines
for its same-turn print, its status and its completion report.

State lives in GitHub, git and herdr, nowhere else. An open, in-progress
ticket carrying drain's own `drain anchor:` comment is resumed (a worker
started by `implement-dispatch` outside drain has none, so it is never taken)
and its worker or open PR is waited on and checked rather than rebuilt. Only
repos whose origin owner is the `gh` login.

After the last bundle, one full `bash tests/all.sh` runs on current main
(#1415): a red one stops the run and the summary names the merges since the
last green full run (`last-green-<repo>` in the log directory), for Chris.
"""
import argparse
import collections
import contextlib
import ctypes
import fcntl
import os
import json
import re
import resource
import shlex
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "burndown"))

import frontier  # noqa: E402

READY, HUMAN, CLAIMED = "ready-for-agent", "ready-for-human", frontier.CLAIMED_LABEL
ANCHOR_NOTE, BUNDLE_NOTE, HANDED_NOTE = "drain anchor:", "drain bundle:", "drain could not land"
CHOOSER_NOTE = "drain chooser:"  # never `BUNDLE_NOTE`: its digits would read as tickets
# The count a `drain bundle:` note ends with, which is not a ticket.
# `count_note` writes it and `CANDIDATES` strips it: change the two together.
CANDIDATES = re.compile(r"\(of \d+ candidates\)")


def count_note(k):
    return f"(of {k} candidates)"
BUNDLE_MAX = 8
MAX_CONSECUTIVE_FAILURES = 2
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
FULL_SEAM = "bash tests/all.sh"
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
IDLE = ("idle", "done")
# `blocked` is a permission or question dialog nobody here can answer.
STALLED = ("blocked",)
# Consecutive failed looks at a worker (a `gh` or `herdr` call) before the wait
# gives up, so one transient error is not a failed build or a stopped run.
LOOK_ERRORS = 5
# The controller named in every brief. No session bears it: the worker's "PR up"
# send to it finds nobody and the worker stops idle, which is what drain waits
# for. A question the worker would put to a controller goes unanswered the same
# way and shows as an idle worker with no PR, a failed build.
CONTROLLER = "drain"
_ORIGIN = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")

Ctx = collections.namedtuple("Ctx", "root repo default log_dir bundle_max want")
# What an anchor is: a ticket built by a worker, or a spec parent built by a spec run.
TICKET, SPEC = "ticket", "spec"


class DrainError(Exception):
    """A step failed; the message is the reason handed to Chris."""


class DrainStop(Exception):
    """The loop cannot go on, and no ticket is at fault."""


class WorkerGone(DrainError):
    """The worker's herdr agent is gone and its build has no PR."""


def one_line(text, limit=300):
    return " ".join(str(text).split())[:limit]


def run(args, cwd=None, check=True):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    except OSError as exc:
        raise DrainError(f"{args[0]}: {exc}") from exc
    if check and out.returncode:
        raise DrainError(f"{' '.join(args[:3])} failed: {(out.stderr or out.stdout).strip()}")
    return out.stdout.strip()


def gh(*args):
    return run(["gh", *args])


def gh_json(*args):
    try:
        return frontier.gh_json(list(args))
    except frontier.FrontierError as exc:
        raise DrainError(str(exc)) from exc


def labels_of(issue):
    return {x["name"] for x in issue["labels"]}


def _kill(proc):
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()
    if proc.stdout:
        proc.stdout.close()


def run_group(cmd, cwd, timeout, out=None, preexec=None):
    """`(exit code, output)` of a command in its own process group, so the
    wall clock, ctrl-C and SIGTERM reach everything it started."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=out or subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True, preexec_fn=preexec)
    try:
        text, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(proc)
        raise DrainError(f"{cmd[0]} passed the {timeout}s wall clock")
    except BaseException:
        _kill(proc)
        raise
    return proc.returncode, text or ""


def _cap_session():
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_CAP_BYTES, MEMORY_CAP_BYTES))
    ctypes.CDLL(None).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG: die with drain


def origin_slug(root):
    url = run(["git", "config", "--get", "remote.origin.url"], cwd=root)
    m = _ORIGIN.search(url)
    if not m:
        raise DrainError(f"origin {url} is not a github.com repo")
    return f"{m.group(1)}/{m.group(2)}"


def read_frontier(ctx):
    """`(queue, waiting, stranded)`. `queue` is `[(number, title, kind)]`: the unblocked
    ready tickets and the clear spec parents, oldest first; the anchor is the
    first. A slice is neither: it is built inside its spec's run. `waiting` is
    the numbers of specs that have a ready slice and are not in the queue
    (not ready-for-agent, claimed, blocked), which drain cannot start.
    `stranded` is `[(number, why)]`: slices whose spec is closed or in another
    repo, which no spec run can build (#1485)."""
    issues = {}

    def fetch(r, label):
        got = frontier.fetch_issues(r, label)
        issues.update({i["number"]: i for i in got})
        return got

    try:
        buckets = frontier.frontier(ctx.repo, READY, fetch=fetch)
    except frontier.FrontierError as exc:
        raise DrainError(f"frontier: {exc}") from exc
    queue = [(t["number"], t["title"], kind) for kind, bucket in ((TICKET, "unblocked"), (SPEC, "spec"))
             for t in buckets[bucket]]
    queue = sorted((t for t in queue if HUMAN not in labels_of(issues[t[0]])), key=lambda t: t[0])
    waiting = {t["spec"] for t in buckets["slice"]} - {t[0] for t in queue}
    stranded = [(t["number"], t["why"]) for t in buckets["stranded"]]
    return queue, sorted(waiting), stranded


def pick(ctx):
    return read_frontier(ctx)[0]


def branch_of(n, kind):
    """The branch and workspace name `implement-dispatch` gives an anchor."""
    return f"{'spec' if kind == SPEC else 'implement'}-{n}"


def workspace_path(ctx, n, kind):
    return os.path.join(ctx.root, ".claude", "worktrees", branch_of(n, kind))


def anchors(ctx, queue):
    """The queue's tickets that may anchor a bundle: those with no kept
    workspace. A ticket drain handed to Chris keeps its workspace, and
    `implement-dispatch` refuses to start where one exists, so a re-readied one
    would stop every later run at it."""
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
    """The lock `implement-dispatch` holds around its own claims, so a burn
    dispatching at the same moment cannot claim the same ticket."""
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
        view = gh_json("issue", "view", str(anchor), "--repo", ctx.repo, "--json", "state,labels")
        if view["state"].lower() != "open" or READY not in labels_of(view) or CLAIMED in labels_of(view):
            return False
        gh("issue", "comment", str(anchor), "--repo", ctx.repo, "--body", f"{ANCHOR_NOTE} {branch_of(anchor, kind)}")
    return True


def resumable(ctx, ended):
    """`(number, kind)` of the lowest open in-progress ticket or spec whose
    latest drain comment is its anchor note, or `None`. A worker
    `implement-dispatch` started has none, and a ticket drain handed to Chris
    ends in `HANDED_NOTE`, so neither is taken.
    The open list can still carry a ticket just closed, so each candidate's
    state and labels are read again, and an anchor this run already took up
    (`ended`) is never taken twice."""
    try:
        claimed = frontier.fetch_issues(ctx.repo, CLAIMED)
    except frontier.FrontierError as exc:
        raise DrainError(f"frontier: {exc}") from exc
    for issue in sorted(claimed, key=lambda i: i["number"]):
        if issue["number"] in ended or HUMAN in labels_of(issue) or issue.get("pull_request"):
            continue
        view = gh_json("issue", "view", str(issue["number"]), "--repo", ctx.repo, "--json", "state,labels,comments")
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
    comments = gh_json("issue", "view", str(anchor), "--repo", ctx.repo, "--json", "comments")["comments"]
    start = max((i for i, c in enumerate(comments) if c["body"].startswith(ANCHOR_NOTE)), default=-1)
    return {int(x) for c in comments[start + 1:] if c["body"].strip().startswith(BUNDLE_NOTE)
            for x in re.findall(r"\d+", CANDIDATES.sub("", c["body"]))} - {anchor}


_PARENTS = {}  # (repo, number) -> parent number or None; a ticket's parent does not change mid-run


def parent_number(ctx, issue):
    """The number of the parent `issue` (a dict with `number` and `body`) names
    by the sub-issue link or a `Part of` line, or `None`. Read once per ticket:
    the idle wait asks every poll."""
    key = (ctx.repo, issue["number"])
    if key not in _PARENTS:
        try:
            parent = frontier.fetch_parent(ctx.repo, issue)
        except frontier.FrontierError as exc:
            raise DrainError(f"parent of #{issue['number']}: {exc}") from exc
        _PARENTS[key] = parent and parent["number"]
    return _PARENTS[key]


def is_slice_of(ctx, n, spec):
    """Whether ticket `n` (read live) has `spec` as its parent."""
    body = gh_json("issue", "view", str(n), "--repo", ctx.repo, "--json", "body")["body"]
    return parent_number(ctx, {"number": n, "body": body}) == spec


def claimed_slices(ctx, spec):
    """The in-progress tickets whose parent is `spec`: the slices its run holds.
    Read live, since the spec run claims them, not drain."""
    try:
        claimed = frontier.fetch_issues(ctx.repo, CLAIMED)
    except frontier.FrontierError as exc:
        raise DrainError(f"frontier: {exc}") from exc
    held = []
    for i in claimed:
        if i["number"] == spec or i.get("pull_request") or HUMAN in labels_of(i):
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
        view = gh_json("pr", "view", branch, "--repo", ctx.repo, "--json", "closingIssuesReferences")
        hint |= {r["number"] for r in view["closingIssuesReferences"]} - {anchor}
    held = []
    for n in sorted(hint):
        view = gh_json("issue", "view", str(n), "--repo", ctx.repo, "--json", "state,labels")
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
    out = subprocess.run(["herdr", "agent", "get", name], capture_output=True, text=True)
    body = {}
    for text in (out.stdout, out.stderr):  # herdr prints a result on stdout and an error on stderr
        with contextlib.suppress(ValueError):
            body = json.loads(text)
            break
    if out.returncode == 0 and "result" in body:
        return body["result"]["agent"]
    if body.get("error", {}).get("code") == "agent_not_found":
        return None
    raise DrainStop(f"herdr agent get {name} failed: {one_line(out.stderr or out.stdout, 150)}")


def agent_status(name):
    info = agent_info(name)
    return info and info["agent_status"]


def stop_worker(name):
    """Close the worker's pane, so a bundle handed to Chris does not keep working
    beside the next one. The workspace stays for inspection; the session's
    transcript stays with claude. Best effort: a worker already gone is fine."""
    with contextlib.suppress(DrainStop, KeyError):
        info = agent_info(name)
        if info:
            subprocess.run(["herdr", "pane", "close", info["pane_id"]], capture_output=True)


def excerpt(ctx, n):
    """A candidate's body and comments, read live and cut to `EXCERPT_CHARS`, so
    the chooser judges from text and the log shows what it judged from. A ticket
    that cannot be read says so: a blank excerpt would read as an empty ticket.
    A ticket unblocked by GitHub's native dependencies alone may have no body and
    no comments, and says so rather than rendering blank."""
    try:
        view = gh_json("issue", "view", str(n), "--repo", ctx.repo, "--json", "body,comments")
    except DrainError as exc:
        return f"(body not read: {one_line(exc, 80)})"
    text = " ".join([view["body"] or "", *(c["body"] or "" for c in view["comments"])])
    return one_line(text, EXCERPT_CHARS) or "(empty body, no comments)"


def chooser_prompt(anchor, others, bundle_max):
    """`others` is `(number, title, excerpt)` per candidate."""
    listing = "\n".join(f"- #{n} {title}: {text}" for n, title, text in others) or "- (none)"
    return (f"Bundle choice for an unattended run. #{anchor} is the anchor ticket to build next. Other unblocked "
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
    run rather than looping over one ticket. A failure after the claim (herdr
    failing once the workspace exists) leaves the claim and the workspace in
    place: that is this bundle's failed build, not the environment's."""
    which = ["--spec", str(bundle[0])] if kind == SPEC else [str(n) for n in bundle]
    out = subprocess.run(["implement-dispatch", "--repo", ctx.root, "--controller", CONTROLLER, *which],
                         capture_output=True, text=True)
    if out.returncode:
        reason = "implement-dispatch failed: " + one_line(out.stderr or out.stdout, 250)
        view = gh_json("issue", "view", str(bundle[0]), "--repo", ctx.repo, "--json", "labels")
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


def wait_for_worker(ctx, branch, agent, bundle, spec=None):
    """`"pr"` once the branch has an open PR and its worker has gone idle (or is
    gone), `"landed"` when it went idle with every ticket closed and no PR (the
    light tier lands on main itself). A worker idle or blocked with no PR past
    the grace, a vanished one with neither, and the wall clock are failed
    builds. A look that errors (`gh`, herdr) is tried again; `LOOK_ERRORS` in a
    row end the wait. `spec` is the spec number when the worker is a spec run:
    its wall clock is `SPEC_WALL_CLOCK_SECONDS`, and a slice worker at work
    restarts its idle grace."""
    limit = SPEC_WALL_CLOCK_SECONDS if spec else WALL_CLOCK_SECONDS
    deadline, stalled_since, errors = time.monotonic() + limit, None, 0
    while True:
        try:
            status = agent_status(agent)
            outcome, busy = None, False
            if status is None or status in IDLE:
                if open_pr(ctx, branch):
                    outcome = "pr"
                elif all(gh_json("issue", "view", str(n), "--repo", ctx.repo, "--json", "state")["state"].lower()
                         == "closed" for n in bundle):
                    outcome = "landed"
                elif status is None:
                    raise WorkerGone(f"the worker {agent} is gone and the build has no PR")
            if spec and not outcome and status is not None and (status in IDLE or status in STALLED):
                busy = slices_working(ctx, spec)
            errors = 0
        except WorkerGone:
            raise
        except (DrainError, DrainStop) as exc:
            errors += 1
            if errors >= LOOK_ERRORS:
                raise
        else:
            if outcome:
                return outcome
            if (status in IDLE or status in STALLED) and not busy:
                stalled_since = stalled_since or time.monotonic()
                if time.monotonic() - stalled_since >= IDLE_GRACE_SECONDS:
                    raise DrainError(f"the worker {agent} is {status} with no PR")
            else:
                stalled_since = None
        if time.monotonic() > deadline:
            raise DrainError(f"the worker {agent} passed the {limit}s wall clock")
        time.sleep(POLL_SECONDS)


def open_pr(ctx, branch):
    prs = gh_json("pr", "list", "--repo", ctx.repo, "--head", branch, "--state", "open", "--json", "number,url")
    return prs[0] if prs else None


def seam_cmd(ctx):
    return run(["git", "config", "land.testcmd"], cwd=ctx.root, check=False) or FULL_SEAM


def run_in_scratch_tree(ctx, cmd, log, head=None):
    """`cmd` in a throwaway worktree of current main, with `head` merged in when
    given. The merge commit uses the identity the repo is already configured
    with. A tree with a `package-lock.json` gets `npm ci` before `cmd`.
    Raises `DrainError` on a conflict or a non-zero exit."""
    scratch = tempfile.mkdtemp(prefix="drain-seam-")
    try:
        run(["git", "worktree", "add", "-q", "--detach", scratch, ctx.default], cwd=ctx.root)
        if head:
            merged = subprocess.run(["git", "merge", "--no-edit", head], cwd=scratch, capture_output=True, text=True)
            if merged.returncode:
                raise DrainError("merging the PR into current main failed: "
                                 + one_line(merged.stderr or merged.stdout, 200))
        with open(log, "w") as out:
            if os.path.exists(os.path.join(scratch, "package-lock.json")):
                # A bare worktree has no node_modules, so the declared
                # dependencies go in first (#1445).
                try:
                    code, _ = run_group(["npm", "ci"], scratch, WALL_CLOCK_SECONDS, out=out)
                except OSError as exc:
                    raise DrainError(f"`npm ci` could not start: {exc}") from exc
                if code:
                    raise DrainError(f"`npm ci` failed (output in {log})")
            code, _ = run_group(["sh", "-c", cmd], scratch, WALL_CLOCK_SECONDS, out=out)
        if code:
            raise DrainError(f"`{cmd}` failed (output in {log})")
    finally:
        run(["git", "worktree", "remove", "--force", scratch], cwd=ctx.root, check=False)


def seam(ctx, head, log):
    """The repo's seam (`land.testcmd`, else `bash tests/all.sh`) on the PR head
    merged into current main, in a throwaway worktree. The default seam is
    narrowed with `--changed <default>`: the PR's own diff is what it touched.
    Skipped when main is an ancestor of `head`: the worker ran the suite on that
    exact tree after merging main in, and only a main that has moved since can
    make two PRs break each other (#1415)."""
    cmd = seam_cmd(ctx)
    run(["git", "fetch", "-q", "origin"], cwd=ctx.root)
    moved = subprocess.run(["git", "merge-base", "--is-ancestor", ctx.default, head], cwd=ctx.root).returncode != 0
    if not moved:
        return
    if cmd == FULL_SEAM:
        cmd = f"{FULL_SEAM} --changed {shlex.quote(ctx.default)}"
    try:
        run_in_scratch_tree(ctx, cmd, log, head)
    except DrainError as exc:
        raise DrainError(f"seam {exc} on the PR merged into main") from exc


def repo_slug(ctx):
    """`owner__name`: the repo as one file-name component."""
    return ctx.repo.replace("/", "__")


def last_green_path(ctx):
    return os.path.join(ctx.log_dir, "last-green-" + repo_slug(ctx))


def full_run(ctx, merged):
    """One full run of the seam on current main after the last bundle. `None`
    when green, else the reason to stop, naming the merges since the last green
    full run: the commits on main since it when its sha is on record, else this
    run's merges."""
    run(["git", "fetch", "-q", "origin"], cwd=ctx.root)
    tip = run(["git", "rev-parse", ctx.default], cwd=ctx.root)
    try:
        run_in_scratch_tree(ctx, seam_cmd(ctx), os.path.join(ctx.log_dir, "full-suite.log"))
    except DrainError as exc:
        since = [f"{m['pr']} ({m['sha']})" for m in merged]
        try:
            with open(last_green_path(ctx)) as f:
                last = f.read().strip()
            listed = run(["git", "log", "--first-parent", "--format=%h %s", f"{last}..{tip}"], cwd=ctx.root)
            since = listed.splitlines() or since
        except (OSError, DrainError):
            pass
        return (f"the full suite is red on main after this run ({one_line(exc, 150)}). Merges since the last "
                "green full run: " + "; ".join(since))
    with open(last_green_path(ctx), "w") as f:
        f.write(tip + "\n")
    return None


def verify_pr(ctx, branch, anchor, kind):
    view = gh_json("pr", "view", branch, "--repo", ctx.repo, "--json",
                   "isDraft,mergeStateStatus,headRefOid,number,url,closingIssuesReferences")
    if view["isDraft"]:
        raise DrainError(f"{view['url']} is still a draft")
    if view["mergeStateStatus"] != "CLEAN":
        raise DrainError(f"{view['url']} is {view['mergeStateStatus']}, not CLEAN")
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
    seam(ctx, view["headRefOid"], os.path.join(ctx.log_dir, f"{branch}-seam.log"))
    view["closes"] = sorted(closed)
    return view


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


def finish_landed(ctx, branch, tickets):
    """The light tier landed on main itself, with no PR: `merge-cleanup` is all
    that is left, the controller's step in a burn."""
    notes = cleanup_notes(ctx, branch)
    try:
        run(["git", "fetch", "-q", "origin"], cwd=ctx.root)
        sha = run(["git", "rev-parse", ctx.default], cwd=ctx.root)
    except DrainError as exc:
        sha = "unread"
        notes.append(f"main's sha unread: {one_line(exc, 100)}")
    return {"tickets": tickets, "pr": "(landed on main, no PR)", "sha": sha, "note": "; ".join(notes)}


def finish(ctx, anchor, branch, view, kind):
    """After the merge: the squash sha, `merge-cleanup`, and the tickets the
    agent claimed that the PR did not close back to the queue. A step that
    fails is a note on a merged PR, never a reason to build again."""
    notes, sha = [], view["headRefOid"]
    try:
        sha = gh_json("pr", "view", str(view["number"]), "--repo", ctx.repo, "--json", "mergeCommit")["mergeCommit"]["oid"]
    except (DrainError, KeyError, TypeError) as exc:
        notes.append(f"squash sha unread, head shown: {one_line(exc, 100)}")
    notes += cleanup_notes(ctx, branch)
    try:
        for n in set(bundle_of(ctx, anchor, branch, kind)) - set(view["closes"]):
            gh("issue", "edit", str(n), "--repo", ctx.repo, "--remove-label", CLAIMED, "--add-label", READY,
               "--remove-assignee", "@me")
    except DrainError as exc:
        notes.append("releasing unclosed tickets failed: " + one_line(exc, 150))
    return {"tickets": view["closes"], "pr": view["url"], "sha": sha, "note": "; ".join(notes)}


def nudge_text(reason, pr_up, kind):
    head = "Unattended run, no controller: "
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
    if agent_status(agent) is None:
        raise WorkerGone(f"the worker {agent} is gone; nothing to prompt")
    code, text = run_group(["herdr", "agent", "prompt", agent, nudge_text(reason, bool(open_pr(ctx, branch)), kind),
                            "--wait", "--until", "working", "--until", "blocked", "--timeout", "30000"],
                           ctx.root, 60)
    if code:
        raise DrainError(f"herdr agent prompt {agent} failed: {one_line(text, 150)}")


def say(text):
    """One progress line, flushed: `job-run` copies drain's stdout into the run's
    progress file, and a buffered line would reach it only at exit."""
    print(text, flush=True)


def title_of(ctx, n):
    try:
        return one_line(gh_json("issue", "view", str(n), "--repo", ctx.repo, "--json", "title")["title"], 100)
    except (DrainError, KeyError, TypeError):
        return "(title unread)"


def announce(ctx, anchor, tickets, kind):
    """The `bundle started:` line: every ticket with its title and the worker's
    herdr pane, said the moment the bundle's worker exists."""
    say("bundle started: " + "; ".join(f"#{n} {title_of(ctx, n)}" for n in tickets)
        + f"  pane {agent_name(ctx, anchor, kind)}")


def work(ctx, anchor, others, resumed, started, kind):
    """`(merge result, None)` or `(None, the second failure's one-line reason)`;
    appends the bundle's tickets to `started` once its worker exists.
    Attempt 1 starts the worker (a resumed run finds it or its PR already
    there); attempt 2 prompts the same worker with the first failure's reason,
    since its workspace exists and a second dispatch would refuse it."""
    branch, agent, reason, bundle = branch_of(anchor, kind), agent_name(ctx, anchor, kind), "", [anchor]
    # The worker's branch and agent are named for the lowest ticket in the
    # clump, so every ticket bundled with the anchor is a higher number.
    others = [t for t in others if t[0] > anchor]
    for attempt in (1, 2):
        try:
            if attempt == 2:
                nudge(ctx, agent, branch, reason, kind)
            elif not resumed:
                if kind == TICKET:  # a spec's slices are its bundle: nothing to choose
                    bundle, why = choose_bundle(ctx, anchor, others, os.path.join(ctx.log_dir, f"{repo_slug(ctx)}-{branch}-choose.log"))
                    if why:
                        gh("issue", "comment", str(anchor), "--repo", ctx.repo, "--body",
                           f"{CHOOSER_NOTE} #{anchor} alone: {why}")
                    gh("issue", "comment", str(anchor), "--repo", ctx.repo, "--body",
                       f"{BUNDLE_NOTE} {' '.join(str(n) for n in bundle)} {count_note(len(others))}")
                dispatch(ctx, bundle, kind)
            tickets = [anchor] + (sorted(noted(ctx, anchor)) if kind == TICKET else [])
            if attempt == 1:
                announce(ctx, anchor, tickets, kind)
                started[:] = tickets
            if wait_for_worker(ctx, branch, agent, tickets, spec=anchor if kind == SPEC else None) == "landed":
                return finish_landed(ctx, branch, tickets), None
            view = verify_pr(ctx, branch, anchor, kind)
            gh("pr", "merge", str(view["number"]), "--squash", "--match-head-commit", view["headRefOid"],
               "--repo", ctx.repo)
        except DrainError as exc:
            reason = one_line(exc)
            if not started:  # a failure before the announce (a dispatch that failed after the claim): the bundle was still worked
                announce(ctx, anchor, bundle, kind)
                started[:] = bundle
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
        gh("issue", "edit", str(n), "--repo", ctx.repo, "--remove-label", CLAIMED, "--add-label", HUMAN,
           "--remove-assignee", "@me")
        gh("issue", "comment", str(n), "--repo", ctx.repo, "--body",
           f"{HANDED_NOTE} this ticket (bundle {' '.join(f'#{x}' for x in bundle)}) after two attempts. "
           f"Last failure: {reason} The worktree {branch} is kept for inspection and its worker's "
           "pane is closed; drain skips this ticket until that worktree is removed.")
    return bundle


def drain(ctx, limit):
    """`(merged, handed, stop reason or None)`; `limit` counts tickets."""
    merged, handed, stop, failures, done, want = [], [], None, 0, 0, ctx.want
    started = []  # the tickets of a bundle whose start line is out and whose end line is not
    told = set()  # stranded slices already named this run (#1485)
    ended = set()  # the anchors this run has taken up: added before `work()`, so none is taken twice
    try:
        if want:  # refuse before any work, and not only when the loop gets there
            put_first(anchors(ctx, pick(ctx)), want)
        while done < limit:
            taken = resumable(ctx, ended)
            resumed, others = taken is not None, []
            if resumed:
                anchor, kind = taken
            else:
                queue, waiting, stranded = read_frontier(ctx)
                for n, why in stranded:
                    if n not in told:  # every exit names them, once
                        told.add(n)
                        say(f"stranded: #{n}, {why}")
                candidates = anchors(ctx, queue)
                if not candidates:
                    for spec in waiting:
                        say(f"waiting: ready slices of spec #{spec}, which drain cannot start (it is not "
                            "ready-for-agent, is claimed, or is blocked)")
                    break
                if want:
                    if not any(t[0] == want for t in candidates):
                        raise DrainStop(f"--anchor #{want} left the ready queue before drain reached it")
                    candidates, want = put_first(candidates, want), None
                anchor, _, kind = candidates[0]
                others = [(n, title) for n, title, k in queue if k == TICKET and n != anchor]
                if not note_anchor(ctx, anchor, kind):
                    continue
            ended.add(anchor)
            result, reason = work(ctx, anchor, others, resumed, started, kind)
            if result:
                say(f"bundle ended: {' '.join(f'#{n}' for n in result['tickets'])}  merged  {result['pr']}  "
                    f"{result['sha']}")
                started.clear()
                merged.append(result)
                done, failures = done + len(result["tickets"]), 0
            else:
                bundle = hand_to_chris(ctx, anchor, reason, kind)
                say(f"bundle ended: {' '.join(f'#{n}' for n in bundle)}  handed to Chris: {reason}")
                started.clear()
                handed.append((bundle, reason))
                done, failures = done + len(bundle), failures + 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    stop = (f"{failures} bundles in a row went to Chris; the environment is the likelier "
                            f"cause (auth, quota, herdr, implement-dispatch). Check `herdr agent list` and the "
                            f"logs in {ctx.log_dir}.")
                    break
    except (DrainStop, DrainError) as exc:  # a refusal or a tracker failure, said as it is
        stop = str(exc)
    except Exception as exc:  # noqa: BLE001 - the summary of what landed must still print
        stop = f"unexpected {type(exc).__name__}: {one_line(exc)}"
    if started:
        say(f"bundle ended: {' '.join(f'#{n}' for n in started)}  stopped: {stop}")
    if merged:
        try:
            red = full_run(ctx, merged)
        except Exception as exc:  # noqa: BLE001 - the summary of what landed must still print
            red = f"the full suite could not run on main: {type(exc).__name__}: {one_line(exc, 150)}"
        stop = "; ".join(x for x in (stop, red) if x) or None
    return merged, handed, stop


def summary(merged, handed, stop):
    lines = []
    if merged:
        lines += ["merged:"] + [f"  {' '.join(f'#{n}' for n in m['tickets'])}  {m['pr']}  {m['sha']}"
                                 + (f"  ({m['note']})" if m["note"] else "") for m in merged]
    if handed:
        lines += ["handed to Chris:"] + [f"  {' '.join(f'#{n}' for n in b)}  {r}" for b, r in handed]
    if stop:
        lines.append(f"stopped: {stop}")
    return "\n".join(lines or ["nothing to drain"])


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
        common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=args.repo)
        root = os.path.dirname(common)
        repo = origin_slug(root)
        login = gh("api", "user", "--jq", ".login")
        if repo.split("/")[0] != login:
            raise DrainError(f"{repo} is not owned by {login}; drain only runs on the caller's own repos")
        default = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=root)
        log_dir = os.environ.get("DRAIN_LOG_DIR") or os.path.expanduser("~/.cache/drain")
        os.makedirs(log_dir, exist_ok=True)
    except DrainError as exc:
        print(f"drain.py: {exc}", file=sys.stderr)
        return 1
    limit = 1 if args.once else (args.max or sys.maxsize)
    merged, handed, stop = drain(Ctx(root, repo, default, log_dir, args.bundle_max, args.anchor), limit)
    say(summary(merged, handed, stop))
    return 1 if stop else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
