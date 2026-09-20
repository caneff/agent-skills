#!/usr/bin/env python3
"""Tests for the burn run file (#892). Two seams: the read/write contract,
round-tripped through a re-read that stands in for a restart, and the resume
path's re-announce step against a stub agent list.

`BURNDOWN_CACHE_DIR` keeps every case off the real `~/.cache/burndown`.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runfile  # noqa: E402

RUNFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runfile.py")


# Every fixture cache dir this run makes, removed at the end whatever the run
# did. Leaking one per test is how a shared box ends up carrying thousands of
# them (`closure_test.py` measured 1,863 before it grew this) — the cost is
# inodes, not bytes.
FIXTURES = []


def cache():
    """An empty cache dir standing in for `~/.cache/burndown`, removed by
    `clean_fixtures` at the end of the run, pass or fail."""
    root = tempfile.mkdtemp(prefix="runfile-fixture-")
    FIXTURES.append(root)
    return root


def clean_fixtures():
    """Remove every fixture this run made; return the ones that survived. A
    fixture that cannot be removed is reported, never ignored."""
    left = []
    while FIXTURES:
        root = FIXTURES.pop()
        # Two tests take a directory's read or write permission away, so each
        # is opened back up before the tree goes.
        try:
            os.chmod(root, 0o700)
        except OSError:
            pass
        for dirpath, dirnames, filenames in os.walk(root):
            for name in dirnames + filenames:
                try:
                    os.chmod(os.path.join(dirpath, name), 0o700)
                except OSError:
                    pass
        shutil.rmtree(root, ignore_errors=True)
        if os.path.exists(root):
            left.append(root)
    return left


def test_start_writes_the_run_id_and_slot_budget_and_load_reads_them_back():
    root = cache()
    runfile.start("burn-2026-09-20-0905", slots=3, root=root)
    run = runfile.load("burn-2026-09-20-0905", root=root)
    assert run["run_id"] == "burn-2026-09-20-0905", run
    assert run["slots"] == 3, run
    assert run["clumps"] == [], run


def test_the_file_lands_at_run_id_dot_json_under_the_cache_dir():
    root = cache()
    runfile.start("burn-1", slots=1, root=root)
    assert os.path.isfile(os.path.join(root, "burn-1.json")), os.listdir(root)


def test_start_refuses_a_run_id_that_already_has_a_file():
    # A resumed controller that re-runs `start` would otherwise wipe the very
    # state it restarted to read.
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    try:
        runfile.start("burn-1", slots=9, root=root)
    except runfile.RunFileError as exc:
        assert "burn-1" in str(exc), exc
    else:
        raise AssertionError("a second start clobbered the run")
    assert runfile.load("burn-1", root=root)["slots"] == 2


def test_a_run_id_that_would_leave_the_cache_dir_is_refused():
    root = cache()
    for bad in ("../escape", "a/b", "", ".", "..", ".hidden"):
        try:
            runfile.start(bad, slots=1, root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted run id {bad!r}")
    assert os.listdir(root) == [], os.listdir(root)


def test_loading_a_run_that_was_never_started_names_the_path():
    root = cache()
    try:
        runfile.load("burn-nope", root=root)
    except runfile.RunFileError as exc:
        assert "burn-nope.json" in str(exc), exc
    else:
        raise AssertionError("a missing run file read as a run")


# --- Clumps: the ticket list, the workspace, the herdr agent name ----------

def test_a_clump_records_its_tickets_workspace_and_herdr_agent_name():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [902, 901], "/w/implement-901", "implement-901-42",
                  root=root)
    got = runfile.load("burn-1", root=root)["clumps"]
    assert got == [{"tickets": [901, 902], "workspace": "/w/implement-901",
                    "agent": "implement-901-42", "landed": None}], got


def test_a_clump_is_keyed_by_its_lowest_ticket_and_re_registers_in_place():
    # A clump redispatched after a park keeps its identity; the workspace and
    # the herdr agent name are the parts that move.
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.clump("burn-1", [901, 902], "/w/b", "agent-b", root=root)
    got = runfile.load("burn-1", root=root)["clumps"]
    assert len(got) == 1, got
    assert got[0]["workspace"] == "/w/b" and got[0]["agent"] == "agent-b", got


def test_a_ticket_already_in_another_clump_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    try:
        runfile.clump("burn-1", [902, 903], "/w/b", "agent-b", root=root)
    except runfile.RunFileError as exc:
        assert "902" in str(exc), exc
    else:
        raise AssertionError("one ticket landed in two clumps")
    assert len(runfile.load("burn-1", root=root)["clumps"]) == 1


def test_a_clump_needs_at_least_one_ticket_number():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    for bad in ([], ["901"], [0], [-1]):
        try:
            runfile.clump("burn-1", bad, "/w/a", "agent-a", root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted tickets {bad!r}")
    assert runfile.load("burn-1", root=root)["clumps"] == [], "a refusal wrote"


# --- Landings -------------------------------------------------------------

def test_a_landing_records_the_clumps_squash_sha():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "0123456789abcdef0123456789abcdef01234567",
                 root=root)
    got = runfile.load("burn-1", root=root)["clumps"][0]
    assert got["landed"] == "0123456789abcdef0123456789abcdef01234567", got


def test_a_landing_on_a_clump_the_run_never_dispatched_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    try:
        runfile.land("burn-1", 901, "abc1234", root=root)
    except runfile.RunFileError as exc:
        assert "901" in str(exc), exc
    else:
        raise AssertionError("a landing recorded against no clump")


def test_a_second_different_sha_for_a_landed_clump_is_refused():
    # The squash sha is final. A second, different one is a stale writer.
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)  # idempotent
    try:
        runfile.land("burn-1", 901, "def5678", root=root)
    except runfile.RunFileError as exc:
        assert "abc1234" in str(exc), exc
    else:
        raise AssertionError("a landing sha was overwritten")
    assert runfile.load("burn-1", root=root)["clumps"][0]["landed"] == "abc1234"


def test_a_landing_sha_is_hex():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    for bad in ("", "HEAD", "abc123", "zzzzzzz", "abc1234 "):
        try:
            runfile.land("burn-1", 901, bad, root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted sha {bad!r}")
    got = runfile.load("burn-1", root=root)["clumps"][0]
    assert got["landed"] is None, got


def test_re_registering_a_landed_clump_keeps_its_sha():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a2", root=root)
    assert runfile.load("burn-1", root=root)["clumps"][0]["landed"] == "abc1234"


# --- Resume: reconcile against the live agents, re-announce the controller -

def three_clumps(root):
    runfile.start("burn-1", slots=3, controller="burn-ctl-1a", root=root)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.clump("burn-1", [903], "/w/b", "agent-b", root=root)
    runfile.clump("burn-1", [905], "/w/c", "agent-c", root=root)
    runfile.land("burn-1", 905, "abc1234", root=root)


def test_resume_splits_live_from_vanished_workers_and_from_landings():
    root = cache()
    three_clumps(root)
    got = runfile.resume("burn-1", ["agent-a", "someone-elses-agent"],
                         root=root)
    assert [c["agent"] for c in got["announce"]] == ["agent-a"], got
    assert [c["agent"] for c in got["vanished"]] == ["agent-b"], got
    assert [c["tickets"] for c in got["landed"]] == [[905]], got


def test_resume_recovers_the_slot_budget_and_counts_the_free_slots():
    root = cache()
    three_clumps(root)
    got = runfile.resume("burn-1", ["agent-a"], root=root)
    assert got["slots"] == 3, got
    assert got["free"] == 2, got  # one live worker holds one of the three


def test_a_landed_clump_is_never_re_announced_even_if_its_agent_is_alive():
    root = cache()
    three_clumps(root)
    got = runfile.resume("burn-1", ["agent-a", "agent-c"], root=root)
    assert [c["agent"] for c in got["announce"]] == ["agent-a"], got
    assert got["free"] == 2, got


def test_resume_writes_the_controllers_current_agent_name_into_the_run_file():
    # The restart that renamed the controller is the whole reason this file
    # exists: every live worker's brief carries the dead name.
    root = cache()
    three_clumps(root)
    got = runfile.resume("burn-1", ["agent-a"], controller="burn-ctl-f3",
                         root=root)
    assert got["controller"] == "burn-ctl-f3", got
    assert runfile.load("burn-1", root=root)["controller"] == "burn-ctl-f3"


def test_resume_without_a_new_name_leaves_the_recorded_controller_alone():
    root = cache()
    three_clumps(root)
    got = runfile.resume("burn-1", [], root=root)
    assert got["controller"] == "burn-ctl-1a", got
    assert runfile.load("burn-1", root=root)["controller"] == "burn-ctl-1a"


# --- Durability: the write the restart interrupts --------------------------

def test_a_write_that_dies_before_it_finishes_leaves_the_old_run_intact():
    # The premise of the whole file: the machine can go down mid-run. A
    # half-written run file is worse than a stale one — it reads as a run
    # with no clumps.
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    before = open(runfile.path("burn-1", root=root)).read()

    replace = os.replace
    os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("power cut"))
    try:
        runfile.land("burn-1", 901, "abc1234", root=root)
    except runfile.RunFileError:
        pass
    else:
        raise AssertionError("a failed write reported success")
    finally:
        os.replace = replace

    assert open(runfile.path("burn-1", root=root)).read() == before
    assert os.listdir(root) == ["burn-1.json"], os.listdir(root)



# --- The CLI: what a controller actually runs ------------------------------

def cli(root, *args):
    return subprocess.run(
        [sys.executable, RUNFILE, *args], capture_output=True, text=True,
        env={**os.environ, "BURNDOWN_CACHE_DIR": root})


def test_a_run_killed_mid_flight_is_recovered_by_a_second_process():
    # The round trip the ticket asks for, across process boundaries: nothing
    # of the run survives in memory, only the file.
    root = cache()
    assert cli(root, "start", "burn-1", "--slots", "3",
               "--controller", "burn-ctl-1a").returncode == 0
    assert cli(root, "clump", "burn-1", "--tickets", "901,902",
               "--workspace", "/w/a", "--agent", "agent-a").returncode == 0
    assert cli(root, "clump", "burn-1", "--tickets", "905",
               "--workspace", "/w/c", "--agent", "agent-c").returncode == 0
    assert cli(root, "land", "burn-1", "--clump", "905",
               "--sha", "abc1234").returncode == 0

    got = cli(root, "resume", "burn-1", "--live", "agent-a",
              "--controller", "burn-ctl-f3")
    assert got.returncode == 0, got.stderr
    out = got.stdout
    assert "slots 3" in out and "free 2" in out, out
    assert "burn-ctl-f3" in out, out
    assert "re-announce  agent-a" in out, out
    assert "#901,#902" in out and "/w/a" in out, out
    assert "landed" in out and "abc1234" in out, out


def test_the_cli_reports_a_vanished_worker_by_its_herdr_agent_name():
    root = cache()
    cli(root, "start", "burn-1", "--slots", "2")
    cli(root, "clump", "burn-1", "--tickets", "903", "--workspace", "/w/b",
        "--agent", "agent-b")
    got = cli(root, "resume", "burn-1", "--live", "agent-a")
    assert "vanished" in got.stdout and "agent-b" in got.stdout, got.stdout
    assert "re-announce" not in got.stdout, got.stdout


def test_show_prints_the_run_without_touching_it():
    root = cache()
    cli(root, "start", "burn-1", "--slots", "2", "--controller", "ctl")
    cli(root, "clump", "burn-1", "--tickets", "901", "--workspace", "/w/a",
        "--agent", "agent-a")
    before = open(os.path.join(root, "burn-1.json")).read()
    got = cli(root, "show", "burn-1")
    assert got.returncode == 0, got.stderr
    assert "run burn-1" in got.stdout and "agent-a" in got.stdout, got.stdout
    assert open(os.path.join(root, "burn-1.json")).read() == before


def test_a_refusal_is_one_stderr_line_and_a_nonzero_exit():
    root = cache()
    got = cli(root, "show", "burn-nope")
    assert got.returncode == 1, got
    assert got.stdout == "", got.stdout
    assert len(got.stderr.strip().splitlines()) == 1, got.stderr
    assert "Traceback" not in got.stderr, got.stderr


def test_the_default_home_is_the_cache_dir_that_survives_a_wsl_restart():
    # Nothing here writes: the default path is asserted, not exercised. It is
    # `~/.cache` and not `/tmp` or a session scratchpad, both of which a WSL
    # restart wipes — the event the run file exists for.
    was = os.environ.pop("BURNDOWN_CACHE_DIR", None)
    try:
        got = runfile.path("burn-1", root=None)
    finally:
        if was is not None:
            os.environ["BURNDOWN_CACHE_DIR"] = was
    assert got == os.path.expanduser("~/.cache/burndown/burn-1.json"), got


def test_the_suite_leaves_no_fixtures_behind():
    # Run as its own process with its own TMPDIR: the only honest witness
    # that the teardown removes what the run made.
    if os.environ.get("RUNFILE_TEST_CHILD"):
        return  # one child per run, not a suite per suite forever
    tmp = tempfile.mkdtemp(prefix="runfile-child-")
    FIXTURES.append(tmp)
    got = subprocess.run(
        [sys.executable, os.path.abspath(__file__)], capture_output=True,
        text=True, env={**os.environ, "TMPDIR": tmp, "RUNFILE_TEST_CHILD": "1"})
    assert got.returncode == 0, got.stdout + got.stderr
    assert os.listdir(tmp) == [], os.listdir(tmp)


def test_a_trailing_newline_does_not_sneak_through_a_run_id_or_a_sha():
    # `$` matches before a final newline; `\Z` does not. A run id with a
    # newline in it is a filename with a newline in it.
    root = cache()
    try:
        runfile.start("burn-1\n", slots=1, root=root)
    except runfile.RunFileError:
        pass
    else:
        raise AssertionError("a run id with a newline was accepted")
    runfile.start("burn-1", slots=1, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    try:
        runfile.land("burn-1", 901, "abc1234\n", root=root)
    except runfile.RunFileError:
        pass
    else:
        raise AssertionError("a sha with a newline was accepted")
    assert os.listdir(root) == ["burn-1.json"], os.listdir(root)


def test_a_slot_budget_that_is_not_a_positive_count_is_refused():
    root = cache()
    for bad in (0, -1, "3", 1.5, None, True):
        try:
            runfile.start("burn-1", slots=bad, root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted slots {bad!r}")
    assert os.listdir(root) == [], os.listdir(root)


def test_a_file_that_is_not_a_run_is_refused_rather_than_half_read():
    # The file outlives the code that wrote it, so a shape this module does
    # not recognise has to say so, not KeyError three calls later.
    root = cache()
    with open(os.path.join(root, "burn-1.json"), "w") as fh:
        fh.write('{"run_id": "burn-1", "slots": 2}')
    try:
        runfile.load("burn-1", root=root)
    except runfile.RunFileError as exc:
        assert "clumps" in str(exc), exc
    else:
        raise AssertionError("a file missing half the run read as a run")
    for name, content in (("burn-2", '["not a run at all"]'),
                          ("burn-3", '7'), ("burn-4", '"burn-4"')):
        with open(os.path.join(root, f"{name}.json"), "w") as fh:
            fh.write(content)
        try:
            runfile.load(name, root=root)
        except runfile.RunFileError as exc:
            assert "not a run" in str(exc) or "missing" in str(exc), exc
        else:
            raise AssertionError(f"{content} read as a run")


def test_a_clump_with_no_workspace_or_no_agent_name_is_refused():
    # An agent name is the only way to reach that worker after a restart, and
    # a workspace path is the only way to read what it did. Blank is not an
    # answer to either.
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    for workspace, agent in (("", "agent-a"), ("/w/a", ""), ("/w/a", None),
                             (None, "agent-a"), ("/w/a", "  ")):
        try:
            runfile.clump("burn-1", [901], workspace, agent, root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted workspace {workspace!r} agent {agent!r}")
    assert runfile.load("burn-1", root=root)["clumps"] == []


def test_a_cache_dir_that_cannot_be_written_is_a_refusal_not_a_traceback():
    # After a restart `$HOME` can be full, read-only, or hold a file where the
    # cache dir belongs. A resumed controller needs the reason, not a stack.
    root = cache()
    with open(os.path.join(root, "afile"), "w") as fh:
        fh.write("not a directory")
    try:
        runfile.start("burn-1", slots=1, root=os.path.join(root, "afile", "sub"))
    except runfile.RunFileError as exc:
        assert "burn-1.json" in str(exc), exc
    else:
        raise AssertionError("a path through a file read as a cache dir")

    closed = os.path.join(root, "closed")
    os.mkdir(closed, 0o500)
    try:
        runfile.start("burn-1", slots=1, root=os.path.join(closed, "sub"))
    except runfile.RunFileError:
        pass
    else:
        raise AssertionError("a read-only parent wrote a run file")
    finally:
        os.chmod(closed, 0o700)


def test_a_cache_dir_that_cannot_be_read_still_records_the_write():
    # Mode 0300: writable and searchable, not readable. The write lands, so
    # reporting it as failed would leave the state on disk and the caller
    # told otherwise — and the retry then refuses with "already has a file".
    root = cache()
    os.chmod(root, 0o300)
    try:
        runfile.start("burn-1", slots=2, root=root)
    finally:
        os.chmod(root, 0o700)
    assert runfile.load("burn-1", root=root)["slots"] == 2


def test_a_clump_entry_of_a_shape_this_module_does_not_know_is_refused():
    root = cache()
    bad = ('{"run_id": "burn-1", "slots": 2, "controller": null,'
           ' "clumps": [{"tickets": [901]}]}')
    with open(os.path.join(root, "burn-1.json"), "w") as fh:
        fh.write(bad)
    try:
        runfile.load("burn-1", root=root)
    except runfile.RunFileError as exc:
        assert "clump" in str(exc), exc
    else:
        raise AssertionError("a clump missing its agent and sha read as one")
    for name, clumps in (("burn-2", '{"a": 1}'), ("burn-3", '[[901]]'),
                         ("burn-5", '7'), ("burn-6", 'null'),
                         ("burn-4", '[{"tickets": [], "workspace": "/w",'
                                    ' "agent": "a", "landed": null}]')):
        with open(os.path.join(root, f"{name}.json"), "w") as fh:
            fh.write('{"run_id": "%s", "slots": 1, "controller": null,'
                     ' "clumps": %s}' % (name, clumps))
        try:
            runfile.load(name, root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"clumps {clumps} read as a run")


def test_re_registering_a_clump_may_not_drop_a_ticket_from_it():
    # The file answers "which tickets are out". A clump re-registered under
    # its lowest ticket alone would drop the rest silently.
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    try:
        runfile.clump("burn-1", [901], "/w/b", "agent-b", root=root)
    except runfile.RunFileError as exc:
        assert "902" in str(exc), exc
    else:
        raise AssertionError("#902 was dropped from its own clump")
    assert runfile.load("burn-1", root=root)["clumps"][0]["tickets"] == [901, 902]
    # Growing the clump is the legitimate move: a closure re-resolve adds one.
    runfile.clump("burn-1", [901, 902, 903], "/w/a", "agent-a", root=root)
    assert runfile.load("burn-1", root=root)["clumps"][0]["tickets"] == [901, 902, 903]


def test_the_cli_refuses_a_ticket_list_python_would_read_creatively():
    # `int()` accepts `9_01` and `+901`. A run file that says #901 when the
    # brief said `9_01` is a wrong answer, not a lenient one.
    root = cache()
    cli(root, "start", "burn-1", "--slots", "2")
    # A doubled separator is not in this list: `901,,902` names exactly two
    # tickets and no other reading of it exists.
    # `str.isdigit()` is true for `²` (which `int()` then rejects) and for
    # `٩` (which `int()` accepts as 9) — one is a traceback, the other is a
    # ticket the brief never named.
    for bad in ("9_01", "+901", "901.0", " ", "-901", "0x385", "\u00b2",
                "\u0669" + "01"):
        got = cli(root, "clump", "burn-1", "--tickets", bad,
                  "--workspace", "/w/a", "--agent", "agent-a")
        assert got.returncode == 1, (bad, got.stdout, got.stderr)
        assert "Traceback" not in got.stderr, got.stderr
    assert runfile.load("burn-1", root=root)["clumps"] == []


def test_the_cli_expands_a_tilde_in_the_cache_dir_override():
    # `BURNDOWN_CACHE_DIR='~/.cache/x'` must not create a literal `./~/`
    # directory in whatever the controller's cwd happens to be.
    root = cache()
    home = os.path.join(root, "home")
    os.makedirs(home)
    got = subprocess.run(
        [sys.executable, RUNFILE, "start", "burn-1", "--slots", "1"],
        capture_output=True, text=True,
        env={**os.environ, "HOME": home, "BURNDOWN_CACHE_DIR": "~/cachedir"},
        cwd=root)
    assert got.returncode == 0, got.stderr
    assert os.path.isfile(os.path.join(home, "cachedir", "burn-1.json")), \
        sorted(os.listdir(root))
    assert "~" not in os.listdir(root), os.listdir(root)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    try:
        for test in tests:
            test()
            print(f"ok  {test.__name__}")
        print(f"{len(tests)} passed")
    finally:
        # In `finally`, because a failing assertion is exactly the run that
        # would otherwise leave its fixtures behind.
        left = clean_fixtures()
        if left:
            print(f"fixtures left behind: {', '.join(left)}", file=sys.stderr)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
