#!/usr/bin/env python3
"""`drain.py [--repo <path>] [--once] [--max <n>] [--bundle-max <k>]`: work the
`ready-for-agent` queue unattended, serially, one PR at a time (#1403).

The **anchor** is the oldest unblocked ready ticket (`burndown/frontier.py`).
`drain` claims it and starts one headless `claude -p` session in a worktree
on `implement-<anchor>`, handing it the anchor and the number and title of
every other unblocked ready ticket. The agent chooses the **bundle**: the
others it would naturally fix in the same PR (at most `--bundle-max` tickets
in all), claims each, records the bundle in a `drain bundle: <numbers>`
comment on the anchor, and closes every one in one PR with one review wave.
`drain` does no directory or closure grouping. `--max` and `--once` count PRs.

Then it checks (the PR is not draft, CLEAN, closes the anchor within the
bundle cap, and the repo's seam passes on the PR merged into current main),
squash-merges and runs `merge-cleanup`, and releases any ticket the agent
claimed but the PR did not close. A build or check that fails is run once
more in the same worktree; a second failure labels the anchor and every
claimed ticket `ready-for-human` with a comment saying why, keeps the
worktree, and the loop moves on.

State lives in GitHub and git, nowhere else: an open, in-progress ticket
with an `implement-<n>` worktree is resumed, and an open PR is checked
rather than rebuilt. Only repos whose owner is the `gh` login.
"""
import argparse
import json
import os
import re
import resource
import signal
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "burndown"))

import frontier  # noqa: E402

READY, CLAIMED, HUMAN = "ready-for-agent", "in-progress", "ready-for-human"
BUNDLE_MAX = 8
# The caps of one build session, stated here and nowhere else: the equivalent
# of `ulimit -v 32G` (address space, not resident memory, hence generous) and a
# three-hour wall clock after which the whole process group is killed. The seam
# gets the same wall clock.
MEMORY_CAP_BYTES = 32 << 30
WALL_CLOCK_SECONDS = 3 * 60 * 60
# Never a permission-skipping flag: the session runs in the mode the harness
# already trusts for unattended work. Unverified that `/implement` completes
# under it headless (#1403 asks for that check); a refusal shows as a failed
# build, and the second failure hands the ticket to Chris.
PERMISSION_MODE = "auto"
_BUNDLE_NOTE = re.compile(r"^drain bundle:[ \t]*((?:#?\d+[ ,\t]*)+)$")


class DrainError(Exception):
    """A step failed; the message is the reason handed to Chris."""


def run(args, cwd=None, check=True):
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and out.returncode:
        raise DrainError(f"{' '.join(args[:3])} failed: {(out.stderr or out.stdout).strip()}")
    return out.stdout.strip()


def gh(*args, cwd=None):
    return run(["gh", *args], cwd=cwd)


def gh_json(*args, cwd=None):
    return json.loads(gh(*args, cwd=cwd))


def pick(repo):
    """`[(number, title)]`: the unblocked ready queue, oldest first; the
    anchor is the first."""
    issues = {}

    def fetch(r, label):
        got = frontier.fetch_issues(r, label)
        issues.update({i["number"]: i for i in got})
        return got

    try:
        queue = frontier.frontier(repo, READY, fetch=fetch)["unblocked"]
    except frontier.FrontierError as exc:
        raise DrainError(f"frontier: {exc}") from exc
    return [(t["number"], t["title"]) for t in queue
            if HUMAN not in {x["name"] for x in issues[t["number"]]["labels"]}]


def bundle_of(repo, anchor):
    """The numbers the agent recorded in its `drain bundle:` comment on the
    anchor, anchor first; just the anchor when it recorded none."""
    comments = gh_json("issue", "view", str(anchor), "--repo", repo, "--json", "comments")["comments"]
    for comment in reversed(comments):
        m = _BUNDLE_NOTE.match(comment["body"].strip())
        if m:
            numbers = [int(x) for x in re.findall(r"\d+", m.group(1))]
            return [anchor] + [n for n in dict.fromkeys(numbers) if n != anchor]
    return [anchor]


def resumable(root, repo):
    """The lowest `implement-<n>` worktree whose ticket is open and
    in-progress, or `None`."""
    base = os.path.join(root, ".claude", "worktrees")
    names = sorted(int(m.group(1)) for d in (os.listdir(base) if os.path.isdir(base) else [])
                   if (m := re.fullmatch(r"implement-(\d+)", d)))
    for n in names:
        view = gh_json("issue", "view", str(n), "--repo", repo, "--json", "state,labels")
        labels = {x["name"] for x in view["labels"]}
        if view["state"].lower() == "open" and CLAIMED in labels and HUMAN not in labels:
            return n
    return None


def claim(repo, n):
    gh("issue", "edit", str(n), "--repo", repo, "--remove-label", READY,
       "--add-label", CLAIMED, "--add-assignee", "@me")


def workspace(root, branch, default):
    path = os.path.join(root, ".claude", "worktrees", branch)
    if os.path.isdir(path):
        return path
    run(["git", "fetch", "origin"], cwd=root)
    if run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=root, check=False):
        run(["git", "worktree", "add", path, branch], cwd=root)
    else:
        run(["git", "worktree", "add", "-b", branch, path, default], cwd=root)
    return path


def _cap_memory():
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_CAP_BYTES, MEMORY_CAP_BYTES))


def brief(anchor, others, bundle_max):
    """The prompt: `/implement` on the anchor, then the agent's bundle choice."""
    listing = "\n".join(f"- #{n} {title}" for n, title in others) or "- (none)"
    return (f"/implement {anchor} --tier heavy\n\n"
            "Unattended run, no controller: send no messages. Stop once the PR is up and CLEAN, "
            "and print `PR up: <url>`.\n\n"
            f"Bundle: #{anchor} is the anchor. Other unblocked ready tickets:\n{listing}\n"
            f"Read the ones that look related and add those you would naturally fix in the same PR, "
            f"at most {bundle_max} tickets in all with the anchor. Claim each one you add "
            f"(`gh issue edit <n> --remove-label {READY} --add-label {CLAIMED} --add-assignee @me`), "
            f"post one comment on #{anchor} reading `drain bundle: <numbers, anchor first>`, and build "
            "them in one worktree and one PR whose body has a closing keyword for each, working one "
            "ticket at a time: test first, green, one commit per ticket before the next. If you run out "
            "of context or time partway, the PR closes only the finished tickets and you relabel the rest "
            f"`{READY}` with `{CLAIMED}` removed. "
            "The bundle gets one review wave; the spec axis receives every ticket in it and checks "
            "each one's acceptance criteria.")


def build(path, prompt, log):
    """One headless session running `/implement`; a non-zero exit or the wall
    clock is a failed build."""
    with open(log, "w") as out:
        proc = subprocess.Popen(["claude", "-p", prompt, "--permission-mode", PERMISSION_MODE],
                                cwd=path, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True, preexec_fn=_cap_memory)
        try:
            code = proc.wait(timeout=WALL_CLOCK_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise DrainError(f"build passed the {WALL_CLOCK_SECONDS}s wall clock (log {log})")
    if code:
        raise DrainError(f"build exited {code} (log {log})")


def open_pr(repo, branch):
    prs = gh_json("pr", "list", "--repo", repo, "--head", branch, "--state", "open", "--json", "number,url")
    return prs[0] if prs else None


def seam(root, default, head):
    """The repo's seam (`land.testcmd`, else `bash tests/all.sh`) on the PR head
    merged into current main, in a throwaway worktree. The merge commit uses
    the identity the repo is already configured with."""
    cmd = run(["git", "config", "land.testcmd"], cwd=root, check=False) or "bash tests/all.sh"
    run(["git", "fetch", "origin"], cwd=root)
    scratch = tempfile.mkdtemp(prefix="drain-seam-")
    try:
        run(["git", "worktree", "add", "--detach", scratch, default], cwd=root)
        if subprocess.run(["git", "merge", "--no-edit", head], cwd=scratch, capture_output=True).returncode:
            raise DrainError("the PR does not merge cleanly into current main")
        try:
            out = subprocess.run(["sh", "-c", cmd], cwd=scratch, capture_output=True, text=True,
                                 timeout=WALL_CLOCK_SECONDS)
        except subprocess.TimeoutExpired:
            raise DrainError(f"seam `{cmd}` passed the {WALL_CLOCK_SECONDS}s wall clock")
        if out.returncode:
            raise DrainError(f"seam `{cmd}` failed on the PR merged into main:\n"
                             + (out.stdout + out.stderr)[-1500:])
    finally:
        run(["git", "worktree", "remove", "--force", scratch], cwd=root, check=False)


def check(root, repo, default, branch, anchor, bundle_max):
    view = gh_json("pr", "view", branch, "--repo", repo, "--json",
                   "isDraft,mergeStateStatus,headRefOid,number,url,closingIssuesReferences")
    if view["isDraft"]:
        raise DrainError(f"{view['url']} is still a draft")
    if view["mergeStateStatus"] != "CLEAN":
        raise DrainError(f"{view['url']} is {view['mergeStateStatus']}, not CLEAN")
    closed = {r["number"] for r in view["closingIssuesReferences"]}
    if anchor not in closed:
        raise DrainError(f"{view['url']} does not close the anchor #{anchor}")
    if len(closed) > bundle_max:
        raise DrainError(f"{view['url']} closes {len(closed)} tickets, over --bundle-max {bundle_max}")
    seam(root, default, view["headRefOid"])
    view["closes"] = sorted(closed)
    return view


def land(root, repo, branch, view):
    """Squash-merge bound to the checked head, then `merge-cleanup`. A cleanup
    failure is a note on a merged PR, not a failed build."""
    gh("pr", "merge", str(view["number"]), "--squash", "--match-head-commit",
       view["headRefOid"], "--repo", repo)
    sha = gh_json("pr", "view", str(view["number"]), "--repo", repo, "--json", "mergeCommit")["mergeCommit"]["oid"]
    cleanup = subprocess.run(["merge-cleanup", "--repo", root, branch], capture_output=True, text=True)
    note = "" if cleanup.returncode == 0 else f"merge-cleanup failed: {(cleanup.stderr or cleanup.stdout).strip()}"
    return {"tickets": None, "pr": view["url"], "sha": sha, "note": note}


def hand_to_chris(repo, anchor, reason):
    bundle = bundle_of(repo, anchor)
    for n in bundle:
        gh("issue", "edit", str(n), "--repo", repo, "--remove-label", CLAIMED, "--add-label", HUMAN)
        gh("issue", "comment", str(n), "--repo", repo, "--body",
           f"drain could not land this ticket (bundle {' '.join(f'#{x}' for x in bundle)}) after two builds. "
           f"Last failure: {reason} The worktree implement-{anchor} is kept for inspection.")
    return bundle


def release_stranded(repo, anchor, closes):
    """Back to the queue: a ticket the agent claimed that the merged PR did not close."""
    for n in set(bundle_of(repo, anchor)) - set(closes):
        gh("issue", "edit", str(n), "--repo", repo, "--remove-label", CLAIMED, "--add-label", READY)


def work(root, repo, default, anchor, others, resumed, args, log_dir):
    """The merge result dict, or the second failure's reason as a string."""
    branch = f"implement-{anchor}"
    path = workspace(root, branch, default)
    prompt = brief(anchor, others, args.bundle_max)
    reason = ""
    for attempt in (1, 2):
        try:
            if not (resumed and attempt == 1 and open_pr(repo, branch)):
                build(path, prompt, os.path.join(log_dir, f"{branch}-{attempt}.log"))
            if not open_pr(repo, branch):
                raise DrainError("the build ended with no open PR")
            view = check(root, repo, default, branch, anchor, args.bundle_max)
            result = land(root, repo, branch, view)
            result["tickets"] = view["closes"]
            release_stranded(repo, anchor, view["closes"])
            return result
        except DrainError as exc:
            reason = str(exc)
    return reason


def drain(root, repo, default, limit, args, log_dir):
    merged, handed = [], []
    for _ in range(limit):
        anchor = resumable(root, repo)
        resumed = anchor is not None
        others = []
        if not resumed:
            queue = pick(repo)
            if not queue:
                break
            anchor, others = queue[0][0], queue[1:]
            claim(repo, anchor)
        result = work(root, repo, default, anchor, others, resumed, args, log_dir)
        if isinstance(result, dict):
            merged.append(result)
        else:
            handed.append((hand_to_chris(repo, anchor, result), result))
    return merged, handed


def summary(merged, handed):
    lines = ["merged:"] + [f"  {' '.join(f'#{n}' for n in m['tickets'])}  {m['pr']}  {m['sha']}"
                            + (f"  ({m['note']})" if m["note"] else "") for m in merged]
    lines += ["handed to Chris:"] + [f"  {' '.join(f'#{n}' for n in b)}  {r.splitlines()[0]}" for b, r in handed]
    return "\n".join(lines if merged or handed else ["nothing to drain"])


def main(argv):
    parser = argparse.ArgumentParser(description="work the ready-for-agent queue, one bundle at a time")
    parser.add_argument("--repo", default=".", help="the repo's primary checkout")
    parser.add_argument("--once", action="store_true", help="one bundle, then stop")
    parser.add_argument("--max", type=int, default=None, help="stop after this many bundles")
    parser.add_argument("--bundle-max", type=int, default=BUNDLE_MAX)
    args = parser.parse_args(argv)
    try:
        root = run(["git", "rev-parse", "--show-toplevel"], cwd=args.repo)
        repo = gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner", cwd=root)
        login = gh("api", "user", "--jq", ".login")
        if repo.split("/")[0] != login:
            raise DrainError(f"{repo} is not owned by {login}; drain only runs on the caller's own repos")
        default = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=root)
        log_dir = os.environ.get("DRAIN_LOG_DIR") or os.path.expanduser("~/.cache/drain")
        os.makedirs(log_dir, exist_ok=True)
        limit = 1 if args.once else (args.max if args.max is not None else sys.maxsize)
        print(summary(*drain(root, repo, default, limit, args, log_dir)))
    except DrainError as exc:
        print(f"drain.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
