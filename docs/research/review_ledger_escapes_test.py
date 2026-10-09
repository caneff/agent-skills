"""Tests for the ledger's escape measure (#1401, ADR 0005): a bug fixed on the
default branch within 14 days whose diff touches lines a reviewed PR changed is
an escape of that PR, attributed to the review components its ledger rows show
were skipped. `append --type <axis> --skip-reason` writes the skip row the
ablation needs; `escapes` reads a checkout's history and the ledger.

Every test runs the command line on a throwaway repository, with HOME in a temp
dir, so nothing here reaches the real ~/.cache or the real history."""
import json
import os
import subprocess

import pytest

from review_ledger_support import Env

DAY = 86400
T0 = 1_790_000_000


class Repo(Env):
    """A throwaway origin and clone, the ledger beside them, and the commands that read both."""

    def __init__(self, tmp):
        super().__init__(tmp)
        self.git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.git_env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        origin = self.tmp / "origin.git"
        self.repo = self.tmp / "skills"
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(origin))
        self.git(self.tmp, "clone", "-q", str(origin), str(self.repo))

    def git(self, cwd, *args, when=None):
        env = dict(self.git_env)
        if when is not None:
            env.update(GIT_AUTHOR_DATE=f"{when} +0000", GIT_COMMITTER_DATE=f"{when} +0000")
        done = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
        assert done.returncode == 0, (args, done.stderr)
        return done.stdout.strip()

    def land(self, files, subject, day, body=""):
        """One commit on main, `day` days after T0; `files` maps path -> full text."""
        for name, text in files.items():
            (self.repo / name).write_text(text)
            self.git(self.repo, "add", name)
        message = subject + (f"\n\n{body}" if body else "")
        self.git(self.repo, "commit", "-q", "-m", message, when=T0 + day * DAY)
        return self.git(self.repo, "rev-parse", "HEAD")

    def publish(self):
        self.git(self.repo, "push", "-q", "origin", "main")
        self.git(self.repo, "remote", "set-head", "origin", "main")

    def skip(self, ticket, rtype, reason):
        r = self.run("append", "--repo", "skills", "--ticket", ticket, "--type", rtype, "--skip-reason", reason,
                     "--ledger", self.ledger)
        assert r.returncode == 0, r.stderr

    def escapes(self, *extra):
        r = self.run("escapes", "--repo-dir", self.repo, "--ledger", self.ledger, "--format", "json", *extra)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


class TestAxisSkipRow:
    def test_a_skipped_axis_writes_a_row_with_its_reason_and_no_findings(self, repo):
        repo.skip(11, "standards", "ablation")
        (row,) = repo.rows().values()
        assert (row["type"], row["skip_reason"], row["findings"]) == ("standards", "ablation", [])
        assert row["status"]["fields"]["findings"] == {"status": "skipped", "reason": "ablation"}

    def test_a_skipped_axis_is_not_a_run_that_found_nothing_in_the_report(self, repo):
        repo.skip(11, "standards", "ablation")
        r = repo.run("report", "--ledger", repo.ledger, "--format", "json")
        assert r.returncode == 0, r.stderr
        (std,) = [t for t in json.loads(r.stdout)["types"] if t["type"] == "standards"]
        assert (std["skipped_rows"], std["unknown_finding_rows"], std["findings"]) == (1, 0, 0)

    @pytest.mark.parametrize("extra", [["--skip-reason", "  "], ["--skip-reason", "x", "--cache", "TMP"],
                                       ["--skip-reason", "x", "--refusal", "y"]])
    def test_an_empty_reason_or_a_cache_alongside_it_is_refused(self, repo, extra):
        extra = [str(repo.tmp) if a == "TMP" else a for a in extra]
        r = repo.run("append", "--repo", "skills", "--ticket", 11, "--type", "spec", *extra,
                     "--ledger", repo.ledger)
        assert r.returncode == 2, extra
        assert not repo.ledger.exists()

    def test_verification_cannot_be_skipped_it_is_not_a_review_axis(self, repo):
        r = repo.run("append", "--repo", "skills", "--ticket", 11, "--type", "verification", "--skip-reason", "x",
                     "--ledger", repo.ledger)
        assert r.returncode == 2
        assert "append --type verification: error: unrecognized arguments: --skip-reason x" in r.stderr


class TestEscape:
    @pytest.fixture
    def repo(self, repo):
        repo.land({"a.py": "a1\na2\na3\na4\na5\na6\n", "b.py": "b1\nb2\nb3\nb4\nb5\nb6\n"}, "base", 0)
        # PR A (ticket 11) rewrites a.py line 2; its ledger shows the standards axis was switched off.
        repo.pr_a = repo.land({"a.py": "a1\nA2\na3\na4\na5\na6\n"}, "a: add the thing (#31)", 1, "Closes #11")
        repo.skip(11, "standards", "ablation")
        # PR B (ticket 12) rewrites b.py line 5; its Codex pass was skipped for size.
        repo.pr_b = repo.land({"b.py": "b1\nb2\nb3\nb4\nB5\nb6\n"}, "b: add the other thing (#32)", 2, "Closes #12")
        repo.skip(12, "codex-gate", "size")
        return repo

    def test_a_fix_within_14_days_touching_a_reviewed_line_is_an_escape_of_that_pr(self, repo):
        fix = repo.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: crash in a.py", 4)
        repo.publish()
        got = repo.escapes()
        assert [(e["ticket"], e["fix"], e["files"]) for e in got["escapes"]] == [(11, fix, ["a.py"])]
        assert got["escapes"][0]["days"] == 3
        assert got["escapes"][0]["skipped"] == ["standards:ablation"]
        assert (got["reviewed"], got["landed"], got["not_landed"]) == (2, 2, [])

    def test_each_skipped_component_reports_its_prs_and_escapes(self, repo):
        repo.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: crash in a.py", 4)
        repo.publish()
        got = repo.escapes()["by_component"]
        assert got == {"standards:ablation": {"prs": 1, "escapes": 1},
                       "codex-gate:size": {"prs": 1, "escapes": 0}}

    def test_a_fix_after_the_window_is_not_an_escape(self, repo):
        repo.land({"b.py": "b1\nb2\nb3\nb4\nLATE\nb6\n"}, "fix: b.py much later", 2 + 20)
        repo.publish()
        assert repo.escapes()["escapes"] == []
        # ... but a window the caller widens catches it.
        assert len(repo.escapes("--days", "30")["escapes"]) == 1

    def test_a_commit_that_is_not_a_fix_or_touches_other_lines_is_not_an_escape(self, repo):
        repo.land({"a.py": "a1\nrefactored\na3\na4\na5\na6\n"}, "refactor: tidy a.py", 4)
        repo.land({"a.py": "a1\nrefactored\na3\na4\nFIXED5\na6\n"}, "fix: an unreviewed base line", 5)
        repo.publish()
        assert repo.escapes()["escapes"] == []

    def test_a_fix_pattern_the_caller_names_replaces_the_default(self, repo):
        repo.land({"a.py": "a1\nPATCHED\na3\na4\na5\na6\n"}, "patch: crash in a.py", 4)
        repo.publish()
        assert repo.escapes()["escapes"] == []
        assert len(repo.escapes("--fix-pattern", "^patch")["escapes"]) == 1

    def test_a_reviewed_ticket_that_never_landed_is_named_not_counted_as_clean(self, repo):
        repo.skip(99, "spec", "ablation")
        repo.publish()
        got = repo.escapes()
        assert got["not_landed"] == [99]
        assert got["reviewed"] == 3
        assert got["landed"] == 2

    def test_a_file_name_with_a_space_or_non_ascii_letters_is_attributed_not_fatal(self, repo):
        # #1401 C3: names come from `--name-only -z`, not from a patch header.
        repo.land({"Sticker Final é.json": "x1\nx2\nx3\n"}, "c: add the sticker (#33)", 3, "Closes #13")
        repo.skip(13, "spec", "ablation")
        repo.land({"Sticker Final é.json": "x1\nFIX\nx3\n"}, "fix: sticker", 4)
        repo.publish()
        got = repo.escapes()
        assert [(e["ticket"], e["files"]) for e in got["escapes"]] == [(13, ["Sticker Final é.json"])]

    def test_a_removed_line_that_looks_like_a_patch_header_is_not_misread(self, repo):
        repo.land({"d.txt": "d1\n-- not a header\nd3\n"}, "d: add (#34)", 3, "Closes #14")
        repo.skip(14, "spec", "ablation")
        repo.land({"d.txt": "d1\nFIXED\nd3\n"}, "fix: d", 4)
        repo.publish()
        assert [e["files"] for e in repo.escapes()["escapes"]] == [["d.txt"]]

    def test_a_fix_that_only_inserts_lines_is_attributed_to_the_lines_around_it(self, repo):
        repo.land({"a.py": "a1\nA2\ninserted\na3\na4\na5\na6\n"}, "fix: missing guard in a.py", 4)
        repo.publish()
        assert [e["ticket"] for e in repo.escapes()["escapes"]] == [11]

    def test_a_landing_is_found_by_the_ticket_in_its_subject_when_the_body_has_no_closes(self, repo):
        repo.land({"e.py": "e1\ne2\ne3\n"}, "e: add the thing (#15) (#35)", 3)
        repo.skip(15, "spec", "ablation")
        repo.land({"e.py": "e1\nFIXED\ne3\n"}, "fix: e", 4)
        repo.publish()
        got = repo.escapes()
        assert ([e["ticket"] for e in got["escapes"]], got["not_landed"]) == ([15], [])

    def test_the_oldest_landing_is_the_pr_and_a_later_mention_is_a_follow_up(self, repo):
        # The follow-up commit says `Closes #11` too, later; blame points at the first landing.
        repo.land({"a.py": "a1\nA2\na3\na4\na5\na6\n", "g.txt": "g\n"}, "g: follow-up (#36)", 3, "Closes #11")
        repo.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: a.py", 4)
        repo.publish()
        (e,) = repo.escapes()["escapes"]
        assert (e["ticket"], e["landing"]) == (11, repo.pr_a)

    def test_a_merge_commit_is_not_a_fix_commit(self, repo):
        repo.git(repo.repo, "checkout", "-q", "-b", "side")
        repo.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "side work", 4)
        repo.git(repo.repo, "checkout", "-q", "main")
        repo.land({"z.txt": "z\n"}, "z: unrelated", 5)
        repo.git(repo.repo, "merge", "-q", "--no-ff", "-m", "fix: merge the side branch", "side", when=T0 + 6 * DAY)
        repo.publish()
        assert repo.escapes()["escapes"] == []

    def test_a_sweep_commit_is_not_an_escape_whatever_its_subject_says(self, repo):
        repo.land({"a.py": "a1\nSWEPT\na3\na4\na5\na6\n"}, "Sweep: fix leftovers from burn x", 4)
        repo.publish()
        assert repo.escapes()["escapes"] == []

    def test_components_are_named_by_a_known_reason_and_free_text_is_one_other(self, repo):
        repo.skip(16, "codex-gate", "codex usage 71% at or above reserve ceiling 70%, resets 2026-10-05")
        repo.land({"h.txt": "h\n"}, "h (#37)", 3, "Closes #16")
        repo.publish()
        assert "codex-gate:other" in repo.escapes()["by_component"]

    def test_origin_is_fetched_first_so_a_fix_pushed_from_elsewhere_counts(self, repo):
        other = repo.tmp / "elsewhere"
        repo.git(repo.tmp, "clone", "-q", str(repo.tmp / "origin.git"), str(other))
        repo.publish()  # PR A and B are on origin; the fix arrives only through `other`
        repo.git(other, "pull", "-q", "origin", "main")
        (other / "a.py").write_text("a1\nFIXED\na3\na4\na5\na6\n")
        repo.git(other, "add", "a.py")
        repo.git(other, "commit", "-q", "-m", "fix: a.py", when=T0 + 4 * DAY)
        repo.git(other, "push", "-q", "origin", "main")
        r = repo.run("escapes", "--repo-dir", repo.repo, "--ledger", repo.ledger, "--format", "json", "--no-fetch")
        assert json.loads(r.stdout)["escapes"] == []  # origin as this checkout last saw it
        assert len(repo.escapes()["escapes"]) == 1  # fetched first

    def test_a_git_failure_is_refused_not_counted_as_fewer_escapes(self, repo):
        repo.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: crash in a.py", 4)
        repo.publish()
        repo.git(repo.repo, "remote", "set-url", "origin", str(repo.tmp / "no-such.git"))
        r = repo.run("escapes", "--repo-dir", repo.repo, "--ledger", repo.ledger)
        assert r.returncode == 2
        assert "git fetch" in r.stderr

    def test_no_default_branch_recorded_is_refused_by_name(self, repo):
        r = repo.run("escapes", "--repo-dir", repo.repo, "--ledger", repo.ledger)
        assert r.returncode == 2
        assert "origin/HEAD" in r.stderr

    def test_a_missing_ledger_is_refused_not_read_as_no_escapes(self, repo):
        repo.publish()
        r = repo.run("escapes", "--repo-dir", repo.repo, "--ledger", repo.tmp / "none.jsonl")
        assert r.returncode == 2

    def test_markdown_output_names_the_decision_rule_inputs(self, repo):
        repo.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: crash in a.py", 4)
        repo.publish()
        r = repo.run("escapes", "--repo-dir", repo.repo, "--ledger", repo.ledger)
        assert r.returncode == 0, r.stderr
        assert "| standards:ablation | 1 | 1 |" in r.stdout
        assert "1 escape(s)" in r.stdout
