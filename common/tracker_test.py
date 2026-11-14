import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import tracker  # noqa: E402


def issue(n, labels=(), **extra):
    return {"number": n, "title": f"t{n}", "state": "open", "body": "", "assignees": [],
            "labels": [{"name": x} for x in labels], **extra}


def test_labels_reads_names_from_a_rest_or_view_issue():
    assert tracker.labels(issue(1, ["a", "b"])) == {"a", "b"}
    assert tracker.labels(issue(1)) == set()


@pytest.mark.parametrize("bad", [{}, {"labels": None}, {"labels": "a"}, {"labels": [{"id": 1}]}],
                         ids=["absent", "null", "string", "nameless"])
def test_labels_refuses_an_issue_that_does_not_say_its_labels(bad):
    with pytest.raises(tracker.TrackerError, match="labels"):
        tracker.labels(bad)


def test_memory_tracker_lists_open_issues_by_label():
    t = tracker.MemoryTracker([issue(1, ["x"]), issue(2, ["y"]), issue(3, ["x"], state="closed")])
    assert [i["number"] for i in t.issues("x")] == [1]
    assert t.claimed() == []


def test_claimed_is_the_in_progress_label():
    t = tracker.MemoryTracker([issue(1, ["in-progress"]), issue(2, ["ready-for-agent"])])
    assert [i["number"] for i in t.claimed()] == [1]


def test_memory_tracker_records_comments_and_merges():
    t = tracker.MemoryTracker([issue(1)], viewer="me")
    t.comment(1, "hi")
    t.merge(9, "abc")
    assert t.comments == [(1, "hi")] and t.merges == [(9, "abc")] and t.viewer_login() == "me"


def test_memory_tracker_parent_and_state_and_prs():
    t = tracker.MemoryTracker([issue(1, parent=2), issue(2)], prs=[{"number": 5, "url": "u", "head": "b"}])
    assert t.parent_link(issue(1))["number"] == 2
    assert t.parent_link(issue(2)) is None
    assert t.state(2) == "open" and t.state(99) is None
    assert t.open_prs("b") == [{"number": 5, "url": "u"}]
    assert t.open_prs("zzz") == []


def test_memory_tracker_unreadable_things_raise_like_gh():
    t = tracker.MemoryTracker([issue(1)], broken={"claimed": "gh down"})
    with pytest.raises(tracker.TrackerError, match="gh down"):
        t.claimed()


# The gh adapter, driven through a fake `gh` binary on PATH (the one contract test).
@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    log = tmp_path / "calls"
    script = tmp_path / "gh"
    script.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\n"
        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "a = sys.argv[1:]\n"
        "if os.environ.get('FAKE_GH_FAIL'):\n    sys.stderr.write('boom'); sys.exit(1)\n"
        "if a[:2] == ['pr', 'list']:\n    print(json.dumps([{'number': 5, 'url': 'u'}]))\n"
        "elif a[:2] == ['api', 'user']:\n    print('me')\n"
        "elif a[:2] == ['api', '--paginate']:\n    print(json.dumps([[{'number': 1, 'labels': []}]]))\n"
        "elif a[:2] == ['issue', 'comment']:\n    pass\n"
        "elif a[:2] == ['pr', 'merge']:\n    pass\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    return lambda: [json.loads(x) for x in log.read_text().splitlines()]


def test_gh_adapter_contract(fake_gh):
    t = tracker.GhTracker("o/r")
    assert [i["number"] for i in t.claimed()] == [1]
    assert t.open_prs("b") == [{"number": 5, "url": "u"}]
    assert t.viewer_login() == "me"
    t.comment(1, "hello")
    t.merge(5, "abc")
    calls = fake_gh()
    assert any("labels=in-progress" in c[-1] for c in calls)
    assert ["issue", "comment", "1", "--repo", "o/r", "--body", "hello"] in calls
    assert ["pr", "merge", "5", "--repo", "o/r", "--squash", "--match-head-commit", "abc"] in calls


def test_gh_adapter_failure_is_a_tracker_error(fake_gh, monkeypatch):
    monkeypatch.setenv("FAKE_GH_FAIL", "1")
    with pytest.raises(tracker.TrackerError, match="boom"):
        tracker.GhTracker("o/r").claimed()
    with pytest.raises(tracker.TrackerError):
        tracker.GhTracker("o/r").viewer_login()
