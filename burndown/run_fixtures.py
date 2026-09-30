"""Fixtures the burndown suites share; not a suite itself."""
import json

import runfile


def drop_repo_field(run_id, root):
    """Rewrite a run file as one written before the `repo` field existed."""
    target = runfile.path(run_id, root)
    with open(target) as fh:
        run = json.load(fh)
    del run["repo"]
    with open(target, "w") as fh:
        json.dump(run, fh)
