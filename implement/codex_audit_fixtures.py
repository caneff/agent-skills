"""Fixtures shared by the Codex audit's two test files (#1405 S5): the git identity, the ledger skip
row as `review_ledger.py append --skip-reason` writes it, and the fabricated-repo helpers, so the
skip-row shape lives in one test place. Not a suite: `tests/all.sh` discovers only `*_test.py`."""
import os
import subprocess

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def skip_row(ticket, reason, repo="skills", phase="gate"):
    """A ledger row as `review_ledger.py append --skip-reason` writes it (the fields the scripts read)."""
    return {"row_id": f"{repo}/{ticket}/codex-{phase}/1/codex-skipped-{ticket}-{phase}", "origin": "append",
            "repo": repo, "ticket": ticket, "tickets": [ticket], "type": f"codex-{phase}", "findings": [],
            "skip_reason": reason,
            "status": {"fields": {"findings": {"status": "skipped", "reason": reason}}}}


class GitRepoCase:
    """Mixin for a unittest case holding `self.env` (the git identity) and `self.repo` (a checkout)."""

    def git(self, *args, date=None):
        env = {**self.env, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {})}
        return subprocess.run(["git", *args], cwd=self.repo, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, message, date, path="f"):
        """A commit rewriting `path` with `message`, dated `date`; its sha."""
        (self.repo / path).write_text(message)
        self.git("add", path)
        self.git("commit", "-q", "-m", message, date=date)
        return self.git("rev-parse", "HEAD")
