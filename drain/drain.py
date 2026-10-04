#!/usr/bin/env python3
"""`drain.py [--repo <path>] [--once] [--max <n>] [--bundle-max <k>] [--anchor <n>]`:
work the `ready-for-agent` queue unattended, serially, one PR at a time (#1403).

The **anchor** is the oldest unblocked ready ticket (`burndown/frontier.py`),
or, for the first bundle only, the ticket `--anchor <n>` names (refused unless
`<n>` is open, ready and unblocked).
`drain` claims it, leaves a `drain anchor:` comment, and starts one headless
`claude -p` session in a worktree on `implement-<anchor>`, handing it the
anchor and the number and title of every other unblocked ready ticket. The
agent chooses the **bundle**: the others it would naturally fix in the same
PR (at most `--bundle-max` tickets in all). It claims each, records them in a
`drain bundle:` comment on the anchor, and closes every one in one PR with one
review wave. `drain` does no directory or closure grouping, and always asks
for the heavy tier. `--max` stops the loop after that many tickets (a bundle
counts all of its tickets); `--once` stops after one bundle.

Then it checks (the PR is not draft, CLEAN, closes the anchor within the
bundle cap, and the repo's seam passes on the PR merged into current main,
narrowed to what the PR touched; the check is skipped when main has not moved
past the PR's base, because the worker ran the same suite on that exact tree),
squash-merges, runs `merge-cleanup`, and returns any ticket the agent claimed
but the PR did not close to the queue. A bundle that fails is built once more
in the same worktree; a second failure labels the anchor and every claimed
ticket `ready-for-human` with a one-line comment, keeps the worktree, and the
loop moves on. Two bundles in a row handed to Chris stop the loop instead: that
is the environment failing (auth, quota, the permission mode, headless
`/implement`), not the tickets.

State lives in GitHub and git, nowhere else. An open, in-progress ticket
carrying drain's own `drain anchor:` comment is resumed (a worker started by
`implement-dispatch` has none, so it is never taken), an open PR is checked
rather than rebuilt, and a process still running in the worktree stops the
run. The worktree setup is `implement-dispatch`'s steps without herdr, which
that command cannot skip; the commit-identity guard it installs is a
precondition here, not reinstalled. Only repos whose origin owner is the
`gh` login.

After the last bundle, one full `bash tests/all.sh` runs on current main (#1415):
a red one stops the run and the summary names the merges since the last green
full run (`last-green-<repo>` in the log directory), for Chris.

Each build runs in a herdr pane, so `herdr agent list` shows it as
`<repo-short>-drain-<anchor>` while it works, and `claude -p` streams
`stream-json` into the pane and the build log as it happens. Without herdr on
PATH the build is a bare subprocess streaming the same output into the log. A
SIGKILL of drain leaves the pane's session running (nothing in the pane can
know); the rerun's `busy()` check then stops on it.
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
import shutil
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "burndown"))

import frontier  # noqa: E402

READY, HUMAN, CLAIMED = "ready-for-agent", "ready-for-human", frontier.CLAIMED_LABEL
ANCHOR_NOTE, BUNDLE_NOTE, HANDED_NOTE = "drain anchor:", "drain bundle:", "drain could not land"
BUNDLE_MAX = 8
MAX_CONSECUTIVE_FAILURES = 2
# The caps of one build session, stated here and nowhere else: the equivalent
# of `ulimit -v 32G` (address space, not resident memory, hence generous) and a
# three-hour wall clock after which the whole process group is killed. The seam
# gets the same wall clock. TERM and ctrl-C kill the build's whole group;
# SIGKILL of drain kills only the session itself (PR_SET_PDEATHSIG), and the
# rerun's `busy()` check then stops on whatever it left running.
MEMORY_CAP_BYTES = 32 << 30
WALL_CLOCK_SECONDS = 3 * 60 * 60
# Never a permission-skipping flag: the session runs in the mode the harness
# already trusts for unattended work. Unverified that `/implement` completes
# under it headless (#1403 asks for that check): a refusal shows as a failed
# build, and the consecutive-failure stop keeps it from emptying the queue.
PERMISSION_MODE = "auto"
# `claude -p` prints nothing until it exits unless asked to stream: the log of a
# build stays empty for hours otherwise (#1415).
STREAM_ARGS = ["--output-format", "stream-json", "--verbose"]
FULL_SEAM = "bash tests/all.sh"
PANE_POLL_SECONDS = 0.2
# The hook files `implement-dispatch` installs (`install_identity_guard` in
# flow/lane/src/bin/implement_dispatch.rs); drain refuses to run without them.
GUARD_HOOKS = ("pre-commit", "pre-push", "commit-identity-guard", "commit-identity-guard-pre-push")
_ORIGIN = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")

Ctx = collections.namedtuple("Ctx", "root repo default log_dir bundle_max want", defaults=(None,))


class DrainError(Exception):
    """A step failed; the message is the reason handed to Chris."""


class DrainStop(Exception):
    """The loop cannot go on, and no ticket is at fault."""


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


def require_guard(ctx):
    hooks = run(["git", "rev-parse", "--path-format=absolute", "--git-path", "hooks"], cwd=ctx.root)
    missing = [h for h in GUARD_HOOKS if not os.access(os.path.join(hooks, h), os.X_OK)]
    if missing:
        raise DrainError(f"the commit-identity guard is not installed in {ctx.root} ({', '.join(missing)} "
                         "missing); run implement-dispatch once in this repo, then rerun")


def pick(ctx):
    """`[(number, title)]`: the unblocked ready queue, oldest first; the
    anchor is the first."""
    issues = {}

    def fetch(r, label):
        got = frontier.fetch_issues(r, label)
        issues.update({i["number"]: i for i in got})
        return got

    try:
        queue = frontier.frontier(ctx.repo, READY, fetch=fetch)["unblocked"]
    except frontier.FrontierError as exc:
        raise DrainError(f"frontier: {exc}") from exc
    return [(t["number"], t["title"]) for t in queue if HUMAN not in labels_of(issues[t["number"]])]


def put_first(queue, want):
    """`queue` with ticket `want` first; refused when it is not in it. The
    queue is the unblocked ready tickets, so `want` is open, ready and unblocked
    exactly when it is there."""
    chosen = [t for t in queue if t[0] == want]
    if not chosen:
        raise DrainError(f"--anchor #{want} is not an open, ready, unblocked ticket (not in the ready queue)")
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


def claim(ctx, anchor):
    """True when this run claimed the anchor, False when another claim took it
    since the pick (read again under the lock, as `implement-dispatch` does)."""
    with claim_lock(ctx):
        view = gh_json("issue", "view", str(anchor), "--repo", ctx.repo, "--json", "state,labels")
        if view["state"].lower() != "open" or READY not in labels_of(view) or CLAIMED in labels_of(view):
            return False
        # The note first: a kill between the two leaves a ready ticket with a
        # stray note, which the next pick simply claims again; the other order
        # leaves an in-progress ticket no rerun resumes and no pick offers.
        gh("issue", "comment", str(anchor), "--repo", ctx.repo, "--body", f"{ANCHOR_NOTE} implement-{anchor}")
        gh("issue", "edit", str(anchor), "--repo", ctx.repo, "--remove-label", READY,
           "--add-label", CLAIMED, "--add-assignee", "@me")
    return True


def resumable(ctx):
    """The lowest open in-progress ticket whose latest drain comment is its
    anchor note, or `None`. A worker `implement-dispatch` started has none, and
    a ticket drain handed to Chris ends in `HANDED_NOTE`, so neither is taken."""
    try:
        claimed = frontier.fetch_issues(ctx.repo, CLAIMED)
    except frontier.FrontierError as exc:
        raise DrainError(f"frontier: {exc}") from exc
    for issue in sorted(claimed, key=lambda i: i["number"]):
        if HUMAN in labels_of(issue) or issue.get("pull_request"):
            continue
        view = gh_json("issue", "view", str(issue["number"]), "--repo", ctx.repo, "--json", "comments")
        marks = [c["body"] for c in view["comments"] if c["body"].startswith((ANCHOR_NOTE, HANDED_NOTE))]
        if marks and marks[-1].startswith(ANCHOR_NOTE):
            return issue["number"]
    return None


def noted(ctx, anchor):
    """The numbers in `drain bundle:` comments posted after the anchor's latest
    claim: what the agent says it took. Digits are read with `findall`, so a
    note that wraps lines or ends in punctuation still parses."""
    comments = gh_json("issue", "view", str(anchor), "--repo", ctx.repo, "--json", "comments")["comments"]
    start = max((i for i, c in enumerate(comments) if c["body"].startswith(ANCHOR_NOTE)), default=-1)
    return {int(x) for c in comments[start + 1:] if c["body"].strip().startswith(BUNDLE_NOTE)
            for x in re.findall(r"\d+", c["body"])} - {anchor}


def bundle_of(ctx, anchor, branch):
    """The anchor plus the tickets it is still holding: those the agent named
    and those an open PR closes, each read live, so a closed, human-held or
    unclaimed one is not the bundle's."""
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


def workspace(ctx, branch):
    path = os.path.join(ctx.root, ".claude", "worktrees", branch)
    if os.path.isdir(path):
        return path
    run(["git", "fetch", "-q", "origin"], cwd=ctx.root)
    if run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=ctx.root, check=False):
        run(["git", "worktree", "add", "-q", path, branch], cwd=ctx.root)
    else:
        remote = f"origin/{branch}"
        base = remote if run(["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}"],
                             cwd=ctx.root, check=False) else ctx.default
        run(["git", "worktree", "add", "-q", "--no-track", "-b", branch, path, base], cwd=ctx.root)
    return path


def busy(path):
    """Whether any process has `path` as its working directory."""
    for pid in os.listdir("/proc"):
        if pid.isdigit() and int(pid) != os.getpid():
            with contextlib.suppress(OSError):
                cwd = os.readlink(f"/proc/{pid}/cwd")
                if cwd == path or cwd.startswith(path + os.sep):
                    return True
    return False


def brief(anchor, others, bundle_max):
    """The prompt: `/implement` on the anchor, then the agent's bundle choice."""
    listing = "\n".join(f"- #{n} {title}" for n, title in others) or "- (none)"
    return (f"/implement {anchor} --tier heavy\n\n"
            "Unattended run, no controller: send no messages. Fix every valid review finding in the PR "
            "and file no leftover or sweep ticket (docs/adr/0004-workers-fix-their-own-findings.md).\n\n"
            f"Bundle: #{anchor} is the anchor. Other unblocked ready tickets:\n{listing}\n"
            f"Read the ones that look related and add those you would naturally fix in the same PR, "
            f"at most {bundle_max} tickets in all with the anchor. First post one comment on "
            f"#{anchor} reading `{BUNDLE_NOTE} <numbers, anchor first>`, then claim each ticket you add "
            f"(`gh issue edit <n> --remove-label {READY} --add-label {CLAIMED} --add-assignee @me`). Then build "
            "them as one clump (implement/SKILL.md § The brief), working one ticket at a time: test first, "
            "green, one commit per ticket before the next. If you run out of context or time partway, the "
            f"PR closes only the finished tickets and you relabel the rest `{READY}` with `{CLAIMED}` and "
            "your assignee removed. The bundle gets one review wave: its spec axis receives every ticket "
            "and checks each one's acceptance criteria.")


def herdr_usable():
    return shutil.which("herdr") is not None and subprocess.run(
        ["herdr", "status", "--json"], capture_output=True).returncode == 0


def herdr_json(*args):
    out = subprocess.run(["herdr", *args], capture_output=True, text=True)
    if out.returncode:
        raise DrainError(f"herdr {args[0]} {args[1]} failed: {one_line(out.stderr or out.stdout, 150)}")
    return json.loads(out.stdout)["result"]


def pane_session(path, prompt, log, name):
    """The build in a herdr pane named `name`. The pane runs a launcher script
    (so the prompt never passes through a shell string) that tees the session's
    stream into `log` and leaves its exit status in `<log>.exit`; this waits
    for that file under the wall clock. The workspace is closed on every way
    out, which takes the session with it."""
    exit_file = log + ".exit"
    for stale in (exit_file, log):
        with contextlib.suppress(FileNotFoundError):
            os.remove(stale)
    with open(log + ".prompt", "w") as f:
        f.write(prompt)
    claude = " ".join(shlex.quote(a) for a in ["--permission-mode", PERMISSION_MODE, *STREAM_ARGS])
    with open(log + ".sh", "w") as f:
        f.write(f"#!/bin/bash\ncd {shlex.quote(path)} || exit 97\nulimit -v {MEMORY_CAP_BYTES >> 10}\n"
                f"claude -p \"$(cat {shlex.quote(log + '.prompt')})\" {claude} 2>&1 | tee {shlex.quote(log)}\n"
                f"echo ${{PIPESTATUS[0]}} > {shlex.quote(exit_file + '.tmp')}\n"
                f"mv {shlex.quote(exit_file + '.tmp')} {shlex.quote(exit_file)}\n")
    workspace_id = None
    try:
        made = herdr_json("workspace", "create", "--cwd", path, "--label", name, "--no-focus")
        workspace_id, pane = made["workspace"]["workspace_id"], made["root_pane"]["pane_id"]
        run(["herdr", "pane", "run", pane, "bash", log + ".sh"])  # prints nothing on success
        named, deadline = False, time.monotonic() + WALL_CLOCK_SECONDS
        while True:
            if not named:  # the pane becomes an agent once herdr sees `claude` start
                named = subprocess.run(["herdr", "agent", "rename", pane, name], capture_output=True).returncode == 0
            if os.path.exists(exit_file):
                break
            if time.monotonic() > deadline:
                raise DrainError(f"claude passed the {WALL_CLOCK_SECONDS}s wall clock")
            time.sleep(PANE_POLL_SECONDS)
        return int(read_text(exit_file).strip() or 1)
    finally:
        if workspace_id:
            subprocess.run(["herdr", "workspace", "close", workspace_id], capture_output=True)


def read_text(path):
    with open(path) as f:
        return f.read()


def build(path, prompt, log, name=None):
    """One headless session running `/implement`, streaming into `log`; a
    non-zero exit or the wall clock is a failed build. With a `name` and a
    usable herdr it runs in a pane of that name, else as a bare subprocess."""
    if busy(path):
        raise DrainStop(f"a process is still running in {path}; rerun when it exits")
    if name and herdr_usable():
        code = pane_session(path, prompt, log, name)
    else:
        with open(log, "w") as out:
            code, _ = run_group(["claude", "-p", prompt, "--permission-mode", PERMISSION_MODE, *STREAM_ARGS], path,
                                WALL_CLOCK_SECONDS, out=out, preexec=_cap_session)
    if code:
        raise DrainError(f"build exited {code} (log {log})")


def open_pr(ctx, branch):
    prs = gh_json("pr", "list", "--repo", ctx.repo, "--head", branch, "--state", "open", "--json", "number,url")
    return prs[0] if prs else None


def seam_cmd(ctx):
    return run(["git", "config", "land.testcmd"], cwd=ctx.root, check=False) or FULL_SEAM


def run_in_scratch_tree(ctx, cmd, log, head=None):
    """`cmd` in a throwaway worktree of current main, with `head` merged in when
    given. The merge commit uses the identity the repo is already configured
    with. Raises `DrainError` on a conflict or a non-zero exit."""
    scratch = tempfile.mkdtemp(prefix="drain-seam-")
    try:
        run(["git", "worktree", "add", "-q", "--detach", scratch, ctx.default], cwd=ctx.root)
        if head:
            merged = subprocess.run(["git", "merge", "--no-edit", head], cwd=scratch, capture_output=True, text=True)
            if merged.returncode:
                raise DrainError("merging the PR into current main failed: "
                                 + one_line(merged.stderr or merged.stdout, 200))
        with open(log, "w") as out:
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


def last_green_path(ctx):
    return os.path.join(ctx.log_dir, "last-green-" + ctx.repo.replace("/", "__"))


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
            last = read_text(last_green_path(ctx)).strip()
            listed = run(["git", "log", "--first-parent", "--format=%h %s", f"{last}..{tip}"], cwd=ctx.root)
            since = listed.splitlines() or since
        except (OSError, DrainError):
            pass
        return (f"the full suite is red on main after this run ({one_line(exc, 150)}). Merges since the last "
                "green full run: " + "; ".join(since))
    with open(last_green_path(ctx), "w") as f:
        f.write(tip + "\n")
    return None


def verify_pr(ctx, branch, anchor):
    view = gh_json("pr", "view", branch, "--repo", ctx.repo, "--json",
                   "isDraft,mergeStateStatus,headRefOid,number,url,closingIssuesReferences")
    if view["isDraft"]:
        raise DrainError(f"{view['url']} is still a draft")
    if view["mergeStateStatus"] != "CLEAN":
        raise DrainError(f"{view['url']} is {view['mergeStateStatus']}, not CLEAN")
    closed = {r["number"] for r in view["closingIssuesReferences"]}
    if anchor not in closed:
        raise DrainError(f"{view['url']} does not close the anchor #{anchor}")
    unrecorded = closed - {anchor} - noted(ctx, anchor)
    if unrecorded:
        raise DrainError(f"{view['url']} closes " + ", ".join(f"#{n}" for n in sorted(unrecorded))
                         + f" which no {BUNDLE_NOTE} comment on #{anchor} names")
    if len(closed) > ctx.bundle_max:
        raise DrainError(f"{view['url']} closes {len(closed)} tickets, over --bundle-max {ctx.bundle_max}")
    seam(ctx, view["headRefOid"], os.path.join(ctx.log_dir, f"{branch}-seam.log"))
    view["closes"] = sorted(closed)
    return view


def finish(ctx, anchor, branch, view):
    """After the merge: the squash sha, `merge-cleanup`, and the tickets the
    agent claimed that the PR did not close back to the queue. A step that
    fails is a note on a merged PR, never a reason to build again."""
    notes, sha = [], view["headRefOid"]
    try:
        sha = gh_json("pr", "view", str(view["number"]), "--repo", ctx.repo, "--json", "mergeCommit")["mergeCommit"]["oid"]
    except (DrainError, KeyError, TypeError) as exc:
        notes.append(f"squash sha unread, head shown: {one_line(exc, 100)}")
    try:
        cleanup = subprocess.run(["merge-cleanup", "--repo", ctx.root, branch], capture_output=True, text=True)
        if cleanup.returncode:
            notes.append("merge-cleanup failed: " + one_line(cleanup.stderr or cleanup.stdout, 150))
    except OSError as exc:
        notes.append(f"merge-cleanup: {exc}")
    try:
        for n in set(bundle_of(ctx, anchor, branch)) - set(view["closes"]):
            gh("issue", "edit", str(n), "--repo", ctx.repo, "--remove-label", CLAIMED, "--add-label", READY,
               "--remove-assignee", "@me")
    except DrainError as exc:
        notes.append("releasing unclosed tickets failed: " + one_line(exc, 150))
    return {"tickets": view["closes"], "pr": view["url"], "sha": sha, "note": "; ".join(notes)}


def work(ctx, anchor, others, resumed):
    """`(merge result, None)` or `(None, the second failure's one-line reason)`."""
    branch, prompt, reason = f"implement-{anchor}", brief(anchor, others, ctx.bundle_max), ""
    for attempt in (1, 2):
        try:
            path = workspace(ctx, branch)
            if not (resumed and attempt == 1 and open_pr(ctx, branch)):
                build(path, prompt, os.path.join(ctx.log_dir, f"{branch}-{attempt}.log"),
                      name=f"{os.path.basename(ctx.root)}-drain-{anchor}")
            if not open_pr(ctx, branch):
                raise DrainError("the build ended with no open PR")
            view = verify_pr(ctx, branch, anchor)
            gh("pr", "merge", str(view["number"]), "--squash", "--match-head-commit", view["headRefOid"],
               "--repo", ctx.repo)
        except DrainError as exc:
            reason = one_line(exc)
        else:
            return finish(ctx, anchor, branch, view), None
    return None, reason


def hand_to_chris(ctx, anchor, reason):
    bundle = bundle_of(ctx, anchor, f"implement-{anchor}")
    for n in bundle:
        gh("issue", "edit", str(n), "--repo", ctx.repo, "--remove-label", CLAIMED, "--add-label", HUMAN,
           "--remove-assignee", "@me")
        gh("issue", "comment", str(n), "--repo", ctx.repo, "--body",
           f"{HANDED_NOTE} this ticket (bundle {' '.join(f'#{x}' for x in bundle)}) after two attempts. "
           f"Last failure: {reason} The worktree implement-{anchor} is kept for inspection.")
    return bundle


def drain(ctx, limit):
    """`(merged, handed, stop reason or None)`; `limit` counts tickets."""
    merged, handed, stop, failures, done, want = [], [], None, 0, 0, ctx.want
    try:
        require_guard(ctx)
        if want:  # refuse before any work, and not only when the loop gets there
            put_first(pick(ctx), want)
        while done < limit:
            anchor = resumable(ctx)
            resumed, others = anchor is not None, []
            if not resumed:
                queue = pick(ctx)
                if not queue:
                    break
                if want:
                    queue, want = put_first(queue, want) if any(t[0] == want for t in queue) else queue, None
                anchor, others = queue[0][0], queue[1:]
                if not claim(ctx, anchor):
                    continue
            result, reason = work(ctx, anchor, others, resumed)
            if result:
                merged.append(result)
                done, failures = done + len(result["tickets"]), 0
            else:
                bundle = hand_to_chris(ctx, anchor, reason)
                handed.append((bundle, reason))
                done, failures = done + len(bundle), failures + 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    stop = (f"{failures} bundles in a row went to Chris; the environment is the likelier "
                            "cause (auth, quota, permission mode, headless /implement). Check the build logs.")
                    break
    except (DrainStop, DrainError) as exc:  # a refusal or a tracker failure, said as it is
        stop = str(exc)
    except Exception as exc:  # noqa: BLE001 - the summary of what landed must still print
        stop = f"unexpected {type(exc).__name__}: {one_line(exc)}"
    if merged:
        try:
            red = full_run(ctx, merged)
        except (DrainError, OSError) as exc:
            red = f"the full suite could not run on main: {one_line(exc, 150)}"
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
        root = run(["git", "rev-parse", "--show-toplevel"], cwd=args.repo)
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
    print(summary(merged, handed, stop))
    return 1 if stop else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
