#!/usr/bin/env python3
"""Tests for `gitcmd.py` (#1405 S6): the one git helper of the Codex audit's scripts."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from gitcmd import GitError, git


class GitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = Path.cwd()
        self.addCleanup(lambda: os.chdir(self.cwd))
        os.chdir(self._tmp.name)
        subprocess.run(["git", "init", "-q"], check=True)

    def test_success_returns_the_result(self):
        self.assertEqual(git("rev-parse", "--is-inside-work-tree").stdout.strip(), "true")

    def test_a_failure_raises_with_the_command_and_stderr(self):
        with self.assertRaises(GitError) as e:
            git("rev-parse", "--verify", "nope")
        self.assertTrue(str(e.exception).startswith("git rev-parse --verify nope: "), str(e.exception))

    def test_an_exit_named_as_an_answer_is_returned_and_any_other_still_raises(self):
        self.assertEqual(git("rev-parse", "--verify", "--quiet", "nope^{commit}", ok=(0, 1)).returncode, 1)
        with self.assertRaises(GitError):  # exit 129 is a usage error, not the answer 1
            git("merge-base", "--no-such-flag", ok=(0, 1))
        with self.assertRaises(GitError):
            git("merge-base", "--is-ancestor", "nope", "nope2", ok=(0, 1))  # exit 128: not a commit


if __name__ == "__main__":
    unittest.main()
