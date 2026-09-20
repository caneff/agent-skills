#!/usr/bin/env python3
"""Tests for the burn loop (#893). The seams the ticket names: a fixture run
over a stub tracker and a stub agent list, and the resume announce against a
stub messenger. The loop's prose — its step list, its refusals, its stated
consequences — is guarded in `burndown/loop-steps.test.sh`; there is no
harness that runs a skill's own text.
"""
import json
import os
import subprocess
import sys
import tempfile

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
             "agent": "burn-455", "closure": ["examples/renban.js", HOT]}]


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
    # every process on the box — 27 leaves room for one more, 28 does not.
    assert loop.box_check(processes=27, committed_gb=0, add_gb=0)["ok"] is True
    assert loop.box_check(processes=28, committed_gb=0, add_gb=0)["ok"] is False


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
    loop.announce(resume_state(),
                  lambda agent, msg: sent.append((agent, msg)))
    assert [agent for agent, _ in sent] == ["burn-455"]
    assert sent[0][1].count("skills-dc") == 1, sent[0][1]
    assert "#455" in sent[0][1]


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
        loop.announce(state, send)
    except loop.LoopError as exc:
        assert "burn-455" in str(exc), exc
    else:
        raise AssertionError("a send that fails must not read as announced")


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


def loop_py(*args, cwd=None):
    return subprocess.run([sys.executable, LOOP, *args],
                          capture_output=True, text=True, timeout=60, cwd=cwd)


def test_the_cli_box_check_exits_nonzero_on_a_refusal():
    ok = loop_py("box", "--processes", "4", "--committed-gb", "4",
                 "--add-gb", "4")
    assert ok.returncode == 0, ok.stderr
    refused = loop_py("box", "--processes", "40", "--committed-gb", "0")
    assert refused.returncode == 1
    assert "cap of 28" in refused.stderr, refused.stderr


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
            got = loop_py("dispatch", "--candidates", bad, "--free", "1",
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
        if agent == "burn-457":
            raise RuntimeError("no such peer")

    try:
        loop.announce(state, send)
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
        got = loop_py("dispatch", "--candidates", cand, "--free", "1",
                      "--processes", "40", "--committed-gb", "0")
        assert got.returncode == 1, got
        assert "dispatch" not in got.stdout, got.stdout
        assert "cap of 28" in got.stderr, got.stderr


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
    assert loop.box_check(processes=27, committed_gb=0, workers=1)["ok"] is True
    assert loop.box_check(processes=27, committed_gb=0, workers=3)["ok"] is False
    assert loop.box_check(processes=2, committed_gb=21, add_gb=1,
                          workers=4)["ok"] is False


def test_the_cli_dispatch_takes_only_what_the_box_has_room_for():
    with tempfile.TemporaryDirectory() as tmp:
        cand = os.path.join(tmp, "candidates.json")
        with open(cand, "w") as fh:
            json.dump([{"tickets": [452], "closure": ["a.js"]},
                       {"tickets": [457], "closure": ["b.js"]},
                       {"tickets": [458], "closure": ["c.js"]}], fh)
        got = loop_py("dispatch", "--candidates", cand, "--free", "3",
                      "--processes", "27", "--committed-gb", "23",
                      "--add-gb", "1")
        assert got.returncode == 0, got.stderr
        assert got.stdout.count("dispatch  ") == 1, got.stdout
        assert "room for 1 of 3" in got.stdout, got.stdout


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
