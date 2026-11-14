"""The one way a Python script asks git, GitHub or herdr a question (#1778, spec #1730).

Every call has an `ok=` exit contract (an exit outside it raises `CmdError`, so a tool that failed
outright is never read as the answer an exit 1 can be), a timeout, and an environment with the
git-redirecting variables removed (#625): a leaked `GIT_DIR` would otherwise point every `git -C`
call at another repo. The directory belongs to no skill; callers wrap `CmdError` in their own
exception type at their edge."""
import contextlib
import json
import os
import re
import subprocess
import threading

TIMEOUT = 120  # seconds; every call is bounded, a hung tool is an error and never a wait

# Git reads these ahead of any `-C` or path argument (#625).
GIT_REDIRECT_VARS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


class CmdError(Exception):
    """A command exited outside `ok=`, timed out, or was not found; str() is `<cmd>: <why>`."""


def scrubbed_env():
    """The current environment minus the git-redirecting variables."""
    return {k: v for k, v in os.environ.items() if k not in GIT_REDIRECT_VARS}


def _run(cmd, ok, cwd, timeout):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=scrubbed_env(), timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CmdError(f"{' '.join(cmd)}: timed out after {timeout}s") from None
    except OSError as e:
        raise CmdError(f"{' '.join(cmd)}: {e}") from None
    if r.returncode not in ok:
        raise CmdError(f"{' '.join(cmd)}: {r.stderr.strip() or f'exit {r.returncode}'}")
    return r


def git(args, ok=(0,), cwd=None, timeout=TIMEOUT):
    """`git <args>`'s CompletedProcess, raising CmdError on an exit not in `ok`. A query whose exit 1
    is an answer (`rev-parse --verify --quiet`, `merge-base --is-ancestor`) passes `ok=(0, 1)`."""
    return _run(["git", *args], ok, cwd, timeout)


def gh(args, ok=(0,), cwd=None, timeout=TIMEOUT):
    """`gh <args>`'s CompletedProcess, with the same contract as `git`."""
    return _run(["gh", *args], ok, cwd, timeout)


def herdr_agent(name, timeout=TIMEOUT):
    """The herdr record of agent `name` (`agent_status`, `pane_id`, ...), or None when herdr has no
    such agent. Any other failure, a timeout included, raises CmdError: a herdr that cannot be
    asked is not a worker that is gone."""
    cmd = ["herdr", "agent", "get", name]
    r = _run(cmd, (0, 1, 2), None, timeout)
    body = {}
    for text in (r.stdout, r.stderr):  # a result prints on stdout, an error on stderr
        with contextlib.suppress(ValueError):
            body = json.loads(text)
            break
    if r.returncode == 0 and isinstance(body, dict) and "result" in body:
        return body["result"]["agent"]
    if isinstance(body, dict) and (body.get("error") or {}).get("code") == "agent_not_found":
        return None
    raise CmdError(f"{' '.join(cmd)}: {(r.stderr or r.stdout).strip()[:150] or f'exit {r.returncode}'}")


_WORKTREE_LOCK = threading.Lock()  # `git worktree add` and `prune` are not safe to run at once


@contextlib.contextmanager
def scratch_worktree(repo, rev, path):
    """Yield `path`, a detached worktree of `repo` at `rev`; remove and prune it on every exit,
    an exception included. Raises CmdError when the add fails."""
    with _WORKTREE_LOCK:
        git(["-C", repo, "worktree", "add", "--detach", path, rev])
    try:
        yield path
    finally:
        with _WORKTREE_LOCK:
            git(["-C", repo, "worktree", "remove", "--force", path], ok=(0, 128))
            git(["-C", repo, "worktree", "prune"], ok=(0, 128))


def default_branch(repo):
    """`origin/<default>` as `repo` records it. Refuses, never guesses `main`, when `origin/HEAD`
    is unset, naming the `git remote set-head` that records it."""
    try:
        return git(["-C", repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"]).stdout.strip()
    except CmdError as e:
        raise CmdError(f"{e} — {repo} has no recorded default branch and will not be assumed to be "
                       "`main`: record it with `git remote set-head origin -a`") from None


_SLUG = re.compile(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$")


def origin_slug(repo):
    """`owner/name` of `repo`'s origin, or None when origin is not a github.com remote. A name
    with dots in it (`a.b`) keeps them; only a trailing `.git` is dropped."""
    url = git(["-C", repo, "remote", "get-url", "origin"], ok=(0, 2)).stdout.strip()
    m = _SLUG.search(url)
    return m.group(1) if m else None
