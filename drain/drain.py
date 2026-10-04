#!/usr/bin/env python3
"""`drain.py [--repo <path>] [--once] [--max <n>] [--bundle-max <k>]`: work the
`ready-for-agent` queue unattended, serially, one PR at a time (#1403).

The **anchor** is the oldest unblocked ready ticket (`burndown/frontier.py`).
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
bundle cap, and the repo's seam passes on the PR merged into current main),
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
"""
import argparse
import collections
import contextlib
import ctypes
import fcntl
import os
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "burndown"))

import frontier  # noqa: E402

READY, HUMAN, CLAIMED = "ready-for-agent", "ready-for-human", frontier.CLAIMED_LABEL
ANCHOR_NOTE, BUNDLE_NOTE = "drain anchor:", "drain bundle:"
BUNDLE_MAX = 8
MAX_CONSECUTIVE_FAILURES = 2
# The caps of one build session, stated here and nowhere else: the equivalent
# of `ulimit -v 32G` (address space, not resident memory, hence generous) and a
# three-hour wall clock after which the whole process group is killed. The seam
# gets the same wall clock. A killed drain takes its build with it
# (PR_SET_PDEATHSIG, and a TERM/INT handler that kills the group).
MEMORY_CAP_BYTES = 32 << 30
WALL_CLOCK_SECONDS = 3 * 60 * 60
# Never a permission-skipping flag: the session runs in the mode the harness
# already trusts for unattended work. Unverified that `/implement` completes
# under it headless (#1403 asks for that check): a refusal shows as a failed
# build, and the consecutive-failure stop keeps it from emptying the queue.
PERMISSION_MODE = "auto"
# The hook files `implement-dispatch` installs (`install_identity_guard` in
# flow/lane/src/bin/implement_dispatch.rs); drain refuses to run without them.
GUARD_HOOKS = ("pre-commit", "pre-push", "commit-identity-guard", "commit-identity-guard-pre-push")
_ORIGIN = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")

Ctx = collections.namedtuple("Ctx", "root repo default log_dir bundle_max")


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
        gh("issue", "edit", str(anchor), "--repo", ctx.repo, "--remove-label", READY,
           "--add-label", CLAIMED, "--add-assignee", "@me")
        gh("issue", "comment", str(anchor), "--repo", ctx.repo, "--body", f"{ANCHOR_NOTE} implement-{anchor}")
    return True


def resumable(ctx):
    """The lowest open in-progress ticket carrying drain's own anchor comment,
    or `None`. A worker `implement-dispatch` started has none."""
    for issue in sorted(frontier.fetch_issues(ctx.repo, CLAIMED), key=lambda i: i["number"]):
        if HUMAN in labels_of(issue) or issue.get("pull_request"):
            continue
        view = gh_json("issue", "view", str(issue["number"]), "--repo", ctx.repo, "--json", "comments")
        if any(c["body"].startswith(ANCHOR_NOTE) for c in view["comments"]):
            return issue["number"]
    return None


def bundle_of(ctx, anchor, offered=()):
    """The anchor plus every ticket it is still holding for this run: the
    numbers in `drain bundle:` comments posted after the latest claim, and the
    offered tickets now in-progress. Each is read live; a closed, human-held
    or unclaimed one is not the bundle's."""
    comments = gh_json("issue", "view", str(anchor), "--repo", ctx.repo, "--json", "comments")["comments"]
    start = max((i for i, c in enumerate(comments) if c["body"].startswith(ANCHOR_NOTE)), default=-1)
    named = {int(x) for c in comments[start + 1:] if c["body"].strip().startswith(BUNDLE_NOTE)
             for x in re.findall(r"\d+", c["body"])}
    held = []
    for n in sorted((named | set(offered)) - {anchor}):
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
            f"at most {bundle_max} tickets in all with the anchor. First claim each one you add "
            f"(`gh issue edit <n> --remove-label {READY} --add-label {CLAIMED} --add-assignee @me`) and "
            f"post one comment on #{anchor} reading `{BUNDLE_NOTE} <numbers, anchor first>`. Then build "
            "them as one clump (implement/SKILL.md § The brief), working one ticket at a time: test first, "
            "green, one commit per ticket before the next. If you run out of context or time partway, the "
            f"PR closes only the finished tickets and you relabel the rest `{READY}` with `{CLAIMED}` and "
            "your assignee removed. The bundle gets one review wave: its spec axis receives every ticket "
            "and checks each one's acceptance criteria.")


def build(path, prompt, log):
    """One headless session running `/implement`; a non-zero exit or the wall
    clock is a failed build."""
    if busy(path):
        raise DrainStop(f"a process is still running in {path}; rerun when it exits")
    with open(log, "w") as out:
        code, _ = run_group(["claude", "-p", prompt, "--permission-mode", PERMISSION_MODE], path,
                            WALL_CLOCK_SECONDS, out=out, preexec=_cap_session)
    if code:
        raise DrainError(f"build exited {code} (log {log})")


def open_pr(ctx, branch):
    prs = gh_json("pr", "list", "--repo", ctx.repo, "--head", branch, "--state", "open", "--json", "number,url")
    return prs[0] if prs else None


def seam(ctx, head, log):
    """The repo's seam (`land.testcmd`, else `bash tests/all.sh`) on the PR head
    merged into current main, in a throwaway worktree. The merge commit uses
    the identity the repo is already configured with."""
    cmd = run(["git", "config", "land.testcmd"], cwd=ctx.root, check=False) or "bash tests/all.sh"
    run(["git", "fetch", "-q", "origin"], cwd=ctx.root)
    scratch = tempfile.mkdtemp(prefix="drain-seam-")
    try:
        run(["git", "worktree", "add", "-q", "--detach", scratch, ctx.default], cwd=ctx.root)
        merged = subprocess.run(["git", "merge", "--no-edit", head], cwd=scratch, capture_output=True, text=True)
        if merged.returncode:
            raise DrainError("merging the PR into current main failed: "
                             + one_line(merged.stderr or merged.stdout, 200))
        with open(log, "w") as out:
            code, _ = run_group(["sh", "-c", cmd], scratch, WALL_CLOCK_SECONDS, out=out)
        if code:
            raise DrainError(f"seam `{cmd}` failed on the PR merged into main (output in {log})")
    finally:
        run(["git", "worktree", "remove", "--force", scratch], cwd=ctx.root, check=False)


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
    if len(closed) > ctx.bundle_max:
        raise DrainError(f"{view['url']} closes {len(closed)} tickets, over --bundle-max {ctx.bundle_max}")
    seam(ctx, view["headRefOid"], os.path.join(ctx.log_dir, f"{branch}-seam.log"))
    view["closes"] = sorted(closed)
    return view


def finish(ctx, anchor, others, branch, view):
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
        for n in set(bundle_of(ctx, anchor, [n for n, _ in others])) - set(view["closes"]):
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
                build(path, prompt, os.path.join(ctx.log_dir, f"{branch}-{attempt}.log"))
            if not open_pr(ctx, branch):
                raise DrainError("the build ended with no open PR")
            view = verify_pr(ctx, branch, anchor)
            gh("pr", "merge", str(view["number"]), "--squash", "--match-head-commit", view["headRefOid"],
               "--repo", ctx.repo)
        except DrainError as exc:
            reason = one_line(exc)
        else:
            return finish(ctx, anchor, others, branch, view), None
    return None, reason


def hand_to_chris(ctx, anchor, others, reason):
    bundle = bundle_of(ctx, anchor, [n for n, _ in others])
    for n in bundle:
        gh("issue", "edit", str(n), "--repo", ctx.repo, "--remove-label", CLAIMED, "--add-label", HUMAN,
           "--remove-assignee", "@me")
        gh("issue", "comment", str(n), "--repo", ctx.repo, "--body",
           f"drain could not land this ticket (bundle {' '.join(f'#{x}' for x in bundle)}) after two attempts. "
           f"Last failure: {reason} The worktree implement-{anchor} is kept for inspection.")
    return bundle


def drain(ctx, limit):
    """`(merged, handed, stop reason or None)`; `limit` counts tickets."""
    merged, handed, stop, failures, done = [], [], None, 0, 0
    try:
        require_guard(ctx)
        while done < limit:
            anchor = resumable(ctx)
            resumed, others = anchor is not None, []
            if not resumed:
                queue = pick(ctx)
                if not queue:
                    break
                anchor, others = queue[0][0], queue[1:]
                if not claim(ctx, anchor):
                    continue
            result, reason = work(ctx, anchor, others, resumed)
            if result:
                merged.append(result)
                done, failures = done + len(result["tickets"]), 0
            else:
                bundle = hand_to_chris(ctx, anchor, others, reason)
                handed.append((bundle, reason))
                done, failures = done + len(bundle), failures + 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    stop = (f"{failures} bundles in a row went to Chris; the environment is the likelier "
                            "cause (auth, quota, permission mode, headless /implement). Check the build logs.")
                    break
    except DrainStop as exc:
        stop = str(exc)
    except Exception as exc:  # noqa: BLE001 - the summary of what landed must still print
        stop = f"unexpected {type(exc).__name__}: {one_line(exc)}"
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
    merged, handed, stop = drain(Ctx(root, repo, default, log_dir, args.bundle_max), limit)
    print(summary(merged, handed, stop))
    return 1 if stop else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
