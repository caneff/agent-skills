"""`implement/pr_settle.py`: wait for a PR to read CLEAN, then merge it.

Seam: `settle` and `merge` in-process with a fake clock (the 60 s and 15 min
limits have no real-time witness), and the command line against a fake `gh`
for the exit status and the printed line, which is the contract both callers
(`drain/drain.py`, `implement/SKILL.md` § The merge) read.
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pr_settle  # noqa: E402

sys.path.insert(0, os.path.join(HERE, "..", "common"))
import tracker  # noqa: E402
import owners  # noqa: E402

SHA = "a" * 40


def view(state="CLEAN", draft=False, checks=(), pr_state="OPEN", head=SHA):
    return {"isDraft": draft, "mergeStateStatus": state, "headRefOid": head,
            "state": pr_state, "statusCheckRollup": list(checks)}


def run_check(status="COMPLETED", conclusion="SUCCESS", name="gate"):
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}


class Clock:
    """A fake clock: `sleep` is the only thing that moves time."""
    def __init__(self):
        self.t = 0.0
        self.sleeps = 0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(seconds, 1)  # a zero poll must still advance, or a limit never fires
        self.sleeps += 1


def settle_seq(views, poll=5, ci=lambda: False):
    """Settle against `views` in order, the last one repeating; `ci()` says whether the repo runs
    workflows on pull_request (none, unless a test says so)."""
    clock, reads = Clock(), []

    def read():
        reads.append(1)
        return views[min(len(reads), len(views)) - 1]
    try:
        out = pr_settle.settle(read, sleep=clock.sleep, now=clock.now, poll=poll, ci=ci)
    except pr_settle.SettleError as exc:
        return exc, clock, reads
    return out, clock, reads


def test_clean_with_no_check_yet_waits_in_a_repo_with_a_pull_request_workflow():
    out, clock, reads = settle_seq([view("CLEAN"), view("CLEAN", checks=[run_check()])], ci=lambda: True)
    assert out["statusCheckRollup"] and len(reads) == 2 and clock.sleeps == 1


def test_clean_with_no_check_ever_registering_fails_naming_it():
    exc, clock, _ = settle_seq([view("CLEAN")], ci=lambda: True)
    assert isinstance(exc, pr_settle.SettleError)
    assert "no check registered" in str(exc) and SHA in str(exc)
    assert 60 <= clock.t < 75


def test_clean_with_no_check_is_accepted_at_once_when_no_workflow_runs_on_pull_request():
    out, clock, reads = settle_seq([view("CLEAN")], ci=lambda: False)
    assert out["mergeStateStatus"] == "CLEAN" and len(reads) == 1 and clock.sleeps == 0


def test_a_failed_workflow_lookup_waits_and_never_accepts():
    t = tracker.MemoryTracker(broken={"workflow_texts": "gh: rate limited"})
    exc, _, reads = settle_seq([view("CLEAN")], ci=lambda: pr_settle.runs_on_pull_request(t))
    assert isinstance(exc, pr_settle.SettleError) and "no check registered" in str(exc)
    assert len(reads) > 1


def test_clean_with_every_check_passed_does_not_ask_about_workflows():
    asked = []
    out, _, _ = settle_seq([view("CLEAN", checks=[run_check()])], ci=lambda: asked.append(1) or True)
    assert out["mergeStateStatus"] == "CLEAN" and not asked


def test_clean_with_a_running_check_waits_for_it_in_a_pull_request_repo():
    running = run_check(status="IN_PROGRESS", conclusion=None)
    out, clock, reads = settle_seq([view("CLEAN", checks=[running]), view("CLEAN", checks=[run_check()])],
                                   ci=lambda: True)
    assert out["statusCheckRollup"][0]["status"] == "COMPLETED" and len(reads) == 2 and clock.sleeps == 1


def test_clean_with_a_running_check_is_accepted_when_no_workflow_runs_on_pull_request():
    running = run_check(status="IN_PROGRESS", conclusion=None)
    out, _, reads = settle_seq([view("CLEAN", checks=[running])], ci=lambda: False)
    assert out["mergeStateStatus"] == "CLEAN" and len(reads) == 1


def test_clean_with_a_check_running_past_the_limit_fails_naming_it():
    running = run_check(status="IN_PROGRESS", conclusion=None, name="gate")
    exc, clock, _ = settle_seq([view("CLEAN", checks=[running])], ci=lambda: True)
    assert isinstance(exc, pr_settle.SettleError) and "gate" in str(exc) and "not CLEAN" not in str(exc)
    assert clock.t >= pr_settle.CHECKS_SECONDS


def test_merge_waits_for_a_check_to_register_in_a_pull_request_repo():
    exc, calls, reads = merge_with([(0, "")], views=[view("CLEAN"), view("CLEAN", checks=[run_check()])],
                                   ci=lambda: True)
    assert exc is None and calls == [SHA] and len(reads) == 2


def test_merge_refuses_when_no_check_ever_registers_in_a_pull_request_repo():
    exc, calls, _ = merge_with([(0, "")], views=[view("CLEAN")], ci=lambda: True)
    assert isinstance(exc, pr_settle.SettleError) and "no check registered" in str(exc) and not calls


def test_settle_and_merge_require_the_ci_answer():
    with pytest.raises(TypeError):
        pr_settle.settle(lambda: view())
    with pytest.raises(TypeError):
        pr_settle.merge(lambda: view(), lambda head: (0, ""), SHA)


WF_PR = "name: ci\non:\n  pull_request:\n    branches: [main]\njobs: {}\n"
WF_PUSH = "name: ci\non:\n  push:\n    branches: [main]\n# pull_request is not a trigger here\njobs: {}\n"


@pytest.mark.parametrize("texts,expected", [
    ([WF_PR], True), (["on: pull_request\n"], True), (["on: [push, pull_request]\n"], True),
    (["on:\n  pull_request_target:\n"], True), ([WF_PUSH], False), ([], False),
    (['"on":\n  pull_request:\n'], True),
    (["on:\n  push:  # not pull_request\njobs:\n  a:\n    if: github.event_name == 'pull_request'\n"], False),
    (["on: push\njobs:\n  a:\n    if: github.event_name == 'pull_request'\n"], False),
    (["name: x\njobs: {}\n"], False), ([WF_PUSH, WF_PR], True)])
def test_runs_on_pull_request_reads_the_workflow_triggers(texts, expected):
    t = tracker.MemoryTracker(workflows=texts)
    assert pr_settle.runs_on_pull_request(t) is expected


def test_runs_on_pull_request_is_true_when_the_lookup_fails():
    t = tracker.MemoryTracker(broken={"workflow_texts": "boom"})
    assert pr_settle.runs_on_pull_request(t) is True


def test_clean_returns_at_once():
    out, clock, reads = settle_seq([view("CLEAN")])
    assert out["headRefOid"] == SHA
    assert len(reads) == 1 and clock.sleeps == 0


def test_unknown_is_reread_until_clean():
    out, clock, _ = settle_seq([view("UNKNOWN"), view("UNKNOWN"), view("CLEAN")])
    assert out["mergeStateStatus"] == "CLEAN"
    assert clock.sleeps == 2


def test_unknown_gives_up_after_sixty_seconds_naming_the_state():
    exc, clock, _ = settle_seq([view("UNKNOWN")])
    assert isinstance(exc, pr_settle.SettleError)
    assert "UNKNOWN" in str(exc) and "60" in str(exc)
    assert 60 <= clock.t < 75


def test_unstable_waits_for_running_checks_then_clean():
    running = view("UNSTABLE", checks=[run_check("IN_PROGRESS", "")])
    out, clock, _ = settle_seq([running] * 40 + [view("CLEAN")])
    assert out["mergeStateStatus"] == "CLEAN"
    assert clock.t > 60  # past the unknown limit: the checks are what is awaited


def test_blocked_with_running_checks_gives_up_at_fifteen_minutes():
    running = view("BLOCKED", checks=[run_check("QUEUED", "")])
    exc, clock, _ = settle_seq([running])
    assert isinstance(exc, pr_settle.SettleError)
    assert "BLOCKED" in str(exc) and "900" in str(exc)
    assert 900 <= clock.t < 915


def test_a_failed_check_fails_at_once_even_with_others_running():
    bad = view("UNSTABLE", checks=[run_check("COMPLETED", "FAILURE", "check"),
                                   run_check("IN_PROGRESS", "", "slow")])
    exc, clock, reads = settle_seq([bad])
    assert isinstance(exc, pr_settle.SettleError)
    assert "check" in str(exc) and "failed" in str(exc)
    assert len(reads) == 1 and clock.sleeps == 0


def test_a_failed_status_context_fails():
    bad = view("UNSTABLE", checks=[{"__typename": "StatusContext", "context": "ci", "state": "FAILURE"}])
    exc, _, _ = settle_seq([bad])
    assert isinstance(exc, pr_settle.SettleError) and "ci" in str(exc)


def test_a_completed_check_with_an_unrecognised_conclusion_is_not_a_pass():
    odd = view("UNSTABLE", checks=[run_check("COMPLETED", "MYSTERY", "odd")])
    exc, _, _ = settle_seq([odd])
    assert isinstance(exc, pr_settle.SettleError)
    assert "failed check: odd" in str(exc)  # not the generic "is UNSTABLE, not CLEAN"


def test_a_settled_non_clean_state_fails_at_once():
    for state in ("BEHIND", "DIRTY", "BLOCKED", "UNSTABLE"):
        exc, clock, _ = settle_seq([view(state, checks=[run_check()])])
        assert isinstance(exc, pr_settle.SettleError), state
        assert f"is {state}, not CLEAN" in str(exc)
        assert clock.sleeps == 0


def test_blocked_with_no_checks_yet_gets_the_unknown_window():
    # The push just landed and the rollup has not registered its checks.
    out, clock, _ = settle_seq([view("BLOCKED"), view("BLOCKED"), view("CLEAN")])
    assert out["mergeStateStatus"] == "CLEAN"
    exc, clock, _ = settle_seq([view("BLOCKED")])
    assert isinstance(exc, pr_settle.SettleError) and 60 <= clock.t < 75


def test_a_running_check_does_not_extend_a_state_a_wait_cannot_change():
    running = [run_check("IN_PROGRESS", "")]
    for state in ("DIRTY", "BEHIND"):
        exc, clock, _ = settle_seq([view(state, checks=running)])
        assert isinstance(exc, pr_settle.SettleError) and f"is {state}, not CLEAN" in str(exc)
        assert clock.sleeps == 0, state


def test_unknown_with_a_running_check_still_gets_only_the_unknown_window():
    exc, clock, _ = settle_seq([view("UNKNOWN", checks=[run_check("IN_PROGRESS", "")])])
    assert isinstance(exc, pr_settle.SettleError) and 60 <= clock.t < 75


def test_an_unrecognised_status_context_state_is_a_failure():
    odd = view("UNSTABLE", checks=[{"__typename": "StatusContext", "context": "ci", "state": "MYSTERY"}])
    exc, clock, _ = settle_seq([odd])
    assert isinstance(exc, pr_settle.SettleError) and "failed check: ci" in str(exc)
    assert clock.sleeps == 0


def test_settle_refuses_a_head_other_than_the_one_named():
    clock = Clock()
    with pytest.raises(pr_settle.SettleError, match="head moved"):
        pr_settle.settle(lambda: view("CLEAN", head="b" * 40), head=SHA, sleep=clock.sleep, now=clock.now, ci=lambda: False)


def test_a_draft_fails_at_once():
    exc, clock, _ = settle_seq([view("CLEAN", draft=True)])
    assert isinstance(exc, pr_settle.SettleError) and "draft" in str(exc)
    assert clock.sleeps == 0


def test_a_merged_or_closed_pr_fails_at_once():
    exc, _, _ = settle_seq([view("UNKNOWN", pr_state="MERGED")])
    assert isinstance(exc, pr_settle.SettleError) and "MERGED" in str(exc)


def test_a_read_without_the_rollup_is_not_clean():
    incomplete = {"isDraft": False, "mergeStateStatus": "CLEAN", "headRefOid": SHA, "state": "OPEN"}
    exc, _, _ = settle_seq([incomplete])
    assert isinstance(exc, pr_settle.SettleError) and "statusCheckRollup" in str(exc)


def test_the_error_carries_the_last_view():
    exc, _, _ = settle_seq([view("UNKNOWN")])
    assert exc.view["mergeStateStatus"] == "UNKNOWN" and exc.view["headRefOid"] == SHA


def merge_with(outcomes, views=None, ci=lambda: False):
    """`merge` where the n-th `gh pr merge` returns `outcomes[n]` as (code, text)."""
    clock, calls = Clock(), []
    seq = list(views or [view("CLEAN")])
    reads = []

    def read():
        reads.append(1)
        return seq[min(len(reads), len(seq)) - 1]

    def gh_merge(head):
        calls.append(head)
        return outcomes[min(len(calls), len(outcomes)) - 1]
    try:
        pr_settle.merge(read, gh_merge, SHA, sleep=clock.sleep, now=clock.now, poll=5, ci=ci)
    except pr_settle.SettleError as exc:
        return exc, calls, reads
    return None, calls, reads


BASE = (1, "GraphQL: Base branch was modified. Review and try the merge again. (mergePullRequest)")


def test_merge_succeeds_first_time():
    exc, calls, _ = merge_with([(0, "")])
    assert exc is None and calls == [SHA]


def test_merge_retries_a_base_branch_modified_refusal_then_succeeds():
    exc, calls, reads = merge_with([BASE, BASE, (0, "")])
    assert exc is None and len(calls) == 3
    assert len(reads) >= 3  # settled again before each retry


def test_merge_gives_up_after_three_retries():
    exc, calls, _ = merge_with([BASE])
    assert isinstance(exc, pr_settle.SettleError)
    assert len(calls) == 4  # the first try and three retries
    assert "Base branch was modified" in str(exc)


def test_merge_does_not_retry_another_refusal():
    exc, calls, _ = merge_with([(1, "GraphQL: Pull request is not mergeable")])
    assert isinstance(exc, pr_settle.SettleError) and len(calls) == 1
    assert "not mergeable" in str(exc)


def test_merge_binds_to_the_head_it_was_given():
    exc, calls, _ = merge_with([(0, "")], views=[view("CLEAN", head="b" * 40)])
    assert isinstance(exc, pr_settle.SettleError) and calls == []
    assert "moved" in str(exc)


# -- the gh edges, over the issue module's in-memory adapter (#1786) -----------

def test_the_reader_reads_the_view_through_the_tracker_with_the_extra_fields():
    t = tracker.MemoryTracker(pr_views={7: view("CLEAN")})
    assert pr_settle.gh_reader(7, "o/r", "number", tracker=t)() == view("CLEAN")


def test_a_reader_whose_tracker_cannot_answer_is_a_settle_error_not_a_view():
    t = tracker.MemoryTracker(broken={"pr_view": "gh down"})
    with pytest.raises(pr_settle.SettleError, match="gh pr view failed: gh down"):
        pr_settle.gh_reader(7, "o/r", tracker=t)()


def test_the_merger_squashes_at_the_head_and_reports_zero():
    t = tracker.MemoryTracker()
    assert pr_settle.gh_merger(7, "o/r", tracker=t)(SHA) == (0, "")
    assert t.merges == [(7, SHA)]


def test_the_merger_hands_back_the_refusal_text_the_retry_reads():
    t = tracker.MemoryTracker(broken={"merge": BASE[1]})
    code, text = pr_settle.gh_merger(7, "o/r", tracker=t)(SHA)
    assert code == 1 and pr_settle.BASE_MODIFIED in text


def test_the_ownership_check_passes_the_owner_and_refuses_anyone_else():
    pr_settle.require_own_repo("Me/r", tracker=tracker.MemoryTracker(viewer="me"))
    with pytest.raises(pr_settle.SettleError, match="not the gh login"):
        pr_settle.require_own_repo("o/r", tracker=tracker.MemoryTracker(viewer="me"))


def test_the_ownership_check_passes_an_owner_on_the_owned_list_and_no_other_org():
    pr_settle.require_own_repo("ChinStrap45/r", tracker=tracker.MemoryTracker(viewer="caneff"))
    with pytest.raises(pr_settle.SettleError, match="nor on the owned-owners list"):
        pr_settle.require_own_repo("chinstrap46/r", tracker=tracker.MemoryTracker(viewer="caneff"))


def test_the_ownership_check_refuses_when_the_owned_list_cannot_be_read(monkeypatch, tmp_path):
    monkeypatch.setattr(owners, "OWNERS_FILE", str(tmp_path / "missing"))
    with pytest.raises(pr_settle.SettleError, match="owned-owners list .* cannot be read"):
        pr_settle.require_own_repo("chinstrap45/r", tracker=tracker.MemoryTracker(viewer="caneff"))


def test_the_ownership_check_refuses_when_the_login_cannot_be_read():
    with pytest.raises(pr_settle.SettleError, match="could not read the gh login"):
        pr_settle.require_own_repo("o/r", tracker=tracker.MemoryTracker(broken={"viewer_login": "no auth"}))


FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
st_path = os.environ["FAKE_STATE"]
st = json.load(open(st_path))
a = sys.argv[1:]
if a[:2] == ["api", "user"]:
    if st.get("login") is None:
        sys.stderr.write("gh: not logged in\n"); sys.exit(1)
    print(st["login"])
elif a[:1] == ["api"] and a[-1].endswith("contents/.github/workflows"):
    if st.get("workflows") is None:
        sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
    print(json.dumps([{"type": "file", "name": "ci.yml", "path": ".github/workflows/ci.yml"}]))
elif a[:1] == ["api"] and a[-1].startswith("repos/") and a[-1].count("/") == 2:
    print(json.dumps({"full_name": a[-1][6:]}))
elif a[:1] == ["api"] and a[-1].endswith("contents/.github/workflows/ci.yml"):
    print(st["workflows"])
elif a[:2] == ["pr", "view"]:
    reads = st["views"]
    v = reads[min(st["n"], len(reads) - 1)]
    st["n"] += 1
    json.dump(st, open(st_path, "w"))
    print(json.dumps(v))
elif a[:2] == ["pr", "merge"]:
    st.setdefault("merge_calls", []).append(a)
    code, text = st["merge"][min(len(st["merge_calls"]), len(st["merge"])) - 1]
    json.dump(st, open(st_path, "w"))
    sys.stderr.write(text)
    sys.exit(code)
else:
    sys.exit(2)
'''


@pytest.fixture
def cli(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    state = tmp_path / "state.json"

    def call(views, merge=((0, ""),), *args, login="o", pr="7", repo="o/r", workflows=None):
        state.write_text(json.dumps({"n": 0, "views": views, "merge": merge, "login": login,
                                     "workflows": workflows}))
        env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", FAKE_STATE=str(state), PR_SETTLE_POLL="0")
        r = subprocess.run([sys.executable, os.path.join(HERE, "pr_settle.py"), pr, "--repo", repo, *args],
                           capture_output=True, text=True, env=env)
        return r, json.loads(state.read_text())
    return call


def test_cli_prints_draft_state_and_head_and_exits_zero_on_clean(cli):
    r, _ = cli([view("UNKNOWN"), view("CLEAN")])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"draft=false state=CLEAN head={SHA}"


def test_cli_exits_non_zero_on_a_failed_check_and_still_prints_the_line(cli):
    r, _ = cli([view("UNSTABLE", checks=[run_check("COMPLETED", "FAILURE", "check")])])
    assert r.returncode == 1
    assert r.stdout.strip() == f"draft=false state=UNSTABLE head={SHA}"
    assert "check" in r.stderr


def test_cli_merge_squashes_at_the_head(cli):
    r, st = cli([view("CLEAN")], ((0, ""),), "--head", SHA, "--merge")
    assert r.returncode == 0, r.stderr
    call = st["merge_calls"][0]
    assert call[:3] == ["pr", "merge", "7"] and "--squash" in call
    assert call[call.index("--match-head-commit") + 1] == SHA
    assert call[call.index("--repo") + 1] == "o/r"


def test_cli_merge_retries_base_modified(cli):
    r, st = cli([view("CLEAN")], (BASE, (0, "")), "--head", SHA, "--merge")
    assert r.returncode == 0, r.stderr
    assert len(st["merge_calls"]) == 2


def test_cli_without_merge_still_refuses_a_moved_head(cli):
    r, _ = cli([view("CLEAN", head="b" * 40)], ((0, ""),), "--head", SHA)
    assert r.returncode == 1 and "head moved" in r.stderr


def test_cli_merge_takes_only_a_pr_number(cli):
    r, st = cli([view("CLEAN")], ((0, ""),), "--head", SHA, "--merge", pr="https://github.com/other/x/pull/3")
    assert r.returncode == 2 and "merge_calls" not in st


def test_cli_merge_takes_only_an_owner_slash_name_repo(cli):
    r, st = cli([view("CLEAN")], ((0, ""),), "--head", SHA, "--merge", repo="github.com/o/r")
    assert r.returncode == 1 and "merge_calls" not in st


def test_cli_merge_needs_head(cli):
    r, st = cli([view("CLEAN")], ((0, ""),), "--merge")
    assert r.returncode == 2 and "merge_calls" not in st


def test_cli_merge_refuses_a_repo_the_login_does_not_own(cli):
    r, st = cli([view("CLEAN")], ((0, ""),), "--head", SHA, "--merge", login="someone-else")
    assert r.returncode == 1 and "merge_calls" not in st
    assert "not the gh login" in r.stderr


def test_cli_merge_refuses_when_the_login_cannot_be_read(cli):
    r, st = cli([view("CLEAN")], ((0, ""),), "--head", SHA, "--merge", login=None)
    assert r.returncode == 1 and "merge_calls" not in st
    assert "could not read the gh login" in r.stderr


def test_cli_accepts_clean_with_no_check_when_the_repo_has_no_workflows(cli):
    r, _ = cli([view("CLEAN")])
    assert r.returncode == 0, r.stderr


def test_cli_accepts_clean_with_no_check_when_the_workflows_do_not_run_on_pull_request(cli):
    r, _ = cli([view("CLEAN")], workflows=WF_PUSH)
    assert r.returncode == 0, r.stderr


def test_cli_waits_for_a_check_to_register_in_a_pull_request_repo(cli):
    r, st = cli([view("CLEAN"), view("CLEAN", checks=[run_check()])], workflows=WF_PR)
    assert r.returncode == 0, r.stderr
    assert st["n"] == 2


def test_cli_merge_waits_for_a_check_to_register_in_a_pull_request_repo(cli):
    r, st = cli([view("CLEAN"), view("CLEAN", checks=[run_check()])], ((0, ""),), "--merge", "--head", SHA,
                workflows=WF_PR)
    assert r.returncode == 0, r.stderr
    assert st["n"] >= 2 and len(st["merge_calls"]) == 1
