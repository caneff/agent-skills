"""End-to-end test for spec #1634: `implement-spec` owns the dispatch loop.

The moved tools driven through their own command lines, under a temp HOME and
in a throwaway repo, as a spec run's controller reaches them:

- the run file lands under `~/.cache/spec-run`, and `$SPEC_RUN_CACHE_DIR` moves it;
- `closure.py --json` makes each candidate its own clump, identical closures
  included, in every declaration mode, and refuses `--one-each`;
- `loop.py dispatch` reads those clumps and holds one that shares a file with a
  live workspace, while dispatching the one that does not;
- `drain` runs off `frontier.py` at its new path;
- the retired skill's directory and command are gone from the tree.

What a green run does NOT cover (the seam is blind to it):
- whether a model follows the merged `implement-spec/SKILL.md`: the first real
  spec run after landing is that check;
- the slash-command menu in a fresh Claude Code session, and the skill symlink
  and cache on this machine, which the retirement's landing changed.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "implement-spec"
RETIRED = "burn" + "down"
GIT_ENV = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
           "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1"}


def tool(name, *args, home=None, env=None):
    full = {k: v for k, v in os.environ.items() if k != "SPEC_RUN_CACHE_DIR"}
    full.update(env or {})
    if home:
        full["HOME"] = str(home)
    return subprocess.run([sys.executable, str(SPEC_DIR / name), *args], env=full,
                          text=True, capture_output=True, check=False)


@pytest.fixture
def repo(tmp_path):
    """A git repo with two candidates' files, declaring no include graph."""
    root = tmp_path / "repo"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    (root / "a/one.py").write_text("x\n")
    (root / "b/two.py").write_text("x\n")
    (root / "AGENTS.md").write_text("### Include closure\n\nNone.\n")
    subprocess.run(["git", "init", "-q"], cwd=root, env=GIT_ENV, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, env=GIT_ENV, check=True)
    return root


def test_the_run_file_lives_under_the_renamed_cache(tmp_path, repo):
    home = tmp_path / "home"
    home.mkdir()
    got = tool("runfile.py", "start", "spec-9-t", "--repo", str(repo), home=home)
    assert got.returncode == 0, got.stdout + got.stderr
    assert (home / ".cache/spec-run/spec-9-t.json").is_file()
    assert not (home / ".cache" / RETIRED).exists()


def test_the_renamed_variable_moves_the_cache(tmp_path, repo):
    home = tmp_path / "home"
    home.mkdir()
    runs = tmp_path / "runs"
    got = tool("runfile.py", "start", "spec-9-t", "--repo", str(repo), home=home,
               env={"SPEC_RUN_CACHE_DIR": str(runs)})
    assert got.returncode == 0, got.stdout + got.stderr
    assert (runs / "spec-9-t.json").is_file()
    assert not (home / ".cache/spec-run").exists()


@pytest.mark.parametrize("agents", ["### Include closure\n\nNone.\n", "# Nothing declared\n"])
def test_identical_closures_stay_two_clumps_in_every_mode(repo, agents):
    (repo / "AGENTS.md").write_text(agents)
    got = tool("closure.py", "--json", str(repo), "1=a/one.py", "2=a/one.py")
    assert got.returncode == 0, got.stderr
    assert [c["tickets"] for c in json.loads(got.stdout)] == [[1], [2]]


def test_the_grouping_flag_is_gone(repo):
    got = tool("closure.py", "--json", "--one-each", str(repo), "1=a/one.py")
    assert got.returncode == 2
    assert "--one-each" in got.stderr


def test_dispatch_holds_the_clump_a_live_workspace_overlaps(tmp_path, repo):
    home = tmp_path / "home"
    home.mkdir()
    assert tool("runfile.py", "start", "spec-9-t", "--slots", "2", "--repo", str(repo),
                home=home).returncode == 0
    live = tool("closure.py", "--json", str(repo), "1=a/one.py")
    clear = tool("closure.py", "--json", str(repo), "2=a/one.py", "3=b/two.py")
    in_flight = [{**json.loads(live.stdout)[0], "workspace": str(repo),
                  "agent": "w-1"}]
    assert tool("runfile.py", "clump", "spec-9-t", "--tickets", "1", "--workspace",
                str(repo), "--agent", "w-1", home=home).returncode == 0
    candidates, inflight = tmp_path / "c.json", tmp_path / "i.json"
    candidates.write_text(clear.stdout)
    inflight.write_text(json.dumps(in_flight))
    got = tool("loop.py", "dispatch", "--candidates", str(candidates), "--in-flight",
               str(inflight), "--run", "spec-9-t", "--free", "1", "--processes", "1",
               "--committed-gb", "0", "--no-workspace-diff", home=home)
    assert got.returncode == 0, got.stdout + got.stderr
    assert "dispatch  #3" in got.stdout, got.stdout
    assert "held      #2" in got.stdout, got.stdout


def test_drain_runs_off_the_moved_frontier():
    got = subprocess.run([sys.executable, str(ROOT / "drain/drain.py"), "--help"],
                         text=True, capture_output=True, check=False)
    assert got.returncode == 0, got.stdout + got.stderr
    assert (SPEC_DIR / "frontier.py").is_file()


def test_the_retired_skill_is_gone_from_the_tree():
    # Tracked, not on disk: a long-lived checkout keeps the ignored __pycache__.
    listed = subprocess.run(["git", "ls-files", RETIRED], cwd=ROOT, text=True,
                            capture_output=True, check=True, env=GIT_ENV).stdout
    assert listed == ""
    for module in ("loop", "runfile", "counts", "frontier", "closure"):
        assert (SPEC_DIR / f"{module}.py").is_file(), module
    skill = (SPEC_DIR / "SKILL.md").read_text()
    assert "## The loop" in skill
