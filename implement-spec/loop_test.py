"""Tests for the dispatch loop (#893). The seams the ticket names: a fixture run
over a stub tracker and a stub agent list. The loop's prose — its step list, its refusals, its stated
consequences — has no test: there is no harness that runs a skill's own text.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agents  # noqa: E402
import loop  # noqa: E402
import runfile  # noqa: E402
from run_fixtures import drop_job  # noqa: E402
from run_fixtures import drop_repo_field  # noqa: E402

# A real git checkout to record as a run's target when the case is not about it.
REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


@pytest.fixture
def tmp(tmp_path):
    """`tmp_path` as the string the helpers here join paths onto."""
    return str(tmp_path)


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
    with pytest.raises(loop.LoopError) as exc:
        loop.seat(run)
    assert "worktree" in str(exc.value)
    assert "worker" in str(exc.value)


def test_seat_accepts_a_spec_run_worktree_and_says_so():
    # #1312: `implement-dispatch --spec <n>` starts the spec run in
    # `.claude/worktrees/spec-<n>`, a linked worktree on branch `spec-<n>`.
    run = git_stub(branch="spec-1262",
                   git_dir="/repo/.git/worktrees/spec-1262")
    got = loop.seat(run)
    assert got.startswith("spec-1262"), got
    assert "spec" in got.split("spec-1262", 1)[1], got


@pytest.mark.parametrize(
    "branch", ["spec-", "spec-12x", "myspec-12", "implement-12", ""])
def test_seat_still_refuses_a_worktree_whose_branch_only_looks_like_a_spec(branch):
    run = git_stub(branch=branch,
                   git_dir="/repo/.git/worktrees/implement-12")
    with pytest.raises(loop.LoopError) as exc:
        loop.seat(run)
    assert "worktree" in str(exc.value)


def test_seat_refuses_a_integration_branch_in_the_primary_checkout():
    # The exception is for the linked worktree `--spec` makes; an integration branch
    # on the primary checkout is still not the default branch.
    with pytest.raises(loop.LoopError) as exc:
        loop.seat(git_stub(branch="spec-1262"))
    assert "spec-1262" in str(exc.value) and "main" in str(exc.value)


def test_seat_refuses_a_branch_that_is_not_the_default():
    with pytest.raises(loop.LoopError) as exc:
        loop.seat(git_stub(branch="implement-893"))
    assert "implement-893" in str(exc.value) and "main" in str(exc.value)


def test_seat_refuses_a_detached_head():
    with pytest.raises(loop.LoopError) as exc:
        loop.seat(git_stub(branch=""))
    assert "detached" in str(exc.value)


# The #781 fixture, as the run actually stood after `#453` landed: `#452`,
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


def picked_for(candidates, in_flight, free):
    return loop.picks(loop.frontier(candidates, in_flight), free)[0]


def parked_455():
    return [{"tickets": [455], "workspace": "/w/implement-455",
             "agent": "run-455", "closure": ["examples/renban.js", HOT],
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
            picked_for(candidates_781(), parked_455(), 1)] == [[501]]


def test_picks_fills_every_free_slot_widest_first_ticket_ties():
    # No wave: two slots free and nothing in flight, so both go at once.
    # #452, #457 and #458 tie at closure size 2 (widest); #501 is narrower at
    # 1. The same-tick guard holds #457 and #458 over #452's shared file, so
    # #452 and the untied #501 are what actually goes out — this fixture
    # cannot tell widest-first from lowest-ticket-first on its own; the
    # untied case is `test_picks_takes_the_widest_closure_first`.
    picked = picked_for(candidates_781(), [], 2)
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


def test_picks_names_a_same_tick_collision_past_the_free_slot_cut():
    # #1049: at --free 1 the walk stopped at #452 and never examined #457 or
    # #458, so a controller saw one pick and no held line. Both collide with
    # the pick and must be named; #501 collides with nothing, so it is
    # simply out of slots, not held.
    picked, held = loop.picks(loop.frontier(candidates_781(), []), 1)
    assert [c["tickets"] for c in picked] == [[452]]
    by_ticket = {tuple(h["clump"]["tickets"]): h for h in held}
    assert sorted(by_ticket) == [(457,), (458,)]
    assert by_ticket[(458,)]["holder"] == 452
    assert by_ticket[(458,)]["same_tick"] is True


def test_picks_holds_a_clump_sharing_a_directory_with_a_same_tick_pick():
    # #1342: #1337 and #1338 named disjoint files in one directory and both
    # diffs reached `implement-spec/loop.py`. A body under-names its targets, so
    # two clumps whose lists share a directory are not picked in one tick.
    candidates = [
        {"tickets": [1311], "files": ["implement-spec/runfile.py", "implement-spec/SKILL.md"]},
        {"tickets": [1312, 1313], "files": ["implement-spec/loop.py"]},
        {"tickets": [1400], "files": ["implement/SKILL.md"]},
    ]
    picked, held = loop.picks(loop.frontier(candidates, []), 3)
    assert [c["tickets"] for c in picked] == [[1311], [1400]]
    assert len(held) == 1
    assert held[0]["clump"]["tickets"] == [1312, 1313]
    assert held[0]["holder"] == 1311
    assert held[0]["over"] == ["implement-spec/"]
    assert held[0]["same_tick"] is True


def test_picks_holds_a_nested_directory():
    c = [{"tickets": [1], "files": ["d/a.py", "d/b.py"]},
         {"tickets": [2], "files": ["d/r/x.md"]}]
    picked, held = loop.picks(loop.frontier(c, []), 2)
    assert [x["tickets"] for x in picked] == [[1]] and held[0]["over"] == ["d/"]


def test_picks_does_not_treat_the_repo_root_as_a_shared_directory():
    candidates = [
        {"tickets": [1], "files": ["AGENTS.md"]},
        {"tickets": [2], "files": ["GLOSSARY.md"]},
    ]
    picked, held = loop.picks(loop.frontier(candidates, []), 2)
    assert [c["tickets"] for c in picked] == [[1], [2]]
    assert held == []


def test_the_cli_names_a_same_tick_directory_hold_as_a_held_line(tmp):
    cand = os.path.join(tmp, "candidates.json")
    live = os.path.join(tmp, "live.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [10], "files": ["d/a.py"]},
                   {"tickets": [11], "files": ["d/b.py"]}], fh)
    with open(live, "w") as fh:
        json.dump([], fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--free", "2", "--processes", "4", "--committed-gb", "4")
    assert got.returncode == 0, got
    assert "dispatch  #10" in got.stdout, got.stdout
    assert "dispatch  #11" not in got.stdout, got.stdout
    assert "held      #11  by #10 this tick  over d/" in got.stdout, got.stdout


def test_a_live_workspace_holds_a_clump_naming_its_directory():
    # spec-649-smcc (#1406 C1): #666 listed the directory `examples/hit-counts`
    # and was dispatched beside live #655, which was editing
    # `examples/hit-counts/build_size.py`. The live hold reads directories as
    # the same-tick guard does, so the directory hold outlasts its tick.
    candidates = [{"tickets": [666], "files": ["examples/hit-counts"]},
                  {"tickets": [700], "files": ["docs/a.md"]}]
    live = [{"tickets": [655], "workspace": "/w/implement-655",
             "files": ["examples/hit-counts/build_size.py"]}]
    state = loop.frontier(candidates, live)
    assert [c["tickets"] for c in state["dispatchable"]] == [[700]]
    assert len(state["held"]) == 1, state["held"]
    assert state["held"][0]["holder"] == 655
    assert state["held"][0]["over"] == ["examples/"]


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


def test_a_wide_clump_held_by_a_live_workspace_stays_off_the_frontier():
    # #1026 review, P2: the widest-first sort runs inside `picks`, on what
    # `frontier` already filtered — a regression that moved the sort above
    # the frontier's exclusion would dispatch #20 straight into #455's
    # collision. #20 is the widest candidate here and still held; #30, the
    # narrower one, is what goes out.
    candidates = [
        {"tickets": [20], "closure": ["b.js", "c.js", "d.js", HOT]},
        {"tickets": [30], "closure": ["f.js", "g.js"]},
    ]
    picked = loop.picks(loop.frontier(candidates, parked_455()), 2)[0]
    assert [c["tickets"] for c in picked] == [[30]]


def test_the_cli_dispatch_names_the_widest_clump_first(tmp):
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


def test_each_pick_prints_its_implement_dispatch_command_carrying_the_run(tmp):
    # A run's --run on every plain dispatch was prose only (#1173 S1, P2,
    # C2, codex-second-1): the command the controller runs is printed here,
    # with the run id dispatch was itself given. It also carries the run's
    # recorded target checkout, not the cwd's (#1190): `implement-dispatch`
    # resolves issue numbers against a checkout, and the cwd may be another repo.
    target = os.path.realpath(os.path.join(tmp, "target"))
    os.makedirs(target)
    subprocess.run(["git", "init", "-q", target], check=True)
    cand, live, env = run_file_dispatch(tmp, ("none",), repo=target)
    with open(cand, "w") as fh:
        json.dump([{"tickets": [500, 502], "closure": ["fresh.py"]}], fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "2", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 0, got
    commands = [line for line in got.stdout.splitlines()
                if line.startswith("command")]
    assert commands == [
        f"command   implement-dispatch 500 502 --run run-t --repo {target}"
    ], got.stdout


def test_the_printed_command_shell_quotes_a_target_path_with_a_space_1190(tmp):
    target = os.path.realpath(os.path.join(tmp, "a repo"))
    os.makedirs(target)
    subprocess.run(["git", "init", "-q", target], check=True)
    cand, live, env = run_file_dispatch(tmp, ("none",), repo=target)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "2", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 0, got
    assert f"--run run-t --repo '{target}'" in got.stdout, got.stdout


def test_dispatch_refuses_a_run_file_that_names_no_target_repo_1190(tmp):
    # A run file from before the field loads, but a command printed without
    # `--repo` would claim against the cwd's origin: refuse, never omit.
    cand, live, env = run_file_dispatch(tmp, ("none",), legacy=True)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "2", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 1, got
    assert "names no target repo" in got.stderr, got.stderr
    assert "implement-dispatch" not in got.stdout, got.stdout


def test_the_cli_names_a_same_tick_collision_as_a_held_line(tmp):
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


def test_picks_takes_nothing_when_no_slot_is_free():
    assert picked_for(candidates_781(), [], 0) == []


def test_a_landing_frees_its_slot_without_waiting_for_the_other_clump():
    # #501 lands while #455 is still parked: the recomputed frontier is the
    # blocked family, so the freed slot stays empty rather than colliding —
    # and the run drains out of ticket order.
    left = [c for c in candidates_781() if c["tickets"] != [501]]
    assert loop.picks(loop.frontier(left, parked_455()), 1)[0] == []
    # #455 lands too, and the same call now fills from the family it held.
    assert [c["tickets"] for c in picked_for(left, [], 1)] == [[452]]


def test_a_clump_clumped_by_subtree_is_checked_on_its_named_files():
    # Subtree mode resolves no closure, so `closure.py` emits `files` and no
    # `closure` key. The exclusion still has to read something.
    candidates = [{"tickets": [601], "files": ["examples/thermo.js"]}]
    live = [{"tickets": [455], "workspace": "/w/implement-455",
             "agent": "run-455", "files": ["examples/thermo.js"]}]
    assert loop.picks(loop.frontier(candidates, live), 1)[0] == []


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

def test_the_cli_dispatch_charges_live_workers_at_their_peak(tmp):
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


def test_an_idle_boxs_os_process_count_is_not_the_cap_reading(tmp, empty_live):
    # A WSL box idles at ~190 OS processes. The cap counts agent processes,
    # so the CLI must dispatch when the agent count is small, and the
    # refusal must name what it counted.
    cand = os.path.join(tmp, "candidates.json")
    with open(cand, "w") as fh:
        json.dump(candidates_781(), fh)
    idle = loop_py("dispatch", "--in-flight", empty_live, "--candidates", cand, "--free", "1",
                   "--processes", "19", "--committed-gb", "0")
    assert idle.returncode == 0, idle.stderr
    assert "dispatch  #" in idle.stdout, idle.stdout
    full = loop_py("dispatch", "--in-flight", empty_live, "--candidates", cand, "--free", "1",
                   "--processes", "28", "--committed-gb", "0")
    assert full.returncode == 1
    assert "28 agent processes" in full.stderr, full.stderr
    assert "not OS processes" in full.stderr, full.stderr


# A negative count would sit under the cap for any workers asked about,
# so the documented escape hatch would switch the gate off on a typo.
@pytest.mark.parametrize("cmd", [("box", "--live", "0"),
                                 ("dispatch", "--candidates", "x", "--free", "1")])
def test_the_cli_refuses_a_negative_processes_override(cmd):
    got = loop_py(*cmd, "--processes", "-1", "--committed-gb", "0")
    assert got.returncode != 0, got
    assert "box ok" not in got.stdout and "dispatch" not in got.stdout
    assert "--processes" in got.stderr and "negative" in got.stderr, \
        got.stderr


def test_the_cli_accepts_a_processes_override_of_zero():
    zero = loop_py("box", "--processes", "0", "--committed-gb", "0",
                    "--live", "0")
    assert zero.returncode == 0, zero.stderr


def test_the_cli_dispatch_refuses_when_ps_cannot_be_run(tmp, empty_live):
    cand = os.path.join(tmp, "candidates.json")
    with open(cand, "w") as fh:
        json.dump(candidates_781(), fh)
    nobin = os.path.join(tmp, "empty-path")
    os.mkdir(nobin)
    got = loop_py("dispatch", "--in-flight", empty_live, "--candidates",
                  cand, "--free", "1", "--committed-gb", "0",
                  env={"PATH": nobin})
    assert got.returncode == 1, got
    assert "dispatch  #" not in got.stdout, got.stdout
    assert "--processes" in got.stderr, got.stderr


def test_the_cli_refuses_when_ps_cannot_be_run(tmp):
    env = {**os.environ, "PATH": tmp}
    got = subprocess.run([sys.executable, LOOP, "box", "--committed-gb",
                          "0", "--live", "0"], capture_output=True, text=True,
                         timeout=60, env=env)
    assert got.returncode == 1, got
    assert "--processes" in got.stderr, got.stderr
    assert "box ok" not in got.stdout, got.stdout


LOOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loop.py")


@pytest.fixture
def empty_live(tmp_path):
    """`dispatch` demands its in-flight snapshot; an explicit empty list is how
    a test says no worker is live."""
    path = tmp_path / "empty-live.json"
    path.write_text("[]")
    return str(path)


def loop_py(*args, cwd=None, env=None, real_workspaces=False):
    """Runs loop.py. `dispatch` requires --run, so a call that gives none gets
    a run file built from the `job` fields of its --in-flight file — the
    fixture's own record of each worker's job, moved to where dispatch reads
    it."""
    args = list(args)
    tmp = None
    if args[:1] == ["dispatch"] and not real_workspaces:
        args.append("--no-workspace-diff")
    if args[:1] == ["dispatch"] and "--run" not in args and "--in-flight" in args:
        tmp = tempfile.TemporaryDirectory()
        env = {**(env or {}), "SPEC_RUN_CACHE_DIR": tmp.name}
        args += ["--run", fixture_run(tmp.name, args[args.index("--in-flight") + 1])]
    try:
        return subprocess.run([sys.executable, LOOP, *args],
                              capture_output=True, text=True, timeout=60,
                              cwd=cwd,
                              env=None if env is None else {**os.environ, **env})
    finally:
        if tmp:
            tmp.cleanup()


def fixture_run(cache, in_flight_path):
    """A run file in `cache` holding each in-flight fixture entry as a clump,
    with its `job` recorded when the fixture carries one, else left unrecorded."""
    import runfile
    runfile.start("fixture", 5, None, root=cache, repo=REPO)
    with open(in_flight_path) as fh:
        clumps = json.load(fh)
    for entry in clumps:
        try:
            lowest = min(entry["tickets"])
            runfile.clump("fixture", entry["tickets"], entry["workspace"],
                          entry.get("agent", f"agent-{lowest}"), root=cache)
            job = entry.get("job")
            if job is not None:
                runfile.job("fixture", lowest, job["state"],
                            job.get("cores", 0), root=cache)
            else:
                # A registration records `none` (#1311); the fixture's
                # "no job" is the legacy no-record state.
                drop_job("fixture", cache, lowest)
        except (KeyError, TypeError, ValueError, AttributeError,
                runfile.RunFileError):
            # A malformed entry is the test's subject: dispatch's own reader
            # refuses it before the run file is consulted.
            continue
    return "fixture"


def test_the_cli_box_check_exits_nonzero_on_a_refusal():
    ok = loop_py("box", "--processes", "4", "--committed-gb", "4",
                 "--live", "0")
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
@pytest.mark.parametrize("extra, said", [
    ((), ["--live"]),
    (("--live", "-1"), ["--live", "negative"]),
])
def test_the_cli_box_refuses_an_absent_or_negative_live_count(extra, said):
    got = loop_py("box", "--processes", "27", "--committed-gb", "0", *extra)
    assert got.returncode != 0 and "box ok" not in got.stdout, got
    for word in said:
        assert word in got.stderr, got.stderr


def test_a_landed_clump_is_not_a_live_worker_for_the_peak_charge(tmp):
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


def test_the_cli_dispatch_prints_the_picks_and_what_holds_the_rest(tmp):
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


def test_the_cli_hub_says_whether_a_landing_moved_the_queues_closures(tmp):
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
             "agent": "run-455", "files": ["examples/renban.js"],
             "closure": ["examples/renban.js", HOT]}]
    assert loop.picks(loop.frontier(candidates, live), 1)[0] == []


def test_picks_takes_nothing_for_a_free_count_below_zero():
    # A miscounted budget reads as a negative free count, and "fill every
    # free slot" must not read that as "fill them all".
    assert picked_for(candidates_781(), [], -1) == []


# A closure that failed to resolve is not an empty closure. Refused with
# nothing in flight too, where there is no live workspace to compare it
# against and the refusal would otherwise never fire.
@pytest.mark.parametrize("in_flight", [[], parked_455()])
def test_a_clump_with_no_files_is_refused_whatever_is_in_flight(in_flight):
    with pytest.raises(loop.LoopError) as exc:
        picked_for([{"tickets": [452]}], in_flight, 1)
    assert "#452" in str(exc.value) and "files" in str(exc.value)


def test_the_frontier_itself_refuses_a_clump_with_no_files():
    # `picks` would also refuse it later; the frontier's own
    # check is what refuses it to a caller reading only the frontier.
    with pytest.raises(loop.LoopError) as exc:
        loop.frontier([{"tickets": [452]}], [])
    assert "#452" in str(exc.value) and "files" in str(exc.value)


@pytest.mark.parametrize("content", [
    '[{"closure": ["a"]}]', '[[452]]', '{"tickets": [452]}', 'not json at all',
    '[{"tickets": ["452"], "closure": ["a"]}]'])
def test_a_malformed_clump_file_is_one_line_and_not_a_traceback(
        tmp, empty_live, content):
    bad = os.path.join(tmp, "candidates.json")
    with open(bad, "w") as fh:
        fh.write(content)
    got = loop_py("dispatch", "--in-flight", empty_live, "--candidates", bad, "--free", "1",
                  "--processes", "2", "--committed-gb", "0")
    assert got.returncode == 1, got
    assert "Traceback" not in got.stderr, got.stderr
    assert got.stderr.startswith("loop.py: "), got.stderr
    assert len(got.stderr.strip().splitlines()) == 1, got.stderr


def test_seat_names_the_remedy_when_origin_head_is_unset():
    def run(args):
        if args[0] == "symbolic-ref":
            raise loop.LoopError("git symbolic-ref failed: not a symbolic ref")
        return git_stub()(args)
    with pytest.raises(loop.LoopError) as exc:
        loop.seat(run)
    assert "git remote set-head origin -a" in str(exc.value)


def test_the_cli_dispatch_refuses_when_the_box_has_no_room(tmp, empty_live):
    cand = os.path.join(tmp, "candidates.json")
    with open(cand, "w") as fh:
        json.dump(candidates_781(), fh)
    got = loop_py("dispatch", "--in-flight", empty_live, "--candidates", cand, "--free", "1",
                  "--processes", "40", "--committed-gb", "0")
    assert got.returncode == 1, got
    assert "dispatch" not in got.stdout, got.stdout
    assert "agent processes" in got.stderr, got.stderr


def test_the_cli_refuses_a_seat_in_a_worktree_it_makes_itself(tmp):
    # Deterministic, unlike reading whichever seat the suite happens to run
    # in: a repo with a linked worktree, built here, refused there.
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


def test_the_cli_accepts_a_seat_in_a_spec_worktree_it_makes_itself(tmp):
    primary = os.path.join(tmp, "primary")
    linked = os.path.join(tmp, "linked")
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", primary], check=True, timeout=60)
    open(os.path.join(primary, "f"), "w").close()
    subprocess.run([*git, "-C", primary, "add", "f"], check=True, timeout=60)
    subprocess.run([*git, "-C", primary, "commit", "-q", "-m", "one"],
                   check=True, timeout=60)
    subprocess.run(["git", "-C", primary, "worktree", "add", "-q", linked,
                    "-b", "spec-1262"], check=True, timeout=60)
    got = loop_py("seat", cwd=linked)
    assert got.returncode == 0, got
    assert got.stdout.startswith("spec-1262"), got.stdout
    subprocess.run(["git", "-C", primary, "worktree", "remove", "--force",
                    linked], check=True, timeout=60)


def test_an_in_flight_entry_with_no_workspace_is_one_line_not_a_traceback(tmp):
    # The other flag's hand-built file: `frontier` indexes `workspace` on
    # every live entry, so the reader has to require it there.
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


def test_the_cli_dispatch_takes_only_what_the_box_has_room_for(tmp, empty_live):
    cand = os.path.join(tmp, "candidates.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [452], "closure": ["a.js"]},
                   {"tickets": [457], "closure": ["b.js"]},
                   {"tickets": [458], "closure": ["c.js"]}], fh)
    got = loop_py("dispatch", "--in-flight", empty_live, "--candidates", cand, "--free", "3",
                  "--processes", "23", "--committed-gb", "23")
    assert got.returncode == 0, got.stderr
    assert got.stdout.count("dispatch  ") == 1, got.stdout
    assert "room for 1 of 3" in got.stdout, got.stdout


# `set("shared.py")` is a set of six letters, which intersects no real
# path set — so a malformed closure would read as a clump that collides
# with nobody and dispatch a second worker into a held file.
@pytest.mark.parametrize(
    "closure", ["shared.py", {"a": 1}, ["shared.py", 7], [""], []])
def test_a_closure_that_is_not_a_list_of_paths_is_refused(closure):
    with pytest.raises(loop.LoopError) as exc:
        loop.paths({"tickets": [1], "closure": closure})
    assert "#1" in str(exc.value)


@pytest.mark.parametrize("closure", ["shared.py", {"a": 1}, ["shared.py", 7]])
def test_a_malformed_closure_reaches_the_cli_as_one_line(tmp, closure):
    cand = os.path.join(tmp, "candidates.json")
    live = os.path.join(tmp, "live.json")
    with open(live, "w") as fh:
        json.dump([{"tickets": [2], "workspace": "/w/2",
                    "closure": ["shared.py"], "job": NO_JOB}], fh)
    with open(cand, "w") as fh:
        json.dump([{"tickets": [1], "closure": closure}], fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight",
                  live, "--free", "1", "--processes", "4",
                  "--committed-gb", "4")
    assert got.returncode == 1, got
    assert "dispatch" not in got.stdout, got.stdout
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
    with pytest.raises(loop.LoopError) as exc:
        loop.cleanup_ready(landed_454(), ["may I drop the 4x4 case?"])
    assert "#454" in str(exc.value)
    assert "implement-454-12" in str(exc.value)
    assert "may I drop the 4x4 case?" in str(exc.value)


def test_cleanup_is_ready_once_every_question_is_answered():
    assert loop.cleanup_ready(landed_454(), []) is True
    assert loop.cleanup_ready(landed_454()) is True


# A bare string iterates as characters, so "is it ok?" would read as ten
# outstanding questions and answer none of them — the same fail-closed
# rule `paths` applies one layer down.
@pytest.mark.parametrize(
    "outstanding", ["is it ok?", {"q": 1}, ["one?", 7], [""], [None]])
@pytest.mark.parametrize("call", [loop.landing_steps, loop.cleanup_ready],
                         ids=["landing_steps", "cleanup_ready"])
def test_an_outstanding_list_that_is_not_a_list_of_questions_is_refused(
        call, outstanding):
    with pytest.raises(loop.LoopError) as exc:
        call(landed_454(), outstanding)
    assert "#454" in str(exc.value)


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
    with pytest.raises(loop.LoopError) as exc:
        loop.landing_steps(landed_454(), ["one?\ntwo?"])
    assert "#454" in str(exc.value)
    assert "one line" in str(exc.value)


# A refusal whose job is to name the worker must not name nobody, and a
# clump is a ticket number. Nothing outstanding, so the flags are the
# only thing that can refuse this call — with a question outstanding the
# cleanup gate refuses anyway and the check would witness nothing.
@pytest.mark.parametrize("args, reason", [
    (("--clump", "454", "--agent", ""), "no agent named"),
    (("--clump", "0", "--agent", "run-1"), "ticket number"),
    (("--clump", "-5", "--agent", "run-1"), "ticket number"),
])
def test_the_cli_landing_refuses_an_empty_agent_and_a_non_positive_clump(
        args, reason):
    got = loop_py("landing", *args)
    assert got.returncode == 1, got
    assert reason in got.stderr, got.stderr
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
             "run-454", "--outstanding", "may I drop 4x4?"],
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
             "run-454", *questions],
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
    # skills-2 has sent "PR up", so an `idle` answer for it passes through as
    # herdr's word rather than reading `stalled` (#1148).
    return [
        {"tickets": [1], "workspace": "/w/1", "agent": "skills-1"},
        {"tickets": [2], "workspace": "/w/2", "agent": "skills-2",
         "pr_up": 1160},
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
    assert [w["agent"] for w in state["workers"]] == ["skills-1", "skills-3"], state


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
                          "pane": "run-1"}}}


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


def test_a_finished_pane_with_no_pr_up_is_stalled_and_says_read_the_pane():
    """#1095: the worker ended its turn mid-lane with a summary to no one,
    herdr showed `done`, and the sweep had no verdict for it. A finished pane
    (`done`, or `idle` once someone focused it) on an unsettled clump whose "PR
    up" is not on record is `stalled`, and its line says to read the pane,
    since a worker waiting on the controller's answer reads the same. With
    "PR up" on record the sweep prints herdr's own word."""
    calls = []
    clumps = live_clumps() + [
        {"tickets": [4], "workspace": "/w/4", "agent": "skills-4",
         "pr_up": 1161}]
    get = agent_stub({"skills-1": herdr_agent("done"),
                      "skills-2": herdr_agent("done"),
                      "skills-3": herdr_agent("idle"),
                      "skills-4": herdr_agent("idle")}, calls)
    state = loop.sweep(clumps, get)
    verdicts = {w["agent"]: w["verdict"] for w in state["workers"]}
    assert verdicts == {"skills-1": "stalled", "skills-2": "done",
                        "skills-3": "stalled", "skills-4": "idle"}, verdicts
    rendered = loop.render_sweep(state)
    assert ("stalled   #1  skills-1  /w/1  done with no PR up; read the pane "
            "(a worker waiting on your answer reads the same)") in rendered, \
        rendered
    assert ("stalled   #3  skills-3  /w/3  idle with no PR up; read the pane "
            "(a worker waiting on your answer reads the same)") in rendered, \
        rendered
    assert "done      #2" in rendered, rendered
    assert "idle      #4" in rendered, rendered


@pytest.mark.parametrize("bad", [0, "x", False, -3, True])
def test_a_pr_up_that_is_not_a_pr_number_does_not_quiet_a_done_pane(bad):
    """The sweep's `--workers` file is often hand-built, so a `pr_up` of 0,
    "x" or false reaches it unvalidated; only a real PR number is on record."""
    clumps = live_clumps()[:1]
    clumps[0]["pr_up"] = bad
    state = loop.sweep(clumps, agent_stub(
        {"skills-1": herdr_agent("done")}, []))
    assert state["workers"][0]["verdict"] == "stalled", state


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


def test_the_cli_holds_the_slot_and_says_so_in_its_status_line(tmp):
    cand, live = dispatch_files(tmp, {"state": "running", "cores": 8})
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--free", "1", "--processes", "4", "--committed-gb", "4")
    assert got.returncode == 0, got
    assert "cores" in got.stdout and "#351" in got.stdout, got.stdout
    assert "dispatch  #500" not in got.stdout, got.stdout


def test_the_cli_dispatch_treats_a_landed_clumps_null_job_as_a_freed_slot(tmp):
    # A run file sets `landed` without ever clearing `job`; charging that
    # entry's absent job record before filtering it out refuses the whole
    # tick with "live with no job record" (#1003).
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


def test_the_cli_dispatch_frontier_ignores_a_landed_clumps_own_closure(tmp):
    # A landed clump's workspace is dead — its change is on main, and the
    # next worker branches from main — so it holds nothing. `frontier` must
    # be fed the same `unsettled` collection core_room and the peak count
    # use, or a candidate sharing a file with the landed clump's closure
    # reads as blocked by a workspace that no longer exists (Codex gate on
    # PR #1050).
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


def test_the_cli_dispatch_reads_a_clump_closed_in_the_run_file_as_not_live(tmp):
    # #1310: a clump closed with no landing (already fixed on main, or a
    # nested spec run) is still listed in --in-flight, with no job on record
    # and a closure the candidate shares. The run file's `closed` is what
    # frees its slot and its files — nothing in --in-flight says so.
    cache = os.path.join(tmp, "cache")
    runfile.start("run-close", 5, None, root=cache, repo=REPO)
    runfile.clump("run-close", [351], "/w/351", "sm-351", root=cache)
    runfile.clump("run-close", [412], "/w/412", "sm-412", root=cache)
    runfile.job("run-close", 412, "none", root=cache)
    runfile.close("run-close", 351, "nested spec run", root=cache)
    cand = os.path.join(tmp, "candidates.json")
    live = os.path.join(tmp, "live.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [500], "closure": ["verify.py"]}], fh)
    with open(live, "w") as fh:
        json.dump(in_flight_clumps(), fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--free", "1", "--processes", "4", "--committed-gb", "4",
                  "--run", "run-close", env={"SPEC_RUN_CACHE_DIR": cache})
    assert got.returncode == 0, got.stderr
    assert "dispatch  #500" in got.stdout, got.stdout
    assert "held" not in got.stdout, got.stdout


def test_the_cli_dispatch_skips_a_candidate_the_run_file_records_as_landed(tmp, empty_live):
    # #1313: the candidates file is the frozen set and the run file is the
    # progress, so a landed or closed clump is not offered again.
    cache = os.path.join(tmp, "cache")
    runfile.start("run-skip", 5, None, root=cache, repo=REPO)
    runfile.clump("run-skip", [1258], "/w/1258", "a-1258", root=cache)
    runfile.clump("run-skip", [1293, 1294], "/w/1293", "a-1293", root=cache)
    runfile.clump("run-skip", [1278], "/w/1278", "a-1278", root=cache)
    runfile.land("run-skip", 1258, "a1b2c3d", root=cache)
    runfile.close("run-skip", 1293, "already fixed on main", root=cache)
    cand = os.path.join(tmp, "candidates.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [1258], "closure": ["a.py"]},
                   {"tickets": [1293, 1294], "closure": ["b.py"]},
                   {"tickets": [1278], "closure": ["c.py"]},
                   {"tickets": [1400], "closure": ["d.py"]}], fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight",
                  empty_live, "--free", "4", "--processes", "4",
                  "--committed-gb", "4", "--run", "run-skip",
                  env={"SPEC_RUN_CACHE_DIR": cache})
    assert got.returncode == 0, got.stderr
    for n in (1258, 1293):
        assert f"landed #{n}: skipped" in got.stdout, got.stdout
        assert f"dispatch  #{n}" not in got.stdout, got.stdout
    # Still in flight (neither landed nor closed): not skipped.
    assert "landed #1278" not in got.stdout, got.stdout
    assert "dispatch  #1400" in got.stdout, got.stdout


def test_a_closed_clump_is_not_diffed():
    asked = []
    live = [{"tickets": [9], "workspace": "/w/9", "closure": ["a"],
             "closed": "nested spec run"}]
    got = loop.with_workspace_diffs(live, lambda ws: asked.append(ws) or ["z"])
    assert asked == [] and loop.paths(got[0]) == {"a"}, (asked, got)


def test_the_sweep_skips_a_closed_clump():
    calls = []
    clumps = live_clumps()
    clumps[1]["closed"] = "already fixed on main"
    get = agent_stub({"skills-1": herdr_agent("working"),
                      "skills-3": HERDR_GONE}, calls)
    state = loop.sweep(clumps, get)
    assert calls == ["skills-1", "skills-3"], calls
    assert [w["agent"] for w in state["workers"]] == ["skills-1", "skills-3"], state


def test_the_cli_refuses_a_dispatch_while_a_worker_is_unrecorded(tmp):
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
    with pytest.raises(loop.LoopError) as exc:
        loop.core_room(2, in_flight_clumps(job=None, other=NO_JOB))
    assert "#351" in str(exc.value)
    assert "#412" not in str(exc.value)
    assert "runfile.py job" in str(exc.value)


@pytest.mark.parametrize("record", [
    {"state": "running", "cores": 0},
    {"state": "running", "cores": "8"},
    {"state": "spinning", "cores": 1},
    {"state": "running", "cores": True},
    "8",
])
def test_a_job_record_that_is_not_one_is_refused(record):
    with pytest.raises(loop.LoopError) as exc:
        loop.core_room(2, in_flight_clumps(job=record, other=NO_JOB))
    assert "#351" in str(exc.value)


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


def test_the_cli_sweep_probes_each_live_slot_once_through_herdr(tmp):
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
                    "agent": "skills-2", "pr_up": 1160},
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


def test_the_cli_sweep_reads_the_run_file_itself_given_a_run_id(tmp):
    # `--run` loads the run file through runfile.load(), so the controller
    # no longer extracts `.clumps` by hand (#1173 codex-third-1).
    bindir = os.path.join(tmp, "bin")
    os.mkdir(bindir)
    stub = os.path.join(bindir, "herdr")
    with open(stub, "w") as fh:
        fh.write(HERDR_STUB)
    os.chmod(stub, 0o755)
    cache = os.path.join(tmp, "cache")
    runfile.start("run-sweep-run-fixture", slots=2, root=cache, repo=REPO)
    runfile.clump("run-sweep-run-fixture", [1], "/w/1", "skills-1", root=cache)
    runfile.clump("run-sweep-run-fixture", [3], "/w/3", "skills-3", root=cache)
    runfile.clump("run-sweep-run-fixture", [4], "/w/4", "skills-4", root=cache)
    runfile.land("run-sweep-run-fixture", 4, "a1b2c3d", root=cache)
    calls = os.path.join(tmp, "calls")
    env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
               CALLS=calls, SPEC_RUN_CACHE_DIR=cache)
    got = subprocess.run([sys.executable, LOOP, "sweep", "--run",
                          "run-sweep-run-fixture"], capture_output=True, text=True,
                         timeout=60, env=env)
    assert got.returncode == 0, got
    assert "working   #1" in got.stdout, got.stdout
    assert "vanished  #3" in got.stdout, got.stdout
    with open(calls) as fh:
        assert fh.read().split() == ["skills-1", "skills-3"], \
            "a landed clump is not probed"
    missing = subprocess.run([sys.executable, LOOP, "sweep", "--run",
                              "run-none"], capture_output=True,
                             text=True, timeout=60, env=env)
    assert missing.returncode == 1, missing
    assert "run-none" in missing.stderr, missing.stderr
    assert "Traceback" not in missing.stderr, missing.stderr


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


def test_the_cli_sweep_refuses_a_box_with_no_herdr_rather_than_reporting_death(tmp):
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


@pytest.mark.parametrize("content", [
    '{"tickets": [1]}', '[{"tickets": []}]', '[{"tickets": ["1"]}]', 'not json'])
def test_the_cli_sweep_refuses_a_workers_file_it_cannot_read(tmp, content):
    workers = os.path.join(tmp, "workers.json")
    with open(workers, "w") as fh:
        fh.write(content)
    got = loop_py("sweep", "--workers", workers)
    assert got.returncode == 1, got
    assert "Traceback" not in got.stderr, got.stderr
    assert len(got.stderr.strip().splitlines()) == 1, got.stderr


def test_the_cli_says_the_declared_job_holds_the_slot_and_not_the_box(tmp):
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


def test_the_cli_dispatch_measures_before_it_says_a_declared_job_holds_the_slot(tmp):
    # The early "nothing to dispatch" return used to run before the
    # measurement, so a broken `ps` hid behind a healthy exit 0.
    cand, live = dispatch_files(tmp, {"state": "running", "cores": 8})
    nobin = os.path.join(tmp, "empty-path")
    os.mkdir(nobin)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--free", "1", "--committed-gb", "4",
                  env={"PATH": nobin})
    assert got.returncode == 1, got
    assert "held by a declared job" not in got.stdout, got.stdout
    assert "dispatch  #" not in got.stdout, got.stdout
    assert "--processes" in got.stderr, got.stderr


SLOW_HERDR = """#!/usr/bin/env bash
sleep 30
"""


def test_a_probe_that_never_answers_is_given_up_on(tmp, monkeypatch):
    """C3's witness: the sweep is bounded on the wall clock too, because a
    controller waiting on a hung herdr is inside a tool call, where no worker
    can reach it."""
    bindir = os.path.join(tmp, "bin")
    os.mkdir(bindir)
    stub = os.path.join(bindir, "herdr")
    with open(stub, "w") as fh:
        fh.write(SLOW_HERDR)
    os.chmod(stub, 0o755)
    monkeypatch.setenv("PATH", bindir, prepend=os.pathsep)
    started = time.monotonic()
    state = loop.sweep(
        [{"tickets": [1], "workspace": "/w/1", "agent": "skills-1"}],
        agents.herdr_get, budget=0.3)
    waited = time.monotonic() - started
    assert state["workers"][0]["verdict"] == "unreachable", state
    assert "did not answer" in state["workers"][0]["detail"], state
    assert waited < 5, f"the sweep waited {waited:.1f}s on one hung probe"


def test_a_held_clump_is_still_named_when_declared_jobs_hold_every_slot(tmp):
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


def test_the_cli_sweep_of_several_hung_panes_returns_within_one_deadline(tmp):
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
               SPEC_RUN_SWEEP_BUDGET="1")
    started = time.monotonic()
    got = subprocess.run([sys.executable, LOOP, "sweep", "--workers",
                          workers], capture_output=True, text=True,
                         timeout=60, env=env)
    waited = time.monotonic() - started
    assert got.returncode == 0, got
    assert waited < 8, f"four hung panes held the sweep {waited:.1f}s"
    assert got.stdout.count("unswept") >= 2, got.stdout


def test_dispatch_without_an_in_flight_snapshot_is_refused(tmp):
    # An omitted snapshot must not read as "no worker is live" (#933).
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


def run_file_dispatch(tmp, recorded, repo=REPO, legacy=False):
    """`closure.py --json` plus workspace as the controller builds it — no
    `job` field — and a run file in a private cache dir. `recorded` is the
    `runfile.py job` call for clump 351, or None to record nothing. `repo` is
    the run's target checkout; `legacy` writes a run file from before the
    field."""
    import runfile
    cache = os.path.join(tmp, "cache")
    os.makedirs(cache)
    runfile.start("run-t", 5, None, root=cache, repo=repo)
    if legacy:
        drop_repo_field("run-t", cache)
    runfile.clump("run-t", [351], "/w/351", "sm-351", root=cache)
    runfile.clump("run-t", [412], "/w/412", "sm-412", root=cache)
    runfile.job("run-t", 412, "none", root=cache)
    if recorded:
        runfile.job("run-t", 351, *recorded, root=cache)
    else:
        drop_job("run-t", cache, 351)
    cand = os.path.join(tmp, "candidates.json")
    live = os.path.join(tmp, "live.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [500], "closure": ["fresh.py"]}], fh)
    clumps = in_flight_clumps()
    for clump in clumps:
        del clump["job"]
    with open(live, "w") as fh:
        json.dump(clumps, fh)
    return cand, live, {"SPEC_RUN_CACHE_DIR": cache}


def test_dispatch_reads_the_job_record_from_the_run_file_1107(tmp):
    cand, live, env = run_file_dispatch(tmp, ("running", 8))
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "1", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 0, got
    assert "#351 declared 8 cores" in got.stdout, got.stdout
    assert "dispatch  #500" not in got.stdout, got.stdout


def test_dispatch_refuses_a_clump_the_run_file_has_no_job_for_1107(tmp):
    cand, live, env = run_file_dispatch(tmp, None)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "1", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 1, got
    assert "#351 is live with no job record" in got.stderr, got.stderr


def test_dispatch_does_not_wait_for_pr_up_on_a_freshly_registered_clump_1311(tmp):
    # A clump registered and never declared (the worker has sent nothing yet)
    # charges nothing, so the free slot is dispatched into at once.
    cand, live, env = run_file_dispatch(tmp, ("none",))
    cache = env["SPEC_RUN_CACHE_DIR"]
    runfile.clump("run-t", [777], "/w/777", "sm-777", root=cache)
    with open(live) as fh:
        clumps = json.load(fh)
    clumps.append({"tickets": [777], "workspace": "/w/777",
                   "agent": "sm-777", "closure": ["x.py"]})
    with open(live, "w") as fh:
        json.dump(clumps, fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "1", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 0, got
    assert "dispatch  #500" in got.stdout, got.stdout


def test_a_tick_between_the_workers_own_write_and_the_controllers_turn_holds_the_slots_1339(tmp):
    # Registration records `none`, so a tick before any declaration dispatches
    # into the free slot. The worker then records its own 8-core job with the
    # CLI, in its own process, and no controller turn follows: the next tick
    # must read that record and hold the slots (#1339, owner ruling (b)).
    cand, live, env = run_file_dispatch(tmp, ("none",))
    tick = ("dispatch", "--candidates", cand, "--in-flight", live,
            "--run", "run-t", "--free", "1", "--processes", "4",
            "--committed-gb", "4")
    before = loop_py(*tick, env=env)
    assert "dispatch  #500" in before.stdout, before
    wrote = subprocess.run(
        [sys.executable, runfile.__file__, "job", "run-t",
         "--clump", "351", "--cores", "8"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, **env})
    assert wrote.returncode == 0, wrote
    after = loop_py(*tick, env=env)
    assert after.returncode == 0, after
    assert "#351 declared 8 cores" in after.stdout, after.stdout
    assert "dispatch  #500" not in after.stdout, after.stdout


def test_dispatch_names_runfile_clump_for_an_unregistered_clump_1126(tmp):
    # `runfile.py job` fails with "has no clump" on a clump the run file never
    # registered, so the refusal must name `runfile.py clump`, not `job`.
    import runfile
    cand, live, env = run_file_dispatch(tmp, ("none",))
    cache = env["SPEC_RUN_CACHE_DIR"]
    with open(live) as fh:
        clumps = json.load(fh)
    clumps.append({"tickets": [777], "workspace": "/w/777",
                   "agent": "sm-777", "closure": ["x.py"]})
    with open(live, "w") as fh:
        json.dump(clumps, fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "1", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 1, got
    assert "#777" in got.stderr and "runfile.py clump" in got.stderr, \
        got.stderr
    assert "no job record" not in got.stderr, got.stderr
    # A registered clump with no job still names `job`.
    runfile.clump("run-t", [888], "/w/888", "sm-888", root=cache)
    drop_job("run-t", cache, 888)
    clumps[-1]["tickets"] = [888]
    with open(live, "w") as fh:
        json.dump(clumps, fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "1", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 1, got
    assert "#888 is live with no job record" in got.stderr, got.stderr
    assert "not registered" not in got.stderr, got.stderr


def test_dispatch_names_the_overlap_when_an_unregistered_key_shares_tickets(tmp):
    # In-flight [300, 351] against a registered [351]: `runfile.py clump
    # --tickets 300,351` refuses on "already in clump #351", so the refusal
    # names the overlap instead of prescribing it (#1173 C1).
    cand, live, env = run_file_dispatch(tmp, ("none",))
    with open(live) as fh:
        clumps = json.load(fh)
    clumps[0]["tickets"] = [300, 351]
    with open(live, "w") as fh:
        json.dump(clumps, fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "1", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 1, got
    assert "#300" in got.stderr and "#351" in got.stderr, got.stderr
    assert "overlaps" in got.stderr, got.stderr
    assert "runfile.py clump" not in got.stderr, got.stderr


def test_dispatch_refuses_when_only_the_in_flight_file_carries_the_job_1107(tmp):
    # The refusal must come from the run file's silence: an in-flight `job`
    # that would charge cleanly is ignored once --run is given (review C1).
    cand, live, env = run_file_dispatch(tmp, None)
    with open(live) as fh:
        clumps = json.load(fh)
    clumps[0]["job"] = NO_JOB
    with open(live, "w") as fh:
        json.dump(clumps, fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "1", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 1, got
    assert "#351 is live with no job record" in got.stderr, got.stderr


def test_dispatch_matches_a_multi_ticket_clump_by_its_lowest_ticket_1107(tmp):
    # Review C2: the run file, not a stale in-flight `job`, is the charge, and
    # the clump is found by min(tickets) whatever order its tickets are listed.
    import runfile
    cache = os.path.join(tmp, "cache")
    os.makedirs(cache)
    runfile.start("run-t", 5, None, root=cache, repo=REPO)
    runfile.clump("run-t", [351, 360], "/w/351", "sm-351", root=cache)
    runfile.job("run-t", 351, "running", 8, root=cache)
    cand = os.path.join(tmp, "candidates.json")
    live = os.path.join(tmp, "live.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [500], "closure": ["fresh.py"]}], fh)
    with open(live, "w") as fh:
        json.dump([{"tickets": [360, 351], "workspace": "/w/351",
                    "agent": "sm-351", "closure": ["verify.py"],
                    "job": NO_JOB}], fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "1", "--processes", "4",
                  "--committed-gb", "4",
                  env={"SPEC_RUN_CACHE_DIR": cache})
    assert got.returncode == 0, got
    assert "#351 declared 8 cores" in got.stdout, got.stdout


def test_dispatch_requires_a_run_id_1107(tmp, empty_live):
    cand = os.path.join(tmp, "candidates.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [500], "closure": ["fresh.py"]}], fh)
    got = subprocess.run(
        [sys.executable, LOOP, "dispatch", "--candidates", cand,
         "--in-flight", empty_live, "--free", "1", "--processes", "4",
         "--committed-gb", "4"], capture_output=True, text=True,
        timeout=60)
    assert got.returncode != 0, got
    assert "--run" in got.stderr, got.stderr
    assert "dispatch  #500" not in got.stdout, got.stdout


def test_a_job_field_in_the_in_flight_file_is_never_charged_1107(tmp):
    # The in-flight file claims an 8-core job; the run file records none.
    # Only the run file's record is charged, so the slot is free.
    cand, live, env = run_file_dispatch(tmp, ("done",))
    with open(live) as fh:
        clumps = json.load(fh)
    clumps[0]["job"] = {"state": "running", "cores": 8}
    with open(live, "w") as fh:
        json.dump(clumps, fh)
    got = loop_py("dispatch", "--candidates", cand, "--in-flight", live,
                  "--run", "run-t", "--free", "1", "--processes", "4",
                  "--committed-gb", "4", env=env)
    assert got.returncode == 0, got
    assert "declared 8 cores" not in got.stdout, got.stdout
    assert "dispatch  #500" in got.stdout, got.stdout


def test_load_run_reads_a_run_file_and_wraps_its_refusal_as_a_loop_error(tmp):
    # One loader behind `with_run_jobs` and `sweep --run` (#1209 S2).
    runfile.start("run-loader", slots=2, root=tmp, repo=REPO)
    runfile.clump("run-loader", [7], "/w/7", "skills-7", root=tmp)
    run = loop.load_run("run-loader", tmp)
    assert [c["tickets"] for c in run["clumps"]] == [[7]], run
    with pytest.raises(loop.LoopError) as exc:
        loop.load_run("run-none", tmp)
    assert "run-none" in str(exc.value)


def test_a_workspaces_real_diff_joins_its_in_flight_closure():
    # #1212: the closure resolved from the ticket's named files misses what the
    # worker's diff really reaches; the diff is unioned in at every dispatch.
    live = [{"tickets": [431], "workspace": "/w/431", "closure": ["rig.mjs"]}]
    got = loop.with_workspace_diffs(
        live, lambda ws: ["server.collection.test.mjs", "rig.mjs"])
    assert loop.paths(got[0]) == {"rig.mjs", "server.collection.test.mjs"}, got
    assert loop.paths(live[0]) == {"rig.mjs"}, "the input was mutated"


def test_an_undeclared_file_in_the_diff_holds_a_candidate_off_the_frontier():
    live = loop.with_workspace_diffs(
        [{"tickets": [431], "workspace": "/w/431", "closure": ["rig.mjs"]}],
        lambda ws: ["docs/obs-layout.md"])
    cand = [{"tickets": [442], "closure": ["docs/obs-layout.md"]}]
    state = loop.frontier(cand, live)
    assert state["dispatchable"] == [], state
    assert state["held"][0]["over"] == ["docs/obs-layout.md"], state


def test_a_subtree_clump_without_a_closure_gets_the_diff_in_its_files():
    got = loop.with_workspace_diffs(
        [{"tickets": [5], "workspace": "/w/5", "files": ["a/x.js"]}],
        lambda ws: ["b/y.js"])
    assert loop.paths(got[0]) == {"a/x.js", "b/y.js"}, got
    assert "closure" not in got[0], got


def test_a_landed_clump_is_not_diffed():
    asked = []
    live = [{"tickets": [9], "workspace": "/w/9", "closure": ["a"],
             "landed": True}]
    got = loop.with_workspace_diffs(live, lambda ws: asked.append(ws) or ["z"])
    assert asked == [] and loop.paths(got[0]) == {"a"}, (asked, got)


def test_a_diff_that_cannot_be_read_refuses_rather_than_reading_empty():
    def broken(ws):
        raise loop.LoopError(f"no diff for {ws}")
    with pytest.raises(loop.LoopError) as exc:
        loop.with_workspace_diffs(
            [{"tickets": [3], "workspace": "/w/3", "closure": ["a"]}], broken)
    assert "clump #3" in str(exc.value) and "/w/3" in str(exc.value)


def run_in(cwd, *cmd):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def make_workspace(tmp, changed, default="main"):
    """A real clone whose branch adds each of `changed`, one commit apiece,
    past its origin's `default` branch."""
    origin = os.path.join(tmp, "origin.git")
    work = os.path.join(tmp, "work")
    run_in(tmp, "git", "init", "-q", "--bare", "-b", default, origin)
    run_in(tmp, "git", "clone", "-q", origin, work)
    for k, v in (("user.email", "t@example.com"), ("user.name", "t")):
        run_in(work, "git", "config", k, v)
    with open(os.path.join(work, "a.txt"), "w") as fh:
        fh.write("a")
    run_in(work, "git", "add", "a.txt")
    run_in(work, "git", "commit", "-qm", "a")
    run_in(work, "git", "push", "-q", "origin", f"HEAD:{default}")
    run_in(work, "git", "remote", "set-head", "origin", default)
    run_in(work, "git", "checkout", "-q", "-b", "implement-1")
    for name in changed:
        with open(os.path.join(work, name), "w") as fh:
            fh.write("b")
        run_in(work, "git", "add", name)
        run_in(work, "git", "commit", "-qm", f"add {name}")
    return work


def test_workspace_diff_lists_files_changed_against_the_origin_default(tmp):
    # A default that is not `main` and two commits on the branch: a diff
    # against a hard-coded `origin/main`, or against `HEAD~1`, reads wrong
    # (#1212 C6).
    work = make_workspace(tmp, ["b.txt", "c.txt"], default="trunk")
    assert sorted(loop.workspace_diff(work)) == ["b.txt", "c.txt"]
    with pytest.raises(loop.LoopError):
        loop.workspace_diff(os.path.join(tmp, "missing"))


def make_slice_workspace(tmp, own, landed):
    """`make_workspace`, plus an origin `spec-9` holding each of `landed`
    (other slices' files), and a branch cut from it that adds each of `own`
    and records `branch.implement-1.base` as `spec-9` the way dispatch does."""
    work = make_workspace(tmp, [])
    run_in(work, "git", "checkout", "-q", "-b", "spec-9", "origin/main")
    for name in landed:
        with open(os.path.join(work, name), "w") as fh:
            fh.write("s")
        run_in(work, "git", "add", name)
        run_in(work, "git", "commit", "-qm", f"landed {name}")
    run_in(work, "git", "push", "-q", "origin", "spec-9")
    run_in(work, "git", "checkout", "-q", "implement-1")
    run_in(work, "git", "reset", "-q", "--hard", "origin/spec-9")
    run_in(work, "git", "config", "branch.implement-1.base", "spec-9")
    for name in own:
        with open(os.path.join(work, name), "w") as fh:
            fh.write("b")
        run_in(work, "git", "add", name)
        run_in(work, "git", "commit", "-qm", f"add {name}")
    return work


def test_workspace_diff_of_a_slice_is_against_its_integration_branch_1486(tmp):
    # A slice branch holds every slice already landed on `spec-<p>`; against
    # the default they all read as its own files and hold unrelated clumps.
    work = make_slice_workspace(tmp, own=["own.txt"],
                                landed=["landed.txt"])
    assert loop.workspace_diff(work) == ["own.txt"]


def test_workspace_diff_of_a_branch_with_no_recorded_base_is_against_default(tmp):
    work = make_slice_workspace(tmp, own=["own.txt"],
                                landed=["landed.txt"])
    run_in(work, "git", "config", "--unset", "branch.implement-1.base")
    assert sorted(loop.workspace_diff(work)) == ["landed.txt", "own.txt"]


def test_workspace_diff_of_a_slice_that_merged_an_advanced_integration_branch_1486(tmp):
    # The ticket's first criterion: spec-9 moved on after the slice was cut and
    # the slice merged it in; the other slice's file is still not its own.
    work = make_slice_workspace(tmp, own=["own.txt"], landed=[])
    run_in(work, "git", "checkout", "-q", "spec-9")
    with open(os.path.join(work, "later.txt"), "w") as fh:
        fh.write("s")
    run_in(work, "git", "add", "later.txt")
    run_in(work, "git", "commit", "-qm", "later slice")
    run_in(work, "git", "push", "-q", "origin", "spec-9")
    run_in(work, "git", "checkout", "-q", "implement-1")
    run_in(work, "git", "merge", "-q", "--no-edit", "origin/spec-9")
    assert loop.workspace_diff(work) == ["own.txt"]


def test_workspace_diff_reads_a_base_that_is_not_a_integration_branch_as_no_slice(tmp):
    # As `implement/fix_check.py` reads it: only `spec-<n>` marks a slice.
    work = make_slice_workspace(tmp, own=["own.txt"],
                                landed=["landed.txt"])
    run_in(work, "git", "config", "branch.implement-1.base", "main")
    assert sorted(loop.workspace_diff(work)) == ["landed.txt", "own.txt"]


def test_workspace_diff_of_a_slice_whose_integration_branch_is_gone_names_the_key(tmp):
    work = make_slice_workspace(tmp, own=["own.txt"], landed=[])
    run_in(work, "git", "config", "branch.implement-1.base", "spec-77")
    with pytest.raises(loop.LoopError) as exc:
        loop.workspace_diff(work)
    assert "branch.implement-1.base" in str(exc.value)
    assert "origin/spec-77" in str(exc.value)


def test_workspace_diff_includes_uncommitted_and_untracked_edits_1254(tmp):
    # #1212 P2: a worker that has not committed yet has still reached its
    # files; the committed history alone reads it as touching nothing.
    work = make_workspace(tmp, ["b.txt"])
    with open(os.path.join(work, "a.txt"), "w") as fh:
        fh.write("edited, unstaged")
    with open(os.path.join(work, "staged.txt"), "w") as fh:
        fh.write("s")
    run_in(work, "git", "add", "staged.txt")
    with open(os.path.join(work, "untracked.txt"), "w") as fh:
        fh.write("u")
    assert sorted(loop.workspace_diff(work)) == [
        "a.txt", "b.txt", "staged.txt", "untracked.txt"]


def test_workspace_diff_names_both_sides_of_a_rename(tmp):
    # #1212 C1: a candidate naming the old path collides with the rename.
    work = make_workspace(tmp, [])
    run_in(work, "git", "mv", "a.txt", "renamed.txt")
    run_in(work, "git", "commit", "-qm", "rename")
    assert sorted(loop.workspace_diff(work)) == ["a.txt", "renamed.txt"]


def test_workspace_diff_returns_a_non_ascii_path_unquoted(tmp):
    # #1212 C2: git's default output quotes it, so it never matches a raw path.
    work = make_workspace(tmp, ["caf\u00e9.md"])
    assert loop.workspace_diff(work) == ["caf\u00e9.md"]


def test_workspace_diff_refuses_a_directory_that_is_not_its_own_checkout(tmp):
    # #1212 C3: a workspace path with its `.git` gone resolves to the checkout
    # around it and would read as a branch that changed nothing.
    work = make_workspace(tmp, ["b.txt"])
    inner = os.path.join(work, "gone")
    os.mkdir(inner)
    with pytest.raises(loop.LoopError) as exc:
        loop.workspace_diff(inner)
    assert "not a checkout root" in str(exc.value)


def test_the_cli_dispatch_says_when_it_skipped_the_workspace_diff(tmp):
    cand = os.path.join(tmp, "candidates.json")
    live = os.path.join(tmp, "live.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [10], "closure": ["a.js"]}], fh)
    with open(live, "w") as fh:
        json.dump([], fh)
    args = ("dispatch", "--candidates", cand, "--in-flight", live,
            "--free", "1", "--processes", "4", "--committed-gb", "4")
    skipped = loop_py(*args)
    assert "workspace diff: SKIPPED" in skipped.stdout, skipped.stdout
    read = loop_py(*args, real_workspaces=True)
    assert read.returncode == 0, read.stderr
    assert "SKIPPED" not in read.stdout, read.stdout


def test_the_cli_dispatch_holds_a_candidate_on_a_file_only_the_diff_reaches(tmp):
    work = make_workspace(tmp, ["b.txt"])
    cand = os.path.join(tmp, "candidates.json")
    live = os.path.join(tmp, "live.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [442], "closure": ["b.txt"]}], fh)
    with open(live, "w") as fh:
        json.dump([{"tickets": [431], "workspace": work,
                    "closure": ["a.txt"],
                    "job": {"state": "running", "cores": 1}}], fh)
    args = ("dispatch", "--candidates", cand, "--in-flight", live,
            "--free", "1", "--processes", "4", "--committed-gb", "4")
    got = loop_py(*args, real_workspaces=True)
    assert got.returncode == 0, got.stderr
    assert "dispatch  #442" not in got.stdout, got.stdout
    assert "b.txt" in got.stdout, got.stdout
    with open(live, "w") as fh:
        json.dump([{"tickets": [431], "workspace": work + "-gone",
                    "closure": ["a.txt"],
                    "job": {"state": "running", "cores": 1}}], fh)
    refused = loop_py(*args, real_workspaces=True)
    assert refused.returncode == 1, refused.stdout
    assert "431" in refused.stderr, refused.stderr


# --- one handler per subcommand (#1769) ---------------------------------

SUBCOMMAND_HANDLERS = {
    "seat": "cmd_seat", "box": "cmd_box", "dispatch": "cmd_dispatch",
    "sweep": "cmd_sweep", "hub": "cmd_hub", "landing": "cmd_landing",
}


def test_each_subcommand_parses_to_its_own_handler_1769():
    argv = {
        "seat": ["seat"],
        "box": ["box", "--committed-gb", "1", "--live", "0"],
        "dispatch": ["dispatch", "--candidates", "c", "--in-flight", "f",
                     "--run", "r", "--free", "1", "--committed-gb", "1"],
        "sweep": ["sweep", "--run", "r"],
        "hub": ["hub", "--candidates", "c", "--landed", "a"],
        "landing": ["landing", "--clump", "1", "--agent", "a"],
    }
    parser = loop.build_parser()
    for command, handler in SUBCOMMAND_HANDLERS.items():
        assert parser.parse_args(argv[command]).func is getattr(loop, handler)


def test_cmd_dispatch_runs_alone_without_the_parser_1769(tmp, monkeypatch, capsys):
    import argparse
    cand = os.path.join(tmp, "candidates.json")
    live = os.path.join(tmp, "live.json")
    with open(cand, "w") as fh:
        json.dump([{"tickets": [20], "closure": ["b.js"]}], fh)
    with open(live, "w") as fh:
        json.dump([], fh)
    cache = os.path.join(tmp, "cache")
    os.mkdir(cache)
    monkeypatch.setenv("SPEC_RUN_CACHE_DIR", cache)
    run_id = fixture_run(cache, live)
    args = argparse.Namespace(
        candidates=cand, in_flight=live, run=run_id, free=1,
        no_workspace_diff=True, processes=4, committed_gb=4.0)
    assert loop.cmd_dispatch(args) == 0
    assert "dispatch  #20  #20" in capsys.readouterr().out


def test_run_turns_a_handlers_loop_error_into_a_refusal_1769(monkeypatch, capsys):
    def refuse(args):
        raise loop.LoopError("nope")
    monkeypatch.setattr(loop, "cmd_seat", refuse)
    assert loop.run(["loop.py", "seat"]) == 1
    assert "loop.py: nope" in capsys.readouterr().err
