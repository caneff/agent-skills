#!/usr/bin/env python3
"""End-to-end test for spec #1457: an integration branch per spec, with one
review for the whole spec.

One spec's life through the entry points a worker and a controller reach, in
a throwaway repo whose `origin` is a bare clone, with a fake `gh` and the
review cache under a fake HOME:

- a slice on `spec-3` (its base recorded as dispatch records it) passes the
  pre-report gate with no review files, and the merge check refuses its PR
  once it targets `main` instead of `spec-3`;
- the slice lands on `origin/spec-3`, and `main` moves on meanwhile;
- `closing_ticket.py` writes the integration PR's section, naming
  `origin/main...spec-3` and no sha list, and its keep-current block, run as
  written in the spec run's workspace, takes the slice in and merges `main`;
- the spec review is keyed on #3: the pre-report gate on `spec-3` refuses an
  undisposed finding, and with every finding disposed it and the
  controller's `fix-check.sh 3 origin/spec-3` pass.

What a green run does NOT cover (the seam is blind to it):
- `implement-dispatch --spec` cutting `spec-<n>`, a slice's workspace
  branching from it, and `merge-cleanup` treating a slice merged into
  `spec-<n>` as landed: those are the Rust lane's, driven by
  `flow/lane/tests/implement_dispatch.rs` and `merge_cleanup.rs` under the
  same `bash tests/all.sh`, not here;
- GitHub itself: a slice PR opened with base `spec-<n>`, and the integration
  PR into `main` closing every slice and the spec. The fake `gh` stands in
  for both, so they are checked by opening the real thing;
- whether a spec run, a slice worker or the fix worker follows the prose in
  `implement-spec/SKILL.md` and `implement/SKILL.md`.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "implement" / "pre-report-gate.sh"
FIX_CHECK = ROOT / "implement" / "fix-check.sh"
CLOSING = ROOT / "implement-spec" / "closing_ticket.py"
IDENT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
AGENTS = """# Fixture

## End-to-end seam

- **Seam**: `bash tests/all.sh`
- **Blind to**: the live GitHub PRs
"""


class SpecLife(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="integration-branch-e2e-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        home, fakebin = os.path.join(self.tmp, "home"), os.path.join(self.tmp, "bin")
        os.makedirs(fakebin)
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env = {**env, **IDENT, "HOME": home, "PATH": fakebin + os.pathsep + env["PATH"]}
        self.prs = os.path.join(self.tmp, "prs")  # the open slice PRs `gh pr list` answers with
        Path(self.prs).write_text("")
        Path(fakebin, "gh").write_text(
            '#!/usr/bin/env bash\n'
            f'if [ "$1 $2" = "pr list" ]; then cat {self.prs}; exit 0; fi\n'
            'echo "fake gh: unexpected $*" >&2; exit 1\n')
        os.chmod(os.path.join(fakebin, "gh"), 0o755)
        origin = os.path.join(self.tmp, "origin.git")
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", origin)
        self.primary = os.path.join(self.tmp, "repo")
        self.git(self.tmp, "clone", "-q", origin, self.primary)
        Path(self.primary, "AGENTS.md").write_text(AGENTS)
        self.commit(self.primary, "base")
        self.git(self.primary, "push", "-q", "origin", "main")
        self.git(self.primary, "remote", "set-head", "origin", "main")
        self.reviews = os.path.join(home, ".cache", "agent-reviews", "repo")
        os.makedirs(self.reviews)
        # The Codex pass skipped by the size gate, on record, for the spec's review.
        Path(home, ".cache", "agent-reviews", "ledger.jsonl").write_text(json.dumps(
            {"repo": "repo", "ticket": 3, "tickets": [3], "type": "codex-gate",
             "status": {"fields": {"findings": {"status": "skipped", "reason": "size"}}}}) + "\n")

    def git(self, cwd, *args):
        done = subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, (args, done.stderr))
        return done.stdout.strip()

    def commit(self, cwd, name, message=None):
        Path(cwd, name).write_text(name)
        self.git(cwd, "add", name)
        self.git(cwd, "commit", "-q", "-m", message or name)
        return self.git(cwd, "rev-parse", "HEAD")

    def run_tool(self, cwd, *cmd):
        done = subprocess.run([str(c) for c in cmd], cwd=cwd, env=self.env, capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def test_a_spec_lands_through_its_integration_branch(self):
        # The spec run's integration branch and workspace, as `implement-dispatch --spec 3` leaves them.
        self.git(self.primary, "push", "-q", "origin", "main:spec-3")
        spec_ws = os.path.join(self.tmp, "spec-3")
        self.git(self.primary, "fetch", "-q", "origin")
        self.git(self.primary, "worktree", "add", "-q", "-b", "spec-3", spec_ws, "origin/spec-3")

        # A slice of #3: branched from origin/spec-3, its base recorded.
        slice_ws = os.path.join(self.tmp, "implement-4")
        self.git(self.primary, "worktree", "add", "-q", "-b", "implement-4", slice_ws, "origin/spec-3")
        self.git(self.primary, "config", "branch.implement-4.base", "spec-3")
        self.commit(slice_ws, "slice-4", "slice 4\n\nCloses #4")
        code, out = self.run_tool(slice_ws, "bash", GATE, "HEAD")
        self.assertEqual(code, 0, out)
        self.assertIn("slice of spec-3, no review wave", out)
        self.assertFalse(os.listdir(self.reviews), "a slice wrote review files")
        Path(self.prs).write_text("40 main\n")
        code, out = self.run_tool(slice_ws, "bash", FIX_CHECK, "4")
        self.assertEqual(code, 1, out)
        self.assertIn("PR #40 from implement-4 targets main, not spec-3", out)
        Path(self.prs).write_text("40 spec-3\n")
        code, out = self.run_tool(slice_ws, "bash", FIX_CHECK, "4")
        self.assertEqual(code, 0, out)

        # The slice lands on origin/spec-3, as its PR's merge does on GitHub; main moves on.
        self.git(slice_ws, "push", "-q", "origin", "HEAD:spec-3")
        Path(self.prs).write_text("")
        self.commit(self.primary, "elsewhere")
        self.git(self.primary, "push", "-q", "origin", "main")

        # The closing check is the integration PR's.
        code, section = self.run_tool(self.primary, "python3", CLOSING, self.primary, "3",
                                      "--surface", "the integration PR on GitHub")
        self.assertEqual(code, 0, section)
        self.assertIn("base `main`, head `spec-3`", section)
        self.assertIn("`origin/main...spec-3`", section)
        self.assertNotIn("cherry-pick", section)

        # Its keep-current block, run as written in the spec run's workspace: the slice comes
        # in, main is merged (never rebased), and the push lands.
        block = section.split("### The spec-level review", 1)[1].split("```\n", 2)[1]
        code, out = self.run_tool(spec_ws, "bash", "-c", block)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git(spec_ws, "rev-parse", "HEAD"), self.git(spec_ws, "rev-parse", "origin/spec-3"))
        reviewed = self.git(spec_ws, "log", "--format=%s", "origin/main...spec-3")
        self.assertIn("slice 4", reviewed)
        self.git(spec_ws, "merge-base", "--is-ancestor", "origin/main", "spec-3")

        # One review keyed on #3, one fix round on spec-3.
        for axis in ("standards", "spec", "correctness"):
            Path(self.reviews, f"findings-{axis}-3.jsonl").write_text(
                json.dumps({"id": "P1", "axis": "spec", "severity": "hard", "file": "f", "title": "t"}) + "\n"
                if axis == "spec" else "")
            Path(self.reviews, f"findings-{axis}-3.done").write_text("")
        Path(self.reviews, "dispositions-3.jsonl").write_text("")
        code, out = self.run_tool(spec_ws, "bash", GATE, "HEAD")
        self.assertEqual(code, 1, out)
        self.assertIn("no disposition for P1", out)
        fix = self.commit(spec_ws, "fix-p1")
        Path(self.reviews, "dispositions-3.jsonl").write_text(
            json.dumps({"id": "P1", "outcome": "fixed", "sha": fix}) + "\n")
        code, out = self.run_tool(spec_ws, "bash", GATE, "HEAD")
        self.assertEqual(code, 0, out)
        self.assertIn("1 findings, each disposed once", out)

        # The controller's merge check on the pushed integration branch.
        self.git(spec_ws, "push", "-q", "origin", "spec-3")
        code, out = self.run_tool(self.primary, "bash", FIX_CHECK, "3", "origin/spec-3")
        self.assertEqual(code, 0, out)
        self.assertIn("1 findings, each disposed once", out)


if __name__ == "__main__":
    unittest.main()
