"""`implement/pr_settle.py`: wait for a PR to read CLEAN, then merge it (#1526).

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


def settle_seq(views, poll=5):
    """Settle against `views` in order, the last one repeating."""
    clock, reads = Clock(), []

    def read():
        reads.append(1)
        return views[min(len(reads), len(views)) - 1]
    try:
        out = pr_settle.settle(read, sleep=clock.sleep, now=clock.now, poll=poll)
    except pr_settle.SettleError as exc:
        return exc, clock, reads
    return out, clock, reads


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


# -- merge -----------------------------------------------------------------

def merge_with(outcomes, views=None):
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
        pr_settle.merge(read, gh_merge, SHA, sleep=clock.sleep, now=clock.now, poll=5)
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


# -- the command line ------------------------------------------------------

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
st_path = os.environ["FAKE_STATE"]
st = json.load(open(st_path))
a = sys.argv[1:]
if a[:2] == ["api", "user"]:
    if st.get("login") is None:
        sys.stderr.write("gh: not logged in\n"); sys.exit(1)
    print(st["login"])
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

    def call(views, merge=((0, ""),), *args, login="o"):
        state.write_text(json.dumps({"n": 0, "views": views, "merge": merge, "login": login}))
        env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", FAKE_STATE=str(state))
        r = subprocess.run([sys.executable, os.path.join(HERE, "pr_settle.py"), "7", "--repo", "o/r",
                            "--poll", "0", *args], capture_output=True, text=True, env=env)
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
