#!/usr/bin/env python3
"""The merge check and the closing counts must agree on where a ticket's
dispositions sidecar lives (#1258). `fix_check.py` (behind
`fix-check.sh` and `pre-report-gate.sh`) and `counts.py` each derive
`~/.cache/agent-reviews/<repo>/dispositions-<n>.jsonl`; a rename in either
would otherwise turn the merge check into "no sidecar" for a worker whose
sidecar is where the skill says, or the closing counts into a refusal.

Seam: the sidecar is written where `counts.default_reviews_dir` and
`runfile.dispositions_path` say, then the script is run from a linked
worktree of a throwaway repo and must find it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "burndown"))
import counts  # noqa: E402
import runfile  # noqa: E402

CHECK = os.path.join(HERE, "fix-check.sh")
IDENT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def scrubbed_env(home):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return {**env, **IDENT, "HOME": home}


def run(cmd, cwd, env):
    done = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="sidecar-name-")
    try:
        home = os.path.join(tmp, "home")
        env = scrubbed_env(home)
        origin = os.path.join(tmp, "origin.git")
        primary = os.path.join(tmp, "skills-repo")
        work = os.path.join(tmp, "wt")
        for cmd, cwd in ((["git", "init", "-q", "--bare", "-b", "main", origin], tmp),
                         (["git", "clone", "-q", origin, primary], tmp),
                         (["git", "commit", "-q", "--allow-empty", "-m", "x"], primary),
                         (["git", "push", "-q", "origin", "main"], primary),
                         (["git", "remote", "set-head", "origin", "main"], primary),
                         (["git", "worktree", "add", "-q", "-b", "implement-5", work], primary)):
            code, out = run(cmd, cwd, env)
            assert code == 0, (cmd, out)

        os.environ["HOME"] = home
        reviews = counts.default_reviews_dir(runfile.checkout_top(work))
        assert reviews.startswith(home), reviews
        os.makedirs(reviews)
        for axis in ("standards", "spec", "correctness"):
            open(os.path.join(reviews, f"findings-{axis}-5.jsonl"), "w").close()
            open(os.path.join(reviews, f"findings-{axis}-5.done"), "w").close()

        # No sidecar yet: the check must refuse, and name the file it looked for.
        code, out = run(["bash", CHECK, "5"], work, env)
        assert code == 1 and "dispositions-5.jsonl is missing" in out, (code, out)

        # Written where the module says: the check finds it.
        sidecar = runfile.dispositions_path(reviews, 5)
        with open(sidecar, "w") as fh:
            fh.write(json.dumps({"id": "S1", "outcome": "disputed", "reason": "no"}) + "\n")
        code, out = run(["bash", CHECK, "5"], work, env)
        assert code == 1 and "S1 is no finding" in out, (
            f"fix-check.sh did not read {sidecar}: {code} {out}")
        print("ok  the merge check reads the sidecar runfile.dispositions_path names")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
