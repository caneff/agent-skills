#!/usr/bin/env python3
"""Tests for the burn run file (#892). Two seams: the read/write contract,
round-tripped through a re-read that stands in for a restart, and the resume
path's re-announce step against a stub agent list.

`BURNDOWN_CACHE_DIR` keeps every case off the real `~/.cache/burndown`.
"""
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runfile  # noqa: E402
from run_fixtures import drop_job, drop_repo_field, linked_worktree  # noqa: E402
import sweep  # noqa: E402

RUNFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runfile.py")
# A real git checkout for every `start` that is not about the target repo: this
# repo's own primary checkout, which `runfile.start` resolves the same way
# (this suite may run from a linked worktree).
REPO = runfile.checkout_top(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


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
    runfile.start("burn-2026-09-20-0905", slots=3, root=root, repo=REPO)
    run = runfile.load("burn-2026-09-20-0905", root=root)
    assert run["run_id"] == "burn-2026-09-20-0905", run
    assert run["slots"] == 3, run
    assert run["clumps"] == [], run


def test_start_without_slots_records_the_default_of_five():
    root = cache()
    runfile.start("burn-1", root=root, repo=REPO)
    assert runfile.load("burn-1", root=root)["slots"] == 5


def test_cli_start_without_slots_records_five_and_a_named_value_wins():
    root = cache()
    assert cli(root, "start", "--repo", REPO, "burn-1").returncode == 0
    assert runfile.load("burn-1", root=root)["slots"] == 5
    assert cli(root, "start", "--repo", REPO, "burn-2", "--slots", "2").returncode == 0
    assert runfile.load("burn-2", root=root)["slots"] == 2
    assert cli(root, "start", "--repo", REPO, "burn-3", "--slots", "0").returncode != 0


def git_checkout(parent, name):
    path = os.path.join(parent, name)
    os.makedirs(path)
    subprocess.run(["git", "init", "-q", path], check=True)
    return os.path.realpath(path)


def test_checkout_top_of_a_linked_worktree_is_the_primary_checkout_1254():
    # A run started with `--repo <worktree>` must still match
    # `sweep.py counts --repo <primary checkout>` (#1190 C2): both name the
    # one checkout the sidecars are keyed on.
    primary = git_checkout(cache(), "target")
    linked = linked_worktree(primary, "linked")
    assert runfile.checkout_top(linked) == primary
    assert runfile.checkout_top(primary) == primary
    root = cache()
    runfile.start("burn-1", slots=1, root=root, repo=linked)
    assert runfile.load("burn-1", root=root)["repo"] == primary


def test_start_records_the_absolute_top_level_of_the_target_checkout():
    root = cache()
    target = git_checkout(cache(), "target")
    sub = os.path.join(target, "deep")
    os.makedirs(sub)
    runfile.start("burn-1", slots=1, root=root, repo=sub + "/")
    assert runfile.load("burn-1", root=root)["repo"] == target


def test_start_without_a_repo_is_refused_naming_the_flag():
    root = cache()
    try:
        runfile.start("burn-1", slots=1, root=root)
    except Exception as exc:
        assert isinstance(exc, runfile.RunFileError), repr(exc)
        assert "--repo" in str(exc), exc
    else:
        raise AssertionError("start without a target repo was accepted")
    assert not os.path.exists(runfile.path("burn-1", root))
    got = cli(root, "start", "burn-1")
    assert got.returncode == 2 and "--repo" in got.stderr, got
    assert not os.path.exists(runfile.path("burn-1", root))


def test_start_refuses_a_repo_that_is_not_a_git_checkout():
    root = cache()
    plain = cache()
    try:
        runfile.start("burn-1", slots=1, root=root, repo=plain)
    except runfile.RunFileError as exc:
        assert "not a git checkout" in str(exc), exc
    else:
        raise AssertionError("a plain directory was accepted as the target")
    got = cli(root, "start", "burn-2", "--repo", os.path.join(plain, "nope"))
    assert got.returncode == 1 and "not a git checkout" in got.stderr, got
    assert "Traceback" not in got.stderr, got.stderr
    assert not os.path.exists(runfile.path("burn-2", root))


def test_checkout_top_ignores_git_environment_that_repoints_git():
    # A GIT_WORK_TREE inherited from a hook or a parent shell makes raw
    # `git -C <target> rev-parse --show-toplevel` answer with the other repo.
    target = git_checkout(cache(), "target")
    other = git_checkout(cache(), "other")
    saved = os.environ.get("GIT_WORK_TREE")
    os.environ["GIT_WORK_TREE"] = other
    try:
        assert runfile.checkout_top(target) == target
    finally:
        if saved is None:
            del os.environ["GIT_WORK_TREE"]
        else:
            os.environ["GIT_WORK_TREE"] = saved


def test_start_refuses_a_blank_repo_instead_of_recording_the_cwds_repo():
    # `git -C ""` stays in the cwd: an unset `--repo "$TARGET"` would record
    # the controller's own checkout, the #1093 hazard this field closes.
    root = cache()
    for blank in ("", "  "):
        try:
            runfile.start("burn-1", slots=1, root=root, repo=blank)
        except Exception as exc:
            assert isinstance(exc, runfile.RunFileError), repr(exc)
            assert "blank" in str(exc), exc
        else:
            raise AssertionError(f"repo {blank!r} was accepted")
    got = cli(root, "start", "burn-2", "--repo", "")
    assert got.returncode == 1 and "blank" in got.stderr, got
    assert not os.path.exists(runfile.path("burn-2", root))


def test_show_prints_the_recorded_target_repo_and_says_when_there_is_none():
    root = cache()
    runfile.start("burn-1", slots=1, root=root, repo=REPO)
    assert f"repo {REPO}" in cli(root, "show", "burn-1").stdout
    drop_repo_field("burn-1", root)
    assert "repo none recorded" in cli(root, "show", "burn-1").stdout


def test_a_run_file_written_before_the_repo_field_loads_and_names_no_target():
    root = cache()
    runfile.start("burn-1", slots=1, root=root, repo=REPO)
    drop_repo_field("burn-1", root)
    run = runfile.load("burn-1", root=root)
    assert run["repo"] is None, run
    try:
        runfile.target_repo(run)
    except runfile.RunFileError as exc:
        assert "names no target repo" in str(exc), exc
    else:
        raise AssertionError("a run with no target repo returned one")


def test_load_refuses_a_repo_field_that_is_not_a_path():
    root = cache()
    runfile.start("burn-1", slots=1, root=root, repo=REPO)
    target = runfile.path("burn-1", root)
    with open(target) as fh:
        run = json.load(fh)
    for bad in (7, "", "relative/path"):
        run["repo"] = bad
        with open(target, "w") as fh:
            json.dump(run, fh)
        try:
            runfile.load("burn-1", root=root)
        except runfile.RunFileError as exc:
            assert "target repo" in str(exc), (bad, exc)
        else:
            raise AssertionError(f"repo {bad!r} was accepted")


def test_the_file_lands_at_run_id_dot_json_under_the_cache_dir():
    root = cache()
    runfile.start("burn-1", slots=1, root=root, repo=REPO)
    assert os.path.isfile(os.path.join(root, "burn-1.json")), os.listdir(root)


def test_start_refuses_a_run_id_that_already_has_a_file():
    # A resumed controller that re-runs `start` would otherwise wipe the very
    # state it restarted to read.
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    try:
        runfile.start("burn-1", slots=9, root=root, repo=REPO)
    except runfile.RunFileError as exc:
        assert "burn-1" in str(exc), exc
    else:
        raise AssertionError("a second start clobbered the run")
    assert runfile.load("burn-1", root=root)["slots"] == 2


def test_a_run_id_that_would_leave_the_cache_dir_is_refused():
    root = cache()
    for bad in ("../escape", "a/b", "", ".", "..", ".hidden"):
        try:
            runfile.start(bad, slots=1, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [902, 901], "/w/implement-901", "implement-901-42",
                  root=root)
    got = runfile.load("burn-1", root=root)["clumps"]
    assert got == [{"tickets": [901, 902], "workspace": "/w/implement-901",
                    "agent": "implement-901-42", "landed": None,
                    "closed": None,
                    "job": {"state": "none", "cores": 0},
                    "pr_up": None}], got


def test_a_clump_is_keyed_by_its_lowest_ticket_and_re_registers_in_place():
    # A clump redispatched after a park keeps its identity; the workspace and
    # the herdr agent name are the parts that move.
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.clump("burn-1", [901, 902], "/w/b", "agent-b", root=root)
    got = runfile.load("burn-1", root=root)["clumps"]
    assert len(got) == 1, got
    assert got[0]["workspace"] == "/w/b" and got[0]["agent"] == "agent-b", got


def test_a_ticket_already_in_another_clump_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "0123456789abcdef0123456789abcdef01234567",
                 root=root)
    got = runfile.load("burn-1", root=root)["clumps"][0]
    assert got["landed"] == "0123456789abcdef0123456789abcdef01234567", got


def test_a_landing_on_a_clump_the_run_never_dispatched_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    try:
        runfile.land("burn-1", 901, "abc1234", root=root)
    except runfile.RunFileError as exc:
        assert "901" in str(exc), exc
    else:
        raise AssertionError("a landing recorded against no clump")


def test_a_second_different_sha_for_a_landed_clump_is_refused():
    # The squash sha is final. A second, different one is a stale writer.
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    path_ = runfile.dispositions_path(cache(), number)
    shutil.copyfile(source, path_)
    return path_


SIDECAR = named_sidecar()


def test_leftover_copies_only_the_leftover_lines_with_every_field_filled():
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    got = runfile.load("burn-1", root=root)["leftovers"]
    assert len(got) == 1, got


def test_leftover_on_a_clump_the_run_never_dispatched_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    _, added = runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    assert added == ["S3"], added
    _, added_again = runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    assert added_again == [], added_again


def test_leftover_against_a_sidecar_with_no_leftover_line_copies_none():
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    no_leftovers = sidecar_of({"id": "S1", "outcome": "fixed",
                               "sha": "0123abc"})
    _, added = runfile.leftover("burn-1", 901, 950, no_leftovers,
                                root=root)
    assert added == [], added


def sidecar_of(*lines, number=901):
    path_ = runfile.dispositions_path(cache(), number)
    with open(path_, "w") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")
    return path_


def refusal_of(sidecar, root, pr_body=None):
    """The refusal `runfile.leftover` raises for `sidecar`, its message."""
    try:
        runfile.leftover("burn-1", 901, 950, sidecar, root=root,
                         pr_body=pr_body)
    except runfile.RunFileError as exc:
        assert runfile.load("burn-1", root=root)["leftovers"] == []
        return str(exc)
    raise AssertionError("the sidecar was accepted")


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


def test_the_leftover_command_refuses_a_foreign_sidecar_with_rc_1_and_one_stderr_line():
    root = landed_root()
    foreign = sidecar_of({"id": "S1", "outcome": "fixed", "sha": "0123abc"},
                         number=777)
    got = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
              "--from", foreign, "--allow-stale")
    assert got.returncode == 1, (got.returncode, got.stderr)
    assert got.stdout == "", got.stdout
    assert got.stderr.startswith("runfile.py: ") and "#777" in got.stderr, got.stderr
    assert len(got.stderr.splitlines()) == 1, got.stderr


def test_a_sidecar_not_named_for_a_ticket_is_refused():
    root = landed_root()
    got = refusal_of(FIXTURE, root)
    assert "dispositions-<n>.jsonl" in got, got


def test_a_sidecar_for_any_ticket_of_the_clump_is_accepted():
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    _, added = runfile.leftover("burn-1", 901, 950,
                                named_sidecar(number=902), root=root)
    assert added == ["S3"], added


def test_a_leftover_line_missing_a_required_field_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    sidecar = sidecar_of({"id": "S3", "outcome": "leftover",
                          "file": "burndown/loop.py", "title": "t",
                          "severity": "judgement"})  # no "text"
    try:
        runfile.leftover("burn-1", 901, 950, sidecar, root=root)
    except runfile.RunFileError as exc:
        assert "text" in str(exc), exc
    else:
        raise AssertionError("a leftover missing a field was copied")
    assert runfile.load("burn-1", root=root)["leftovers"] == []


def test_a_leftover_line_with_a_blank_or_multiline_field_is_refused():
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
            runfile.leftover("burn-1", 901, 950, sidecar, root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted leftover line {bad!r}")
    assert runfile.load("burn-1", root=root)["leftovers"] == []


def test_leftover_on_an_unlanded_clump_is_refused():
    # A retry or an out-of-order call must not persist leftovers for a PR
    # that may never land, with nothing able to remove them afterward.
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    for bad in (
        {"id": "S3", "file": "x", "title": "t"},  # no outcome key at all
        {"id": "S3", "outcome": "mystery"},        # unrecognised outcome
    ):
        sidecar = sidecar_of(bad)
        try:
            runfile.leftover("burn-1", 901, 950, sidecar, root=root)
        except runfile.RunFileError:
            continue
        raise AssertionError(f"accepted line {bad!r}")

    recognised = sidecar_of(
        {"id": "F1", "outcome": "fixed", "sha": "abc"},
        {"id": "F2", "outcome": "disputed", "reason": "why"},
        {"id": "F3", "outcome": "filed", "ticket": 1},
        {"id": "F4", "outcome": "handed-back", "command": "cmd"},
    )
    _, added = runfile.leftover("burn-1", 901, 950, recognised,
                                root=root)
    assert added == [], added


def test_a_sidecar_carrying_one_id_twice_is_refused_by_both_lines():
    # #1124: two Codex passes each number their findings from 1, so a gate
    # and a second-pass leftover both filed under "1" once copied one and
    # dropped the other without a word, while `sweep.py counts` over the
    # same file counted both.
    def item(file):
        return {"id": "1", "outcome": "leftover", "file": file,
                "title": "t", "severity": "medium", "text": "x"}
    sidecar = sidecar_of(item("a.py"), {"id": "S1", "outcome": "fixed",
                                        "sha": "0123abc"}, item("b.py"))
    got = refusal_of(sidecar, landed_root())
    assert f"{sidecar}:3" in got and "line 1" in got and "'1'" in got, got
    run = {"clumps": [{"tickets": [901], "landed": "abc1234"}]}
    try:
        sweep.counts(run, os.path.dirname(sidecar))
    except runfile.RunFileError as exc:
        assert f"{sidecar}:3" in str(exc), exc
    else:
        raise AssertionError("sweep counts read a duplicated id")


def test_a_second_pr_for_the_same_clump_and_finding_id_is_refused():
    # `(pr, id)` alone lets the same finding land twice under two PR
    # numbers — a typo'd `--pr` would double-count it for the sweep, with
    # no undo but hand-editing the run file.
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    cli(root, "start", "--repo", REPO, "burn-1", "--slots", "2")
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
    runfile.start("burn-1", slots=2, controller="ctl", root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    runfile.resume("burn-1", ["agent-a"], controller="ctl-f3", root=root)
    got = runfile.load("burn-1", root=root)["leftovers"]
    assert len(got) == 1 and got[0]["id"] == "S3", got


# --- Resume: reconcile against the live agents, re-announce the controller -

def three_clumps(root):
    runfile.start("burn-1", slots=3, controller="burn-ctl-1a", root=root, repo=REPO)
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


def test_a_closed_clump_is_reported_closed_and_frees_its_slot():
    # #1236 was found already fixed on main and #1262 was a nested spec run:
    # neither landed a PR here, and neither has a worker to re-announce to.
    root = cache()
    three_clumps(root)
    runfile.close("burn-1", 903, "duplicate of #1202, already fixed on main",
                  root=root)
    got = runfile.resume("burn-1", ["agent-a", "agent-b"], root=root)
    assert [c["agent"] for c in got["announce"]] == ["agent-a"], got
    assert got["vanished"] == [], got
    assert [c["tickets"] for c in got["closed"]] == [[903]], got
    assert [c["tickets"] for c in got["landed"]] == [[905]], got
    assert got["free"] == 2, got
    shown = runfile.render_resume(got)
    assert ("closed       #903  duplicate of #1202, already fixed on main"
            in shown), shown


def test_a_closed_clump_reads_closed_in_show_and_survives_a_reload():
    root = cache()
    three_clumps(root)
    runfile.close("burn-1", 903, "nested spec run", root=root)
    run = runfile.load("burn-1", root=root)
    assert run["clumps"][1]["closed"] == "nested spec run", run
    assert run["clumps"][1]["landed"] is None, run
    assert "closed: nested spec run" in runfile.render(run), runfile.render(run)


def test_closing_a_landed_clump_and_landing_a_closed_one_are_refused():
    # Landed and closed are two different facts about one clump; recording
    # both would make the sweep both count its sidecar and skip it.
    root = cache()
    three_clumps(root)
    for act, why in ((lambda: runfile.close("burn-1", 905, "x", root=root),
                      "abc1234"),
                     (lambda: (runfile.close("burn-1", 903, "dup", root=root),
                               runfile.land("burn-1", 903, "def5678",
                                            root=root)), "closed")):
        try:
            act()
        except runfile.RunFileError as exc:
            assert why in str(exc), exc
        else:
            raise AssertionError("a clump recorded as landed and closed")
    run = runfile.load("burn-1", root=root)
    assert run["clumps"][1]["landed"] is None, run
    assert run["clumps"][2]["closed"] is None, run


def test_a_close_names_its_reason():
    root = cache()
    three_clumps(root)
    refused = []
    for reason in ("", "   ", "two\nlines"):
        try:
            runfile.close("burn-1", 903, reason, root=root)
        except runfile.RunFileError as exc:
            refused.append("close reason" in str(exc))
    assert refused == [True, True, True], refused
    assert runfile.load("burn-1", root=root)["clumps"][1]["closed"] is None


def test_re_registering_a_closed_clump_reopens_it():
    # A clump closed by mistake and dispatched again has a worker in its
    # files: left closed, resume would never re-announce to that worker and
    # dispatch would hand its files to another.
    root = cache()
    three_clumps(root)
    runfile.close("burn-1", 903, "dup", root=root)
    runfile.clump("burn-1", [903], "/w/b2", "agent-b2", root=root)
    got = runfile.resume("burn-1", ["agent-a", "agent-b2"], root=root)
    assert [c["agent"] for c in got["announce"]] == ["agent-a", "agent-b2"], got
    assert got["closed"] == [], got


def test_closing_again_with_the_same_reason_is_a_no_op_and_another_is_refused():
    root = cache()
    three_clumps(root)
    runfile.close("burn-1", 903, "dup", root=root)
    runfile.close("burn-1", 903, "dup", root=root)
    try:
        runfile.close("burn-1", 903, "nested spec run", root=root)
    except runfile.RunFileError as exc:
        assert "already closed: dup" in str(exc), exc
    else:
        raise AssertionError("a close reason was overwritten")
    assert runfile.load("burn-1", root=root)["clumps"][1]["closed"] == "dup"


def hand_edit_clump(root, index, **fields):
    """Rewrite one clump of run `burn-1` in place, as a controller's hand
    edit of the file would."""
    target = runfile.path("burn-1", root)
    with open(target) as fh:
        run = json.load(fh)
    run["clumps"][index].update(fields)
    for key, value in fields.items():
        if value is ...:
            del run["clumps"][index][key]
    with open(target, "w") as fh:
        json.dump(run, fh)


def test_a_run_file_with_a_clump_both_landed_and_closed_is_refused_on_load():
    # The burn-skills-2026-09-30 shape: a clump landed at main's tip, then
    # marked closed by hand. Read as either, one reader is wrong.
    root = cache()
    three_clumps(root)
    hand_edit_clump(root, 2, closed="already fixed on main")
    try:
        runfile.load("burn-1", root=root)
    except runfile.RunFileError as exc:
        assert "#905 both landed and closed" in str(exc), exc
    else:
        raise AssertionError("a clump both landed and closed was loaded")


def test_a_run_file_with_a_blank_close_reason_is_refused_on_load():
    # `""` read as no close would put a finished clump back in flight.
    root = cache()
    three_clumps(root)
    for bad in ("", True, "x\ry"):
        hand_edit_clump(root, 1, closed=bad)
        try:
            runfile.load("burn-1", root=root)
        except runfile.RunFileError as exc:
            assert "close reason" in str(exc), (bad, exc)
        else:
            raise AssertionError(f"closed={bad!r} was loaded")


def test_a_run_file_written_before_closes_existed_loads_with_none_closed():
    # No landing in this run: a landed clump would trip the both-landed-and-
    # closed refusal before the fill-in this test is about could be read.
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.clump("burn-1", [903], "/w/b", "agent-b", root=root)
    for index in range(2):
        hand_edit_clump(root, index, closed=...)
    run = runfile.load("burn-1", root=root)
    assert [c["closed"] for c in run["clumps"]] == [None, None], run


def test_close_from_the_cli_is_what_resume_reads_back():
    root = cache()
    three_clumps(root)
    got = cli(root, "close", "burn-1", "--clump", "903", "--reason",
              "nested spec run")
    assert got.returncode == 0, got.stderr
    back = cli(root, "resume", "burn-1", "--live", "agent-a,agent-b")
    assert back.returncode == 0, back.stderr
    assert "closed       #903  nested spec run" in back.stdout, back.stdout
    assert "agent-b" not in back.stdout, back.stdout


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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    assert cli(root, "start", "--repo", REPO, "burn-1", "--slots", "3",
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
    cli(root, "start", "--repo", REPO, "burn-1", "--slots", "2")
    cli(root, "clump", "burn-1", "--tickets", "903", "--workspace", "/w/b",
        "--agent", "agent-b")
    got = cli(root, "resume", "burn-1", "--live", "agent-a")
    assert "vanished" in got.stdout and "agent-b" in got.stdout, got.stdout
    assert "re-announce" not in got.stdout, got.stdout


def test_show_prints_the_run_without_touching_it():
    root = cache()
    cli(root, "start", "--repo", REPO, "burn-1", "--slots", "2", "--controller", "ctl")
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
        runfile.start("burn-1\n", slots=1, root=root, repo=REPO)
    except runfile.RunFileError:
        pass
    else:
        raise AssertionError("a run id with a newline was accepted")
    runfile.start("burn-1", slots=1, root=root, repo=REPO)
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
            runfile.start("burn-1", slots=bad, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
        runfile.start("burn-1", slots=1, root=os.path.join(root, "afile", "sub"), repo=REPO)
    except runfile.RunFileError as exc:
        assert "burn-1.json" in str(exc), exc
    else:
        raise AssertionError("a path through a file read as a cache dir")

    closed = os.path.join(root, "closed")
    os.mkdir(closed, 0o500)
    try:
        runfile.start("burn-1", slots=1, root=os.path.join(closed, "sub"), repo=REPO)
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
        runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
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
    cli(root, "start", "--repo", REPO, "burn-1", "--slots", "2")
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
        [sys.executable, RUNFILE, "start", "--repo", REPO, "burn-1", "--slots", "1"],
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
    cli(root, "start", "--repo", REPO, "burn-1", "--slots", "4")
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
    cli(root, "start", "--repo", REPO, "burn-1", "--slots", "2")
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
    cli(root, "start", "--repo", REPO, "burn-1", "--slots", "2")
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
        [sys.executable, RUNFILE, "start", "--repo", REPO, "burn-1", "--slots", "1"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "BURNDOWN_CACHE_DIR": root,
             "BURNDOWN_RUNFILE_LOCK_TIMEOUT": "",
             "BURNDOWN_RUNFILE_DELAY_MS": ""})
    assert got.returncode == 0, got.stderr
    assert runfile.load("burn-1", root=root)["slots"] == 1


def test_a_clump_starts_with_a_none_job_on_record_1311():
    """A worker starts with nothing out, so registration records `none`:
    otherwise `loop.py dispatch` refuses every tick until the worker's "PR up"
    declares a job, idling the free slots for an hour."""
    root = cache()
    runfile.start("r-job", 3, "dc", root, repo=REPO)
    run = runfile.clump("r-job", [351], "/w/351", "sm-351", root)
    assert run["clumps"][0]["job"] == {"state": "none", "cores": 0}, run


def test_re_registering_a_clump_keeps_its_declared_job_1311():
    root = cache()
    runfile.start("r-job", 3, "dc", root, repo=REPO)
    runfile.clump("r-job", [351], "/w/351", "sm-351", root)
    runfile.job("r-job", 351, "running", 4, root)
    run = runfile.clump("r-job", [351], "/w/351", "sm-351b", root)
    assert run["clumps"][0]["job"] == {"state": "running", "cores": 4}, run


def test_a_declared_job_survives_a_restart():
    """The whole point: a controller that restarts mid-run recovers the hold.
    The declaration lived in one argv before, so a resume dispatched into the
    contention #351 produced."""
    root = cache()
    runfile.start("r-job2", 3, "dc", root, repo=REPO)
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
    runfile.start("r-job3", 3, "dc", root, repo=REPO)
    runfile.clump("r-job3", [351], "/w/351", "sm-351", root)
    runfile.job("r-job3", 351, "none", root=root)
    assert runfile.load("r-job3", root)["clumps"][0]["job"] == {
        "state": "none", "cores": 0}


def test_a_job_record_that_is_not_one_is_refused():
    root = cache()
    runfile.start("r-job4", 3, "dc", root, repo=REPO)
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
    runfile.start("r-old", 2, "dc", root, repo=REPO)
    runfile.clump("r-old", [401], "/w/401", "sm-401", root)
    drop_job("r-old", root, 401)
    run = runfile.load("r-old", root)
    assert run["clumps"][0]["job"] is None, run


def test_the_cli_records_a_job_and_shows_it():
    root = cache()
    assert cli(root, "start", "--repo", REPO, "r-job5", "--slots", "2").returncode == 0
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


# --- "PR up" is on record, so the sweep can tell stalled from waiting (#1148)

def test_a_clump_starts_with_no_pr_up_on_record():
    root = cache()
    runfile.start("r-pr", 3, "dc", root, repo=REPO)
    run = runfile.clump("r-pr", [1095], "/w/1095", "skills-1095", root)
    assert run["clumps"][0]["pr_up"] is None, run


def test_a_recorded_pr_up_survives_a_restart_and_a_re_register():
    """A resumed controller's sweep reads this record, not its context: a
    `done` pane whose "PR up" was never recorded reads `stalled`."""
    root = cache()
    runfile.start("r-pr2", 3, "dc", root, repo=REPO)
    runfile.clump("r-pr2", [1095], "/w/1095", "skills-1095", root)
    runfile.pr_up("r-pr2", 1095, 1160, root)
    assert runfile.load("r-pr2", root)["clumps"][0]["pr_up"] == 1160
    # The same worker's clump growing after a closure re-resolve keeps it.
    runfile.clump("r-pr2", [1095, 1096], "/w/1095", "skills-1095", root)
    assert runfile.load("r-pr2", root)["clumps"][0]["pr_up"] == 1160


def test_a_redispatch_to_a_new_agent_clears_pr_up_so_a_done_pane_is_stalled():
    import loop
    root = cache()
    runfile.start("r-pr9", 3, "dc", root, repo=REPO)
    runfile.clump("r-pr9", [1095], "/w/1095", "skills-1095", root)
    runfile.pr_up("r-pr9", 1095, 1160, root)
    run = runfile.clump("r-pr9", [1095], "/w/1095", "skills-1095-b", root)
    state = loop.sweep(run["clumps"], lambda agent, timeout: {
        "result": {"agent": {"agent_status": "done"}}})
    assert state["workers"][0]["verdict"] == "stalled", state


def test_a_pr_up_that_is_not_a_pr_number_or_names_no_clump_is_refused():
    root = cache()
    runfile.start("r-pr3", 3, "dc", root, repo=REPO)
    runfile.clump("r-pr3", [1095], "/w/1095", "skills-1095", root)
    for bad in (0, -1, "1160", True):
        try:
            runfile.pr_up("r-pr3", 1095, bad, root)
        except runfile.RunFileError:
            pass
        else:
            raise AssertionError(f"{bad!r} is not a PR number")
    try:
        runfile.pr_up("r-pr3", 999, 1160, root)
    except runfile.RunFileError as exc:
        assert "#999" in str(exc), exc
    else:
        raise AssertionError("a PR-up record must name a clump of this run")


def test_a_run_file_written_before_pr_up_existed_still_reads():
    root = cache()
    runfile.start("r-pr4", 2, "dc", root, repo=REPO)
    runfile.clump("r-pr4", [401], "/w/401", "sm-401", root)
    target = runfile.path("r-pr4", root)
    with open(target) as fh:
        raw = json.load(fh)
    del raw["clumps"][0]["pr_up"]
    with open(target, "w") as fh:
        json.dump(raw, fh)
    assert runfile.load("r-pr4", root)["clumps"][0]["pr_up"] is None


def test_a_run_file_holding_a_pr_up_that_is_not_a_pr_number_is_refused():
    root = cache()
    runfile.start("r-pr6", 2, "dc", root, repo=REPO)
    runfile.clump("r-pr6", [401], "/w/401", "sm-401", root)
    target = runfile.path("r-pr6", root)
    for bad in ("7", 0, True):
        with open(target) as fh:
            raw = json.load(fh)
        raw["clumps"][0]["pr_up"] = bad
        with open(target, "w") as fh:
            json.dump(raw, fh)
        try:
            runfile.load("r-pr6", root)
        except runfile.RunFileError as exc:
            assert "PR number" in str(exc), exc
        else:
            raise AssertionError(f"a pr_up of {bad!r} loaded")


def test_the_cli_records_pr_up_and_shows_it():
    root = cache()
    assert cli(root, "start", "--repo", REPO, "r-pr5", "--slots", "2").returncode == 0
    assert cli(root, "clump", "r-pr5", "--tickets", "1095", "--workspace",
               "/w/1095", "--agent", "skills-1095").returncode == 0
    assert "no PR up" in cli(root, "show", "r-pr5").stdout
    got = cli(root, "pr-up", "r-pr5", "--clump", "1095", "--pr", "1160")
    assert got.returncode == 0, got
    assert "PR #1160 up" in cli(root, "show", "r-pr5").stdout


def test_a_cleared_pr_up_makes_a_done_pane_stalled_again():
    """The controller clears the record when it hands findings back, since
    the PR stays open through a fix round: a worker that then stops mid-fix
    must read `stalled`, not `done` (Codex gate on PR #1166)."""
    import loop
    root = cache()
    assert cli(root, "start", "--repo", REPO, "r-pr7", "--slots", "2").returncode == 0
    assert cli(root, "clump", "r-pr7", "--tickets", "1095", "--workspace",
               "/w/1095", "--agent", "skills-1095").returncode == 0
    assert cli(root, "pr-up", "r-pr7", "--clump", "1095", "--pr",
               "1160").returncode == 0
    cleared = cli(root, "pr-up", "r-pr7", "--clump", "1095", "--clear")
    assert cleared.returncode == 0, cleared
    assert "no PR up" in cleared.stdout, cleared.stdout
    clumps = runfile.load("r-pr7", root)["clumps"]
    assert clumps[0]["pr_up"] is None, clumps
    state = loop.sweep(clumps, lambda agent, timeout: {
        "result": {"agent": {"agent_status": "done"}}})
    assert state["workers"][0]["verdict"] == "stalled", state


def test_pr_up_takes_a_pr_or_clear_but_not_both_and_not_neither():
    root = cache()
    assert cli(root, "start", "--repo", REPO, "r-pr8", "--slots", "2").returncode == 0
    assert cli(root, "clump", "r-pr8", "--tickets", "1095", "--workspace",
               "/w/1095", "--agent", "skills-1095").returncode == 0
    both = cli(root, "pr-up", "r-pr8", "--clump", "1095", "--pr", "1160",
               "--clear")
    assert both.returncode != 0 and "not allowed with" in both.stderr, both
    neither = cli(root, "pr-up", "r-pr8", "--clump", "1095")
    assert neither.returncode != 0 and "required" in neither.stderr, neither
    assert runfile.load("r-pr8", root)["clumps"][0]["pr_up"] is None


# --- A sidecar the PR body disagrees with is stale (#1085, #1147) ---------

def landed_root():
    root = cache()
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    return root


LEFTOVER_S3 = {"id": "S3", "outcome": "leftover", "file": "a.py",
               "title": "t", "severity": "hard", "text": "x"}


def pr_body(text):
    """A PR body as `gh pr view --json body --jq .body` prints it."""
    path_ = os.path.join(cache(), "pr-body.md")
    with open(path_, "w") as fh:
        fh.write(text)
    return path_


# Decisions made lines copied from PR bodies here (PRs 1150, 1153, 1160,
# 1166, 1167): grouped ids, bolded ids with a description before the
# disposition, a disposition word inside the description, a line naming an id
# with no disposition, an id named only as `sidecar <id>` at the end, an id
# another id is a prefix of, and a section that is not Decisions made.
BODY = """## What changed

- S1: this line is outside Decisions made and says leftover.

## Decisions made

- S1, P2, C1: fixed, 283d5ef — jq printed an array, so `$sweep` was not executable.
- C4, S4 (a path ending in a product name, `scripts/node.js`, read as prose): fixed (adjacent) e5418a1.
- P3 and the Codex `[high]` (`src/main.dart` still read as light): the controller overruled my dispute; fixed 80b3140.
- **S2** (standards, judgement): paragraph overflows 80 columns. Claimed fixed in 2abe0b9; the verification pass contested it. leftover.
- **C2** (correctness, CONFIRMED, hard): `check_adjacent.py` still breaches. filed: #1152 (outside this diff).
- P2's broader verdict: the controller accepted the dispute.
- C3: fixed, 5b6b0f1. This was a leftover at the verification pass.
- S3, S5, S6: leftover (all judgement, none high).
- S30: fixed, 9abcdef.
- Codex gate [medium] (table column counts): leftover (controller); sidecar codex-gate-1.

## Last reviewed sha

- S3: fixed. Outside Decisions made again.
"""


def body_sidecar():
    """The sidecar BODY agrees with, line for line."""
    def left(fid):
        return dict(LEFTOVER_S3, id=fid)
    return sidecar_of(
        {"id": "S1", "outcome": "fixed", "sha": "283d5ef"},
        {"id": "P2", "outcome": "fixed", "sha": "283d5ef"},
        {"id": "C1", "outcome": "fixed", "sha": "283d5ef"},
        {"id": "C4", "outcome": "fixed", "sha": "e5418a1", "scope": "adjacent"},
        {"id": "S4", "outcome": "fixed", "sha": "e5418a1", "scope": "adjacent"},
        {"id": "P3", "outcome": "fixed", "sha": "80b3140"},
        left("S2"),
        {"id": "C2", "outcome": "filed", "ticket": 1152},
        {"id": "C3", "outcome": "fixed", "sha": "5b6b0f1"},
        left("S3"), left("S5"), left("S6"),
        left("codex-gate-1"))


def test_a_sidecar_the_pr_body_agrees_with_is_harvested_whatever_came_after():
    # #1147: a doc-only, test-only or re-wrap commit after the verification
    # pass changes no disposition, so nothing about it can refuse the harvest.
    root = landed_root()
    _, added = runfile.leftover("burn-1", 901, 950, body_sidecar(), root=root,
                                pr_body=pr_body(BODY))
    assert added == ["S2", "S3", "S5", "S6", "codex-gate-1"], added


def test_an_over_engineering_leftover_is_harvested_like_any_other_id():
    # #1021: an OE-id finding (an over-engineering cut) joins the PR body
    # and the leftover harvest exactly like an S/P/C one — the id format
    # carries no axis-specific meaning to this reader.
    root = landed_root()
    sidecar = sidecar_of(
        {"id": "S1", "outcome": "fixed", "sha": "283d5ef"},
        {"id": "OE1", "outcome": "leftover", "file": "a.py",
         "title": "yagni: one-caller layer", "severity": "judgement",
         "text": "inline it until a second caller exists"})
    body = pr_body("## Decisions made\n\n- S1: fixed, 283d5ef.\n"
                    "- OE1: leftover (one-caller layer, judgement).\n")
    _, added = runfile.leftover("burn-1", 901, 950, sidecar, root=root,
                                pr_body=body)
    assert added == ["OE1"], added
    entry = runfile.load("burn-1", root=root)["leftovers"][0]
    assert entry["id"] == "OE1" and entry["severity"] == "judgement", entry


def test_an_over_engineering_id_is_recognized_when_the_pr_body_disagrees():
    # #1021 correctness C1: the prior test's PR-body half was a hollow
    # witness — a body that never cites OE1 at all also harvests clean,
    # since an uncited id is "not disputed", not "disputed". Prove the
    # citation grammar itself reads an OE id, by putting it in genuine
    # disagreement with the sidecar and reading the refusal message.
    sidecar = sidecar_of({"id": "OE1", "outcome": "leftover", "file": "a.py",
                          "title": "t", "severity": "judgement", "text": "x"})
    body = pr_body("## Decisions made\n\n- OE1: fixed, 283d5ef.\n")
    got = refusal_of(sidecar, landed_root(), body)
    assert "records OE1 as 'fixed'" in got, got


def test_a_leftover_line_the_pr_body_records_as_fixed_is_refused_until_rewritten():
    # #1085's own case: the fix landed and the PR body says so, but the
    # sidecar line still reads leftover.
    sidecar = sidecar_of(LEFTOVER_S3)
    body = pr_body("## Decisions made\n\n- S3: fixed, abc1234.\n")
    got = refusal_of(sidecar, landed_root(), body)
    assert ("S3" in got and "'fixed'" in got and "'leftover'" in got
            and f"{body}:3" in got and f"{sidecar}:1" in got), got
    # The controller's rewrite: same finding, new outcome.
    with open(sidecar, "w") as fh:
        fh.write(json.dumps({"id": "S3", "outcome": "fixed",
                             "sha": "abc1234"}) + "\n")
    root = landed_root()
    _, added = runfile.leftover("burn-1", 901, 950, sidecar, root=root,
                                pr_body=body)
    assert added == [], added


def test_a_contradiction_refusal_names_the_split_id_way_out():
    # #1174: PR #1172's ruling genuinely split codex-gate-1 — fix the head
    # binding, leave the residual race — and the only path past the
    # contradiction was `--allow-stale`, the override #1147/#1170 exist to
    # stop training. The refusal now names the id-a/id-b way out, by this
    # finding's own id. A controller-only id, not a round-1 one (S3, P2,
    # C1): § Review's split grammar is never a round-1 finding's own id,
    # and the message must not recommend that on the one shape of id it
    # forbids it for.
    sidecar = sidecar_of({"id": "codex-gate-1", "outcome": "leftover",
                          "file": "a.py", "title": "t", "severity": "hard",
                          "text": "x"})
    body = pr_body("## Decisions made\n\n- codex-gate-1: fixed, abc1234.\n")
    got = refusal_of(sidecar, landed_root(), body)
    assert ("codex-gate-1a" in got and "codex-gate-1b" in got
            and "split" in got), got


def test_a_genuine_split_is_written_as_two_ids_not_one():
    # #1174: what PR #1172's ruling actually wanted — fix the head binding
    # now, leave the residual race — expressed as two ids sharing a base,
    # each with its own outcome, rather than one id carrying both.
    root = landed_root()
    sidecar = sidecar_of(
        {"id": "codex-gate-1a", "outcome": "fixed", "sha": "0e5e796"},
        {"id": "codex-gate-1b", "outcome": "leftover",
         "file": "burndown/runfile.py", "title": "residual head-binding race",
         "severity": "medium",
         "text": "a second writer between load and replace still wins"})
    body = pr_body(
        "## Decisions made\n\n"
        "- codex-gate-1a: fixed at 0e5e796 — head binding closed.\n"
        "- codex-gate-1b: leftover — residual race; sidecar codex-gate-1b.\n")
    _, added = runfile.leftover("burn-1", 901, 950, sidecar, root=root,
                                pr_body=body)
    assert added == ["codex-gate-1b"], added
    # Witness that the --pr-body check is genuinely live for split ids, not
    # merely silent about them (correctness C3): a body that disagrees with
    # one split half is still refused, by that half's own id.
    disagreeing = pr_body(
        "## Decisions made\n\n"
        "- codex-gate-1a: leftover — head binding still open.\n"
        "- codex-gate-1b: leftover — residual race; sidecar codex-gate-1b.\n")
    got = refusal_of(sidecar, landed_root(), disagreeing)
    assert "codex-gate-1a" in got and "'leftover'" in got and "'fixed'" in got, got


def test_a_stale_leftover_is_refused_in_each_real_line_shape():
    # Each real shape in BODY, with the sidecar still reading leftover where
    # the body says otherwise: the grouped line, the description-first line,
    # and a fixed line that mentions the word leftover.
    for fid in ("P2", "S4", "P3", "C3", "C2"):
        stale = body_sidecar()
        with open(stale) as fh:
            lines = [json.loads(line) for line in fh]
        with open(stale, "w") as fh:
            for line in lines:
                if line["id"] == fid:
                    line = dict(LEFTOVER_S3, id=fid)
                fh.write(json.dumps(line) + "\n")
        got = refusal_of(stale, landed_root(), pr_body(BODY))
        assert f"records {fid} as" in got, (fid, got)
    # And the reverse, on the line citing its id only as `sidecar <id>`.
    stale = body_sidecar()
    with open(stale) as fh:
        lines = [json.loads(line) for line in fh]
    with open(stale, "w") as fh:
        for line in lines:
            if line["id"] == "codex-gate-1":
                line = {"id": "codex-gate-1", "outcome": "fixed",
                        "sha": "abc1234"}
            fh.write(json.dumps(line) + "\n")
    got = refusal_of(stale, landed_root(), pr_body(BODY))
    assert "records codex-gate-1 as 'leftover'" in got, got


def test_a_round_prefixed_id_does_not_collide_with_the_same_bare_id():
    # #1177: round 2 of a PR's review is `r2-S1`, so round 1's `S1: fixed` and
    # round 2's `r2-S1: disputed` are two findings, and the sidecar of the
    # later round is harvested without --allow-stale.
    sidecar = sidecar_of(
        {"id": "r2-S1", "outcome": "disputed", "reason": "unreachable here"},
        dict(LEFTOVER_S3, id="r2-S3"))
    body = pr_body("## Decisions made\n\n- S1: fixed, abc1234.\n"
                   "- r2-S1: disputed: unreachable here.\n"
                   "- r2-S3: leftover.\n")
    _, added = runfile.leftover("burn-1", 901, 950, sidecar, root=landed_root(),
                                pr_body=body)
    assert added == ["r2-S3"], added


def test_a_bare_id_recorded_twice_with_different_outcomes_is_refused_as_reuse():
    # #1177: two rounds that both used `S1` leave one id with two outcomes.
    # That is an id reused across rounds, not a stale sidecar: the refusal
    # says so and names the prefix rule.
    sidecar = sidecar_of({"id": "S1", "outcome": "disputed", "reason": "x"})
    body = pr_body("## Decisions made\n\n- S1: disputed: x.\n"
                   "- S1: fixed, abc1234.\n")
    got = refusal_of(sidecar, landed_root(), body)
    assert "S1" in got and "more than once" in got and "r2-" in got, got
    assert "reused across review rounds" in got and "records S1 as" not in got, got
    # Two other causes read the same: a ruling appended below the first
    # record, and a sweep PR's items colliding with its own findings.
    assert "appended" in got and "r1-" in got, got
    assert f"{body}:3 and :4" in got, got


def test_reuse_is_found_past_a_first_line_that_states_no_outcome():
    # C2: a first record that only mentions outcome words states nothing, and
    # two later lines still disagree with each other.
    sidecar = sidecar_of({"id": "S1", "outcome": "disputed", "reason": "x"})
    body = pr_body("## Decisions made\n\n- S1 (hard): overflows. Claimed fixed; "
                   "contested. leftover.\n- S1: fixed, abc1234.\n"
                   "- S1: disputed: x.\n")
    got = refusal_of(sidecar, landed_root(), body)
    assert "reused across review rounds" in got, got


def test_a_bare_id_recorded_twice_with_one_outcome_is_not_reuse():
    # The same disposition stated twice is a restatement, not two findings.
    sidecar = sidecar_of({"id": "S1", "outcome": "fixed", "sha": "abc1234"})
    body = pr_body("## Decisions made\n\n- S1: fixed, abc1234.\n"
                   "- S1: fixed, abc1234 (re-read by the controller).\n")
    _, added = runfile.leftover("burn-1", 901, 950, sidecar, root=landed_root(),
                                pr_body=body)
    assert added == [], added


def test_an_id_the_sidecar_does_not_hold_may_repeat_in_the_body():
    # #1213: a sweep PR's body cites its sweep items, which reuse ids across
    # source PRs. Only an id the sidecar holds is compared, so those repeats
    # are not reuse.
    sidecar = sidecar_of(dict(LEFTOVER_S3, id="r1-S3"))
    body = pr_body("## Decisions made\n\n- r1-S3: leftover.\n"
                   "- S3: fixed, abc1234 (from PR #10).\n"
                   "- S3: disputed: unreachable (from PR #11).\n")
    _, added = runfile.leftover("burn-1", 901, 950, sidecar, root=landed_root(),
                                pr_body=body)
    assert added == ["r1-S3"], added


def test_a_file_qualified_id_is_read_as_that_id():
    # #1213: `**e2e/scenarios.mjs S8**` cites S8.
    assert runfile.cited_ids("- **e2e/scenarios.mjs S8**: fixed, abc1234")[0] \
        == ["S8"]
    assert runfile.cited_ids("- `burndown/run.py` r2-S1, P2: leftover")[0] \
        == ["r2-S1", "P2"]
    sidecar = sidecar_of(dict(LEFTOVER_S3, id="S8"))
    body = pr_body("## Decisions made\n\n- **e2e/scenarios.mjs S8**: fixed, "
                   "abc1234.\n")
    got = refusal_of(sidecar, landed_root(), body)
    assert "records S8 as 'fixed'" in got, got


def test_a_missing_sweep_leftover_line_is_refused_under_its_qualified_id():
    # #1315: a file-qualified cite's sidecar line is keyed `<file> <id>`, so
    # the refusal names that form the first time, not the bare id.
    sidecar = sidecar_of(dict(LEFTOVER_S3, id="r1-S3"))
    body = pr_body("## Decisions made\n\n- r1-S3: leftover.\n"
                   "- **e2e/scenarios.mjs S8**: leftover.\n")
    got = refusal_of(sidecar, landed_root(), body)
    assert "records e2e/scenarios.mjs S8 as a leftover" in got, got
    assert "its `id` is the `<file> <id>` form" in got, got
    # A bare cite's refusal still names the bare id.
    bare = refusal_of(sidecar, landed_root(),
                      pr_body("## Decisions made\n\n- r1-S3: leftover.\n"
                              "- S8: leftover.\n"))
    assert "records S8 as a leftover" in bare, bare


def test_a_file_qualifier_may_carry_a_line_and_a_bare_file_needs_backticks():
    # C1: a line number or #L anchor on the path is part of the qualifier.
    for line in ("- **e2e/scenarios.mjs:42 S8**: fixed",
                 "- **e2e/scenarios.mjs#L42 S8**: fixed",
                 "- `runfile.py` S8: fixed"):
        assert runfile.cited_ids(line)[0] == ["S8"], line


def test_a_dotted_word_before_an_id_is_not_read_as_a_file():
    # C3: a product or a version is prose. Only a path with a `/`, or a bare
    # file name in backticks, qualifies an id.
    assert runfile.cited_ids("- Node.js v18: leftover as a follow-up")[0] == []
    assert "S3" not in runfile.cited_ids("- v1.2 S3: fixed")[0]


def test_a_word_before_an_id_is_not_read_as_a_file():
    # A path token carries a `.` or `/`; plain prose before an id does not.
    assert runfile.cited_ids("- Codex S8: leftover")[0] == []


def test_a_leftover_the_body_records_but_the_sidecar_lacks_is_refused():
    # § The merge: a leftover kept only in the PR body never reaches a sweep.
    body = pr_body("## Decisions made\n\n- S1: fixed, 0123abc.\n"
                   "- S2: leftover (controller).\n")
    got = refusal_of(sidecar_of({"id": "S1", "outcome": "fixed",
                                 "sha": "0123abc"}), landed_root(), body)
    assert "records S2 as a leftover" in got and "no line" in got, got


def test_a_leftover_the_body_does_not_cite_is_harvested():
    # Absent is not disagreement, and a body line in a shape the reader
    # cannot see must not retrain the override (#1147).
    body = pr_body("## Decisions made\n\n- S1: fixed, 0123abc.\n"
                   "- The third Codex pass left one item.\n")
    root = landed_root()
    _, added = runfile.leftover(
        "burn-1", 901, 950,
        sidecar_of({"id": "S1", "outcome": "fixed", "sha": "0123abc"},
                   LEFTOVER_S3),
        root=root, pr_body=body)
    assert added == ["S3"], added


def test_a_body_citing_none_of_the_sidecars_ids_is_refused():
    # Another PR's body, or one whose Decisions made the reader cannot parse
    # at all, would otherwise agree with every sidecar.
    got = refusal_of(sidecar_of(LEFTOVER_S3), landed_root(),
                     pr_body("## Decisions made\n\n- C9: fixed.\n"))
    assert "cites none of" in got, got


def test_a_body_with_no_decisions_made_section_is_refused():
    # An empty file is what a failed `gh pr view` leaves behind; and a line
    # outside the section is no record at all.
    for text in (" \n", "## What changed\n\n- S3: leftover.\n"):
        got = refusal_of(sidecar_of(LEFTOVER_S3), landed_root(),
                         pr_body(text))
        assert "no Decisions made section" in got, (text, got)


def test_a_sidecar_line_whose_id_is_missing_or_not_a_string_is_refused():
    for line in ({"outcome": "fixed", "sha": "0123abc"},
                 {"id": 1, "outcome": "fixed", "sha": "0123abc"}):
        got = refusal_of(sidecar_of(line), landed_root())
        assert ":1" in got and "finding id" in got, (line, got)


def test_cli_leftover_needs_pr_body_or_allow_stale():
    root = landed_root()
    bare = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
               "--from", SIDECAR)
    assert bare.returncode != 0, bare.stdout
    stale = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
                "--from", SIDECAR, "--pr-body",
                pr_body("## Decisions made\n\n- S3: fixed, 0123abc.\n"))
    assert (stale.returncode == 1 and "'fixed'" in stale.stderr
            and len(stale.stderr.splitlines()) == 1), stale.stderr
    agreed = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
                 "--from", SIDECAR, "--pr-body", pr_body("## Decisions made\n\n- S3: leftover\n"))
    assert agreed.returncode == 0, agreed.stderr
    assert "copied 1 leftover" in agreed.stdout, agreed.stdout
    gone = cli(root, "leftover", "burn-1", "--clump", "901", "--pr", "950",
               "--from", SIDECAR, "--head-committed", "2026-09-22T10:00:00Z")
    assert gone.returncode != 0, gone.stdout


def test_a_missing_pr_body_is_refused_by_name():
    root = landed_root()
    try:
        runfile.leftover("burn-1", 901, 950, SIDECAR, root=root,
                         pr_body="/nonexistent/pr-body.md")
    except runfile.RunFileError as err:
        assert "/nonexistent/pr-body.md" in str(err), err
    else:
        raise AssertionError("a missing PR body was accepted")


def test_cli_check_runs_the_harvest_comparison_without_a_run_file():
    # The worker's pre-"PR up" gate (#1214): no run id, no landing, only the
    # sidecar against the body.
    root = cache()
    stale = cli(root, "check", "--from", SIDECAR, "--pr-body",
                pr_body("## Decisions made\n\n- S3: fixed, 0123abc.\n"))
    assert stale.returncode == 1 and "S3" in stale.stderr, stale.stderr
    agreed = cli(root, "check", "--from", SIDECAR, "--pr-body",
                 pr_body("## Decisions made\n\n- S3: leftover\n"))
    assert agreed.returncode == 0 and "agree" in agreed.stdout, agreed.stderr


def test_cli_check_refuses_an_empty_sidecar_and_a_malformed_leftover():
    # Harvest refuses a leftover line missing its fields (P2), and an empty
    # sidecar has nothing to compare, which is not agreement (C1).
    root = cache()
    body = pr_body("## Decisions made\n\n- S3: leftover\n")
    for text, want in (("", "no lines"),
                       ('{"id": "S3", "outcome": "leftover"}\n', "missing")):
        side = os.path.join(cache(), "dispositions-901.jsonl")
        with open(side, "w") as fh:
            fh.write(text)
        got = cli(root, "check", "--from", side, "--pr-body", body)
        assert got.returncode == 1 and want in got.stderr, (text, got.stderr)


def test_the_sidecar_name_runfile_builds_is_the_one_it_parses():
    # One module owns both directions of `dispositions-<n>.jsonl` (#1173 S5):
    # the built name names its own ticket and no other.
    built = runfile.dispositions_path("/reviews", 901)
    assert built == "/reviews/dispositions-901.jsonl", built
    runfile.refuse_foreign_sidecar(built, [901])
    try:
        runfile.refuse_foreign_sidecar(built, [902])
    except runfile.RunFileError as err:
        assert "901" in str(err), err
    else:
        raise AssertionError("a sidecar for #901 was accepted for clump #902")


def test_leftover_help_names_every_pr_body_refusal():
    # The docstring lists four refusals; the --pr-body help named two
    # (#1173 S3). argparse re-wraps help text, so compare with spaces folded.
    got = subprocess.run([sys.executable, RUNFILE, "leftover", "--help"],
                         capture_output=True, text=True)
    text = " ".join(got.stdout.split())
    for refusal in ("contradicts", "the sidecar lacks", "cites none",
                    "no Decisions made section", "§ Leftovers"):
        assert refusal in text, (refusal, text)


def test_stated_outcome_reads_no_outcome_from_a_line_with_no_colon():
    # The fall-through path: a Decisions made line with no colon states no
    # outcome, and reads as None rather than raising.
    assert runfile.stated_outcome("S1 fixed in the round") is None
    assert runfile.stated_outcome("S1: fixed") == "fixed"


SWEEP_TICKET = """Some preamble.

## implement/SKILL.md

- **P9** (hard) title nine — clump #10, #10, PR #11: text nine
- **P14** (low) title fourteen — clump #10, #10, PR #11: text fourteen

## burndown/runfile.py

- **P9** (low) same id, other file — clump #12, #12, PR #13: text
"""


def sweep_leftover(file, id_):
    return {"id": f"{file} {id_}", "outcome": "leftover", "file": file,
            "title": "t", "severity": "hard", "text": "x"}


def sweep_refusal(sidecar_lines, body_text):
    sidecar = sidecar_of(*sidecar_lines)
    ticket = os.path.join(cache(), "sweep-ticket.md")
    with open(ticket, "w") as fh:
        fh.write(SWEEP_TICKET)
    try:
        runfile.refuse_unaccounted_sweep_items(ticket, pr_body(body_text),
                                               sidecar)
    except runfile.RunFileError as exc:
        return str(exc)
    return None


def test_sweep_items_are_read_file_qualified_from_the_sweep_grammar():
    assert runfile.sweep_items(SWEEP_TICKET) == [
        "implement/SKILL.md P9", "implement/SKILL.md P14",
        "burndown/runfile.py P9"]


def test_a_sweep_pr_leaving_an_item_out_of_sidecar_and_body_is_refused_by_name():
    got = sweep_refusal(
        [sweep_leftover("implement/SKILL.md", "P9")],
        "## Decisions made\n\n- **implement/SKILL.md P9**: leftover.\n"
        "- **burndown/runfile.py P9**: fixed, abc1234.\n")
    assert got is not None and "implement/SKILL.md P14" in got, got
    assert "burndown/runfile.py P9" not in got, got


def test_a_sweep_pr_accounting_for_every_item_is_accepted():
    got = sweep_refusal(
        [sweep_leftover("implement/SKILL.md", "P9"),
         sweep_leftover("implement/SKILL.md", "P14")],
        "## Decisions made\n\n- **implement/SKILL.md P9**: leftover.\n"
        "- **implement/SKILL.md P14**: leftover.\n"
        "- **burndown/runfile.py P9**: fixed, abc1234.\n")
    assert got is None, got


def test_an_item_body_line_that_says_not_fixed_is_not_done():
    # C1: only a stated `fixed` outcome accounts for an item without a sidecar
    # line; an outcome word elsewhere on the line does not.
    for said in ("not fixed, deferred", "disputed: unreachable",
                 "left undone; will be filed later"):
        got = sweep_refusal(
            [sweep_leftover("implement/SKILL.md", "P9")],
            "## Decisions made\n\n- **implement/SKILL.md P9**: leftover.\n"
            f"- **implement/SKILL.md P14**: {said}\n"
            "- **burndown/runfile.py P9**: fixed, abc1234.\n")
        assert got is not None and "implement/SKILL.md P14" in got, (said, got)


def test_a_ticket_with_no_parsable_item_is_refused_not_passed():
    ticket = os.path.join(cache(), "empty-ticket.md")
    with open(ticket, "w") as fh:
        fh.write("Just prose, no sweep sections.\n")
    try:
        runfile.refuse_unaccounted_sweep_items(
            ticket, pr_body("## Decisions made\n\n- S1: fixed.\n"),
            sidecar_of({"id": "S1", "outcome": "fixed", "sha": "abc1234"}))
    except runfile.RunFileError as exc:
        assert "holds no" in str(exc), exc
    else:
        raise AssertionError("an item-less ticket was accepted")


def test_sweep_items_read_spaced_headings_star_bullets_and_skip_fences():
    text = ("## my notes.md\n\n* **P1** (low) t\n  - **P2** (low) t\n\n"
            "```\n## fenced.md\n- **P3** (low) t\n```\n\n"
            "## Blocked by\n\nNone — can start immediately.\n")
    assert runfile.sweep_items(text) == ["my notes.md P1", "my notes.md P2"]


def test_a_tilde_fence_holding_a_backtick_line_does_not_end_the_ticket():
    # S4: frontier's fence reader, not a second copy of it.
    text = ("## a.md\n\n~~~\n```\n~~~\n\n- **P1** (low) t\n")
    assert runfile.sweep_items(text) == ["a.md P1"]


def test_a_bullet_keeping_its_own_files_prefix_is_read_bare():
    assert runfile.sweep_items(
        "## a/one.md\n\n- **a/one.md P9** (low) t\n") == ["a/one.md P9"]


def test_a_same_id_fixed_under_another_file_does_not_account_for_an_item():
    got = sweep_refusal(
        [sweep_leftover("implement/SKILL.md", "P14")],
        "## Decisions made\n\n- **burndown/runfile.py P9**: fixed, abc1234.\n"
        "- **implement/SKILL.md P14**: leftover.\n")
    assert got is not None and "implement/SKILL.md P9" in got, got


def test_two_sweep_leftovers_are_harvested_under_their_own_files():
    sidecar = sidecar_of(sweep_leftover("implement/SKILL.md", "P9"),
                         sweep_leftover("burndown/runfile.py", "P9"))
    body = pr_body("## Decisions made\n\n- **implement/SKILL.md P9**: "
                   "leftover.\n- **burndown/runfile.py P9**: leftover.\n")
    run, added = runfile.leftover("burn-1", 901, 950, sidecar,
                                  root=landed_root(), pr_body=body)
    assert added == ["implement/SKILL.md P9", "burndown/runfile.py P9"], added
    assert [i["file"] for i in run["leftovers"]] == [
        "implement/SKILL.md", "burndown/runfile.py"]


def test_a_qualified_sidecar_id_the_body_records_fixed_is_refused_until_rewritten():
    sidecar = sidecar_of(sweep_leftover("implement/SKILL.md", "P9"))
    body = pr_body("## Decisions made\n\n- **implement/SKILL.md P9**: "
                   "fixed, abc1234.\n")
    got = refusal_of(sidecar, landed_root(), body)
    assert "implement/SKILL.md P9" in got and "'fixed'" in got, got


def test_run_file_md_usage_block_mirrors_the_runfile_docstring():
    """run-file.md's usage block is runfile.py's docstring usage (#1258): a
    subcommand in one and not the other is drift. Both must also list every
    subcommand the parser defines."""
    def usage(text):
        return [" ".join(ln.split()) for ln in text.splitlines()
                if ln.lstrip().startswith("python3 burndown/runfile.py ")]
    doc = os.path.join(os.path.dirname(RUNFILE), "references", "run-file.md")
    # The first fenced block only: later blocks are worked examples.
    block = open(doc).read().split("```")[1]
    assert sorted(usage(block)) == sorted(usage(runfile.__doc__)), (
        usage(block), usage(runfile.__doc__))
    listed = {ln.split()[2] for ln in usage(runfile.__doc__)}
    defined = set(re.findall(r'subs\.add_parser\(\s*"([a-z-]+)"',
                             open(RUNFILE).read()))
    assert listed == defined, (listed, defined)


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
