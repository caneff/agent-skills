#!/usr/bin/env python3
"""Tests for the burn loop (#893). The seams the ticket names: a fixture run
over a stub tracker and a stub agent list, and the resume announce against a
stub messenger. The loop's prose — its step list, its refusals, its stated
consequences — is guarded in `burndown/loop-steps.test.sh`; there is no
harness that runs a skill's own text.
"""
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop  # noqa: E402


def git_stub(branch="main", git_dir="/repo/.git", common_dir="/repo/.git",
             head="origin/main"):
    """Stands in for `git` as the seat check calls it: one answer per
    question, so a test can move exactly one of them."""
    answers = {
        ("rev-parse", "--absolute-git-dir"): git_dir,
        ("rev-parse", "--git-common-dir"): common_dir,
        ("branch", "--show-current"): branch,
        ("symbolic-ref", "--short", "refs/remotes/origin/HEAD"): head,
    }

    def run(args):
        return answers[tuple(args)]
    return run


def test_seat_accepts_a_primary_checkout_on_its_default_branch():
    assert loop.seat(git_stub()) == "main"


def test_seat_accepts_a_default_branch_that_is_not_main():
    assert loop.seat(git_stub(branch="trunk", head="origin/trunk")) == "trunk"


def test_seat_refuses_a_worktree_and_says_why():
    run = git_stub(git_dir="/repo/.git/worktrees/implement-893")
    try:
        loop.seat(run)
    except loop.LoopError as exc:
        assert "worktree" in str(exc), exc
        assert "worker" in str(exc), exc
    else:
        raise AssertionError("a worktree seat must be refused")


def test_seat_refuses_a_branch_that_is_not_the_default():
    try:
        loop.seat(git_stub(branch="implement-893"))
    except loop.LoopError as exc:
        assert "implement-893" in str(exc) and "main" in str(exc), exc
    else:
        raise AssertionError("a non-default branch must be refused")


def test_seat_refuses_a_detached_head():
    try:
        loop.seat(git_stub(branch=""))
    except loop.LoopError as exc:
        assert "detached" in str(exc), exc
    else:
        raise AssertionError("a detached HEAD must be refused")


# The #781 fixture, as the burn actually stood after `#453` landed: `#452`,
# `#457` and `#458` all include `examples/_shared/line-kind.js`, the same file
# parked `#455` holds open in its workspace; `#501` is outside `examples/`
# entirely. Closures as `closure.py` resolves them — the candidates' own files
# plus every file that includes one of them, one hop.
# What the run file holds for a worker that declared it launched no parallel
# job — the explicit answer, which is not the same as no record at all.
NO_JOB = {"state": "none", "cores": 0}

HOT = "examples/_shared/line-kind.js"


def candidates_781():
    return [
        {"tickets": [452], "closure": ["examples/thermo.js", HOT]},
        {"tickets": [457], "closure": ["examples/arrow.js", HOT]},
        {"tickets": [458], "closure": ["examples/whisper.js", HOT]},
        {"tickets": [501], "closure": ["tests/all.sh"]},
    ]


def parked_455():
    return [{"tickets": [455], "workspace": "/w/implement-455",
             "agent": "burn-455", "closure": ["examples/renban.js", HOT],
             "job": NO_JOB}]


def test_a_clump_sharing_a_file_with_a_live_workspace_is_off_the_frontier():
    state = loop.frontier(candidates_781(), parked_455())
    assert [c["tickets"] for c in state["dispatchable"]] == [[501]]
    held = {tuple(h["clump"]["tickets"]): h for h in state["held"]}
    assert sorted(held) == [(452,), (457,), (458,)]
    assert held[(452,)]["workspace"] == "/w/implement-455"
    assert held[(452,)]["over"] == [HOT]


def test_the_freed_slot_goes_outside_the_blocked_family():
    # One slot free, three candidates in the blocked family and one outside.
    # A controller reading only "open, unblocked, unclaimed" dispatches #452
    # into the collision; the loop takes #501.
    assert [c["tickets"] for c in
            loop.refill(candidates_781(), parked_455(), 1)] == [[501]]


def test_refill_fills_every_free_slot_lowest_ticket_first():
    # No wave: two slots free and nothing in flight, so both go at once.
    picked = loop.refill(candidates_781(), [], 2)
    assert [c["tickets"] for c in picked] == [[452], [501]]


def test_picks_names_a_same_tick_collision_and_its_picked_blocker():
    # #970's own evidence: `closure.py --json` piped a hub family (452, 457,
    # 458) and one independent ticket (501) into `dispatch --free 4` with
    # nothing in flight. #452 is picked first and takes the hub file; #457
    # and #458 collide with it this same tick and must not vanish silently.
    picked, held = loop.picks(loop.frontier(candidates_781(), []), 4)
    assert [c["tickets"] for c in picked] == [[452], [501]]
    by_ticket = {tuple(h["clump"]["tickets"]): h for h in held}
    assert sorted(by_ticket) == [(457,), (458,)]
    assert by_ticket[(457,)]["holder"] == 452
    assert by_ticket[(457,)]["over"] == [HOT]
    assert by_ticket[(457,)]["same_tick"] is True
    assert "workspace" not in by_ticket[(457,)]


def test_picks_takes_the_widest_closure_first():
    # #1026: two free slots, three independent candidates (no collisions)
    # with closure sizes 1, 4 and 2 in ticket order — the widest goes out
    # first, then the next-widest, ahead of ticket order.
    candidates = [
        {"tickets": [10], "closure": ["a.js"]},
        {"tickets": [20], "closure": ["b.js", "c.js", "d.js", "e.js"]},
        {"tickets": [30], "closure": ["f.js", "g.js"]},
    ]
    picked, held = loop.picks(loop.frontier(candidates, []), 2)
    assert [c["tickets"] for c in picked] == [[20], [30]]
    assert held == []


def test_the_cli_dispatch_names_the_widest_clump_first():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        live = os.path.join(tmp, "live.json")
        with open(cand, "w") as fh:
            json.dump([
                {"tickets": [10], "closure": ["a.js"]},
                {"tickets": [20], "closure": ["b.js", "c.js", "d.js", "e.js"]},
                {"tickets": [30], "closure": ["f.js", "g.js"]},
            ], fh)
        with open(live, "w") as fh:
            json.dump([], fh)
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "2", "--processes", "4", "--committed-gb", "4")
        assert got.returncode == 0, got.stderr
        lines = [line for line in got.stdout.splitlines()
                if line.startswith("dispatch")]
        assert lines == ["dispatch  #20  #20", "dispatch  #30  #30"], got.stdout


def test_the_cli_names_a_same_tick_collision_as_a_held_line():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        live = os.path.join(tmp, "live.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        with open(live, "w") as fh:
            json.dump([], fh)
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "4", "--processes", "4", "--committed-gb", "4")
        assert got.returncode == 0, got
        assert "dispatch  #452" in got.stdout, got.stdout
        assert "dispatch  #501" in got.stdout, got.stdout
        assert "held      #457  by #452 this tick" in got.stdout, got.stdout
        assert "held      #458  by #452 this tick" in got.stdout, got.stdout


def test_refill_takes_nothing_when_no_slot_is_free():
    assert loop.refill(candidates_781(), [], 0) == []


def test_a_landing_frees_its_slot_without_waiting_for_the_other_clump():
    # #501 lands while #455 is still parked: the recomputed frontier is the
    # blocked family, so the freed slot stays empty rather than colliding —
    # and the run drains out of ticket order.
    left = [c for c in candidates_781() if c["tickets"] != [501]]
    assert loop.refill(left, parked_455(), 1) == []
    # #455 lands too, and the same call now fills from the family it held.
    assert [c["tickets"] for c in loop.refill(left, [], 1)] == [[452]]


def test_a_clump_clumped_by_subtree_is_checked_on_its_named_files():
    # Subtree mode resolves no closure, so `closure.py` emits `files` and no
    # `closure` key. The exclusion still has to read something.
    candidates = [{"tickets": [601], "files": ["examples/thermo.js"]}]
    live = [{"tickets": [455], "workspace": "/w/implement-455",
             "agent": "burn-455", "files": ["examples/thermo.js"]}]
    assert loop.refill(candidates, live, 1) == []


def test_the_hot_shared_file_is_the_only_hub():
    # A hub is a file in two or more candidates' closures. `tests/all.sh` sits
    # in one, so it is not a hub however central it looks.
    assert loop.hubs(candidates_781() + parked_455()) == {HOT}


def test_a_landing_that_touched_a_hub_asks_for_full_re_exploration():
    assert loop.hub_landing(["examples/renban.js", HOT],
                            loop.hubs(candidates_781())) is True


def test_a_landing_that_touched_no_hub_does_not():
    assert loop.hub_landing(["tests/all.sh"],
                            loop.hubs(candidates_781())) is False
    assert loop.hub_landing([], loop.hubs(candidates_781())) is False


def test_box_check_allows_a_dispatch_with_room_on_the_box():
    assert loop.box_check(processes=12, committed_gb=6, add_gb=4) == {
        "ok": True, "refusals": []}


def test_box_check_refuses_when_one_more_process_breaks_the_cap():
    got = loop.box_check(processes=28, committed_gb=0, add_gb=0)
    assert got["ok"] is False
    assert any("28" in r for r in got["refusals"]), got


def test_box_check_refuses_when_the_ulimit_sum_breaks_the_budget():
    got = loop.box_check(processes=2, committed_gb=22, add_gb=4)
    assert got["ok"] is False
    assert any("24" in r for r in got["refusals"]), got


def test_box_check_refuses_at_the_process_cap_boundary():
    # The cap is the box's, so the reading it is checked against counts
    # agent processes on the box — a new worker is charged at its peak, so 23
    # leaves room for one more and 24 does not.
    assert loop.box_check(processes=23, committed_gb=0, add_gb=0)["ok"] is True
    assert loop.box_check(processes=24, committed_gb=0, add_gb=0)["ok"] is False


def test_a_live_worker_keeps_its_fan_out_headroom_against_the_cap():
    # #933: a live worker is one process now and five at its review peak, so
    # 2 live workers on a box measured at 12 project 12+8+5=25 and fit; a
    # 3rd live worker projects 29 against the cap of 28 and is refused.
    assert loop.box_check(12, 0, live=2)["ok"] is True
    got = loop.box_check(12, 0, live=3)
    assert got["ok"] is False
    assert any("12 of review fan-out headroom for 3 live" in r
               for r in got["refusals"]), got


def test_the_cli_dispatch_charges_live_workers_at_their_peak():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        live = os.path.join(tmp, "live.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        with open(live, "w") as fh:
            json.dump(parked_455(), fh)
        # 1 live worker, 16 measured: 16 + 4 + 5 = 25 fits.
        ok = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                     "--free", "1", "--processes", "16",
                     "--committed-gb", "0")
        assert ok.returncode == 0, ok.stderr
        assert ("peak: 16 agent processes measured, 1 live worker holding 4 "
                "of fan-out headroom") in ok.stdout, ok.stdout
        assert "1 more at 5 each projects 25" in ok.stdout, ok.stdout
        # 20 measured: 20 + 4 + 5 = 29 is over the cap of 28.
        refused = loop_py("dispatch", "--candidates", cand, "--in-flight",
                          live, "--free", "1", "--processes", "20",
                          "--committed-gb", "0")
        assert refused.returncode == 1
        assert "4 of review fan-out headroom for 1 live" in refused.stderr


def test_an_idle_boxs_os_process_count_is_not_the_cap_reading():
    # A WSL box idles at ~190 OS processes. The cap counts agent processes,
    # so the CLI must dispatch when the agent count is small, and the
    # refusal must name what it counted.
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        idle = loop_py("dispatch", "--in-flight", EMPTY_LIVE, "--candidates", cand, "--free", "1",
                       "--processes", "19", "--committed-gb", "0")
        assert idle.returncode == 0, idle.stderr
        assert "dispatch  #" in idle.stdout, idle.stdout
        full = loop_py("dispatch", "--in-flight", EMPTY_LIVE, "--candidates", cand, "--free", "1",
                       "--processes", "28", "--committed-gb", "0")
        assert full.returncode == 1
        assert "28 agent processes" in full.stderr, full.stderr
        assert "not OS processes" in full.stderr, full.stderr


def test_agent_processes_are_counted_by_command_name_not_arguments():
    listing = "bash\nclaude\nnode\nclaude\nchrome\nclaude-hook\n"
    assert loop.count_agent_processes(lambda cmd: (0, listing)) == 2


def test_an_unmeasurable_box_is_a_refusal_not_zero_agents():
    # The last: a healthy listing with no claude in it. The controller is one,
    # so zero means the name did not match, and reading it as zero agents
    # would switch the cap off.
    for failed in ((1, ""), (0, ""), (1, "bash\nclaude\n"),
                   (0, "bash\nnode\n" * 95)):
        try:
            loop.count_agent_processes(lambda cmd, r=failed: r)
        except loop.LoopError as exc:
            assert "count" in str(exc) and "--processes" in str(exc), exc
        else:
            raise AssertionError(f"{failed} read as a count")


def idle_box_listing(agents):
    """~190 OS processes, `agents` of them claude sessions."""
    others = ["bash", "node"] * ((190 - agents) // 2)
    return "\n".join(["claude"] * agents + others) + "\n"


def test_a_measured_idle_box_dispatches_and_agent_pressure_refuses():
    class Args:
        processes = None
    idle = idle_box_listing(19)
    assert len(idle.split()) >= 189
    count, counter = loop.agent_count(Args, lambda cmd: (0, idle))
    assert count == 19
    assert loop.box_check(count, 0, counter=counter)["ok"] is True
    count, counter = loop.agent_count(
        Args, lambda cmd: (0, idle_box_listing(28)))
    refused = loop.box_check(count, 0, counter=counter)
    assert refused["ok"] is False
    assert "28 agent processes" in refused["refusals"][0], refused
    assert "comm=" in refused["refusals"][0], refused


def test_a_processes_override_of_zero_is_used_not_measured():
    class Args:
        processes = 0
    assert loop.agent_count(Args, lambda cmd: (1, "")) == (
        0, "passed by --processes")


def test_the_cli_refuses_a_negative_processes_override():
    # A negative count would sit under the cap for any workers asked about,
    # so the documented escape hatch would switch the gate off on a typo.
    for cmd in (("box", "--live", "0"),
                ("dispatch", "--candidates", "x", "--free", "1")):
        got = loop_py(*cmd, "--processes", "-1", "--committed-gb", "0")
        assert got.returncode != 0, got
        assert "box ok" not in got.stdout and "dispatch" not in got.stdout
        assert "--processes" in got.stderr and "negative" in got.stderr, \
            got.stderr
    zero = loop_py("box", "--processes", "0", "--committed-gb", "0",
                    "--live", "0")
    assert zero.returncode == 0, zero.stderr


def test_the_cli_dispatch_refuses_when_ps_cannot_be_run():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        nobin = os.path.join(tmp, "empty-path")
        os.mkdir(nobin)
        got = subprocess.run(
            [sys.executable, LOOP, "dispatch", "--in-flight", EMPTY_LIVE, "--candidates", cand,
             "--free", "1", "--committed-gb", "0"], capture_output=True,
            text=True, timeout=60, env={**os.environ, "PATH": nobin})
    assert got.returncode == 1, got
    assert "dispatch  #" not in got.stdout, got.stdout
    assert "--processes" in got.stderr, got.stderr


def test_the_cli_refuses_when_ps_cannot_be_run():
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "PATH": tmp}
        got = subprocess.run([sys.executable, LOOP, "box", "--committed-gb",
                              "0", "--live", "0"], capture_output=True, text=True,
                             timeout=60, env=env)
    assert got.returncode == 1, got
    assert "--processes" in got.stderr, got.stderr
    assert "box ok" not in got.stdout, got.stdout


def resume_state():
    """What `runfile.reconcile` hands a resumed controller: one live worker to
    re-announce to, one vanished, one landed."""
    return {
        "run_id": "burn-781", "slots": 3, "controller": "skills-dc",
        "free": 1, "held": 2,
        "announce": [{"tickets": [455], "workspace": "/w/implement-455",
                      "agent": "burn-455", "landed": None}],
        "vanished": [{"tickets": [452], "workspace": "/w/implement-452",
                      "agent": "burn-452", "landed": None}],
        "landed": [{"tickets": [453], "workspace": "/w/implement-453",
                    "agent": "burn-453", "landed": "abc1234"}],
    }


def test_resume_sends_exactly_one_message_per_live_unlanded_worker():
    sent = []

    def send(agent, msg):
        assert agent != "burn-455", (
            "send must never see the durable herdr agent name")
        sent.append((agent, msg))

    def resolve(agent):
        assert agent == "burn-455", agent
        return "session-455"

    loop.announce(resume_state(), send, resolve)
    assert [agent for agent, _ in sent] == ["session-455"]
    assert sent[0][1].count("skills-dc") == 1, sent[0][1]
    assert "#455" in sent[0][1]
    assert "resolve-controller" in sent[0][1], sent[0][1]


# One canned answer per name. `burn-bad-exit` and `burn-empty-ok` exist to
# keep resolve_via_binary's two guards from masking each other (#1013 C1):
# each fails a different way, so a test can delete either guard on its own
# and still see a red that only that guard would have caught.
RESOLVE_CONTROLLER_STUB = """#!/usr/bin/env bash
case "$1" in
  burn-455) echo "session-455" ;;
  burn-bad-exit) echo "not-a-name"; exit 1 ;;
  burn-empty-ok) exit 0 ;;
  *) echo "resolve-controller: $1 is neither a herdr agent name nor the name of a live session" >&2
     exit 1 ;;
esac
"""


@contextlib.contextmanager
def stubbed_resolve_controller(script=RESOLVE_CONTROLLER_STUB):
    """Puts a fake `resolve-controller` on `PATH` for the block, restoring
    `PATH` after — the ritual every test below needs, in one place rather
    than copied three times (#1013 S1). `os.environ.get("PATH", "")` rather
    than `None` so a caller with no `PATH` set (`env -i`) does not raise
    concatenating past it (#1013 S2/C3)."""
    with tempfile.TemporaryDirectory() as tmp:
        stub = os.path.join(tmp, "resolve-controller")
        with open(stub, "w") as fh:
            fh.write(script)
        os.chmod(stub, 0o755)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = tmp + os.pathsep + old_path
        try:
            yield tmp
        finally:
            os.environ["PATH"] = old_path


def test_resolve_via_binary_prints_the_resolved_session_name():
    with stubbed_resolve_controller():
        assert loop.resolve_via_binary("burn-455") == "session-455"


def test_resolve_via_binary_refuses_a_name_that_does_not_resolve():
    with stubbed_resolve_controller():
        try:
            loop.resolve_via_binary("burn-999")
        except loop.LoopError as exc:
            assert "burn-999" in str(exc), exc
        else:
            raise AssertionError("an unresolved name must be refused")


def test_resolve_via_binary_refuses_a_nonzero_exit_even_with_stdout_output():
    # A binary that exits non-zero after printing something on stdout must
    # not be read as a resolved name — that reading is the mask deleting
    # the exit-status check alone would leave in place.
    with stubbed_resolve_controller():
        try:
            loop.resolve_via_binary("burn-bad-exit")
        except loop.LoopError as exc:
            # No stderr, so the refusal falls back to the stdout it must not
            # treat as a resolved name.
            assert "not-a-name" in str(exc), exc
        else:
            raise AssertionError(
                "a non-zero exit must be refused whatever it printed")


def test_resolve_via_binary_refuses_a_zero_exit_with_empty_stdout():
    # A binary that exits 0 but prints nothing must not resolve to "" — the
    # mask deleting the empty-stdout check alone would leave in place.
    with stubbed_resolve_controller():
        try:
            loop.resolve_via_binary("burn-empty-ok")
        except loop.LoopError as exc:
            assert "burn-empty-ok" in str(exc), exc
        else:
            raise AssertionError(
                "an empty answer must be refused, not read as a name")


def test_resolve_via_binary_refuses_when_the_binary_is_missing():
    with tempfile.TemporaryDirectory() as tmp:
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = tmp
        try:
            loop.resolve_via_binary("burn-455")
        except loop.LoopError as exc:
            assert "resolve-controller" in str(exc), exc
        else:
            raise AssertionError("a missing binary must be refused, not silent")
        finally:
            os.environ["PATH"] = old_path


def test_announce_uses_the_default_resolver_when_none_is_passed():
    # #1013 P2: every other announce test injects its own `resolve`, so
    # nothing exercises the wiring between `announce` and its default
    # (`resolve_via_binary`) — a regression that swapped the default for an
    # identity function would still pass the suite. This one calls
    # `announce` with only `send`, over a stubbed `resolve-controller`.
    sent = []

    def send(agent, msg):
        assert agent != "burn-455", (
            "send must never see the durable herdr agent name")
        sent.append((agent, msg))

    with stubbed_resolve_controller():
        loop.announce(resume_state(), send)
    assert sent == [("session-455", sent[0][1])]


def test_resume_sends_nothing_to_a_landed_or_vanished_worker():
    sent = []
    state = resume_state()
    state["announce"] = []
    loop.announce(state, lambda agent, message: sent.append((agent, message)))
    assert sent == []


def test_announce_returns_the_agents_it_sent_to_and_reports_a_failure():
    def send(agent, message):
        raise RuntimeError("no such peer")
    state = resume_state()
    try:
        loop.announce(state, send, resolve=lambda agent: f"session-{agent}")
    except loop.LoopError as exc:
        assert "burn-455" in str(exc), exc
    else:
        raise AssertionError("a send that fails must not read as announced")


def test_announce_refuses_a_worker_whose_name_does_not_resolve():
    state = resume_state()

    def resolve(agent):
        raise RuntimeError(f"{agent} is neither a herdr agent nor a live session")

    try:
        loop.announce(state, lambda agent, msg: None, resolve=resolve)
    except loop.LoopError as exc:
        assert "burn-455" in str(exc), exc
        assert "#455" in str(exc), exc
    else:
        raise AssertionError(
            "a worker whose herdr name does not resolve must be refused")


def test_the_candidate_set_is_frozen_against_a_ticket_filed_mid_run():
    frozen = candidates_781()
    try:
        loop.admit(frozen, {"tickets": [700], "closure": ["docs/new.md"]})
    except loop.LoopError as exc:
        assert "frozen" in str(exc), exc
    else:
        raise AssertionError("a mid-run ticket must not join the queue")
    assert len(frozen) == 4


def test_a_ticket_the_run_is_stuck_on_joins_the_run():
    frozen = candidates_781()
    grown = loop.admit(frozen, {"tickets": [700], "closure": ["docs/new.md"]},
                       stuck_on=452)
    assert [c["tickets"] for c in grown][-1] == [700]
    assert len(frozen) == 4, "admit returns a new list, never mutates"


def test_a_stuck_on_ticket_the_run_never_had_is_refused():
    try:
        loop.admit(candidates_781(), {"tickets": [700], "closure": ["d.md"]},
                   stuck_on=999)
    except loop.LoopError as exc:
        assert "#999" in str(exc), exc
    else:
        raise AssertionError("the stuck clump has to be one of this run's")


LOOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loop.py")


# `dispatch` demands its in-flight snapshot; an explicit empty list is how a
# test says no worker is live.
_EMPTY = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
_EMPTY.write("[]")
_EMPTY.close()
EMPTY_LIVE = _EMPTY.name


def loop_py(*args, cwd=None):
    return subprocess.run([sys.executable, LOOP, *args],
                          capture_output=True, text=True, timeout=60, cwd=cwd)


def test_the_cli_box_check_exits_nonzero_on_a_refusal():
    ok = loop_py("box", "--processes", "4", "--committed-gb", "4",
                 "--add-gb", "4", "--live", "0")
    assert ok.returncode == 0, ok.stderr
    refused = loop_py("box", "--processes", "40", "--committed-gb", "0",
                     "--live", "0")
    assert refused.returncode == 1
    assert "agent processes" in refused.stderr, refused.stderr


def test_the_cli_box_charges_live_workers_and_demands_the_count():
    # 12 measured + 2 live x 4 + 1 new x 5 = 25 fits; 3 live makes 29.
    ok = loop_py("box", "--processes", "12", "--committed-gb", "0",
                 "--live", "2")
    assert ok.returncode == 0, ok.stderr
    refused = loop_py("box", "--processes", "12", "--committed-gb", "0",
                      "--live", "3")
    assert refused.returncode == 1
    assert "12 of review fan-out headroom for 3 live" in refused.stderr
    # Absent or negative is refused, never read as zero live workers.
    for extra in ((), ("--live", "-1")):
        got = loop_py("box", "--processes", "27", "--committed-gb", "0",
                      *extra)
        assert got.returncode != 0 and "box ok" not in got.stdout, got
    assert "--live" in got.stderr and "negative" in got.stderr, got.stderr


def test_a_landed_clump_is_not_a_live_worker_for_the_peak_charge():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        live = os.path.join(tmp, "live.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        clumps = parked_455()
        for c in clumps:
            c["landed"] = "abc1234"
        with open(live, "w") as fh:
            json.dump(clumps, fh)
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "1", "--processes", "20",
                      "--committed-gb", "0")
        assert "0 live workers" in got.stdout + got.stderr, got


def test_the_cli_dispatch_prints_the_picks_and_what_holds_the_rest():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        live = os.path.join(tmp, "live.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        with open(live, "w") as fh:
            json.dump(parked_455(), fh)
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "2", "--processes", "6", "--committed-gb", "4")
        assert got.returncode == 0, got.stderr
        assert "dispatch  #501" in got.stdout, got.stdout
        assert "held      #452" in got.stdout, got.stdout
        assert HOT in got.stdout and "/w/implement-455" in got.stdout


def test_the_cli_hub_says_whether_a_landing_moved_the_queues_closures():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        hub = loop_py("hub", "--candidates", cand, "--landed", HOT)
        assert hub.returncode == 0, hub.stderr
        assert "re-explore" in hub.stdout, hub.stdout
        quiet = loop_py("hub", "--candidates", cand, "--landed", "tests/all.sh")
        assert quiet.returncode == 0, quiet.stderr
        assert "no hub" in quiet.stdout, quiet.stdout


def test_the_exclusion_reads_the_closure_and_not_the_named_files():
    # `closure.py` in closure mode emits both keys, and the closure is the
    # wider one: a candidate whose *named* files miss the live workspace
    # entirely still collides through the file that includes them. Reading
    # `files` here would under-detect exactly the collision the rule exists
    # to stop.
    candidates = [{"tickets": [452], "files": ["examples/thermo.js"],
                   "closure": ["examples/thermo.js", HOT]}]
    live = [{"tickets": [455], "workspace": "/w/implement-455",
             "agent": "burn-455", "files": ["examples/renban.js"],
             "closure": ["examples/renban.js", HOT]}]
    assert loop.refill(candidates, live, 1) == []


def test_refill_takes_nothing_for_a_free_count_below_zero():
    # A miscounted budget reads as a negative free count, and "fill every
    # free slot" must not read that as "fill them all".
    assert loop.refill(candidates_781(), [], -1) == []


def test_a_clump_with_no_files_is_refused_whatever_is_in_flight():
    # A closure that failed to resolve is not an empty closure. Refused with
    # nothing in flight too, where there is no live workspace to compare it
    # against and the refusal would otherwise never fire.
    fileless = [{"tickets": [452]}]
    for in_flight in ([], parked_455()):
        try:
            loop.refill(fileless, in_flight, 1)
        except loop.LoopError as exc:
            assert "#452" in str(exc) and "files" in str(exc), exc
        else:
            raise AssertionError("a clump with no files must be refused")


def test_a_malformed_clump_file_is_one_line_and_not_a_traceback():
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "candidates.json")
        for content in ('[{"closure": ["a"]}]', '[[452]]',
                        '{"tickets": [452]}', 'not json at all',
                        '[{"tickets": ["452"], "closure": ["a"]}]'):
            with open(bad, "w") as fh:
                fh.write(content)
            got = loop_py("dispatch", "--in-flight", EMPTY_LIVE, "--candidates", bad, "--free", "1",
                          "--processes", "2", "--committed-gb", "0")
            assert got.returncode == 1, (content, got)
            assert "Traceback" not in got.stderr, (content, got.stderr)
            assert got.stderr.startswith("loop.py: "), (content, got.stderr)
            assert len(got.stderr.strip().splitlines()) == 1, got.stderr


def test_seat_names_the_remedy_when_origin_head_is_unset():
    def run(args):
        if args[0] == "symbolic-ref":
            raise loop.LoopError("git symbolic-ref failed: not a symbolic ref")
        return git_stub()(args)
    try:
        loop.seat(run)
    except loop.LoopError as exc:
        assert "git remote set-head origin -a" in str(exc), exc
    else:
        raise AssertionError("an unset origin/HEAD must be refused")


def test_announce_names_the_workers_already_reached_when_a_send_fails():
    # A retry that re-messages an announced worker breaks the one-message
    # rule, so the refusal has to say who was already reached.
    state = resume_state()
    state["announce"] = [
        {"tickets": [455], "workspace": "/w/455", "agent": "burn-455",
         "landed": None},
        {"tickets": [457], "workspace": "/w/457", "agent": "burn-457",
         "landed": None},
    ]

    def send(agent, message):
        if agent == "session-457":
            raise RuntimeError("no such peer")

    try:
        loop.announce(state, send, resolve=lambda agent: f"session-{agent[5:]}")
    except loop.LoopError as exc:
        assert "burn-457" in str(exc), exc
        assert "burn-455" in str(exc), exc
    else:
        raise AssertionError("a failed send must refuse")


def test_the_cli_dispatch_refuses_when_the_box_has_no_room():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        got = loop_py("dispatch", "--in-flight", EMPTY_LIVE, "--candidates", cand, "--free", "1",
                      "--processes", "40", "--committed-gb", "0")
        assert got.returncode == 1, got
        assert "dispatch" not in got.stdout, got.stdout
        assert "agent processes" in got.stderr, got.stderr


def test_the_cli_refuses_a_seat_in_a_worktree_it_makes_itself():
    # Deterministic, unlike reading whichever seat the suite happens to run
    # in: a repo with a linked worktree, built here, refused there.
    with tempfile.TemporaryDirectory() as tmp:
        primary = os.path.join(tmp, "primary")
        linked = os.path.join(tmp, "linked")
        git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
        subprocess.run(["git", "init", "-q", primary], check=True, timeout=60)
        open(os.path.join(primary, "f"), "w").close()
        subprocess.run([*git, "-C", primary, "add", "f"], check=True, timeout=60)
        subprocess.run([*git, "-C", primary, "commit", "-q", "-m", "one"],
                       check=True, timeout=60)
        subprocess.run(["git", "-C", primary, "worktree", "add", "-q", linked,
                        "-b", "implement-1"], check=True, timeout=60)
        got = loop_py("seat", cwd=linked)
        assert got.returncode == 1, got
        assert "worktree" in got.stderr and "worker" in got.stderr, got.stderr
        subprocess.run(["git", "-C", primary, "worktree", "remove", "--force",
                        linked], check=True, timeout=60)


def test_an_in_flight_entry_with_no_workspace_is_one_line_not_a_traceback():
    # The other flag's hand-built file: `frontier` indexes `workspace` on
    # every live entry, so the reader has to require it there.
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        live = os.path.join(tmp, "live.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        with open(live, "w") as fh:
            json.dump([{"tickets": [455], "closure": [HOT]}], fh)
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "1", "--processes", "2", "--committed-gb", "0")
        assert got.returncode == 1, got
        assert "Traceback" not in got.stderr, got.stderr
        assert "workspace" in got.stderr, got.stderr
        assert len(got.stderr.strip().splitlines()) == 1, got.stderr


def test_box_check_weighs_every_worker_a_dispatch_would_start():
    # Three workers at once is three processes and three ulimit caps, not
    # one: a gate that asks about one more worker passes a tick that starts
    # three.
    assert loop.box_check(processes=13, committed_gb=0, workers=3)["ok"] is True
    assert loop.box_check(processes=14, committed_gb=0, workers=3)["ok"] is False
    assert loop.box_check(processes=2, committed_gb=21, add_gb=1,
                          workers=4)["ok"] is False


def test_the_cli_dispatch_takes_only_what_the_box_has_room_for():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        with open(cand, "w") as fh:
            json.dump([{"tickets": [452], "closure": ["a.js"]},
                       {"tickets": [457], "closure": ["b.js"]},
                       {"tickets": [458], "closure": ["c.js"]}], fh)
        got = loop_py("dispatch", "--in-flight", EMPTY_LIVE, "--candidates", cand, "--free", "3",
                      "--processes", "23", "--committed-gb", "23",
                      "--add-gb", "1")
        assert got.returncode == 0, got.stderr
        assert got.stdout.count("dispatch  ") == 1, got.stdout
        assert "room for 1 of 3" in got.stdout, got.stdout


def test_a_closure_that_is_not_a_list_of_paths_is_refused():
    # `set("shared.py")` is a set of six letters, which intersects no real
    # path set — so a malformed closure would read as a clump that collides
    # with nobody and dispatch a second worker into a held file.
    for closure in ("shared.py", {"a": 1}, ["shared.py", 7], [""], []):
        clump = {"tickets": [1], "closure": closure}
        try:
            loop.paths(clump)
        except loop.LoopError as exc:
            assert "#1" in str(exc), (closure, exc)
        else:
            raise AssertionError(f"{closure!r} must not read as a path set")


def test_a_malformed_closure_reaches_the_cli_as_one_line():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        live = os.path.join(tmp, "live.json")
        with open(live, "w") as fh:
            json.dump([{"tickets": [2], "workspace": "/w/2",
                        "closure": ["shared.py"], "job": NO_JOB}], fh)
        for closure in ("shared.py", {"a": 1}, ["shared.py", 7]):
            with open(cand, "w") as fh:
                json.dump([{"tickets": [1], "closure": closure}], fh)
            got = loop_py("dispatch", "--candidates", cand, "--in-flight",
                          live, "--free", "1", "--processes", "4",
                          "--committed-gb", "4")
            assert got.returncode == 1, (closure, got)
            assert "dispatch" not in got.stdout, (closure, got.stdout)
            assert "Traceback" not in got.stderr, got.stderr
            assert len(got.stderr.strip().splitlines()) == 1, got.stderr


# The #454 fixture, as the trial actually stood: the worker asked for a ruling
# in good faith, the controller merged and ran `merge-cleanup`, and the ruling
# was sent after — to a pane cleanup had already closed
# (`No agent named 'implement-454-12' is reachable`).
def landed_454():
    return {"tickets": [454], "workspace": "/w/implement-454",
            "agent": "implement-454-12",
            "closure": ["examples/renban.js"]}


def test_the_landing_tail_answers_every_outstanding_question_before_cleanup():
    tail = loop.landing_steps(landed_454(), ["may I drop the 4x4 case?"])
    assert [s["step"] for s in tail] == ["answer", "merge", "cleanup"]
    assert tail[0]["question"] == "may I drop the 4x4 case?"
    assert tail[0]["agent"] == "implement-454-12"


def test_a_landing_with_nothing_outstanding_is_merge_then_cleanup():
    assert [s["step"] for s in loop.landing_steps(landed_454())] == [
        "merge", "cleanup"]


def test_every_outstanding_question_is_answered_not_just_the_first():
    tail = loop.landing_steps(landed_454(), ["one?", "two?"])
    assert [s["step"] for s in tail] == ["answer", "answer", "merge", "cleanup"]
    assert [s["question"] for s in tail[:2]] == ["one?", "two?"]


def test_cleanup_is_refused_while_a_question_is_outstanding():
    # The refusal names the clump, the worker and the question, because the
    # controller hitting it has to send the answer, not just wait.
    try:
        loop.cleanup_ready(landed_454(), ["may I drop the 4x4 case?"])
    except loop.LoopError as exc:
        assert "#454" in str(exc), exc
        assert "implement-454-12" in str(exc), exc
        assert "may I drop the 4x4 case?" in str(exc), exc
    else:
        raise AssertionError("cleanup with a question outstanding must be "
                             "refused")


def test_cleanup_is_ready_once_every_question_is_answered():
    assert loop.cleanup_ready(landed_454(), []) is True
    assert loop.cleanup_ready(landed_454()) is True


def test_an_outstanding_list_that_is_not_a_list_of_questions_is_refused():
    # A bare string iterates as characters, so "is it ok?" would read as ten
    # outstanding questions and answer none of them — the same fail-closed
    # rule `paths` applies one layer down.
    for outstanding in ("is it ok?", {"q": 1}, ["one?", 7], [""], [None]):
        for call in (loop.landing_steps, loop.cleanup_ready):
            try:
                call(landed_454(), outstanding)
            except loop.LoopError as exc:
                assert "#454" in str(exc), (outstanding, exc)
            else:
                raise AssertionError(
                    f"{outstanding!r} must not read as a question list")


def test_the_cli_landing_refuses_cleanup_while_a_question_is_outstanding():
    # The exit code answers "may I clean up now?"; stdout answers "what do I
    # owe first?".
    got = loop_py("landing", "--clump", "454", "--agent",
                  "implement-454-12", "--outstanding", "may I drop 4x4?")
    assert got.returncode == 1, got
    # Only what is owed, and a refusal saying so. `cleanup` must not appear
    # as a step on the one path where running it destroys the channel the
    # answer is owed on — an exit code refuses, a printed step list does not.
    assert got.stdout.splitlines() == [
        "refused: 1 answer owed before cleanup",
        "answer    implement-454-12  may I drop 4x4?",
    ], got.stdout
    assert "cleanup" not in got.stdout.replace(
        "refused: 1 answer owed before cleanup", ""), got.stdout
    assert "merge" not in got.stdout, got.stdout
    assert "Traceback" not in got.stderr, got.stderr
    assert len(got.stderr.strip().splitlines()) == 1, got.stderr
    assert "implement-454-12" in got.stderr, got.stderr


def test_the_cli_landing_clears_cleanup_once_nothing_is_outstanding():
    got = loop_py("landing", "--clump", "454", "--agent", "implement-454-12")
    assert got.returncode == 0, got.stderr
    assert got.stdout.splitlines() == ["merge", "cleanup"], got.stdout


def test_a_question_with_a_newline_in_it_is_refused():
    # Each step prints as one line, so a question carrying a newline would
    # emit a line the reader cannot tell from a step of its own.
    try:
        loop.landing_steps(landed_454(), ["one?\ntwo?"])
    except loop.LoopError as exc:
        assert "#454" in str(exc), exc
        assert "one line" in str(exc), exc
    else:
        raise AssertionError("a multi-line question must be refused")


def test_the_cli_landing_refuses_an_empty_agent_and_a_non_positive_clump():
    # A refusal whose job is to name the worker must not name nobody, and a
    # clump is a ticket number. Nothing outstanding, so the flags are the
    # only thing that can refuse this call — with a question outstanding the
    # cleanup gate refuses anyway and the check would witness nothing.
    for args, reason in ((("--clump", "454", "--agent", ""), "no agent named"),
                         (("--clump", "0", "--agent", "burn-1"), "ticket number"),
                         (("--clump", "-5", "--agent", "burn-1"), "ticket number")):
        got = loop_py("landing", *args)
        assert got.returncode == 1, (args, got)
        assert reason in got.stderr, (args, got.stderr)
        assert "Traceback" not in got.stderr, got.stderr
        assert len(got.stderr.strip().splitlines()) == 1, got.stderr


def test_the_cli_landing_survives_a_reader_that_closes_early():
    # `loop.py landing ... | head -1` and its kin. The read end is closed
    # before the child runs, so the first write hits EPIPE every time —
    # racing a real `head` would make this pass on the buffering instead of
    # on the handler. Without it the interpreter prints, at exit, the
    # traceback this module promises never to print.
    read_end, write_end = os.pipe()
    os.close(read_end)
    try:
        got = subprocess.run(
            [sys.executable, LOOP, "landing", "--clump", "454", "--agent",
             "burn-454", "--outstanding", "may I drop 4x4?"],
            stdout=write_end, stderr=subprocess.PIPE, text=True, timeout=60)
    finally:
        os.close(write_end)
    # The refusal's own exit code, because stderr is a different fd and the
    # refusal printed there still arrived.
    assert got.returncode == 1, got
    assert "cleanup closes its pane" in got.stderr, got.stderr
    assert "Traceback" not in got.stderr, got.stderr
    assert "Exception ignored" not in got.stderr, got.stderr


def test_the_cli_landing_survives_a_reader_that_closes_mid_output():
    # Past the io buffer the write fails inside the command itself, not at
    # the flush after it — the same broken pipe, a different line of code.
    # The status is the fail-closed one: a run whose output nobody read
    # cleared nothing, and a caller reading the exit code must not take it
    # for permission to clean up.
    read_end, write_end = os.pipe()
    os.close(read_end)
    questions = []
    for n in range(500):
        questions += ["--outstanding", f"question {n}?"]
    try:
        got = subprocess.run(
            [sys.executable, LOOP, "landing", "--clump", "454", "--agent",
             "burn-454", *questions],
            stdout=write_end, stderr=subprocess.PIPE, text=True, timeout=60)
    finally:
        os.close(write_end)
    assert got.returncode == 1, got
    assert "Traceback" not in got.stderr, got.stderr
    assert "Exception ignored" not in got.stderr, got.stderr
def agent_stub(answers, calls):
    """Stands in for `herdr agent get <name>` as the sweep calls it: one
    decoded answer per agent, and a list the test reads to count the calls."""
    def get(agent, timeout):
        calls.append(agent)
        assert timeout > 0, f"a probe was called with {timeout}s left"
        answer = answers[agent]
        if isinstance(answer, Exception):
            raise answer
        return answer
    return get


def herdr_agent(status):
    return {"id": "cli:agent:get", "result": {"agent": "claude",
                                              "agent_status": status,
                                              "name": "skills-1"}}


HERDR_GONE = {"id": "cli:agent:get",
              "error": {"code": "agent_not_found",
                        "message": "agent target skills-3 not found"}}


def live_clumps():
    return [
        {"tickets": [1], "workspace": "/w/1", "agent": "skills-1"},
        {"tickets": [2], "workspace": "/w/2", "agent": "skills-2"},
        {"tickets": [3], "workspace": "/w/3", "agent": "skills-3"},
    ]


def test_the_sweep_tells_a_vanished_pane_from_a_working_and_an_idle_one():
    calls = []
    get = agent_stub({"skills-1": herdr_agent("working"),
                      "skills-2": herdr_agent("idle"),
                      "skills-3": HERDR_GONE}, calls)
    state = loop.sweep(live_clumps(), get)
    verdicts = {w["agent"]: w["verdict"] for w in state["workers"]}
    assert verdicts == {"skills-1": "working", "skills-2": "idle",
                        "skills-3": "vanished"}, verdicts
    assert [w["agent"] for w in state["vanished"]] == ["skills-3"], state


def test_the_sweep_is_bounded_at_one_probe_per_live_slot():
    calls = []
    get = agent_stub({"skills-1": herdr_agent("working"),
                      "skills-2": herdr_agent("idle"),
                      "skills-3": HERDR_GONE}, calls)
    state = loop.sweep(live_clumps(), get)
    assert calls == ["skills-1", "skills-2", "skills-3"], calls
    assert state["calls"] == 3, state


def test_the_sweep_skips_a_landed_clump():
    calls = []
    clumps = live_clumps()
    clumps[1]["landed"] = "a1b2c3d"
    get = agent_stub({"skills-1": herdr_agent("working"),
                      "skills-3": HERDR_GONE}, calls)
    state = loop.sweep(clumps, get)
    assert calls == ["skills-1", "skills-3"], calls


def test_a_probe_that_fails_is_one_worker_unreachable_not_a_dead_sweep():
    calls = []
    get = agent_stub({"skills-1": RuntimeError("herdr socket is gone"),
                      "skills-2": herdr_agent("idle"),
                      "skills-3": HERDR_GONE}, calls)
    state = loop.sweep(live_clumps(), get)
    verdicts = {w["agent"]: w["verdict"] for w in state["workers"]}
    assert verdicts["skills-1"] == "unreachable", verdicts
    assert verdicts["skills-2"] == "idle", verdicts
    assert calls == ["skills-1", "skills-2", "skills-3"], calls


def test_an_unrecognised_status_is_its_own_verdict():
    calls = []
    get = agent_stub({"skills-1": herdr_agent("wedged")}, calls)
    state = loop.sweep(live_clumps()[:1], get)
    assert state["workers"][0]["verdict"] == "unknown", state
    assert "wedged" in state["workers"][0]["detail"], state


HERDR_NESTED_AGENT = {
    "id": "cli:agent:get",
    "result": {"agent": {"agent_status": "working", "name": "skills-1",
                          "pane": "burn-1"}}}


def test_the_sweep_reads_agent_status_nested_under_result_agent():
    calls = []
    get = agent_stub({"skills-1": HERDR_NESTED_AGENT}, calls)
    state = loop.sweep(live_clumps()[:1], get)
    assert state["workers"][0]["verdict"] == "working", state


def test_the_sweep_names_the_vanished_worker_distinctly_when_rendered():
    calls = []
    get = agent_stub({"skills-1": herdr_agent("working"),
                      "skills-2": herdr_agent("idle"),
                      "skills-3": HERDR_GONE}, calls)
    rendered = loop.render_sweep(loop.sweep(live_clumps(), get))
    assert "vanished  #3" in rendered, rendered
    assert "working   #1" in rendered, rendered
    assert "idle      #2" in rendered, rendered


def in_flight_clumps(job=None, other=None):
    """Two live clumps as `loop.py dispatch --in-flight` reads them: the run
    file's entries, each carrying its worker's job state, plus the closure
    re-resolved at dispatch."""
    return [
        {"tickets": [351], "workspace": "/w/351", "agent": "sm-351",
         "closure": ["verify.py"], "job": job},
        {"tickets": [412], "workspace": "/w/412", "agent": "sm-412",
         "closure": ["other.py"], "job": other},
    ]


def dispatch_files(tmp, job, candidate_closure="fresh.py"):
    """The two files `loop.py dispatch` reads: one fresh candidate, and the
    live clumps as the run file holds them — each with its worker's job
    state, and its closure re-resolved at dispatch."""
    cand = os.path.join(tmp, "candidates.json")
    live = os.path.join(tmp, "live.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [500], "closure": [candidate_closure]}], fh)
    with open(live, "w") as fh:
        json.dump(in_flight_clumps(job=job, other=NO_JOB), fh)
    return cand, live


def test_the_cli_holds_the_slot_and_says_so_in_its_status_line():
    with tempfile.TemporaryDirectory() as tmp:
        cand, live = dispatch_files(tmp, {"state": "running", "cores": 8})
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "1", "--processes", "4", "--committed-gb", "4")
        assert got.returncode == 0, got
        assert "cores" in got.stdout and "#351" in got.stdout, got.stdout
        assert "dispatch  #500" not in got.stdout, got.stdout


def test_the_cli_dispatch_treats_a_landed_clumps_null_job_as_a_freed_slot():
    # A run file sets `landed` without ever clearing `job`; charging that
    # entry's absent job record before filtering it out refuses the whole
    # tick with "live with no job record" (#1003).
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        live = os.path.join(tmp, "live.json")
        with open(cand, "w") as fh:
            json.dump([{"tickets": [500], "closure": ["fresh.py"]}], fh)
        clumps = in_flight_clumps(job=None, other=NO_JOB)
        clumps[0]["landed"] = "a1b2c3d"
        with open(live, "w") as fh:
            json.dump(clumps, fh)
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "1", "--processes", "4", "--committed-gb", "4")
        assert got.returncode == 0, got
        assert "dispatch  #500" in got.stdout, got.stdout


def test_the_cli_dispatch_frontier_ignores_a_landed_clumps_own_closure():
    # A landed clump's workspace is dead — its change is on main, and the
    # next worker branches from main — so it holds nothing. `frontier` must
    # be fed the same `unlanded` collection core_room and the peak count
    # use, or a candidate sharing a file with the landed clump's closure
    # reads as blocked by a workspace that no longer exists (Codex gate on
    # PR #1050).
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        live = os.path.join(tmp, "live.json")
        with open(cand, "w") as fh:
            json.dump([{"tickets": [500], "closure": ["verify.py"]}], fh)
        clumps = in_flight_clumps(job=None, other=NO_JOB)
        clumps[0]["landed"] = "a1b2c3d"
        with open(live, "w") as fh:
            json.dump(clumps, fh)
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "1", "--processes", "4", "--committed-gb", "4")
        assert got.returncode == 0, got
        assert "dispatch  #500" in got.stdout, got.stdout
        assert "held" not in got.stdout, got.stdout


def test_the_cli_refuses_a_dispatch_while_a_worker_is_unrecorded():
    with tempfile.TemporaryDirectory() as tmp:
        cand, live = dispatch_files(tmp, None)
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "1", "--processes", "4", "--committed-gb", "4")
        assert got.returncode == 1, got
        assert "dispatch" not in got.stdout, got.stdout
        assert "#351" in got.stderr and "runfile.py job" in got.stderr, \
            got.stderr
        assert len(got.stderr.strip().splitlines()) == 1, got.stderr


def test_a_declared_heavy_job_holds_the_free_slots():
    state = loop.core_room(2, in_flight_clumps(
        job={"state": "running", "cores": 8}, other=NO_JOB))
    assert state["room"] == 0, state
    line = loop.render_cores(state, 2)
    assert "#351" in line and "8" in line, line


def test_a_run_whose_workers_all_declared_none_has_every_free_slot():
    state = loop.core_room(2, in_flight_clumps(job=NO_JOB, other=NO_JOB))
    assert state["room"] == 2, state
    assert loop.render_cores(state, 2) == "", state


def test_a_finished_job_stops_holding_its_slots():
    state = loop.core_room(2, in_flight_clumps(
        job={"state": "done", "cores": 0}, other=NO_JOB))
    assert state["room"] == 2, state


def test_a_declaration_charges_only_the_cores_past_its_own_slot():
    state = loop.core_room(3, in_flight_clumps(
        job={"state": "running", "cores": 2}, other=NO_JOB))
    assert state["room"] == 2, state


def test_a_live_clump_with_no_job_on_record_is_refused_by_name():
    """Silence is not zero: the reader obeys the rule the skill states, so a
    worker nobody recorded cannot be charged as if it declared none."""
    try:
        loop.core_room(2, in_flight_clumps(job=None, other=NO_JOB))
    except loop.LoopError as exc:
        assert "#351" in str(exc), exc
        assert "#412" not in str(exc), exc
        assert "runfile.py job" in str(exc), exc
    else:
        raise AssertionError("an unrecorded worker must not read as zero")


def test_a_job_record_that_is_not_one_is_refused():
    for record in ({"state": "running", "cores": 0},
                   {"state": "running", "cores": "8"},
                   {"state": "spinning", "cores": 1},
                   {"state": "running", "cores": True}, "8"):
        try:
            loop.core_room(2, in_flight_clumps(job=record, other=NO_JOB))
        except loop.LoopError as exc:
            assert "#351" in str(exc), (record, exc)
        else:
            raise AssertionError(f"{record!r} is not a job record")


HERDR_STUB = """#!/usr/bin/env bash
# Stands in for herdr: one canned answer per agent name, and a line per call
# appended to $CALLS so the test can count them.
echo "$3" >> "$CALLS"
case "$3" in
  skills-1) echo '{"result":{"agent_status":"working"}}' ;;
  skills-2) echo '{"result":{"agent_status":"idle"}}' ;;
  *) echo '{"error":{"code":"agent_not_found","message":"agent target '"$3"' not found"}}'
     exit 1 ;;
esac
"""


def test_the_cli_sweep_probes_each_live_slot_once_through_herdr():
    with tempfile.TemporaryDirectory() as tmp:
        bindir = os.path.join(tmp, "bin")
        os.mkdir(bindir)
        stub = os.path.join(bindir, "herdr")
        with open(stub, "w") as fh:
            fh.write(HERDR_STUB)
        os.chmod(stub, 0o755)
        workers = os.path.join(tmp, "workers.json")
        calls = os.path.join(tmp, "calls")
        with open(workers, "w") as fh:
            json.dump([{"tickets": [1], "workspace": "/w/1",
                        "agent": "skills-1"},
                       {"tickets": [2], "workspace": "/w/2",
                        "agent": "skills-2"},
                       {"tickets": [3], "workspace": "/w/3",
                        "agent": "skills-3"},
                       {"tickets": [4], "workspace": "/w/4",
                        "agent": "skills-4", "landed": "a1b2c3d"}], fh)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
                   CALLS=calls)
        got = subprocess.run([sys.executable, LOOP, "sweep", "--workers",
                              workers], capture_output=True, text=True,
                             timeout=60, env=env)
        assert got.returncode == 0, got
        assert "working   #1" in got.stdout, got.stdout
        assert "idle      #2" in got.stdout, got.stdout
        assert "vanished  #3" in got.stdout, got.stdout
        assert "#4" not in got.stdout, got.stdout
        with open(calls) as fh:
            assert fh.read().split() == ["skills-1", "skills-2", "skills-3"], \
                "the sweep probes each live slot exactly once"


def test_a_clump_with_no_agent_name_is_one_verdict_not_a_dead_sweep():
    calls = []
    clumps = live_clumps()
    clumps[0]["agent"] = ""
    get = agent_stub({"skills-2": herdr_agent("idle"),
                      "skills-3": HERDR_GONE}, calls)
    state = loop.sweep(clumps, get)
    verdicts = [w["verdict"] for w in state["workers"]]
    assert verdicts == ["unnamed", "idle", "vanished"], verdicts
    assert calls == ["skills-2", "skills-3"], calls
    assert state["calls"] == 2, state


def test_the_cli_sweep_refuses_a_box_with_no_herdr_rather_than_reporting_death():
    with tempfile.TemporaryDirectory() as tmp:
        bindir = os.path.join(tmp, "bin")
        os.mkdir(bindir)
        workers = os.path.join(tmp, "workers.json")
        with open(workers, "w") as fh:
            json.dump([{"tickets": [1], "workspace": "/w/1",
                        "agent": "skills-1"}], fh)
        # PATH holds one empty directory: herdr cannot be found at all.
        env = dict(os.environ, PATH=bindir)
        got = subprocess.run([sys.executable, LOOP, "sweep", "--workers",
                              workers], capture_output=True, text=True,
                             timeout=60, env=env)
        assert got.returncode == 1, got
        assert "herdr is not on PATH" in got.stderr, got.stderr
        assert "unreachable" not in got.stdout, got.stdout


def test_the_cli_sweep_refuses_a_workers_file_it_cannot_read():
    with tempfile.TemporaryDirectory() as tmp:
        workers = os.path.join(tmp, "workers.json")
        for content in ('{"tickets": [1]}', '[{"tickets": []}]',
                        '[{"tickets": ["1"]}]', 'not json'):
            with open(workers, "w") as fh:
                fh.write(content)
            got = loop_py("sweep", "--workers", workers)
            assert got.returncode == 1, (content, got)
            assert "Traceback" not in got.stderr, got.stderr
            assert len(got.stderr.strip().splitlines()) == 1, got.stderr


def test_the_cli_says_the_declared_job_holds_the_slot_and_not_the_box():
    with tempfile.TemporaryDirectory() as tmp:
        cand, live = dispatch_files(tmp, {"state": "running", "cores": 8})
        # The box is at its cap *and* a declared job holds the slot. The
        # answer names the job, because that is what a controller can act on.
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "1", "--processes", "28", "--committed-gb",
                      "4")
        assert got.returncode == 0, got
        assert "#351" in got.stdout, got.stdout
        assert "every free slot is held by a declared job" in got.stdout, \
            got.stdout
        assert got.stderr == "", got.stderr


def test_the_cli_dispatch_measures_before_it_says_a_declared_job_holds_the_slot():
    # The early "nothing to dispatch" return used to run before the
    # measurement, so a broken `ps` hid behind a healthy exit 0.
    with tempfile.TemporaryDirectory() as tmp:
        cand, live = dispatch_files(tmp, {"state": "running", "cores": 8})
        nobin = os.path.join(tmp, "empty-path")
        os.mkdir(nobin)
        got = subprocess.run(
            [sys.executable, LOOP, "dispatch", "--candidates", cand,
             "--in-flight", live, "--free", "1", "--committed-gb", "4"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PATH": nobin})
    assert got.returncode == 1, got
    assert "held by a declared job" not in got.stdout, got.stdout
    assert "dispatch  #" not in got.stdout, got.stdout
    assert "--processes" in got.stderr, got.stderr


SLOW_HERDR = """#!/usr/bin/env bash
sleep 30
"""


def test_a_probe_that_never_answers_is_given_up_on():
    """C3's witness: the sweep is bounded on the wall clock too, because a
    controller waiting on a hung herdr is inside a tool call, where no worker
    can reach it."""
    with tempfile.TemporaryDirectory() as tmp:
        bindir = os.path.join(tmp, "bin")
        os.mkdir(bindir)
        stub = os.path.join(bindir, "herdr")
        with open(stub, "w") as fh:
            fh.write(SLOW_HERDR)
        os.chmod(stub, 0o755)
        original_path = os.environ["PATH"]
        os.environ["PATH"] = bindir + os.pathsep + original_path
        try:
            started = time.monotonic()
            state = loop.sweep(
                [{"tickets": [1], "workspace": "/w/1", "agent": "skills-1"}],
                loop.herdr_get, budget=0.3)
            waited = time.monotonic() - started
        finally:
            os.environ["PATH"] = original_path
    assert state["workers"][0]["verdict"] == "unreachable", state
    assert "did not answer" in state["workers"][0]["detail"], state
    assert waited < 5, f"the sweep waited {waited:.1f}s on one hung probe"


def test_a_held_clump_is_still_named_when_declared_jobs_hold_every_slot():
    with tempfile.TemporaryDirectory() as tmp:
        cand, live = dispatch_files(tmp, {"state": "running", "cores": 8},
                                    candidate_closure="verify.py")
        got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                      "--free", "1", "--processes", "4", "--committed-gb", "4")
        assert got.returncode == 0, got
        assert ("held      #500  by #351 in /w/351  over verify.py"
                in got.stdout), got.stdout


def test_the_whole_sweep_is_bounded_by_one_deadline_not_one_per_probe():
    """N hung panes must not hold the controller for N timeouts: the worst
    case is a constant, because a controller inside a tool call hears no
    worker at all (#778)."""
    ticks = iter([0.0, 0.0, 10.0, 10.0, 10.0])
    calls = []

    def hung(agent, timeout):
        calls.append((agent, timeout))
        raise loop.LoopError(f"herdr agent get {agent} did not answer in "
                             f"{timeout:g}s")

    state = loop.sweep(live_clumps(), hung, budget=10.0,
                       clock=lambda: next(ticks))
    verdicts = [w["verdict"] for w in state["workers"]]
    assert verdicts == ["unreachable", "unswept", "unswept"], verdicts
    assert [agent for agent, _ in calls] == ["skills-1"], calls
    assert state["calls"] == 1, state
    for worker in state["workers"][1:]:
        assert "next wake" in worker["detail"], worker


def test_a_probe_is_given_only_the_budget_that_is_left():
    ticks = iter([0.0, 0.0, 4.0, 4.0])
    seen = []

    def get(agent, timeout):
        seen.append((agent, timeout))
        return herdr_agent("idle")

    loop.sweep(live_clumps()[:2], get, budget=10.0, clock=lambda: next(ticks))
    assert seen == [("skills-1", 10.0), ("skills-2", 6.0)], seen


def test_the_cli_sweep_of_several_hung_panes_returns_within_one_deadline():
    with tempfile.TemporaryDirectory() as tmp:
        bindir = os.path.join(tmp, "bin")
        os.mkdir(bindir)
        stub = os.path.join(bindir, "herdr")
        with open(stub, "w") as fh:
            fh.write(SLOW_HERDR)
        os.chmod(stub, 0o755)
        workers = os.path.join(tmp, "workers.json")
        with open(workers, "w") as fh:
            json.dump([{"tickets": [n], "workspace": f"/w/{n}",
                        "agent": f"skills-{n}"} for n in (1, 2, 3, 4)], fh)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
                   BURNDOWN_SWEEP_BUDGET="1")
        started = time.monotonic()
        got = subprocess.run([sys.executable, LOOP, "sweep", "--workers",
                              workers], capture_output=True, text=True,
                             timeout=60, env=env)
        waited = time.monotonic() - started
    assert got.returncode == 0, got
    assert waited < 8, f"four hung panes held the sweep {waited:.1f}s"
    assert got.stdout.count("unswept") >= 2, got.stdout


def test_dispatch_without_an_in_flight_snapshot_is_refused():
    # An omitted snapshot must not read as "no worker is live" (#933).
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        with open(cand, "w") as fh:
            json.dump(candidates_781(), fh)
        got = subprocess.run(
            [sys.executable, LOOP, "dispatch", "--candidates", cand,
             "--free", "1", "--processes", "1", "--committed-gb", "0"],
            capture_output=True, text=True, timeout=60)
    assert got.returncode != 0, got
    assert "--in-flight" in got.stderr, got.stderr
    assert "dispatch  #" not in got.stdout, got.stdout


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()

