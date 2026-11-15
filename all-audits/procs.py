"""How the sweep driver and its modules start a child process: never with
a leaked git-redirecting variable in its environment (#625)."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))

from shellcmd import GIT_REDIRECT_VARS, scrubbed_env  # noqa: E402,F401  (one definition: common/shellcmd.py)


def claude_env():
    """`scrubbed_env` plus an unlimited `claude -p` background-task wait
    (#1278): an audit fans out shards that outlive `claude -p`'s 600 s
    default wait ceiling, which terminates the process with no report; `0`
    waits forever."""
    return {**scrubbed_env(), "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": "0"}


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env or scrubbed_env())
