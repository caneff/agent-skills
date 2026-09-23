#!/usr/bin/env python3
"""Tests for the burn run file (#892). Two seams: the read/write contract,
round-tripped through a re-read that stands in for a restart, and the resume
path's re-announce step against a stub agent list.

`BURNDOWN_CACHE_DIR` keeps every case off the real `~/.cache/burndown`.
"""
import fcntl
import json
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


def test_start_without_slots_records_the_default_of_five():
    root = cache()
    runfile.start("burn-1", root=root)
    assert runfile.load("burn-1", root=root)["slots"] == 5


def test_cli_start_without_slots_records_five_and_a_named_value_wins():
    root = cache()
    assert cli(root, "start", "burn-1").returncode == 0
    assert runfile.load("burn-1", root=root)["slots"] == 5
    assert cli(root, "start", "burn-2", "--slots", "2").returncode == 0
    assert runfile.load("burn-2", root=root)["slots"] == 2
    assert cli(root, "start", "burn-3", "--slots", "0").returncode != 0


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


def runs_in(root):
    """The run files in a cache dir. A `<run-id>.json.lock` is the advisory
    lock, not a run."""
    return sorted(n for n in os.listdir(root) if n.endswith(".json"))


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
                    "agent": "implement-901-42", "landed": None,
                    "job": None}], got


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


# --- Leftovers: copied at landing from a PR's dispositions sidecar --------

# The shared fixture `multi-axis-code-review`/`implement` test against:
# `S1` fixed, `C2` fixed (adjacent), `P1` disputed, `C1` filed, `S2`
# handed-back, `S3` leftover. Only `S3` is a leftover line.
FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "implement", "fixtures",
    "dispositions-sidecar.jsonl")


def named_sidecar(number=901, source=FIXTURE):
    """A copy of `source` named `dispositions-<number>.jsonl`, the name
    `runfile.leftover` binds to a clump's tickets (#1084)."""
    path_ = os.path.join(cache(), f"dispositions-{number}.jsonl")
    shutil.copyfile(source, path_)
    return path_


SIDECAR = named_sidecar()


def test_leftover_copies_only_the_leftover_lines_with_every_field_filled():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    got = runfile.load("burn-1", root=root)["leftovers"]
    assert len(got) == 1, got
    entry = got[0]
    assert entry["clump"] == 901, entry
    assert entry["tickets"] == [901, 902], entry
    assert entry["pr"] == 950, entry
    assert entry["id"] == "S3", entry
    assert entry["file"] == "burndown/loop.py", entry
    assert entry["title"] == "Mysterious name: `tick2`", entry
    assert entry["severity"] == "judgement", entry
    assert "tick2" in entry["text"], entry


def test_leftover_run_twice_for_the_same_pr_does_not_duplicate():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    got = runfile.load("burn-1", root=root)["leftovers"]
    assert len(got) == 1, got


def test_leftover_on_a_clump_the_run_never_dispatched_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    try:
        runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    except runfile.RunFileError as exc:
        assert "901" in str(exc), exc
    else:
        raise AssertionError("a leftover recorded against no clump")


def test_leftover_reports_how_many_it_copied():
    # A wrong path is refused (§ hygiene), but a *readable, wrong-shaped*
    # file — every other command's own sidecar, say — silently copies
    # nothing today; the count is what tells a mistyped `--from` apart from
    # a PR that genuinely left nothing (defect class 1).
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    _, added = runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    assert added == ["S3"], added
    _, added_again = runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    assert added_again == [], added_again


def test_leftover_against_a_sidecar_with_no_leftover_line_copies_none():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    no_leftovers = sidecar_of({"id": "S1", "outcome": "fixed",
                               "sha": "0123abc"})
    try:
        _, added = runfile.leftover("burn-1", 901, 950, no_leftovers,
                                    root=root)
        assert added == [], added
    finally:
        os.remove(no_leftovers)


def sidecar_of(*lines, number=901):
    path_ = os.path.join(cache(), f"dispositions-{number}.jsonl")
    with open(path_, "w") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")
    return path_


def refusal_of(sidecar, root):
    """The refusal `runfile.leftover` raises for `sidecar`, its message."""
    try:
        runfile.leftover("burn-1", 901, 950, sidecar, root=root)
    except runfile.RunFileError as exc:
        assert runfile.load("burn-1", root=root)["leftovers"] == []
        return str(exc)
    raise AssertionError("a foreign sidecar was accepted")


def test_a_valid_sidecar_from_another_pr_is_refused():
    root = landed_root()
    got = refusal_of(named_sidecar(number=777), root)
    assert "#777" in got and "#901" in got, got


def test_a_foreign_sidecar_with_zero_leftovers_is_refused_not_recorded_clean():
    root = landed_root()
    got = refusal_of(
        sidecar_of({"id": "S1", "outcome": "fixed", "sha": "0123abc"},
                   number=777), root)
    assert "#777" in got, got


def test_a_sidecar_not_named_for_a_ticket_is_refused():
    root = landed_root()
    got = refusal_of(FIXTURE, root)
    assert "dispositions-<n>.jsonl" in got, got


def test_a_sidecar_for_any_ticket_of_the_clump_is_accepted():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    _, added = runfile.leftover("burn-1", 901, 950,
                                named_sidecar(number=902), root=root)
    assert added == ["S3"], added


def test_a_leftover_line_missing_a_required_field_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    sidecar = sidecar_of({"id": "S3", "outcome": "leftover",
                          "file": "burndown/loop.py", "title": "t",
                          "severity": "judgement"})  # no "text"
    try:
        try:
            runfile.leftover("burn-1", 901, 950, sidecar, root=root)
        except runfile.RunFileError as exc:
            assert "text" in str(exc), exc
        else:
            raise AssertionError("a leftover missing a field was copied")
    finally:
        os.remove(sidecar)
    assert runfile.load("burn-1", root=root)["leftovers"] == []


def test_a_leftover_line_with_a_blank_or_multiline_field_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    for bad in (
        {"id": "S3", "outcome": "leftover", "file": "",
         "title": "t", "severity": "judgement", "text": "t"},
        {"id": "S3", "outcome": "leftover", "file": "f.py",
         "title": "t", "severity": "judgement", "text": "line one\nline two"},
        {"id": "S3", "outcome": "leftover", "file": "f.py",
         "title": "t", "severity": "judgement", "text": "one\r# two"},
    ):
        sidecar = sidecar_of(bad)
        try:
            try:
                runfile.leftover("burn-1", 901, 950, sidecar, root=root)
            except runfile.RunFileError:
                continue
            raise AssertionError(f"accepted leftover line {bad!r}")
        finally:
            os.remove(sidecar)
    assert runfile.load("burn-1", root=root)["leftovers"] == []


def test_leftover_on_an_unlanded_clump_is_refused():
    # A retry or an out-of-order call must not persist leftovers for a PR
    # that may never land, with nothing able to remove them afterward.
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    try:
        runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    except runfile.RunFileError as exc:
        assert "901" in str(exc) and "land" in str(exc), exc
    else:
        raise AssertionError("leftovers recorded for an unlanded clump")
    assert runfile.load("burn-1", root=root)["leftovers"] == []


def test_a_line_with_no_outcome_or_an_unknown_outcome_is_refused():
    # `outcome != "leftover"` alone cannot tell a sidecar's own four other
    # outcomes from a wholly unrelated file (another command's sidecar, a
    # findings-*.jsonl) — both read as "skip", and a wrong --from silently
    # copies zero either way (defect class 1). The four recognised
    # non-leftover outcomes must still be skipped, not refused.
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    for bad in (
        {"id": "S3", "file": "x", "title": "t"},  # no outcome key at all
        {"id": "S3", "outcome": "mystery"},        # unrecognised outcome
    ):
        sidecar = sidecar_of(bad)
        try:
            try:
                runfile.leftover("burn-1", 901, 950, sidecar, root=root)
            except runfile.RunFileError:
                continue
            raise AssertionError(f"accepted line {bad!r}")
        finally:
            os.remove(sidecar)

    recognised = sidecar_of(
        {"id": "F1", "outcome": "fixed", "sha": "abc"},
        {"id": "F2", "outcome": "disputed", "reason": "why"},
        {"id": "F3", "outcome": "filed", "ticket": 1},
        {"id": "F4", "outcome": "handed-back", "command": "cmd"},
    )
    try:
        _, added = runfile.leftover("burn-1", 901, 950, recognised,
                                    root=root)
        assert added == [], added
    finally:
        os.remove(recognised)


def test_a_second_pr_for_the_same_clump_and_finding_id_is_refused():
    # `(pr, id)` alone lets the same finding land twice under two PR
    # numbers — a typo'd `--pr` would double-count it for the sweep, with
    # no undo but hand-editing the run file.
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    try:
        runfile.leftover("burn-1", 901, 951, SIDECAR, root=root)
    except runfile.RunFileError as exc:
        assert "S3" in str(exc) and "950" in str(exc), exc
    else:
        raise AssertionError("the same finding landed under two PR numbers")
    got = runfile.load("burn-1", root=root)["leftovers"]
    assert len(got) == 1 and got[0]["pr"] == 950, got


def test_cli_leftover_appends_and_show_prints_the_leftovers():
    root = cache()
    cli(root, "start", "burn-1", "--slots", "2")
    cli(root, "clump", "burn-1", "--tickets", "901", "--workspace", "/w/a",
        "--agent", "agent-a")
    cli(root, "land", "burn-1", "--clump", "901", "--sha", "abc1234")
    got = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
              "--from", SIDECAR, "--allow-stale")
    assert got.returncode == 0, got.stderr
    assert "copied 1 leftover" in got.stdout, got.stdout
    shown = cli(root, "show", "burn-1")
    assert shown.returncode == 0, shown.stderr
    assert "S3" in shown.stdout, shown.stdout
    assert "burndown/loop.py" in shown.stdout, shown.stdout
    assert "PR #950" in shown.stdout, shown.stdout
    assert "judgement" in shown.stdout, shown.stdout
    assert "Mysterious name" in shown.stdout, shown.stdout
    again = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
               "--from", SIDECAR, "--allow-stale")
    assert again.returncode == 0, again.stderr
    assert "copied 0 leftover" in again.stdout, again.stdout


def test_leftovers_survive_resume():
    root = cache()
    runfile.start("burn-1", slots=2, controller="ctl", root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    runfile.resume("burn-1", ["agent-a"], controller="ctl-f3", root=root)
    got = runfile.load("burn-1", root=root)["leftovers"]
    assert len(got) == 1 and got[0]["id"] == "S3", got


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


def test_a_vanished_clumps_slot_is_not_free_until_it_is_reconciled():
    # Three slots: one live worker, one vanished and unlanded, one landed. The
    # vanished worker may still be holding its tickets, so refilling its slot
    # puts a second worker in the same files.
    root = cache()
    three_clumps(root)
    got = runfile.resume("burn-1", ["agent-a"], root=root)
    assert got["slots"] == 3, got
    assert [c["agent"] for c in got["vanished"]] == ["agent-b"], got
    assert got["free"] == 1, got


def test_a_landed_clump_is_never_re_announced_even_if_its_agent_is_alive():
    root = cache()
    three_clumps(root)
    got = runfile.resume("burn-1", ["agent-a", "agent-c"], root=root)
    assert [c["agent"] for c in got["announce"]] == ["agent-a"], got
    # agent-c landed, so its slot is genuinely free; agent-b's is not.
    assert got["free"] == 1, got


def test_a_landing_frees_the_slot_a_vanished_clump_was_holding():
    root = cache()
    three_clumps(root)
    before = runfile.resume("burn-1", ["agent-a"], root=root)["free"]
    runfile.land("burn-1", 903, "def5678", root=root)
    after = runfile.resume("burn-1", ["agent-a"], root=root)["free"]
    assert (before, after) == (1, 2), (before, after)


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
    assert runs_in(root) == ["burn-1.json"], os.listdir(root)
    assert not [n for n in os.listdir(root) if n.endswith(".tmp")], os.listdir(root)



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
    assert runs_in(root) == ["burn-1.json"], os.listdir(root)


def test_a_slot_budget_that_is_not_a_positive_count_is_refused():
    root = cache()
    for bad in (0, -1, "3", 1.5, None, True):
        try:
            runfile.start("burn-1", slots=bad, root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted slots {bad!r}")
    assert runs_in(root) == [], os.listdir(root)


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


# --- F4: the shape check reaches every field --------------------------------

def test_a_run_file_whose_fields_are_the_wrong_type_is_refused_cleanly():
    # The guarantee is that an unrecognised run file is refused, and this is
    # the moment it is load-bearing: a controller recovering from a restart
    # needs a diagnostic, not a traceback three calls later.
    root = cache()
    good = {"run_id": "burn-1", "slots": 2, "controller": "ctl",
            "clumps": [{"tickets": [901], "workspace": "/w/a",
                        "agent": "agent-a", "landed": None}]}
    bad = [
        ("slots", "2"), ("slots", 0), ("slots", True), ("slots", 1.5),
        ("controller", 7), ("controller", ""),
        ("run_id", "burn-2"), ("run_id", 1),
        ("leftovers", "nope"), ("leftovers", {}),
    ]
    for key, value in bad:
        run = json.loads(json.dumps(good))
        run[key] = value
        write_run(root, "burn-1", run)
        try:
            runfile.load("burn-1", root=root)
        except runfile.RunFileError as exc:
            assert "burn-1.json" in str(exc), (key, value, exc)
            continue
        raise AssertionError(f"accepted {key}={value!r}")

    for key, value in (("tickets", ["901"]), ("tickets", [0]),
                       ("workspace", ""), ("workspace", None),
                       ("agent", 7), ("agent", "  "),
                       ("landed", "HEAD"), ("landed", 1234567)):
        run = json.loads(json.dumps(good))
        run["clumps"][0][key] = value
        write_run(root, "burn-1", run)
        try:
            runfile.load("burn-1", root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted clump {key}={value!r}")

    good_leftover = {"clump": 901, "tickets": [901], "pr": 950, "id": "S3",
                     "file": "burndown/loop.py", "title": "Mysterious name",
                     "severity": "judgement", "text": "rename it"}
    for key, value in (("clump", "901"), ("clump", 0), ("tickets", []),
                       ("pr", 0), ("pr", True),
                       ("id", ""), ("id", "a\nb"),
                       ("file", ""), ("file", "a\nb"),
                       ("title", "  "), ("severity", None),
                       ("text", "line one\nline two")):
        run = json.loads(json.dumps(good))
        run["leftovers"] = [json.loads(json.dumps(good_leftover))]
        run["leftovers"][0][key] = value
        write_run(root, "burn-1", run)
        try:
            runfile.load("burn-1", root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted leftover {key}={value!r}")

    write_run(root, "burn-1", good)
    assert runfile.load("burn-1", root=root)["slots"] == 2


def test_a_run_file_that_resume_cannot_arithmetic_on_never_reaches_resume():
    root = cache()
    write_run(root, "burn-1", {"run_id": "burn-1", "slots": "2",
                               "controller": None, "clumps": []})
    try:
        runfile.resume("burn-1", [], root=root)
    except runfile.RunFileError as exc:
        assert "slot budget" in str(exc), exc
    else:
        raise AssertionError("resume did arithmetic on a string slot budget")


def write_run(root, run_id, run):
    with open(os.path.join(root, f"{run_id}.json"), "w") as fh:
        json.dump(run, fh)


# --- F3: one writer at a time, enforced ------------------------------------

def test_two_concurrent_writers_do_not_lose_an_update():
    # Each process holds its critical section open past the other's read, so
    # without the lock the second replace would write back a run that never
    # saw the first clump. The delay is what makes this witness the lock
    # rather than pass on how two processes happen to interleave (the same
    # device flow/lane's two_concurrent_dispatches test uses).
    root = cache()
    cli(root, "start", "burn-1", "--slots", "4")
    env = {**os.environ, "BURNDOWN_CACHE_DIR": root,
           "BURNDOWN_RUNFILE_DELAY_MS": "400"}
    procs = [subprocess.Popen(
        [sys.executable, RUNFILE, "clump", "burn-1", "--tickets", str(n),
         "--workspace", f"/w/{n}", "--agent", f"agent-{n}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        for n in (901, 902, 903)]
    for proc in procs:
        out, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, err

    got = runfile.load("burn-1", root=root)["clumps"]
    assert [c["tickets"][0] for c in got] == [901, 902, 903], got


def test_a_lock_someone_else_holds_times_out_as_a_refusal():
    root = cache()
    cli(root, "start", "burn-1", "--slots", "2")
    lock = runfile.path("burn-1", root=root) + ".lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        # Bounded: a waiter that never gives up would otherwise hang the suite
        # instead of failing it, which is how this guard regresses unseen.
        got = subprocess.run(
            [sys.executable, RUNFILE, "clump", "burn-1", "--tickets", "901",
             "--workspace", "/w/a", "--agent", "agent-a"],
            capture_output=True, text=True, timeout=20,
            env={**os.environ, "BURNDOWN_CACHE_DIR": root,
                 "BURNDOWN_RUNFILE_LOCK_TIMEOUT": "1"})
    except subprocess.TimeoutExpired:
        raise AssertionError("the writer never gave up waiting for the lock")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert got.returncode == 1, got
    assert "lock" in got.stderr, got.stderr
    assert "Traceback" not in got.stderr, got.stderr
    assert runfile.load("burn-1", root=root)["clumps"] == []


# --- The environment reads: the same clean-refusal boundary -----------------

def test_a_malformed_environment_value_is_a_refusal_not_a_traceback():
    # Round 1's F4 was malformed persisted state escaping the clean-refusal
    # path; an unguarded `float()` on an inherited env value is the same
    # contract with a new surface. A bad value inherited from a parent shell
    # must not turn a restart recovery into a stack trace.
    root = cache()
    cli(root, "start", "burn-1", "--slots", "2")
    for name, value in (("BURNDOWN_RUNFILE_LOCK_TIMEOUT", "30s"),
                        ("BURNDOWN_RUNFILE_LOCK_TIMEOUT", "inf"),
                        ("BURNDOWN_RUNFILE_LOCK_TIMEOUT", "nan"),
                        ("BURNDOWN_RUNFILE_LOCK_TIMEOUT", "-5"),
                        ("BURNDOWN_RUNFILE_DELAY_MS", "abc"),
                        ("BURNDOWN_RUNFILE_DELAY_MS", "-1"),
                        ("BURNDOWN_RUNFILE_DELAY_MS", "nan")):
        got = subprocess.run(
            [sys.executable, RUNFILE, "clump", "burn-1", "--tickets", "901",
             "--workspace", "/w/a", "--agent", "agent-a"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "BURNDOWN_CACHE_DIR": root, name: value})
        assert got.returncode == 1, (name, value, got.stdout, got.stderr)
        assert "Traceback" not in got.stderr, got.stderr
        assert len(got.stderr.strip().splitlines()) == 1, got.stderr
        assert name in got.stderr, got.stderr
    assert runfile.load("burn-1", root=root)["clumps"] == []


def test_an_empty_environment_value_reads_as_unset():
    # `VAR=` is the shell's own way to clear an override, and every one of
    # these has a documented default to fall back to.
    root = cache()
    got = subprocess.run(
        [sys.executable, RUNFILE, "start", "burn-1", "--slots", "1"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "BURNDOWN_CACHE_DIR": root,
             "BURNDOWN_RUNFILE_LOCK_TIMEOUT": "",
             "BURNDOWN_RUNFILE_DELAY_MS": ""})
    assert got.returncode == 0, got.stderr
    assert runfile.load("burn-1", root=root)["slots"] == 1


def test_a_clump_starts_with_no_job_on_record():
    root = cache()
    runfile.start("r-job", 3, "dc", root)
    run = runfile.clump("r-job", [351], "/w/351", "sm-351", root)
    assert run["clumps"][0]["job"] is None, run


def test_a_declared_job_survives_a_restart():
    """The whole point: a controller that restarts mid-run recovers the hold.
    The declaration lived in one argv before, so a resume dispatched into the
    contention #351 produced."""
    root = cache()
    runfile.start("r-job2", 3, "dc", root)
    runfile.clump("r-job2", [351], "/w/351", "sm-351", root)
    runfile.job("r-job2", 351, "running", 8, root)
    # A fresh read stands in for the restart.
    run = runfile.load("r-job2", root)
    assert run["clumps"][0]["job"] == {"state": "running", "cores": 8}, run
    runfile.job("r-job2", 351, "done", root=root)
    assert runfile.load("r-job2", root)["clumps"][0]["job"] == {
        "state": "done", "cores": 0}


def test_a_worker_that_launched_no_job_is_recorded_as_having_said_so():
    root = cache()
    runfile.start("r-job3", 3, "dc", root)
    runfile.clump("r-job3", [351], "/w/351", "sm-351", root)
    runfile.job("r-job3", 351, "none", root=root)
    assert runfile.load("r-job3", root)["clumps"][0]["job"] == {
        "state": "none", "cores": 0}


def test_a_job_record_that_is_not_one_is_refused():
    root = cache()
    runfile.start("r-job4", 3, "dc", root)
    runfile.clump("r-job4", [351], "/w/351", "sm-351", root)
    for state, cores in (("running", 0), ("running", "8"), ("spinning", 1),
                         ("running", True), ("none", 4)):
        try:
            runfile.job("r-job4", 351, state, cores, root)
        except runfile.RunFileError:
            pass
        else:
            raise AssertionError(f"{state!r}/{cores!r} is not a job record")
    try:
        runfile.job("r-job4", 999, "none", root=root)
    except runfile.RunFileError as exc:
        assert "#999" in str(exc), exc
    else:
        raise AssertionError("a job must name a clump of this run")


def test_a_run_file_written_before_jobs_existed_still_reads():
    """#892's files have no `job` key. A controller resuming one of those
    must get its run back, not a refusal about a field that did not exist."""
    root = cache()
    runfile.start("r-old", 2, "dc", root)
    runfile.clump("r-old", [401], "/w/401", "sm-401", root)
    target = runfile.path("r-old", root)
    with open(target) as fh:
        raw = json.load(fh)
    del raw["clumps"][0]["job"]
    with open(target, "w") as fh:
        json.dump(raw, fh)
    run = runfile.load("r-old", root)
    assert run["clumps"][0]["job"] is None, run


def test_the_cli_records_a_job_and_shows_it():
    root = cache()
    assert cli(root, "start", "r-job5", "--slots", "2").returncode == 0
    assert cli(root, "clump", "r-job5", "--tickets", "351", "--workspace",
               "/w/351", "--agent", "sm-351").returncode == 0
    got = cli(root, "job", "r-job5", "--clump", "351", "--cores", "8")
    assert got.returncode == 0, got
    assert "8 cores" in got.stdout, got.stdout
    shown = cli(root, "show", "r-job5")
    assert "8 cores" in shown.stdout, shown.stdout
    none = cli(root, "job", "r-job5", "--clump", "351", "--none")
    assert none.returncode == 0, none
    assert "no parallel job" in cli(root, "show", "r-job5").stdout


# --- A sidecar older than the PR's head commit is stale (#1085) ------------

def landed_root():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    return root


def test_a_sidecar_line_rewritten_from_leftover_to_fixed_yields_no_leftover():
    leftover_line = {"id": "S3", "outcome": "leftover", "file": "a.py",
                     "title": "t", "severity": "hard", "text": "x"}
    sidecar = sidecar_of(leftover_line)
    os.utime(sidecar, (1_000_000_000, 1_000_000_000))  # 2001, before the head
    try:
        root = landed_root()
        head = "2026-09-22T10:00:00Z"
        try:
            runfile.leftover("burn-1", 901, 950, sidecar, root=root,
                             head_committed=head)
        except runfile.RunFileError:
            pass
        else:
            raise AssertionError("the stale sidecar was accepted")
        # The controller's rewrite: same finding, new outcome, fresh mtime.
        with open(sidecar, "w") as fh:
            fh.write(json.dumps({"id": "S3", "outcome": "fixed",
                                 "sha": "abc1234"}) + "\n")
        _, added = runfile.leftover("burn-1", 901, 950, sidecar, root=root,
                                    head_committed=head)
        assert added == [], added
        assert runfile.load("burn-1", root=root)["leftovers"] == []
    finally:
        os.remove(sidecar)


def test_a_head_committed_without_a_utc_offset_is_refused():
    root = landed_root()
    try:
        runfile.leftover("burn-1", 901, 950, SIDECAR, root=root,
                         head_committed="2026-09-22T10:00:00")
    except runfile.RunFileError as err:
        assert "no UTC offset" in str(err), err
    else:
        raise AssertionError("a naive timestamp was accepted")


def test_a_sidecar_older_than_the_pr_head_commit_is_refused():
    sidecar = sidecar_of({"id": "S3", "outcome": "leftover", "file": "a.py",
                          "title": "t", "severity": "hard", "text": "x"})
    os.utime(sidecar, (1_000_000_000, 1_000_000_000))  # 2001
    try:
        root = landed_root()
        try:
            runfile.leftover("burn-1", 901, 950, sidecar, root=root,
                             head_committed="2026-09-22T10:00:00Z")
        except runfile.RunFileError as err:
            assert "older than" in str(err), err
        else:
            raise AssertionError("a stale sidecar was accepted")
        assert runfile.load("burn-1", root=root)["leftovers"] == []
        # A sidecar written after the head commit is not stale.
        os.utime(sidecar, (1_900_000_000, 1_900_000_000))  # 2030
        _, added = runfile.leftover("burn-1", 901, 950, sidecar, root=root,
                                    head_committed="2026-09-22T10:00:00Z")
        assert added == ["S3"], added
    finally:
        os.remove(sidecar)


def test_cli_leftover_needs_head_committed_or_allow_stale():
    root = landed_root()
    bare = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
               "--from", SIDECAR)
    assert bare.returncode != 0, bare.stdout
    stale = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
                "--from", SIDECAR, "--head-committed", "2999-01-01T00:00:00Z")
    assert stale.returncode != 0 and "older than" in stale.stderr, stale.stderr
    ok = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
             "--from", SIDECAR, "--allow-stale")
    assert ok.returncode == 0, ok.stderr


def test_a_missing_sidecar_is_refused_by_name_under_head_committed():
    root = landed_root()
    try:
        runfile.leftover("burn-1", 901, 950, "/nonexistent/sidecar.jsonl",
                         root=root, head_committed="2026-09-22T10:00:00Z")
    except runfile.RunFileError as err:
        assert "/nonexistent/sidecar.jsonl" in str(err), err
    else:
        raise AssertionError("a missing sidecar was accepted")


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
