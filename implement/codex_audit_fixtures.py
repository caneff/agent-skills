"""Fixtures shared by the Codex audit's test files (#1405 S5): the git
identity, the ledger skip row as `review_ledger.py append --skip-reason`
writes it, the fabricated-repo helpers, and `AuditEnv`, the whole
`codex-audit.py` test environment, so the skip-row shape lives in one test
place. Not a suite: `tests/all.sh` discovers only `*_test.py`."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "codex-audit.py"

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
    """Mixin for a plain test-environment class holding `self.env` (the git identity) and `self.repo` (a checkout)."""

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


# A `gh` that answers `issue view <n>` with FAKE_ISSUES[n] whole, whatever `--json` fields are asked
# for, and fails on any other command or ticket, so a call the script was not meant to make shows up.
FAKE_GH = """#!{py}
import json, os, sys
a = sys.argv[1:]
issues = json.loads(os.environ.get("FAKE_ISSUES", "{{}}"))
if a[:2] == ["issue", "view"] and a[2] in issues:
    print(json.dumps(issues[a[2]]))
    sys.exit(0)
print("fake gh: no answer for " + " ".join(a), file=sys.stderr)
sys.exit(1)
"""
# A `codex` that never answers, so the gate's live `--percent` read is `unknown`, never a real RPC.
FAKE_CODEX = "#!/bin/sh\nexit 1\n"

TRIAL_HEAD = """# Codex adversarial-review trial (#812)

**Audit marks (#1362).** One line per audited repo.

{marks}

| Ticket | PR | codex-only, confirmed | also found by Claude | disputed | codex-only confirmed findings |
|---|---|---|---|---|---|
| #814 | #816 | 1 | 2 | 1 | a row |
"""

def usage_cache(pct):
    now = time.time()
    return {"fetchedAt": now,
            "primary": {"usedPercent": pct, "windowDurationMins": 10080, "resetsAt": now + 3 * 86400},
            "secondary": None}


class AuditEnv(GitRepoCase):
    """The environment `codex-audit.py` tests run in, built under `tmp` (a `tmp_path`): a git repo
    `skills` with an origin, a fake `gh` and `codex` on PATH, a CODEX_HOME holding a usage cache at 40 %,
    an empty ledger, a cache dir and a trial doc with one audit mark. Nothing reaches the real ~/.cache.

    Use from any directory's test (put `implement/` on sys.path first):
        from codex_audit_fixtures import AuditEnv
        env = AuditEnv(tmp_path)   # then env.merge(...), env.run_audit(...), env.git(...), env.rows()
    """

    def __init__(self, tmp):
        self.tmp = tmp
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, text in (("gh", FAKE_GH.format(py=sys.executable)), ("codex", FAKE_CODEX)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        self.codex_home = self.tmp / "codex-home"
        self.codex_home.mkdir()
        self.issues = {}
        self.env = {**os.environ, **GIT_ENV, "HOME": str(self.tmp), "CODEX_HOME": str(self.codex_home),
                    "PATH": f"{self.bin}:{os.environ['PATH']}"}
        self.repo = self.tmp / "skills"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", "https://github.com/caneff/skills.git")
        self.root = self.commit("root", "2026-09-01T00:00:00+00:00")
        self.ledger = self.tmp / "ledger.jsonl"
        self.ledger.write_text("")
        self.cache = self.tmp / "cache"
        self.trial = self.tmp / "trial.md"
        self.set_mark(f"- skills: 2026-09-01 {self.root}")
        self.set_usage(40)

    def merge(self, pr, ticket, path, date):
        """A squash merge as GitHub writes it, touching `path`; its ticket is readable through `gh`."""
        self.issues[str(ticket)] = {"body": f"Ticket {ticket} asks for {path}.", "comments": []}
        return self.commit(f"Work for {ticket} (#{pr})\n\nCloses #{ticket}\n", date, path)

    def set_mark(self, line):
        self.trial.write_text(TRIAL_HEAD.format(marks=line))

    def set_usage(self, pct):
        (self.codex_home / "usage-cache.json").write_text(json.dumps(usage_cache(pct)))

    def kill_switch(self):
        d = self.tmp / ".config" / "agent-skills"
        d.mkdir(parents=True)
        (d / "codex-reviews-off").write_text("")

    def write_ledger(self, rows):
        self.ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def rows(self, kind="codex-audit"):
        return [r for r in map(json.loads, self.ledger.read_text().splitlines()) if r.get("type") == kind]

    def run_audit(self, *extra):
        env = {**self.env, "FAKE_ISSUES": json.dumps(self.issues)}
        return subprocess.run([sys.executable, SCRIPT, "run", "--base", "main", "--ledger", self.ledger,
                               "--cache", self.cache, "--trial", self.trial, "--dry-run", *extra],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def record(self):
        [path] = self.cache.glob("codex-audit-*.json")
        return json.loads(path.read_text())

    def mark(self, *extra):
        return subprocess.run([sys.executable, SCRIPT, "mark", "--trial", self.trial, *extra],
                              cwd=self.repo, env=self.env, capture_output=True, text=True)
