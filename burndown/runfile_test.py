"""Tests for the burn run file (#892). Two seams: the read/write contract,
round-tripped through a re-read that stands in for a restart, and the resume
path's re-announce step against a stub agent list.

The `cache` fixture points `BURNDOWN_CACHE_DIR` at a per-test directory, which
keeps every case off the real `~/.cache/burndown`.
"""
import fcntl
import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runfile  # noqa: E402
from run_fixtures import drop_job, drop_repo_field, reopen_permissions  # noqa: E402

RUNFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runfile.py")
# A real git checkout for every `start` that is not about the target repo: this
# repo's own primary checkout, which `runfile.start` resolves the same way
# (this suite may run from a linked worktree).
REPO = runfile.checkout_top(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """An empty cache dir standing in for `~/.cache/burndown`, named by
    `BURNDOWN_CACHE_DIR` for the test. Two tests take a directory's read or
    write permission away, so teardown opens the tree back up before pytest's
    own cleanup reaches it."""
    root = tmp_path / "cache"
    root.mkdir()
    monkeypatch.setenv("BURNDOWN_CACHE_DIR", str(root))
    yield str(root)
    reopen_permissions(root)


@pytest.fixture
def cli(cache):
    def run(*args):
        return subprocess.run(
            [sys.executable, RUNFILE, *args], capture_output=True, text=True,
            env={**os.environ, "BURNDOWN_CACHE_DIR": cache})
    return run


@pytest.fixture
def git_checkout(tmp_path):
    """Factory: `git_checkout(name)` is a fresh `git init` directory."""
    def make(name):
        path = tmp_path / "checkouts" / name
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        return os.path.realpath(path)
    return make


@pytest.fixture
def three_clumps(cache):
    runfile.start("burn-1", slots=3, controller="burn-ctl-1a", root=cache, repo=REPO)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=cache)
    runfile.clump("burn-1", [903], "/w/b", "agent-b", root=cache)
    runfile.clump("burn-1", [905], "/w/c", "agent-c", root=cache)
    runfile.land("burn-1", 905, "abc1234", root=cache)
    return cache


@pytest.fixture
def hand_edit_clump(cache):
    """Rewrite one clump of run `burn-1` in place, as a controller's hand
    edit of the file would."""
    def edit(index, **fields):
        target = runfile.path("burn-1", cache)
        with open(target) as fh:
            run = json.load(fh)
        run["clumps"][index].update(fields)
        for key, value in fields.items():
            if value is ...:
                del run["clumps"][index][key]
        with open(target, "w") as fh:
            json.dump(run, fh)
    return edit


@pytest.fixture
def sidecar_file(tmp_path):
    def make(*lines):
        path_ = tmp_path / "dispositions-901.jsonl"
        path_.write_text("".join(line + "\n" for line in lines))
        return str(path_)
    return make


def runs_in(root):
    """The run files in a cache dir. A `<run-id>.json.lock` is the advisory
    lock, not a run."""
    return sorted(n for n in os.listdir(root) if n.endswith(".json"))


def write_run(root, run_id, run):
    with open(os.path.join(root, f"{run_id}.json"), "w") as fh:
        json.dump(run, fh)


def test_start_writes_the_run_id_and_slot_budget_and_load_reads_them_back(cache):
    runfile.start("burn-2026-09-20-0905", slots=3, root=cache, repo=REPO)
    run = runfile.load("burn-2026-09-20-0905", root=cache)
    assert run["run_id"] == "burn-2026-09-20-0905", run
    assert run["slots"] == 3, run
    assert run["clumps"] == [], run


def test_start_without_slots_records_the_default_of_five(cache):
    runfile.start("burn-1", root=cache, repo=REPO)
    assert runfile.load("burn-1", root=cache)["slots"] == 5


def test_cli_start_without_slots_records_five_and_a_named_value_wins(cache, cli):
    assert cli("start", "--repo", REPO, "burn-1").returncode == 0
    assert runfile.load("burn-1", root=cache)["slots"] == 5
    assert cli("start", "--repo", REPO, "burn-2", "--slots", "2").returncode == 0
    assert runfile.load("burn-2", root=cache)["slots"] == 2
    assert cli("start", "--repo", REPO, "burn-3", "--slots", "0").returncode != 0


def test_start_records_the_absolute_top_level_of_the_target_checkout(cache, git_checkout):
    target = git_checkout("target")
    sub = os.path.join(target, "deep")
    os.makedirs(sub)
    runfile.start("burn-1", slots=1, root=cache, repo=sub + "/")
    assert runfile.load("burn-1", root=cache)["repo"] == target


def test_start_without_a_repo_is_refused_naming_the_flag(cache, cli):
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.start("burn-1", slots=1, root=cache)
    assert "--repo" in str(exc.value), exc.value
    assert not os.path.exists(runfile.path("burn-1", cache))
    got = cli("start", "burn-1")
    assert got.returncode == 2 and "--repo" in got.stderr, got
    assert not os.path.exists(runfile.path("burn-1", cache))


def test_start_refuses_a_repo_that_is_not_a_git_checkout(cache, cli, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.start("burn-1", slots=1, root=cache, repo=str(plain))
    assert "not a git checkout" in str(exc.value), exc.value
    got = cli("start", "burn-2", "--repo", str(plain / "nope"))
    assert got.returncode == 1 and "not a git checkout" in got.stderr, got
    assert "Traceback" not in got.stderr, got.stderr
    assert not os.path.exists(runfile.path("burn-2", cache))


def test_checkout_top_ignores_git_environment_that_repoints_git(git_checkout, monkeypatch):
    # A GIT_WORK_TREE inherited from a hook or a parent shell makes raw
    # `git -C <target> rev-parse --show-toplevel` answer with the other repo.
    target = git_checkout("target")
    other = git_checkout("other")
    monkeypatch.setenv("GIT_WORK_TREE", other)
    assert runfile.checkout_top(target) == target


@pytest.mark.parametrize("blank", ["", "  "])
def test_start_refuses_a_blank_repo_instead_of_recording_the_cwds_repo(cache, blank):
    # `git -C ""` stays in the cwd: an unset `--repo "$TARGET"` would record
    # the controller's own checkout, the #1093 hazard this field closes.
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.start("burn-1", slots=1, root=cache, repo=blank)
    assert "blank" in str(exc.value), exc.value


def test_cli_start_refuses_a_blank_repo(cache, cli):
    got = cli("start", "burn-2", "--repo", "")
    assert got.returncode == 1 and "blank" in got.stderr, got
    assert not os.path.exists(runfile.path("burn-2", cache))


def test_show_prints_the_recorded_target_repo_and_says_when_there_is_none(cache, cli):
    runfile.start("burn-1", slots=1, root=cache, repo=REPO)
    assert f"repo {REPO}" in cli("show", "burn-1").stdout
    drop_repo_field("burn-1", cache)
    assert "repo none recorded" in cli("show", "burn-1").stdout


def test_a_run_file_written_before_the_repo_field_loads_and_names_no_target(cache):
    runfile.start("burn-1", slots=1, root=cache, repo=REPO)
    drop_repo_field("burn-1", cache)
    run = runfile.load("burn-1", root=cache)
    assert run["repo"] is None, run
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.target_repo(run)
    assert "names no target repo" in str(exc.value), exc.value


@pytest.mark.parametrize("bad", [7, "", "relative/path"])
def test_load_refuses_a_repo_field_that_is_not_a_path(cache, bad):
    runfile.start("burn-1", slots=1, root=cache, repo=REPO)
    target = runfile.path("burn-1", cache)
    with open(target) as fh:
        run = json.load(fh)
    run["repo"] = bad
    with open(target, "w") as fh:
        json.dump(run, fh)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.load("burn-1", root=cache)
    assert "target repo" in str(exc.value), (bad, exc.value)


def test_the_file_lands_at_run_id_dot_json_under_the_cache_dir(cache):
    runfile.start("burn-1", slots=1, root=cache, repo=REPO)
    assert os.path.isfile(os.path.join(cache, "burn-1.json")), os.listdir(cache)


def test_start_refuses_a_run_id_that_already_has_a_file(cache):
    # A resumed controller that re-runs `start` would otherwise wipe the very
    # state it restarted to read.
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.start("burn-1", slots=9, root=cache, repo=REPO)
    assert "burn-1" in str(exc.value), exc.value
    assert runfile.load("burn-1", root=cache)["slots"] == 2


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", ".", "..", ".hidden"])
def test_a_run_id_that_would_leave_the_cache_dir_is_refused(cache, bad):
    with pytest.raises(runfile.RunFileError):
        runfile.start(bad, slots=1, root=cache, repo=REPO)
    assert os.listdir(cache) == [], os.listdir(cache)


def test_loading_a_run_that_was_never_started_names_the_path(cache):
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.load("burn-nope", root=cache)
    assert "burn-nope.json" in str(exc.value), exc.value


# --- Clumps: the ticket list, the workspace, the herdr agent name ----------

def test_a_clump_records_its_tickets_workspace_and_herdr_agent_name(cache):
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    runfile.clump("burn-1", [902, 901], "/w/implement-901", "implement-901-42",
                  root=cache)
    got = runfile.load("burn-1", root=cache)["clumps"]
    assert got == [{"tickets": [901, 902], "workspace": "/w/implement-901",
                    "agent": "implement-901-42", "landed": None,
                    "closed": None,
                    "job": {"state": "none", "cores": 0},
                    "pr_up": None}], got


def test_a_clump_is_keyed_by_its_lowest_ticket_and_re_registers_in_place(cache):
    # A clump redispatched after a park keeps its identity; the workspace and
    # the herdr agent name are the parts that move.
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=cache)
    runfile.clump("burn-1", [901, 902], "/w/b", "agent-b", root=cache)
    got = runfile.load("burn-1", root=cache)["clumps"]
    assert len(got) == 1, got
    assert got[0]["workspace"] == "/w/b" and got[0]["agent"] == "agent-b", got


def test_a_ticket_already_in_another_clump_is_refused(cache):
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=cache)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.clump("burn-1", [902, 903], "/w/b", "agent-b", root=cache)
    assert "902" in str(exc.value), exc.value
    assert len(runfile.load("burn-1", root=cache)["clumps"]) == 1


@pytest.mark.parametrize("bad", [[], ["901"], [0], [-1]])
def test_a_clump_needs_at_least_one_ticket_number(cache, bad):
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    with pytest.raises(runfile.RunFileError):
        runfile.clump("burn-1", bad, "/w/a", "agent-a", root=cache)
    assert runfile.load("burn-1", root=cache)["clumps"] == [], "a refusal wrote"


# --- Landings -------------------------------------------------------------

def test_a_landing_records_the_clumps_squash_sha(cache):
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=cache)
    runfile.land("burn-1", 901, "0123456789abcdef0123456789abcdef01234567",
                 root=cache)
    got = runfile.load("burn-1", root=cache)["clumps"][0]
    assert got["landed"] == "0123456789abcdef0123456789abcdef01234567", got


def test_a_landing_on_a_clump_the_run_never_dispatched_is_refused(cache):
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.land("burn-1", 901, "abc1234", root=cache)
    assert "901" in str(exc.value), exc.value


def test_a_second_different_sha_for_a_landed_clump_is_refused(cache):
    # The squash sha is final. A second, different one is a stale writer.
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=cache)
    runfile.land("burn-1", 901, "abc1234", root=cache)
    runfile.land("burn-1", 901, "abc1234", root=cache)  # idempotent
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.land("burn-1", 901, "def5678", root=cache)
    assert "abc1234" in str(exc.value), exc.value
    assert runfile.load("burn-1", root=cache)["clumps"][0]["landed"] == "abc1234"


@pytest.mark.parametrize("bad", ["", "HEAD", "abc123", "zzzzzzz", "abc1234 "])
def test_a_landing_sha_is_hex(cache, bad):
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=cache)
    with pytest.raises(runfile.RunFileError):
        runfile.land("burn-1", 901, bad, root=cache)
    got = runfile.load("burn-1", root=cache)["clumps"][0]
    assert got["landed"] is None, got


def test_re_registering_a_landed_clump_keeps_its_sha(cache):
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=cache)
    runfile.land("burn-1", 901, "abc1234", root=cache)
    runfile.clump("burn-1", [901], "/w/a", "agent-a2", root=cache)
    assert runfile.load("burn-1", root=cache)["clumps"][0]["landed"] == "abc1234"


# --- Resume: reconcile against the live agents, re-announce the controller -

def test_resume_splits_live_from_vanished_workers_and_from_landings(three_clumps):
    root = three_clumps
    got = runfile.resume("burn-1", ["agent-a", "someone-elses-agent"],
                         root=root)
    assert [c["agent"] for c in got["announce"]] == ["agent-a"], got
    assert [c["agent"] for c in got["vanished"]] == ["agent-b"], got
    assert [c["tickets"] for c in got["landed"]] == [[905]], got


def test_a_vanished_clumps_slot_is_not_free_until_it_is_reconciled(three_clumps):
    # Three slots: one live worker, one vanished and unlanded, one landed. The
    # vanished worker may still be holding its tickets, so refilling its slot
    # puts a second worker in the same files.
    root = three_clumps
    got = runfile.resume("burn-1", ["agent-a"], root=root)
    assert got["slots"] == 3, got
    assert [c["agent"] for c in got["vanished"]] == ["agent-b"], got
    assert got["free"] == 1, got


def test_a_landed_clump_is_never_re_announced_even_if_its_agent_is_alive(three_clumps):
    root = three_clumps
    got = runfile.resume("burn-1", ["agent-a", "agent-c"], root=root)
    assert [c["agent"] for c in got["announce"]] == ["agent-a"], got
    # agent-c landed, so its slot is genuinely free; agent-b's is not.
    assert got["free"] == 1, got


def test_a_landing_frees_the_slot_a_vanished_clump_was_holding(three_clumps):
    root = three_clumps
    before = runfile.resume("burn-1", ["agent-a"], root=root)["free"]
    runfile.land("burn-1", 903, "def5678", root=root)
    after = runfile.resume("burn-1", ["agent-a"], root=root)["free"]
    assert (before, after) == (1, 2), (before, after)


def test_a_closed_clump_is_reported_closed_and_frees_its_slot(three_clumps):
    # #1236 was found already fixed on main and #1262 was a nested spec run:
    # neither landed a PR here, and neither has a worker to re-announce to.
    root = three_clumps
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


def test_a_closed_clump_reads_closed_in_show_and_survives_a_reload(three_clumps):
    root = three_clumps
    runfile.close("burn-1", 903, "nested spec run", root=root)
    run = runfile.load("burn-1", root=root)
    assert run["clumps"][1]["closed"] == "nested spec run", run
    assert run["clumps"][1]["landed"] is None, run
    assert "closed: nested spec run" in runfile.render(run), runfile.render(run)


# Landed and closed are two different facts about one clump; recording
# both would make the sweep both count its sidecar and skip it.

def test_closing_a_landed_clump_is_refused(three_clumps):
    root = three_clumps
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.close("burn-1", 905, "x", root=root)
    assert "abc1234" in str(exc.value), exc.value
    assert runfile.load("burn-1", root=root)["clumps"][2]["closed"] is None


def test_landing_a_closed_clump_is_refused(three_clumps):
    root = three_clumps
    runfile.close("burn-1", 903, "dup", root=root)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.land("burn-1", 903, "def5678", root=root)
    assert "closed" in str(exc.value), exc.value
    assert runfile.load("burn-1", root=root)["clumps"][1]["landed"] is None


@pytest.mark.parametrize("reason", ["", "   ", "two\nlines"])
def test_a_close_names_its_reason(three_clumps, reason):
    root = three_clumps
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.close("burn-1", 903, reason, root=root)
    assert "close reason" in str(exc.value), exc.value
    assert runfile.load("burn-1", root=root)["clumps"][1]["closed"] is None


def test_re_registering_a_closed_clump_reopens_it(three_clumps):
    # A clump closed by mistake and dispatched again has a worker in its
    # files: left closed, resume would never re-announce to that worker and
    # dispatch would hand its files to another.
    root = three_clumps
    runfile.close("burn-1", 903, "dup", root=root)
    runfile.clump("burn-1", [903], "/w/b2", "agent-b2", root=root)
    got = runfile.resume("burn-1", ["agent-a", "agent-b2"], root=root)
    assert [c["agent"] for c in got["announce"]] == ["agent-a", "agent-b2"], got
    assert got["closed"] == [], got


def test_closing_again_with_the_same_reason_is_a_no_op_and_another_is_refused(three_clumps):
    root = three_clumps
    runfile.close("burn-1", 903, "dup", root=root)
    runfile.close("burn-1", 903, "dup", root=root)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.close("burn-1", 903, "nested spec run", root=root)
    assert "already closed: dup" in str(exc.value), exc.value
    assert runfile.load("burn-1", root=root)["clumps"][1]["closed"] == "dup"


def test_a_run_file_with_a_clump_both_landed_and_closed_is_refused_on_load(
        three_clumps, hand_edit_clump):
    # The burn-skills-2026-09-30 shape: a clump landed at main's tip, then
    # marked closed by hand. Read as either, one reader is wrong.
    root = three_clumps
    hand_edit_clump(2, closed="already fixed on main")
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.load("burn-1", root=root)
    assert "#905 both landed and closed" in str(exc.value), exc.value


@pytest.mark.parametrize("bad", ["", True, "x\ry"])
def test_a_run_file_with_a_blank_close_reason_is_refused_on_load(
        three_clumps, hand_edit_clump, bad):
    # `""` read as no close would put a finished clump back in flight.
    root = three_clumps
    hand_edit_clump(1, closed=bad)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.load("burn-1", root=root)
    assert "close reason" in str(exc.value), (bad, exc.value)


def test_a_run_file_written_before_closes_existed_loads_with_none_closed(
        cache, hand_edit_clump):
    # No landing in this run: a landed clump would trip the both-landed-and-
    # closed refusal before the fill-in this test is about could be read.
    root = cache
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    runfile.clump("burn-1", [903], "/w/b", "agent-b", root=root)
    for index in range(2):
        hand_edit_clump(index, closed=...)
    run = runfile.load("burn-1", root=root)
    assert [c["closed"] for c in run["clumps"]] == [None, None], run


def test_close_from_the_cli_is_what_resume_reads_back(three_clumps, cli):
    got = cli("close", "burn-1", "--clump", "903", "--reason",
              "nested spec run")
    assert got.returncode == 0, got.stderr
    back = cli("resume", "burn-1", "--live", "agent-a,agent-b")
    assert back.returncode == 0, back.stderr
    assert "closed       #903  nested spec run" in back.stdout, back.stdout
    assert "agent-b" not in back.stdout, back.stdout


def test_resume_writes_the_controllers_current_agent_name_into_the_run_file(three_clumps):
    # The restart that renamed the controller is the whole reason this file
    # exists: every live worker's brief carries the dead name.
    root = three_clumps
    got = runfile.resume("burn-1", ["agent-a"], controller="burn-ctl-f3",
                         root=root)
    assert got["controller"] == "burn-ctl-f3", got
    assert runfile.load("burn-1", root=root)["controller"] == "burn-ctl-f3"


def test_resume_without_a_new_name_leaves_the_recorded_controller_alone(three_clumps):
    root = three_clumps
    got = runfile.resume("burn-1", [], root=root)
    assert got["controller"] == "burn-ctl-1a", got
    assert runfile.load("burn-1", root=root)["controller"] == "burn-ctl-1a"


# --- Durability: the write the restart interrupts --------------------------

def test_a_write_that_dies_before_it_finishes_leaves_the_old_run_intact(cache, monkeypatch):
    # The premise of the whole file: the machine can go down mid-run. A
    # half-written run file is worse than a stale one — it reads as a run
    # with no clumps.
    root = cache
    runfile.start("burn-1", slots=2, root=root, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=root)
    before = open(runfile.path("burn-1", root=root)).read()

    def power_cut(*a, **k):
        raise OSError("power cut")

    monkeypatch.setattr(os, "replace", power_cut)
    with pytest.raises(runfile.RunFileError):
        runfile.land("burn-1", 901, "abc1234", root=root)
    monkeypatch.undo()

    assert open(runfile.path("burn-1", root=root)).read() == before
    assert runs_in(root) == ["burn-1.json"], os.listdir(root)
    assert not [n for n in os.listdir(root) if n.endswith(".tmp")], os.listdir(root)


# --- The CLI: what a controller actually runs ------------------------------

def test_a_run_killed_mid_flight_is_recovered_by_a_second_process(cli):
    # The round trip the ticket asks for, across process boundaries: nothing
    # of the run survives in memory, only the file.
    assert cli("start", "--repo", REPO, "burn-1", "--slots", "3",
               "--controller", "burn-ctl-1a").returncode == 0
    assert cli("clump", "burn-1", "--tickets", "901,902",
               "--workspace", "/w/a", "--agent", "agent-a").returncode == 0
    assert cli("clump", "burn-1", "--tickets", "905",
               "--workspace", "/w/c", "--agent", "agent-c").returncode == 0
    assert cli("land", "burn-1", "--clump", "905",
               "--sha", "abc1234").returncode == 0

    got = cli("resume", "burn-1", "--live", "agent-a",
              "--controller", "burn-ctl-f3")
    assert got.returncode == 0, got.stderr
    out = got.stdout
    assert "slots 3" in out and "free 2" in out, out
    assert "burn-ctl-f3" in out, out
    assert "re-announce  agent-a" in out, out
    assert "#901,#902" in out and "/w/a" in out, out
    assert "landed" in out and "abc1234" in out, out


def test_the_cli_reports_a_vanished_worker_by_its_herdr_agent_name(cli):
    cli("start", "--repo", REPO, "burn-1", "--slots", "2")
    cli("clump", "burn-1", "--tickets", "903", "--workspace", "/w/b",
        "--agent", "agent-b")
    got = cli("resume", "burn-1", "--live", "agent-a")
    assert "vanished" in got.stdout and "agent-b" in got.stdout, got.stdout
    assert "re-announce" not in got.stdout, got.stdout


def test_show_prints_the_run_without_touching_it(cache, cli):
    cli("start", "--repo", REPO, "burn-1", "--slots", "2", "--controller", "ctl")
    cli("clump", "burn-1", "--tickets", "901", "--workspace", "/w/a",
        "--agent", "agent-a")
    before = open(os.path.join(cache, "burn-1.json")).read()
    got = cli("show", "burn-1")
    assert got.returncode == 0, got.stderr
    assert "run burn-1" in got.stdout and "agent-a" in got.stdout, got.stdout
    assert open(os.path.join(cache, "burn-1.json")).read() == before


def test_a_refusal_is_one_stderr_line_and_a_nonzero_exit(cli):
    got = cli("show", "burn-nope")
    assert got.returncode == 1, got
    assert got.stdout == "", got.stdout
    assert len(got.stderr.strip().splitlines()) == 1, got.stderr
    assert "Traceback" not in got.stderr, got.stderr


def test_the_default_home_is_the_cache_dir_that_survives_a_wsl_restart(monkeypatch):
    # Nothing here writes: the default path is asserted, not exercised. It is
    # `~/.cache` and not `/tmp` or a session scratchpad, both of which a WSL
    # restart wipes — the event the run file exists for.
    monkeypatch.delenv("BURNDOWN_CACHE_DIR", raising=False)
    got = runfile.path("burn-1", root=None)
    assert got == os.path.expanduser("~/.cache/burndown/burn-1.json"), got


def test_a_trailing_newline_does_not_sneak_through_a_run_id_or_a_sha(cache):
    # `$` matches before a final newline; `\Z` does not. A run id with a
    # newline in it is a filename with a newline in it.
    with pytest.raises(runfile.RunFileError):
        runfile.start("burn-1\n", slots=1, root=cache, repo=REPO)
    runfile.start("burn-1", slots=1, root=cache, repo=REPO)
    runfile.clump("burn-1", [901], "/w/a", "agent-a", root=cache)
    with pytest.raises(runfile.RunFileError):
        runfile.land("burn-1", 901, "abc1234\n", root=cache)
    assert runs_in(cache) == ["burn-1.json"], os.listdir(cache)


@pytest.mark.parametrize("bad", [0, -1, "3", 1.5, None, True])
def test_a_slot_budget_that_is_not_a_positive_count_is_refused(cache, bad):
    with pytest.raises(runfile.RunFileError):
        runfile.start("burn-1", slots=bad, root=cache, repo=REPO)
    assert runs_in(cache) == [], os.listdir(cache)


def test_a_file_that_is_not_a_run_is_refused_rather_than_half_read(cache):
    # The file outlives the code that wrote it, so a shape this module does
    # not recognise has to say so, not KeyError three calls later.
    with open(os.path.join(cache, "burn-1.json"), "w") as fh:
        fh.write('{"run_id": "burn-1", "slots": 2}')
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.load("burn-1", root=cache)
    assert "clumps" in str(exc.value), exc.value


@pytest.mark.parametrize("content", ['["not a run at all"]', '7', '"burn-4"'])
def test_a_json_value_that_is_not_a_run_object_is_refused(cache, content):
    with open(os.path.join(cache, "burn-2.json"), "w") as fh:
        fh.write(content)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.load("burn-2", root=cache)
    assert "not a run" in str(exc.value) or "missing" in str(exc.value), exc.value


@pytest.mark.parametrize("workspace, agent", [
    ("", "agent-a"), ("/w/a", ""), ("/w/a", None), (None, "agent-a"),
    ("/w/a", "  ")])
def test_a_clump_with_no_workspace_or_no_agent_name_is_refused(cache, workspace, agent):
    # An agent name is the only way to reach that worker after a restart, and
    # a workspace path is the only way to read what it did. Blank is not an
    # answer to either.
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    with pytest.raises(runfile.RunFileError):
        runfile.clump("burn-1", [901], workspace, agent, root=cache)
    assert runfile.load("burn-1", root=cache)["clumps"] == []


def test_a_cache_dir_under_a_file_is_a_refusal_not_a_traceback(cache):
    # After a restart `$HOME` can be full, read-only, or hold a file where the
    # cache dir belongs. A resumed controller needs the reason, not a stack.
    with open(os.path.join(cache, "afile"), "w") as fh:
        fh.write("not a directory")
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.start("burn-1", slots=1, root=os.path.join(cache, "afile", "sub"), repo=REPO)
    assert "burn-1.json" in str(exc.value), exc.value


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory modes")
def test_a_cache_dir_under_a_read_only_parent_is_a_refusal(cache):
    closed = os.path.join(cache, "closed")
    os.mkdir(closed, 0o500)
    with pytest.raises(runfile.RunFileError):
        runfile.start("burn-1", slots=1, root=os.path.join(closed, "sub"), repo=REPO)


def test_a_cache_dir_that_cannot_be_read_still_records_the_write(cache):
    # Mode 0300: writable and searchable, not readable. The write lands, so
    # reporting it as failed would leave the state on disk and the caller
    # told otherwise — and the retry then refuses with "already has a file".
    os.chmod(cache, 0o300)
    try:
        runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    finally:
        os.chmod(cache, 0o700)
    assert runfile.load("burn-1", root=cache)["slots"] == 2


def test_a_clump_entry_missing_its_agent_and_sha_is_refused(cache):
    bad = ('{"run_id": "burn-1", "slots": 2, "controller": null,'
           ' "clumps": [{"tickets": [901]}]}')
    with open(os.path.join(cache, "burn-1.json"), "w") as fh:
        fh.write(bad)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.load("burn-1", root=cache)
    assert "clump" in str(exc.value), exc.value


@pytest.mark.parametrize("clumps", [
    '{"a": 1}', '[[901]]', '7', 'null',
    '[{"tickets": [], "workspace": "/w", "agent": "a", "landed": null}]'])
def test_a_clump_entry_of_a_shape_this_module_does_not_know_is_refused(cache, clumps):
    name = "burn-2"
    with open(os.path.join(cache, f"{name}.json"), "w") as fh:
        fh.write('{"run_id": "%s", "slots": 1, "controller": null,'
                 ' "clumps": %s}' % (name, clumps))
    with pytest.raises(runfile.RunFileError):
        runfile.load(name, root=cache)


def test_re_registering_a_clump_may_not_drop_a_ticket_from_it(cache):
    # The file answers "which tickets are out". A clump re-registered under
    # its lowest ticket alone would drop the rest silently.
    runfile.start("burn-1", slots=2, root=cache, repo=REPO)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=cache)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.clump("burn-1", [901], "/w/b", "agent-b", root=cache)
    assert "902" in str(exc.value), exc.value
    assert runfile.load("burn-1", root=cache)["clumps"][0]["tickets"] == [901, 902]
    # Growing the clump is the legitimate move: a closure re-resolve adds one.
    runfile.clump("burn-1", [901, 902, 903], "/w/a", "agent-a", root=cache)
    assert runfile.load("burn-1", root=cache)["clumps"][0]["tickets"] == [901, 902, 903]


# A doubled separator is not in this list: `901,,902` names exactly two
# tickets and no other reading of it exists. `int()` accepts `9_01` and
# `+901`; `str.isdigit()` is true for `²` (which `int()` then rejects) and for
# `٩` (which `int()` accepts as 9) — one is a traceback, the other is a
# ticket the brief never named.
@pytest.mark.parametrize("bad", ["9_01", "+901", "901.0", " ", "-901", "0x385",
                                 "²", "٩" + "01"])
def test_the_cli_refuses_a_ticket_list_python_would_read_creatively(cache, cli, bad):
    # A run file that says #901 when the brief said `9_01` is a wrong answer,
    # not a lenient one.
    cli("start", "--repo", REPO, "burn-1", "--slots", "2")
    got = cli("clump", "burn-1", "--tickets", bad,
              "--workspace", "/w/a", "--agent", "agent-a")
    assert got.returncode == 1, (bad, got.stdout, got.stderr)
    assert "Traceback" not in got.stderr, got.stderr
    assert runfile.load("burn-1", root=cache)["clumps"] == []


def test_the_cli_expands_a_tilde_in_the_cache_dir_override(tmp_path):
    # `BURNDOWN_CACHE_DIR='~/.cache/x'` must not create a literal `./~/`
    # directory in whatever the controller's cwd happens to be.
    root = tmp_path / "cwd"
    home = root / "home"
    home.mkdir(parents=True)
    got = subprocess.run(
        [sys.executable, RUNFILE, "start", "--repo", REPO, "burn-1", "--slots", "1"],
        capture_output=True, text=True,
        env={**os.environ, "HOME": str(home), "BURNDOWN_CACHE_DIR": "~/cachedir"},
        cwd=root)
    assert got.returncode == 0, got.stderr
    assert os.path.isfile(os.path.join(home, "cachedir", "burn-1.json")), \
        sorted(os.listdir(root))
    assert "~" not in os.listdir(root), os.listdir(root)


# --- F4: the shape check reaches every field --------------------------------

def test_a_run_file_that_resume_cannot_arithmetic_on_never_reaches_resume(cache):
    write_run(cache, "burn-1", {"run_id": "burn-1", "slots": "2",
                                "controller": None, "clumps": []})
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.resume("burn-1", [], root=cache)
    assert "slot budget" in str(exc.value), exc.value


# --- F3: one writer at a time, enforced ------------------------------------

def test_two_concurrent_writers_do_not_lose_an_update(cache, cli):
    # Each process holds its critical section open past the other's read, so
    # without the lock the second replace would write back a run that never
    # saw the first clump. The delay is what makes this witness the lock
    # rather than pass on how two processes happen to interleave (the same
    # device flow/lane's two_concurrent_dispatches test uses).
    cli("start", "--repo", REPO, "burn-1", "--slots", "4")
    env = {**os.environ, "BURNDOWN_CACHE_DIR": cache,
           "BURNDOWN_RUNFILE_DELAY_MS": "400"}
    procs = [subprocess.Popen(
        [sys.executable, RUNFILE, "clump", "burn-1", "--tickets", str(n),
         "--workspace", f"/w/{n}", "--agent", f"agent-{n}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        for n in (901, 902, 903)]
    for proc in procs:
        out, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, err

    got = runfile.load("burn-1", root=cache)["clumps"]
    assert [c["tickets"][0] for c in got] == [901, 902, 903], got


def test_a_lock_someone_else_holds_times_out_as_a_refusal(cache, cli):
    cli("start", "--repo", REPO, "burn-1", "--slots", "2")
    lock = runfile.path("burn-1", root=cache) + ".lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        # Bounded: a waiter that never gives up would otherwise hang the suite
        # instead of failing it, which is how this guard regresses unseen.
        got = subprocess.run(
            [sys.executable, RUNFILE, "clump", "burn-1", "--tickets", "901",
             "--workspace", "/w/a", "--agent", "agent-a"],
            capture_output=True, text=True, timeout=20,
            env={**os.environ, "BURNDOWN_CACHE_DIR": cache,
                 "BURNDOWN_RUNFILE_LOCK_TIMEOUT": "1"})
    except subprocess.TimeoutExpired:
        pytest.fail("the writer never gave up waiting for the lock")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert got.returncode == 1, got
    assert "lock" in got.stderr, got.stderr
    assert "Traceback" not in got.stderr, got.stderr
    assert runfile.load("burn-1", root=cache)["clumps"] == []


# --- The environment reads: the same clean-refusal boundary -----------------

@pytest.mark.parametrize("name, value", [
    ("BURNDOWN_RUNFILE_LOCK_TIMEOUT", "30s"),
    ("BURNDOWN_RUNFILE_LOCK_TIMEOUT", "inf"),
    ("BURNDOWN_RUNFILE_LOCK_TIMEOUT", "nan"),
    ("BURNDOWN_RUNFILE_LOCK_TIMEOUT", "-5"),
    ("BURNDOWN_RUNFILE_DELAY_MS", "abc"),
    ("BURNDOWN_RUNFILE_DELAY_MS", "-1"),
    ("BURNDOWN_RUNFILE_DELAY_MS", "nan")])
def test_a_malformed_environment_value_is_a_refusal_not_a_traceback(cache, cli, name, value):
    # Round 1's F4 was malformed persisted state escaping the clean-refusal
    # path; an unguarded `float()` on an inherited env value is the same
    # contract with a new surface. A bad value inherited from a parent shell
    # must not turn a restart recovery into a stack trace.
    cli("start", "--repo", REPO, "burn-1", "--slots", "2")
    got = subprocess.run(
        [sys.executable, RUNFILE, "clump", "burn-1", "--tickets", "901",
         "--workspace", "/w/a", "--agent", "agent-a"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "BURNDOWN_CACHE_DIR": cache, name: value})
    assert got.returncode == 1, (name, value, got.stdout, got.stderr)
    assert "Traceback" not in got.stderr, got.stderr
    assert len(got.stderr.strip().splitlines()) == 1, got.stderr
    assert name in got.stderr, got.stderr
    assert runfile.load("burn-1", root=cache)["clumps"] == []


def test_an_empty_environment_value_reads_as_unset(cache):
    # `VAR=` is the shell's own way to clear an override, and every one of
    # these has a documented default to fall back to.
    got = subprocess.run(
        [sys.executable, RUNFILE, "start", "--repo", REPO, "burn-1", "--slots", "1"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "BURNDOWN_CACHE_DIR": cache,
             "BURNDOWN_RUNFILE_LOCK_TIMEOUT": "",
             "BURNDOWN_RUNFILE_DELAY_MS": ""})
    assert got.returncode == 0, got.stderr
    assert runfile.load("burn-1", root=cache)["slots"] == 1


def test_a_clump_starts_with_a_none_job_on_record_1311(cache):
    """A worker starts with nothing out, so registration records `none`:
    otherwise `loop.py dispatch` refuses every tick until the worker's "PR up"
    declares a job, idling the free slots for an hour."""
    runfile.start("r-job", 3, "dc", cache, repo=REPO)
    run = runfile.clump("r-job", [351], "/w/351", "sm-351", cache)
    assert run["clumps"][0]["job"] == {"state": "none", "cores": 0}, run


def test_re_registering_a_clump_keeps_its_declared_job_1311(cache):
    runfile.start("r-job", 3, "dc", cache, repo=REPO)
    runfile.clump("r-job", [351], "/w/351", "sm-351", cache)
    runfile.job("r-job", 351, "running", 4, cache)
    run = runfile.clump("r-job", [351], "/w/351", "sm-351b", cache)
    assert run["clumps"][0]["job"] == {"state": "running", "cores": 4}, run


def test_a_declared_job_survives_a_restart(cache):
    """The whole point: a controller that restarts mid-run recovers the hold.
    The declaration lived in one argv before, so a resume dispatched into the
    contention #351 produced."""
    runfile.start("r-job2", 3, "dc", cache, repo=REPO)
    runfile.clump("r-job2", [351], "/w/351", "sm-351", cache)
    runfile.job("r-job2", 351, "running", 8, cache)
    # A fresh read stands in for the restart.
    run = runfile.load("r-job2", cache)
    assert run["clumps"][0]["job"] == {"state": "running", "cores": 8}, run
    runfile.job("r-job2", 351, "done", root=cache)
    assert runfile.load("r-job2", cache)["clumps"][0]["job"] == {
        "state": "done", "cores": 0}


def test_a_worker_that_launched_no_job_is_recorded_as_having_said_so(cache):
    runfile.start("r-job3", 3, "dc", cache, repo=REPO)
    runfile.clump("r-job3", [351], "/w/351", "sm-351", cache)
    runfile.job("r-job3", 351, "none", root=cache)
    assert runfile.load("r-job3", cache)["clumps"][0]["job"] == {
        "state": "none", "cores": 0}


@pytest.mark.parametrize("state, cores", [
    ("running", 0), ("running", "8"), ("spinning", 1), ("running", True),
    ("none", 4)])
def test_a_job_record_that_is_not_one_is_refused(cache, state, cores):
    runfile.start("r-job4", 3, "dc", cache, repo=REPO)
    runfile.clump("r-job4", [351], "/w/351", "sm-351", cache)
    with pytest.raises(runfile.RunFileError):
        runfile.job("r-job4", 351, state, cores, cache)


def test_a_job_must_name_a_clump_of_this_run(cache):
    runfile.start("r-job4", 3, "dc", cache, repo=REPO)
    runfile.clump("r-job4", [351], "/w/351", "sm-351", cache)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.job("r-job4", 999, "none", root=cache)
    assert "#999" in str(exc.value), exc.value


def test_a_run_file_written_before_jobs_existed_still_reads(cache):
    """#892's files have no `job` key. A controller resuming one of those
    must get its run back, not a refusal about a field that did not exist."""
    runfile.start("r-old", 2, "dc", cache, repo=REPO)
    runfile.clump("r-old", [401], "/w/401", "sm-401", cache)
    drop_job("r-old", cache, 401)
    run = runfile.load("r-old", cache)
    assert run["clumps"][0]["job"] is None, run


def test_the_cli_records_a_job_and_shows_it(cli):
    assert cli("start", "--repo", REPO, "r-job5", "--slots", "2").returncode == 0
    assert cli("clump", "r-job5", "--tickets", "351", "--workspace",
               "/w/351", "--agent", "sm-351").returncode == 0
    got = cli("job", "r-job5", "--clump", "351", "--cores", "8")
    assert got.returncode == 0, got
    assert "8 cores" in got.stdout, got.stdout
    shown = cli("show", "r-job5")
    assert "8 cores" in shown.stdout, shown.stdout
    none = cli("job", "r-job5", "--clump", "351", "--none")
    assert none.returncode == 0, none
    assert "no parallel job" in cli("show", "r-job5").stdout


# --- "PR up" is on record, so the sweep can tell stalled from waiting (#1148)

def test_a_clump_starts_with_no_pr_up_on_record(cache):
    runfile.start("r-pr", 3, "dc", cache, repo=REPO)
    run = runfile.clump("r-pr", [1095], "/w/1095", "skills-1095", cache)
    assert run["clumps"][0]["pr_up"] is None, run


def test_a_recorded_pr_up_survives_a_restart_and_a_re_register(cache):
    """A resumed controller's sweep reads this record, not its context: a
    `done` pane whose "PR up" was never recorded reads `stalled`."""
    runfile.start("r-pr2", 3, "dc", cache, repo=REPO)
    runfile.clump("r-pr2", [1095], "/w/1095", "skills-1095", cache)
    runfile.pr_up("r-pr2", 1095, 1160, cache)
    assert runfile.load("r-pr2", cache)["clumps"][0]["pr_up"] == 1160
    # The same worker's clump growing after a closure re-resolve keeps it.
    runfile.clump("r-pr2", [1095, 1096], "/w/1095", "skills-1095", cache)
    assert runfile.load("r-pr2", cache)["clumps"][0]["pr_up"] == 1160


def test_a_redispatch_to_a_new_agent_clears_pr_up_so_a_done_pane_is_stalled(cache):
    import loop
    runfile.start("r-pr9", 3, "dc", cache, repo=REPO)
    runfile.clump("r-pr9", [1095], "/w/1095", "skills-1095", cache)
    runfile.pr_up("r-pr9", 1095, 1160, cache)
    run = runfile.clump("r-pr9", [1095], "/w/1095", "skills-1095-b", cache)
    state = loop.sweep(run["clumps"], lambda agent, timeout: {
        "result": {"agent": {"agent_status": "done"}}})
    assert state["workers"][0]["verdict"] == "stalled", state


@pytest.mark.parametrize("bad", [0, -1, "1160", True])
def test_a_pr_up_that_is_not_a_pr_number_is_refused(cache, bad):
    runfile.start("r-pr3", 3, "dc", cache, repo=REPO)
    runfile.clump("r-pr3", [1095], "/w/1095", "skills-1095", cache)
    with pytest.raises(runfile.RunFileError):
        runfile.pr_up("r-pr3", 1095, bad, cache)


def test_a_pr_up_record_must_name_a_clump_of_this_run(cache):
    runfile.start("r-pr3", 3, "dc", cache, repo=REPO)
    runfile.clump("r-pr3", [1095], "/w/1095", "skills-1095", cache)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.pr_up("r-pr3", 999, 1160, cache)
    assert "#999" in str(exc.value), exc.value


def test_a_run_file_written_before_pr_up_existed_still_reads(cache):
    runfile.start("r-pr4", 2, "dc", cache, repo=REPO)
    runfile.clump("r-pr4", [401], "/w/401", "sm-401", cache)
    target = runfile.path("r-pr4", cache)
    with open(target) as fh:
        raw = json.load(fh)
    del raw["clumps"][0]["pr_up"]
    with open(target, "w") as fh:
        json.dump(raw, fh)
    assert runfile.load("r-pr4", cache)["clumps"][0]["pr_up"] is None


@pytest.mark.parametrize("bad", ["7", 0, True])
def test_a_run_file_holding_a_pr_up_that_is_not_a_pr_number_is_refused(cache, bad):
    runfile.start("r-pr6", 2, "dc", cache, repo=REPO)
    runfile.clump("r-pr6", [401], "/w/401", "sm-401", cache)
    target = runfile.path("r-pr6", cache)
    with open(target) as fh:
        raw = json.load(fh)
    raw["clumps"][0]["pr_up"] = bad
    with open(target, "w") as fh:
        json.dump(raw, fh)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.load("r-pr6", cache)
    assert "PR number" in str(exc.value), exc.value


def test_the_cli_records_pr_up_and_shows_it(cli):
    assert cli("start", "--repo", REPO, "r-pr5", "--slots", "2").returncode == 0
    assert cli("clump", "r-pr5", "--tickets", "1095", "--workspace",
               "/w/1095", "--agent", "skills-1095").returncode == 0
    assert "no PR up" in cli("show", "r-pr5").stdout
    got = cli("pr-up", "r-pr5", "--clump", "1095", "--pr", "1160")
    assert got.returncode == 0, got
    assert "PR #1160 up" in cli("show", "r-pr5").stdout


def test_a_cleared_pr_up_makes_a_done_pane_stalled_again(cache, cli):
    """The controller clears the record when it hands findings back, since
    the PR stays open through a fix round: a worker that then stops mid-fix
    must read `stalled`, not `done` (Codex gate on PR #1166)."""
    import loop
    assert cli("start", "--repo", REPO, "r-pr7", "--slots", "2").returncode == 0
    assert cli("clump", "r-pr7", "--tickets", "1095", "--workspace",
               "/w/1095", "--agent", "skills-1095").returncode == 0
    assert cli("pr-up", "r-pr7", "--clump", "1095", "--pr",
               "1160").returncode == 0
    cleared = cli("pr-up", "r-pr7", "--clump", "1095", "--clear")
    assert cleared.returncode == 0, cleared
    assert "no PR up" in cleared.stdout, cleared.stdout
    clumps = runfile.load("r-pr7", cache)["clumps"]
    assert clumps[0]["pr_up"] is None, clumps
    state = loop.sweep(clumps, lambda agent, timeout: {
        "result": {"agent": {"agent_status": "done"}}})
    assert state["workers"][0]["verdict"] == "stalled", state


def test_pr_up_takes_a_pr_or_clear_but_not_both_and_not_neither(cache, cli):
    assert cli("start", "--repo", REPO, "r-pr8", "--slots", "2").returncode == 0
    assert cli("clump", "r-pr8", "--tickets", "1095", "--workspace",
               "/w/1095", "--agent", "skills-1095").returncode == 0
    both = cli("pr-up", "r-pr8", "--clump", "1095", "--pr", "1160",
               "--clear")
    assert both.returncode != 0 and "not allowed with" in both.stderr, both
    neither = cli("pr-up", "r-pr8", "--clump", "1095")
    assert neither.returncode != 0 and "required" in neither.stderr, neither
    assert runfile.load("r-pr8", cache)["clumps"][0]["pr_up"] is None


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
    defined = set(re.findall(r'subs\.add_parser\(\s*"([a-z0-9-]+)"',
                             open(RUNFILE).read()))
    assert listed == defined, (listed, defined)


# --- The dispositions sidecar reader (#1401) -------------------------------

def test_read_dispositions_reads_the_three_outcomes(sidecar_file):
    sidecar = sidecar_file(
        '{"id": "S1", "outcome": "fixed", "sha": "abc1234"}',
        '{"id": "P1", "outcome": "moved", "ticket": 12}',
        '{"id": "C1", "outcome": "disputed", "reason": "r"}')
    got = [obj["outcome"] for _, obj in runfile.read_dispositions(sidecar)]
    assert got == ["fixed", "moved", "disputed"], got


@pytest.mark.parametrize("outcome", ["leftover", "filed", "handed-back",
                                     "mystery", None])
def test_read_dispositions_refuses_a_removed_or_unknown_outcome_by_file_and_line(
        sidecar_file, outcome):
    # `leftover`, `filed` and `handed-back` are gone (#1401); a reader that
    # skipped them would count low and exit clean.
    sidecar = sidecar_file('{"id": "S1", "outcome": "fixed", "sha": "a"}',
                           json.dumps({"id": "S2", "outcome": outcome}))
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.read_dispositions(sidecar)
    assert f"{sidecar}:2" in str(exc.value) and repr(outcome) in str(exc.value), exc.value


@pytest.mark.parametrize("bad", ['{"id": "S1", "outcome": "fi', "[1, 2]",
                                 '{"outcome": "fixed"}',
                                 '{"id": 5, "outcome": "fixed"}'])
def test_read_dispositions_refuses_a_line_that_is_not_a_json_object_or_has_no_id(
        sidecar_file, bad):
    sidecar = sidecar_file(bad)
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.read_dispositions(sidecar)
    assert f"{sidecar}:1" in str(exc.value), exc.value


def test_read_dispositions_refuses_a_second_line_with_the_same_id_naming_both_lines(
        sidecar_file):
    sidecar = sidecar_file('{"id": "S1", "outcome": "fixed", "sha": "a"}',
                           '{"id": "P1", "outcome": "disputed", "reason": "r"}',
                           '{"id": "S1", "outcome": "moved", "ticket": 3}')
    with pytest.raises(runfile.RunFileError) as exc:
        runfile.read_dispositions(sidecar)
    assert f"{sidecar}:3" in str(exc.value) and "line 1" in str(exc.value), exc.value
