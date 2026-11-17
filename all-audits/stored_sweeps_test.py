"""`stored_sweeps`' tracker calls, run against `MemoryTracker` instead of a fake `gh` (#1879)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
import stored_sweeps  # noqa: E402
import tracker  # noqa: E402


def mem(monkeypatch, **kw):
    t = tracker.MemoryTracker(**kw)
    monkeypatch.setattr(stored_sweeps, "new_tracker", lambda slug=None: t)
    return t


def test_repo_identity_accepts_the_owner_and_refuses_another(monkeypatch, tmp_path):
    mem(monkeypatch, identity=("caneff", "r"))
    assert stored_sweeps.repo_identity(str(tmp_path)) == ("caneff/r", None)
    mem(monkeypatch, identity=("someone", "r"))
    assert stored_sweeps.repo_identity(str(tmp_path)) == (None, "owner is someone, not caneff")
    mem(monkeypatch, broken={"repo_identity": "gh down"})
    slug, why = stored_sweeps.repo_identity(str(tmp_path))
    assert slug is None and "gh down" in why


def test_label_refusal_reads_the_repos_label_names(monkeypatch):
    mem(monkeypatch, labels_defined=["needs-triage"])
    assert stored_sweeps.label_refusal("caneff/r", "needs-triage") is None
    assert "missing" in stored_sweeps.label_refusal("caneff/r", "other")
    mem(monkeypatch, broken={"label_names": "gh down"})
    assert "gh down" in stored_sweeps.label_refusal("caneff/r", "needs-triage")


def test_open_specs_of_names_the_open_issues_that_carry_the_sweep_line(monkeypatch, tmp_path):
    sweep = str(tmp_path / "repo" / "sweep-1")
    body = f"Sweep run: /x/{os.path.basename(os.path.dirname(sweep))}/sweep-1\n"
    mem(monkeypatch, issues=[
        {"number": 4, "state": "open", "body": body, "labels": []},
        {"number": 5, "state": "open", "body": "unrelated", "labels": []},
        {"number": 6, "state": "closed", "body": body, "labels": []}])
    assert stored_sweeps.open_specs_of(sweep, {"repo": "caneff/repo"}) == ([4], None)


def test_file_audit_record_files_the_issue_and_posts_the_rest_as_comments(monkeypatch, tmp_path):
    t = mem(monkeypatch, issues=[{"number": 1, "state": "open", "body": "", "labels": []}])
    stored = tmp_path / "stored"
    stored.mkdir()
    url, error = stored_sweeps.file_audit_record(str(stored), "Audit record: r s", "needs-triage",
                                                 ["first", "second"], {"repo": "caneff/r"})
    assert error is None and url.endswith("/issues/2")
    assert t.issue(2)["body"] == "first" and t.comments == [(2, "second")]
    assert [c["body"] for c in t.issue_view(2, "comments")["comments"]] == ["second"]
