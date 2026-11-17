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
    assert t.open_prs("b") == [{"number": 5, "url": "u", "baseRefName": None}]
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


# -- the operations #1786's callers need (spec #1730) --------------------------------------------

def test_memory_tracker_answers_pr_and_issue_views_runs_logs_and_comments():
    t = tracker.MemoryTracker(
        [issue(1, body="b", comments=[{"body": "c"}])],
        pr_views={7: {"mergeStateStatus": "CLEAN"}}, pr_comments={7: ["selector: x"]},
        runs=[{"databaseId": 9, "status": "completed"}], logs={9: "FAIL a"})
    assert t.issue_view(1, "body,comments") == {"body": "b", "comments": [{"body": "c"}]}
    assert t.pr_view(7, "mergeStateStatus") == {"mergeStateStatus": "CLEAN"}
    assert t.pr_comments(7) == ["selector: x"]
    assert t.runs("ci.yml", "main") == [{"databaseId": 9, "status": "completed"}]
    assert t.run_failed_log(9) == "FAIL a"


def test_memory_tracker_creates_an_issue_and_hands_back_its_url():
    t = tracker.MemoryTracker([issue(4)], repo="o/r")
    url = t.create_issue("title", "body", ["bug"])
    assert url == "https://github.com/o/r/issues/5"
    assert [i["number"] for i in t.issues("bug")] == [5]


@pytest.mark.parametrize("call", [
    lambda t: t.issue_view(99, "body"), lambda t: t.pr_view(99, "state"), lambda t: t.pr_comments(99),
    lambda t: t.run_failed_log(99)], ids=["issue_view", "pr_view", "pr_comments", "run_log"])
def test_memory_tracker_refuses_what_it_holds_nothing_for(call):
    with pytest.raises(tracker.TrackerError):
        call(tracker.MemoryTracker())


def test_memory_tracker_open_prs_name_their_base():
    t = tracker.MemoryTracker(prs=[{"number": 5, "url": "u", "head": "b", "base": "spec-3"}])
    assert t.open_prs("b") == [{"number": 5, "url": "u", "baseRefName": "spec-3"}]


@pytest.fixture
def scripted_gh(tmp_path, monkeypatch):
    """A `gh` that logs its argv and prints FAKE_GH_OUT, so each adapter call's command line is
    read and a reply of the wrong shape can be fed to it."""
    log = tmp_path / "calls"
    script = tmp_path / "gh"
    script.write_text(
        "#!/usr/bin/env python3\nimport os, sys, json\n"
        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.stdout.write(os.environ.get('FAKE_GH_OUT', ''))\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    return lambda: [json.loads(x) for x in log.read_text().splitlines()]


def test_gh_adapter_reads_views_runs_logs_comments_and_creates_issues(scripted_gh, monkeypatch):
    t = tracker.GhTracker("o/r")
    monkeypatch.setenv("FAKE_GH_OUT", '{"body": "b", "comments": []}')
    assert t.issue_view(3, "body,comments") == {"body": "b", "comments": []}
    monkeypatch.setenv("FAKE_GH_OUT", '{"state": "OPEN"}')
    assert t.pr_view("7", "state") == {"state": "OPEN"}
    monkeypatch.setenv("FAKE_GH_OUT", '{"comments": [{"body": "x"}, {"body": null}]}')
    assert t.pr_comments(7) == ["x", ""]
    monkeypatch.setenv("FAKE_GH_OUT", '[{"databaseId": 1}]')
    assert t.runs("ci.yml", "main") == [{"databaseId": 1}]
    monkeypatch.setenv("FAKE_GH_OUT", "FAIL a\n")
    assert t.run_failed_log(1) == "FAIL a"
    monkeypatch.setenv("FAKE_GH_OUT", "https://github.com/o/r/issues/9\n")
    assert t.create_issue("t", "b", ["bug", "ready-for-agent"]) == "https://github.com/o/r/issues/9"
    calls = scripted_gh()
    assert ["issue", "view", "3", "--repo", "o/r", "--json", "body,comments"] in calls
    assert ["pr", "view", "7", "--repo", "o/r", "--json", "state"] in calls
    assert ["issue", "create", "--repo", "o/r", "--title", "t", "--body", "b",
            "--label", "bug", "--label", "ready-for-agent"] in calls
    assert any(c[:3] == ["run", "list", "--repo"] and "--event" in c and "schedule" in c for c in calls)


@pytest.mark.parametrize("call, reply", [
    (lambda t: t.issue_view(1, "body"), "[1, 2]"), (lambda t: t.pr_view(1, "state"), "[1, 2]"),
    (lambda t: t.pr_comments(1), '{"comments": "x"}'), (lambda t: t.runs("w", "main"), '{"a": 1}')],
    ids=["issue_view", "pr_view", "pr_comments", "runs"])
def test_gh_adapter_refuses_a_reply_of_the_wrong_shape(scripted_gh, monkeypatch, call, reply):
    monkeypatch.setenv("FAKE_GH_OUT", reply)
    with pytest.raises(tracker.TrackerError):
        call(tracker.GhTracker("o/r"))


def test_gh_adapter_refuses_an_empty_run_log_and_an_issue_url_it_cannot_read(scripted_gh, monkeypatch):
    monkeypatch.setenv("FAKE_GH_OUT", "")
    with pytest.raises(tracker.TrackerError, match="no log"):
        tracker.GhTracker("o/r").run_failed_log(1)
    with pytest.raises(tracker.TrackerError, match="no URL"):
        tracker.GhTracker("o/r").create_issue("t", "b", [])


def test_search_prs_hands_back_the_rows_and_refuses_unreadable_output(scripted_gh, monkeypatch):
    monkeypatch.setenv("FAKE_GH_OUT", '[{"repository": {"nameWithOwner": "a/b"}}]')
    assert tracker.GhTracker().search_prs("2026-01-01", 5) == [{"repository": {"nameWithOwner": "a/b"}}]
    monkeypatch.setenv("FAKE_GH_OUT", "not json")
    with pytest.raises(tracker.TrackerError, match="JSONDecodeError.*not json"):
        tracker.GhTracker().search_prs("2026-01-01", 5)


def test_every_gh_adapter_call_goes_through_its_run_seam():
    calls = []

    def run(args):
        calls.append(args)
        return "me\n" if args[:2] == ["api", "user"] else "x\n"

    t = tracker.GhTracker("o/r", run=run)
    t.comment(1, "hi")
    t.merge(5, "abc")
    assert t.viewer_login() == "me"
    assert t.run_failed_log(9) == "x"
    assert t.create_issue("t", "b", []) == "x"
    assert [c[:2] for c in calls] == [["issue", "comment"], ["pr", "merge"], ["api", "user"],
                                      ["run", "view"], ["issue", "create"]]


def test_gh_adapter_refuses_empty_output_where_it_asked_for_pages(scripted_gh, monkeypatch):
    monkeypatch.setenv("FAKE_GH_OUT", "")
    with pytest.raises(tracker.TrackerError, match="pages"):
        tracker.GhTracker("o/r").native_blockers({"number": 2})
    monkeypatch.setenv("FAKE_GH_OUT", "[[]]")
    assert tracker.GhTracker("o/r").native_blockers({"number": 2}) == []


def recording(answers=None):
    calls = []

    def run(args, **kw):
        calls.append((list(args), kw))
        return (answers or {}).get(args[0], "")

    return calls, run


def test_relabel_edits_labels_and_assignee_in_one_call():
    calls, run = recording()
    tracker.GhTracker("o/r", run=run).relabel(7, add=["ready-for-agent"], remove=["in-progress"], unassign="@me")
    assert calls[0][0] == ["issue", "edit", "7", "--repo", "o/r", "--remove-label", "in-progress",
                           "--add-label", "ready-for-agent", "--remove-assignee", "@me"]


def test_memory_relabel_moves_labels_and_drops_the_assignee():
    t = tracker.MemoryTracker([issue(7, ["in-progress", "x"], assignees=[{"login": "me"}, {"login": "z"}])])
    t.relabel(7, add=["ready-for-agent"], remove=["in-progress"], unassign="me")
    assert tracker.labels(t.issue(7)) == {"x", "ready-for-agent"}
    assert t.issue(7)["assignees"] == [{"login": "z"}]
    with pytest.raises(tracker.TrackerError, match="404"):
        t.relabel(99, add=[], remove=[])


def test_closed_events_are_the_closed_events_of_every_page():
    pages = json.dumps([[{"event": "labeled"}, {"event": "closed", "commit_id": "a"}], [{"event": "closed", "commit_id": None}]])
    calls, run = recording({"api": pages})
    assert tracker.GhTracker("o/r", run=run).closed_events(5) == [
        {"event": "closed", "commit_id": "a"}, {"event": "closed", "commit_id": None}]
    assert calls[0][0] == ["api", "--paginate", "--slurp", "repos/o/r/issues/5/events"]
    with pytest.raises(tracker.TrackerError, match="pages"):
        tracker.GhTracker("o/r", run=recording({"api": ""})[1]).closed_events(5)


def test_memory_closed_events_come_from_the_issue_and_none_is_an_empty_answer():
    t = tracker.MemoryTracker([issue(5, events=[{"event": "labeled"}, {"event": "closed", "commit_id": "a"}]), issue(6)])
    assert t.closed_events(5) == [{"event": "closed", "commit_id": "a"}]
    assert t.closed_events(6) == []
    with pytest.raises(tracker.TrackerError, match="404"):
        t.closed_events(9)


def test_repo_identity_reads_the_checkouts_owner_and_name():
    calls, run = recording({"repo": '{"owner": {"login": "caneff"}, "name": "r"}'})
    assert tracker.GhTracker(run=run).repo_identity("/x/r") == ("caneff", "r")
    assert calls[0] == (["repo", "view", "--json", "owner,name"], {"cwd": "/x/r"})
    for bad in ("", "[]", '{"owner": {}, "name": "r"}', "not json"):
        with pytest.raises(tracker.TrackerError):
            tracker.GhTracker(run=recording({"repo": bad})[1]).repo_identity("/x/r")
    assert tracker.MemoryTracker(identity=("caneff", "r")).repo_identity("/any") == ("caneff", "r")


def test_label_names_lists_the_repos_labels():
    calls, run = recording({"label": '[{"name": "a"}, {"name": "b"}]'})
    assert tracker.GhTracker("o/r", run=run).label_names() == {"a", "b"}
    assert calls[0][0] == ["label", "list", "--repo", "o/r", "--limit", "1000", "--json", "name"]
    with pytest.raises(tracker.TrackerError):
        tracker.GhTracker("o/r", run=recording({"label": '{"name": "a"}'})[1]).label_names()
    assert tracker.MemoryTracker([], labels_defined=["x"]).label_names() == {"x"}


def test_open_issues_carries_the_chosen_fields_and_the_limit():
    calls, run = recording({"issue": '[{"number": 1, "body": "b"}]'})
    assert tracker.GhTracker("o/r", run=run).open_issues("number,body", 50) == [{"number": 1, "body": "b"}]
    assert calls[0][0] == ["issue", "list", "--repo", "o/r", "--state", "open", "--limit", "50",
                           "--json", "number,body"]
    with pytest.raises(tracker.TrackerError, match="list"):
        tracker.GhTracker("o/r", run=recording({"issue": "{}"})[1]).open_issues("number", 5)
    t = tracker.MemoryTracker([issue(1, body="x"), issue(2, state="closed"), issue(3)])
    assert t.open_issues("number,body", 10) == [{"number": 1, "body": "x"}, {"number": 3, "body": ""}]
    assert len(t.open_issues("number", 1)) == 1


def test_create_issue_and_comment_can_read_their_body_from_a_file(tmp_path):
    calls, run = recording({"issue": "https://github.com/o/r/issues/4\n"})
    t = tracker.GhTracker("o/r", run=run)
    assert t.create_issue_from_file("T", "/b.md", ["l"]) == "https://github.com/o/r/issues/4"
    t.comment_from_file(4, "/c.md")
    assert calls[0][0] == ["issue", "create", "--repo", "o/r", "--title", "T", "--body-file", "/b.md", "--label", "l"]
    assert calls[1][0] == ["issue", "comment", "4", "--repo", "o/r", "--body-file", "/c.md"]
    (tmp_path / "b.md").write_text("body")
    (tmp_path / "c.md").write_text("more")
    m = tracker.MemoryTracker([issue(1)])
    assert m.create_issue_from_file("T", str(tmp_path / "b.md"), ["l"]).endswith("/issues/2")
    assert m.issue(2)["body"] == "body"
    m.comment_from_file(2, str(tmp_path / "c.md"))
    assert m.comments == [(2, "more")]
    with pytest.raises(tracker.TrackerError, match="b.md"):
        m.create_issue_from_file("T", str(tmp_path / "nope" / "b.md"), [])


def test_a_memory_comment_reads_back_through_issue_view():
    t = tracker.MemoryTracker([issue(1)])
    t.comment(1, "first")
    t.comment(1, "second")
    got = t.issue_view(1, "comments")["comments"]
    assert [c["body"] for c in got] == ["first", "second"]
    assert all(c["author"]["login"] == "me" and c["createdAt"] for c in got)
    assert t.comments == [(1, "first"), (1, "second")]


def test_repo_identity_refuses_an_owner_or_name_that_is_not_a_string():
    for bad in ('{"owner": {"login": null}, "name": "r"}', '{"owner": {"login": "c"}, "name": 5}'):
        with pytest.raises(tracker.TrackerError, match="owner and a repo"):
            tracker.GhTracker(run=recording({"repo": bad})[1]).repo_identity("/x/r")


def test_create_issue_from_file_refuses_a_gh_that_prints_no_url():
    with pytest.raises(tracker.TrackerError, match="no URL"):
        tracker.GhTracker("o/r", run=recording({"issue": "\n"})[1]).create_issue_from_file("T", "/b.md", [])


def test_closed_events_refuse_a_page_with_a_malformed_event():
    pages = json.dumps([[{"event": "closed", "commit_id": "a"}, "oops"]])
    with pytest.raises(tracker.TrackerError, match="malformed"):
        tracker.GhTracker("o/r", run=recording({"api": pages})[1]).closed_events(5)


def test_memory_comments_are_stamped_in_posting_order():
    t = tracker.MemoryTracker([issue(1)])
    for body in ("a", "b", "c"):
        t.comment(1, body)
    stamps = [c["createdAt"] for c in t.issue_view(1, "comments")["comments"]]
    assert stamps == sorted(stamps) and len(set(stamps)) == 3
