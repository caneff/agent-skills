"""The one place a Python suite names a fixture git identity (#1144, #1728).

A suite that wrote `user.email`/`user.name` into the real checkout, or built
its own `GIT_AUTHOR_*` set, has put `t <t@t>` on a real worker's commit.
`configure` writes only into a repo under the caller's own temp root;
`env` and `c_args` hand out the same identity for the env and `-c` forms.
`tests/fixture-identity-sites.test.sh` fails any other writer.
"""
import os
import subprocess

NAME = "t"
EMAIL = "t@example.invalid"


def env(name=NAME, email=EMAIL):
    """The four GIT_AUTHOR_*/GIT_COMMITTER_* variables for one identity."""
    return {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}


def c_args():
    """`git -c` arguments committing as the fixture identity, for a repo with no config."""
    return ["-c", f"user.name={NAME}", "-c", f"user.email={EMAIL}"]


def _real(path, env=None):
    cmd = ["git", "-C", path, "rev-parse", "--show-toplevel"]
    out = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return out.stdout.strip() if out.returncode == 0 else ""


def configure(repo, root, env=None):
    """Set the identity in `repo` only when its toplevel sits under `root`.

    A bare `git config` after a failed chdir wrote the real checkout's config,
    so the target is named and checked. An empty or unresolvable `root` would
    admit any repo, so it is refused too. `env` is the child environment (a
    scrubbed one, when GIT_DIR may have leaked). Raises ValueError, writing
    nothing.
    """
    if not root or not os.path.isdir(root):
        raise ValueError(f"fixture root {root!r} does not resolve to a directory")
    real = _real(repo, env)
    top, base = os.path.realpath(real) if real else "", os.path.realpath(root)
    if not top or not top.startswith(base + os.sep):
        raise ValueError(f"fixture repo {repo} is not under {root}")
    for key, value in (("user.email", EMAIL), ("user.name", NAME)):
        cmd = ["git", "-C", repo, "config", key, value]
        subprocess.run(cmd, check=True, capture_output=True, env=env)
