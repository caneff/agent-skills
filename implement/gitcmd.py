"""The one way the Codex audit's scripts (`codex-audit.py`, `codex-audit-range.py`) ask git a
question (#1405 S6): one helper and one error contract, so a git failure reads the same in both."""
import subprocess


class GitError(Exception):
    """git exited with a status the caller did not name as an answer; str() is `git <args>: <stderr>`."""


def git(*args: str, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    """`git <args>`'s result, raising GitError on any exit not in `ok`. A query whose exit 1 is an
    answer (`rev-parse --verify --quiet`, `merge-base --is-ancestor`) passes `ok=(0, 1)`, so a git
    that failed outright is never read as that answer."""
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode not in ok:
        raise GitError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r
