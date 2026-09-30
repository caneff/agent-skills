"""Fixtures the burndown suites share; not a suite itself."""
import json
import os
import subprocess

import runfile


def drop_repo_field(run_id, root):
    """Rewrite a run file as one written before the `repo` field existed."""
    target = runfile.path(run_id, root)
    with open(target) as fh:
        run = json.load(fh)
    del run["repo"]
    with open(target, "w") as fh:
        json.dump(run, fh)


def linked_worktree(primary, name):
    """A linked worktree of the git checkout `primary`, a sibling directory
    called `name` (an empty commit gives the checkout a HEAD to branch from)."""
    ident = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", "-C", primary, "commit", "-q", "--allow-empty",
                    "-m", "x"], check=True, env={**os.environ, **ident})
    path = os.path.join(os.path.dirname(primary), name)
    subprocess.run(["git", "-C", primary, "worktree", "add", "-q", "--detach",
                    path], check=True)
    return os.path.realpath(path)
