"""`review_ledger.py cache-dir` (#1527): the one place the review cache directory is
chosen. The key is the repo's own name read off the common `.git`, folded by the
ledger's `fold_repo`, so a checkout named `agent-skills` and one named `skills` write
one directory.

Seam: the real script, run from a checkout (or a linked worktree of one) of a
throwaway repo, with HOME pointed at a temp dir.
"""
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "review_ledger.py"


def run(cwd, home, *args):
    done = subprocess.run(["python3", str(SCRIPT), "cache-dir", *args], cwd=cwd,
                          env={"HOME": str(home), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    return done.returncode, done.stdout.strip(), done.stderr


def init(parent, name):
    repo = parent / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


@pytest.mark.parametrize("name, key", [("skills", "skills"), ("agent-skills", "skills"),
                                       ("sudoku-kit", "sudoku-kit")])
def test_the_directory_is_the_folded_repo_name_under_the_review_cache(tmp_path, name, key):
    home = tmp_path / "home"
    code, out, err = run(init(tmp_path, name), home)
    assert (code, out) == (0, str(home / ".cache" / "agent-reviews" / key)), err


def test_a_linked_worktree_keys_on_the_repo_not_the_worktree(tmp_path):
    repo = init(tmp_path, "agent-skills")
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "base"], check=True)
    wt = tmp_path / "implement-9"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b", "implement-9", str(wt)], check=True)
    code, out, err = run(wt, tmp_path / "home")
    assert (code, out) == (0, str(tmp_path / "home" / ".cache" / "agent-reviews" / "skills")), err


def test_outside_a_git_repo_it_refuses_rather_than_printing_a_directory(tmp_path):
    code, out, err = run(tmp_path, tmp_path / "home")
    assert code != 0 and out == "" and "git" in err.lower()
