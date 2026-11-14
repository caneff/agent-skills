"""The review cache's key: where a repo's review files live (#1774).

`~/.cache/agent-reviews/<repo>/` holds every sidecar, ledger row source, Codex
record and dispositions file of one repo. `<repo>` is the repo's own name off
the common `.git` directory (never the worktree's), folded by `fold_repo`. This
module is the one place that rule is written; the ledger, counts, fix-check,
codex-audit, the brief renderers and the tally import it from here.
"""
import os
import re
import subprocess
from pathlib import Path

REVIEWS_ROOT = Path.home() / ".cache" / "agent-reviews"

# agent-skills is the same repo as skills, checked out under two directory
# names historically.
REPO_ALIASES = {
    "agent-skills": "skills",
}


class CacheDirError(Exception):
    """The repo whose cache directory was asked for cannot be named."""


def fold_repo(repo_dir: str) -> str:
    """Fold known aliases onto one canonical repo name."""
    return REPO_ALIASES.get(repo_dir, repo_dir)


def repo_for_checkout(cwd: Path | str, env: dict | None = None) -> str:
    """The folded repo name of the checkout at `cwd`: the directory holding the common `.git`."""
    done = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd,
                          capture_output=True, text=True, env=env)
    if done.returncode != 0:
        raise CacheDirError(f"git cannot name the repo of {cwd}: {done.stderr.strip() or 'no output'}")
    return fold_repo(os.path.basename(os.path.dirname(done.stdout.strip())))


def cache_dir_for(cwd: Path | str, env: dict | None = None) -> Path:
    """The review cache directory of the repo `cwd` is in."""
    return REVIEWS_ROOT / repo_for_checkout(cwd, env)


def dispositions_path(reviews_dir: Path | str, lowest) -> str:
    """The dispositions sidecar of clump `<lowest>` under `reviews_dir`."""
    return os.path.join(reviews_dir, f"dispositions-{lowest}.jsonl")


def write_cache_file(repo: str, stem: str, text: str) -> Path:
    """Write `text` to `<REVIEWS_ROOT>/<repo>/<stem>.md` and return the path, taking `<stem>-2.md`,
    `-3`, ... when the name is held: `O_EXCL` is the never-overwrite. `repo` is already folded; a
    character of `stem` outside `[A-Za-z0-9._-]` becomes `-`, so a branch name cannot name a directory."""
    directory = REVIEWS_ROOT / repo
    directory.mkdir(parents=True, exist_ok=True)
    stem, k = re.sub(r"[^A-Za-z0-9._-]", "-", stem), 1
    while True:
        path = directory / (f"{stem}.md" if k == 1 else f"{stem}-{k}.md")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            k += 1
            continue
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        return path
