"""How the sweep driver and its modules start a child process: never with
a leaked git-redirecting variable in its environment (#625)."""
import os
import subprocess

# Git reads these ahead of any `-C` or path argument, so a caller's leaked
# GIT_DIR (a shell export, a git hook's environment) silently redirects every
# git call at that repo instead of the one the driver was handed (#625).
GIT_REDIRECT_VARS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def scrubbed_env():
    """The current environment minus the git-redirecting variables (#625).
    Every child the driver spawns gets at least this — `claude` and `uv` run
    git of their own inside a worktree, so they must not inherit the leak
    either."""
    return {k: v for k, v in os.environ.items() if k not in GIT_REDIRECT_VARS}


def claude_env():
    """`scrubbed_env` plus an unlimited `claude -p` background-task wait
    (#1278): an audit fans out shards that outlive `claude -p`'s 600 s
    default wait ceiling, which terminates the process with no report; `0`
    waits forever."""
    return {**scrubbed_env(), "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": "0"}


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env or scrubbed_env())
