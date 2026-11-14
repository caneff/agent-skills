"""Tests for agent counting (#1770): the box's caps, the process, herdr and
session-file counts behind them, and `_proc_start`'s read of a fake `/proc`.
The `loop.py box` CLI that reads them is tested in `loop_test.py`.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agents  # noqa: E402


@pytest.fixture
def tmp(tmp_path):
    """`tmp_path` as the string the helpers here join paths onto."""
    return str(tmp_path)




def test_box_check_allows_a_dispatch_with_room_on_the_box():
    assert agents.box_check(processes=12, committed_gb=6) == {
        "ok": True, "refusals": []}


def test_box_check_refuses_when_one_more_process_breaks_the_cap():
    got = agents.box_check(processes=28, committed_gb=0)
    assert got["ok"] is False
    assert any("28" in r for r in got["refusals"]), got


def test_box_check_refuses_when_the_committed_caps_break_the_budget():
    got = agents.box_check(processes=2, committed_gb=25)
    assert got["ok"] is False
    assert any("24" in r for r in got["refusals"]), got


def test_box_check_refuses_at_the_process_cap_boundary():
    # The cap is the box's, so the reading it is checked against counts
    # agent processes on the box — a new worker is charged at its peak, so 23
    # leaves room for one more and 24 does not.
    assert agents.box_check(processes=23, committed_gb=0)["ok"] is True
    assert agents.box_check(processes=24, committed_gb=0)["ok"] is False


def test_a_live_worker_keeps_its_fan_out_headroom_against_the_cap():
    # #933: a live worker is one process now and five at its review peak, so
    # 2 live workers on a box measured at 12 project 12+8+5=25 and fit; a
    # 3rd live worker projects 29 against the cap of 28 and is refused.
    assert agents.box_check(12, 0, live=2)["ok"] is True
    got = agents.box_check(12, 0, live=3)
    assert got["ok"] is False
    assert any("12 of review fan-out headroom for 3 live" in r
               for r in got["refusals"]), got


def test_agent_processes_are_counted_by_command_name_not_arguments():
    listing = "bash\nclaude\nnode\nclaude\nchrome\nclaude-hook\n"
    assert agents.count_agent_processes(lambda cmd: (0, listing)) == 2


# The last: a healthy listing with no claude in it. The controller is one,
# so zero means the name did not match, and reading it as zero agents
# would switch the cap off.
@pytest.mark.parametrize("failed", [(1, ""), (0, ""), (1, "bash\nclaude\n"),
                                    (0, "bash\nnode\n" * 95)])
def test_an_unmeasurable_box_is_a_refusal_not_zero_agents(failed):
    with pytest.raises(agents.AgentError) as exc:
        agents.count_agent_processes(lambda cmd: failed)
    assert "count" in str(exc.value) and "--processes" in str(exc.value)


def herdr_listing(*agents):
    """A `herdr agent list` answer: one entry per (session_id, status)."""
    return json.dumps({"result": {"agents": [
        {"name": f"a{i}", "agent_status": status,
         "agent_session": {"value": sid}}
        for i, (sid, status) in enumerate(agents)]}})


def pid_comm_listing(*pids, comm="claude", others=(("9", "bash"),)):
    """A `ps -eo pid,comm` answer: one `claude` line per pid given, plus
    whatever non-claude lines `others` names."""
    lines = [f"{pid} {comm}" for pid in pids]
    lines += [f"{pid} {name}" for pid, name in others]
    return "\n".join(lines) + "\n"


def sessions_map(mapping):
    """A `sessions` stand-in: `{sessionId: pid}` returned as-is, the
    contract `count_working_herdr_agents` reads the registry through."""
    return lambda: dict(mapping)


def test_working_herdr_agents_counts_working_panes_plus_unlisted_pids():
    # sid-A -> pid 100, working; sid-B -> pid 101, idle (matched, not
    # working); pid 102 is a claude process no listed pane resolves to (a
    # subagent or headless run) and fail-closes as working.
    listing = herdr_listing(("sid-A", "working"), ("sid-B", "idle"))
    ps = lambda cmd: (0, pid_comm_listing(100, 101, 102))
    herdr = lambda cmd: (0, listing)
    sessions = sessions_map({"sid-A": 100, "sid-B": 101})
    working, unlisted = agents.count_working_herdr_agents(
        ps=ps, herdr=herdr, sessions=sessions)
    assert (working, unlisted) == (1, 1), (working, unlisted)


def test_an_unresolvable_listed_pane_fails_closed_as_working():
    # sid-A resolves and is working (so the listing is not a total
    # mismatch); sid-B cannot be resolved to any pid at all and fails
    # closed as working rather than being dropped.
    listing = herdr_listing(("sid-A", "working"), ("sid-B", "idle"))
    ps = lambda cmd: (0, pid_comm_listing(100, 101, 102))
    herdr = lambda cmd: (0, listing)
    sessions = sessions_map({"sid-A": 100})
    working, unlisted = agents.count_working_herdr_agents(
        ps=ps, herdr=herdr, sessions=sessions)
    assert (working, unlisted) == (2, 2), (working, unlisted)


def test_a_matched_but_all_idle_listing_is_trusted_at_zero_working():
    listing = herdr_listing(("sid-A", "idle"), ("sid-B", "done"))
    ps = lambda cmd: (0, pid_comm_listing(100, 101))
    herdr = lambda cmd: (0, listing)
    sessions = sessions_map({"sid-A": 100, "sid-B": 101})
    working, unlisted = agents.count_working_herdr_agents(
        ps=ps, herdr=herdr, sessions=sessions)
    assert (working, unlisted) == (0, 0), (working, unlisted)


def test_a_resolved_pane_with_no_or_unknown_status_counts_as_working():
    # A missing agent_status and an unrecognised string are neither
    # "idle" nor "done" — only those two exclude a pane, so both count.
    panes = [
        {"name": "a0", "agent_session": {"value": "sid-A"}},
        {"name": "a1", "agent_status": "wedged",
         "agent_session": {"value": "sid-B"}},
    ]
    listing = json.dumps({"result": {"agents": panes}})
    ps = lambda cmd: (0, pid_comm_listing(100, 101))
    herdr = lambda cmd: (0, listing)
    sessions = sessions_map({"sid-A": 100, "sid-B": 101})
    working, unlisted = agents.count_working_herdr_agents(
        ps=ps, herdr=herdr, sessions=sessions)
    assert (working, unlisted) == (2, 0), (working, unlisted)


def test_a_stale_session_record_does_not_swallow_a_live_unlisted_pid(tmp):
    # sid-A's registry record claims pid 100, but its procStart is stale
    # (pid 100 is now a different, unlisted claude process — a WSL restart
    # or an ordinary pid reuse). sid-B is a genuine, valid match, so the
    # listing is not a total mismatch. Before the fix, the stale record
    # resolved anyway, pid 100 landed in matched_pids, dropped out of
    # unlisted, and sid-A's idle status added nothing — the live process
    # at pid 100 went uncounted entirely.
    with open(os.path.join(tmp, "100.json"), "w") as fh:
        json.dump({"pid": 100, "sessionId": "sid-A", "procStart": "111"}, fh)
    with open(os.path.join(tmp, "101.json"), "w") as fh:
        json.dump({"pid": 101, "sessionId": "sid-B", "procStart": "222"}, fh)
    proc_start = lambda pid: "222" if pid == 101 else "999"
    sessions = lambda: agents._session_pids(tmp, proc_start=proc_start)
    listing = herdr_listing(("sid-A", "idle"), ("sid-B", "working"))
    ps = lambda cmd: (0, pid_comm_listing(100, 101))
    herdr = lambda cmd: (0, listing)
    working, unlisted = agents.count_working_herdr_agents(
        ps=ps, herdr=herdr, sessions=sessions)
    # pid 100 is no longer silently absorbed by sid-A's stale match —
    # it counts, via unlisted; sid-A's own pane fails closed as
    # working too, since it could not be resolved to any pid at all.
    assert unlisted == 1, (working, unlisted)
    assert working == 2, (working, unlisted)


# Empty, and non-empty-but-unresolvable, are the same failure: herdr's
# registry reads as broken, not the box as idle.
@pytest.mark.parametrize("listing", [herdr_listing(),
                                     herdr_listing(("sid-Z", "working"))])
def test_a_herdr_listing_that_matches_none_of_the_boxs_pids_is_a_refusal(listing):
    ps = lambda cmd: (0, pid_comm_listing(100, 101))
    with pytest.raises(agents.AgentError) as exc:
        agents.count_working_herdr_agents(
            ps=ps, herdr=lambda cmd: (0, listing), sessions=sessions_map({}))
    assert "claude pid" in str(exc.value) or "none" in str(exc.value)


@pytest.mark.parametrize("failed", [
    (1, ""), (0, "not json"), (0, json.dumps({"result": {}})),
    (0, json.dumps({"error": {"code": "some_error"}})),
    (0, json.dumps({"result": {"agents": "nope"}}))])
def test_an_unreadable_herdr_listing_is_a_refusal_not_zero_agents(failed):
    ps = lambda cmd: (0, pid_comm_listing(100))
    with pytest.raises(agents.AgentError) as exc:
        agents.count_working_herdr_agents(
            ps=ps, herdr=lambda cmd: failed, sessions=sessions_map({}))
    assert "herdr agent list" in str(exc.value)


@pytest.mark.parametrize("failed", [(1, ""), (0, "")])
def test_working_herdr_agents_refuses_when_ps_pid_listing_cannot_be_taken(failed):
    herdr = lambda cmd: (0, herdr_listing())
    with pytest.raises(agents.AgentError) as exc:
        agents.count_working_herdr_agents(
            ps=lambda cmd: failed, herdr=herdr, sessions=sessions_map({}))
    assert "pid" in str(exc.value)


def test_session_pids_reads_the_registry_directory_given(tmp):
    with open(os.path.join(tmp, "100.json"), "w") as fh:
        json.dump({"pid": 100, "sessionId": "sid-A", "procStart": "111"}, fh)
    # Not a session file; skipped rather than raising.
    with open(os.path.join(tmp, "not-json.json"), "w") as fh:
        fh.write("{not json")
    with open(os.path.join(tmp, "ignored.txt"), "w") as fh:
        fh.write("100")
    proc_start = lambda pid: "111" if pid == 100 else None
    assert agents._session_pids(tmp, proc_start=proc_start) == {"sid-A": 100}


def test_session_pids_drops_a_record_whose_procstart_no_longer_matches(tmp):
    # pid 100 is alive, but `/proc`'s own start-time fingerprint no longer
    # matches the registry record's — a WSL restart or an ordinary pid
    # reuse left a stale record behind, now naming a different process.
    with open(os.path.join(tmp, "100.json"), "w") as fh:
        json.dump({"pid": 100, "sessionId": "sid-A", "procStart": "111"}, fh)
    proc_start = lambda pid: "999"
    assert agents._session_pids(tmp, proc_start=proc_start) == {}


def test_session_pids_on_a_missing_directory_is_an_empty_mapping():
    assert agents._session_pids("/no/such/registry/dir") == {}


def idle_box_listing(agents):
    """~190 OS processes, `agents` of them claude sessions."""
    others = ["bash", "node"] * ((190 - agents) // 2)
    return "\n".join(["claude"] * agents + others) + "\n"


def dual_ps(pid_out, comm_out):
    """A `ps` stand-in for `agent_count`'s two call shapes: `pid,comm` for
    the herdr path, bare `comm=` for the process-count fallback."""
    def ps(cmd):
        return (0, pid_out) if "pid,comm" in cmd else (0, comm_out)
    return ps


def test_agent_count_prefers_herdrs_working_plus_unlisted_over_ps_alone():
    class Args:
        processes = None
    listing = herdr_listing(("sid-A", "working"), ("sid-B", "idle"))
    ps = dual_ps(pid_comm_listing(100, 101, 102),
                "claude\nclaude\nclaude\nbash\n")
    count, counter, working, unlisted = agents.agent_count(
        Args, herdr=lambda cmd: (0, listing), ps=ps,
        sessions=sessions_map({"sid-A": 100, "sid-B": 101}))
    assert (count, working, unlisted) == (2, 1, 1)
    assert agents.box_check(count, 0, counter=counter)["ok"] is True
    assert "herdr" in counter and "working" in counter


def test_agent_count_falls_back_to_the_process_count_when_herdr_cannot_answer():
    class Args:
        processes = None
    idle = idle_box_listing(19)
    count, counter, working, unlisted = agents.agent_count(
        Args, herdr=lambda cmd: (1, "herdr: connection refused"),
        ps=lambda cmd: (0, idle))
    assert count == 19
    assert (working, unlisted) == (None, None)
    assert agents.box_check(count, 0, counter=counter)["ok"] is True
    count, counter, working, unlisted = agents.agent_count(
        Args, herdr=lambda cmd: (1, ""),
        ps=lambda cmd: (0, idle_box_listing(28)))
    refused = agents.box_check(count, 0, counter=counter)
    assert refused["ok"] is False
    assert "28 agent processes" in refused["refusals"][0], refused
    assert "comm=" in refused["refusals"][0], refused
    assert "herdr" in refused["refusals"][0], refused


def test_render_peak_names_the_working_and_unlisted_split():
    line = agents.render_peak(6, 1, 2, working=4, unlisted=2)
    assert "6 agent processes measured" in line
    assert "4 working, 2 unlisted" in line, line


def test_render_peak_omits_the_split_when_not_given():
    line = agents.render_peak(6, 1, 2, working=None, unlisted=None)
    assert "working" not in line and "unlisted" not in line, line
    line = agents.render_peak(6, 1, 2)
    assert "working" not in line and "unlisted" not in line, line


def test_a_processes_override_of_zero_is_used_not_measured():
    class Args:
        processes = 0
    got = agents.agent_count(Args, herdr=lambda cmd: (1, ""),
                           ps=lambda cmd: (1, ""))
    assert got == (0, "passed by --processes", None, None), got


def test_box_check_weighs_every_worker_a_dispatch_would_start():
    # Three workers at once is three processes and three ulimit caps, not
    # one: a gate that asks about one more worker passes a tick that starts
    # three.
    assert agents.box_check(processes=13, committed_gb=0, workers=3)["ok"] is True
    assert agents.box_check(processes=14, committed_gb=0, workers=3)["ok"] is False


def fake_proc(root, pid, comm, start="4242"):
    """A `/proc/<pid>/stat` under `root`: pid, `(comm)`, then fields 3-22,
    field 22 being `start`."""
    os.makedirs(os.path.join(root, str(pid)))
    rest = ["S"] + [str(n) for n in range(4, 22)] + [start, "99", "100"]
    with open(os.path.join(root, str(pid), "stat"), "w") as fh:
        fh.write(f"{pid} ({comm}) " + " ".join(rest) + "\n")


@pytest.mark.parametrize("comm", ["claude", "a b) (c", "x)"])
def test_proc_start_reads_field_22_past_the_last_paren(tmp, comm):
    # A comm with spaces or a `)` of its own would shift every field of a
    # whitespace split; the read splits on the last `)` instead.
    fake_proc(tmp, 100, comm)
    assert agents._proc_start(100, proc_root=tmp) == "4242"


def test_proc_start_is_none_for_a_gone_process(tmp):
    assert agents._proc_start(100, proc_root=tmp) is None


@pytest.mark.parametrize("text", ["100 claude S 4 5\n", "100 (claude) S 4 5\n"])
def test_proc_start_is_none_for_a_stat_it_cannot_read(tmp, text):
    os.makedirs(os.path.join(tmp, "100"))
    with open(os.path.join(tmp, "100", "stat"), "w") as fh:
        fh.write(text)
    assert agents._proc_start(100, proc_root=tmp) is None


def test_session_pids_validates_records_against_a_fake_proc(tmp_path):
    # The registry read end to end through `_proc_start`: a record whose
    # procStart matches the fake `/proc` resolves, a stale one and one
    # whose pid is gone do not.
    proc, reg = tmp_path / "proc", tmp_path / "sessions"
    reg.mkdir()
    fake_proc(str(proc), 100, "claude", start="111")
    fake_proc(str(proc), 101, "claude", start="999")
    for pid, sid in ((100, "sid-A"), (101, "sid-B"), (102, "sid-C")):
        (reg / f"{pid}.json").write_text(json.dumps(
            {"pid": pid, "sessionId": sid, "procStart": "111"}))
    got = agents._session_pids(
        str(reg), proc_start=lambda pid: agents._proc_start(pid, str(proc)))
    assert got == {"sid-A": 100}
