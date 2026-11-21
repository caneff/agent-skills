"""Fixtures the run suites share; not a suite itself."""
import json
import sys
import os
import subprocess

import runfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../common"))
import fixture_identity  # noqa: E402


def _commit_shas():
    """Two distinct commits of this repo: `land` refuses a sha that is no commit there (#1979)."""
    here = os.path.dirname(os.path.abspath(__file__))
    top = runfile.checkout_top(here)
    out = subprocess.run(["git", "-C", top, "rev-list", "--max-count=2", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.split()
    return out[0], out[-1]


SHA_A, SHA_B = _commit_shas()


def reopen_permissions(root):
    """Give every entry under `root` (and `root` itself) owner access again, so
    pytest can remove a tree a test took permissions away from."""
    for dirpath, dirnames, filenames in os.walk(root):
        os.chmod(dirpath, 0o700)
        for name in dirnames + filenames:
            try:
                os.chmod(os.path.join(dirpath, name), 0o700)
            except OSError:
                pass


def drop_repo_field(run_id, root):
    """Rewrite a run file as one written before the `repo` field existed."""
    target = runfile.path(run_id, root)
    with open(target) as fh:
        run = json.load(fh)
    del run["repo"]
    with open(target, "w") as fh:
        json.dump(run, fh)


def drop_job(run_id, root, lowest):
    """Rewrite a run file as one written before jobs existed: a clump with no
    `job` key, which reads as no record at all (a fresh registration records
    `none`)."""
    target = runfile.path(run_id, root)
    with open(target) as fh:
        run = json.load(fh)
    matched = [e for e in run["clumps"] if min(e["tickets"]) == lowest]
    if not matched:
        raise KeyError(f"no clump #{lowest} in run {run_id}")
    del matched[0]["job"]
    with open(target, "w") as fh:
        json.dump(run, fh)


def linked_worktree(primary, name):
    """A linked worktree of the git checkout `primary`, a sibling directory
    called `name` (an empty commit gives the checkout a HEAD to branch from)."""
    ident = fixture_identity.env()
    subprocess.run(["git", "-C", primary, "commit", "-q", "--allow-empty",
                    "-m", "x"], check=True, env={**os.environ, **ident})
    path = os.path.join(os.path.dirname(primary), name)
    subprocess.run(["git", "-C", primary, "worktree", "add", "-q", "--detach",
                    path], check=True)
    return os.path.realpath(path)


def commit_in(repo):
    """An empty commit in the fixture checkout `repo`, and its sha: a `land` target (#1979)."""
    subprocess.run(["git", "-C", repo, "commit", "-q", "--allow-empty", "-m", "x"],
                   check=True, env={**os.environ, **fixture_identity.env()})
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
