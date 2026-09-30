#!/usr/bin/env python3
"""The shell gates and `runfile.py` must agree on where a ticket's
dispositions sidecar lives (#1258). `pre-report-gate.sh` and
`verification-check.sh` re-derive `~/.cache/agent-reviews/<repo>/dispositions-<n>.jsonl`
in shell; `runfile.dispositions_path` and `sweep.default_reviews_dir` own it.
A rename in the module would otherwise turn both gates into "no sidecar" —
a refusal the worker reads as a skipped verification pass, not as drift.

Seam: the sidecar is written where the module says, then each script is run
from a linked worktree of a throwaway repo and must find it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "burndown"))
import runfile  # noqa: E402
import sweep  # noqa: E402

GATE = os.path.join(HERE, "pre-report-gate.sh")
CHECK = os.path.join(HERE, "verification-check.sh")
IDENT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def scrubbed_env(home, path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return {**env, **IDENT, "HOME": home, "PATH": path}


def run(cmd, cwd, env):
    done = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="sidecar-name-")
    try:
        home = os.path.join(tmp, "home")
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        # The gate asks gh whether the ticket is a sweep; no network here.
        with open(os.path.join(bindir, "gh"), "w") as fh:
            fh.write("#!/usr/bin/env bash\necho 'Ordinary ticket'\n")
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        env = scrubbed_env(home, bindir + os.pathsep + os.environ["PATH"])
        repo = os.path.join(tmp, "skills-repo")
        work = os.path.join(tmp, "wt")
        subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True, env=env)
        subprocess.run(["git", "-C", repo, "commit", "-q", "--allow-empty",
                        "-m", "x"], check=True, env=env)
        subprocess.run(["git", "-C", repo, "worktree", "add", "-q", "-b",
                        "implement-5", work], check=True, env=env)

        # Resolved the way the module resolves it, under the fake HOME.
        os.environ["HOME"] = home
        reviews = sweep.default_reviews_dir(runfile.checkout_top(work))
        assert reviews.startswith(home), reviews
        os.makedirs(reviews)
        sidecar = runfile.dispositions_path(reviews, 5)
        with open(sidecar, "w") as fh:
            fh.write(json.dumps({"id": "S1", "outcome": "disputed",
                                 "reason": "no"}) + "\n")

        code, out = run(["bash", CHECK, "5"], work, env)
        assert code == 0 and "present" in out, (
            f"verification-check.sh did not find {sidecar}: {code} {out}")

        # The gate reads the sidecar and the PR body from the same directory:
        # a body that contradicts the line must be refused, naming the id.
        with open(os.path.join(reviews, "pr-body-5.md"), "w") as fh:
            fh.write("## Decisions made\n\n- S1: fixed, abc1234.\n")
        code, out = run(["bash", GATE, "HEAD"], work, env)
        assert code == 1 and "S1" in out and "fixed" in out, (
            f"pre-report-gate.sh did not compare {sidecar}: {code} {out}")
        print("ok  both gates find the sidecar runfile.dispositions_path names")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
