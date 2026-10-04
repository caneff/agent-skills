#!/usr/bin/env python3
"""Tests for `burndown/counts.py`, the closing report's fixed and moved counts.
Two seams: `counts` over a fixture run file and sidecar directory, and the CLI.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runfile  # noqa: E402
from run_fixtures import drop_repo_field, linked_worktree  # noqa: E402
import counts as counts_mod  # noqa: E402

# A real git checkout to record as a run's target when the case is not about it.
REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

COUNTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "counts.py")

FIXTURES = []


def tracked_tempdir(prefix):
    """A temp dir `clean_fixtures` removes at the end of the run."""
    root = tempfile.mkdtemp(prefix=prefix)
    FIXTURES.append(root)
    return root


def cache():
    return tracked_tempdir("counts-fixture-")


def clean_fixtures():
    left = []
    for root in FIXTURES:
        shutil.rmtree(root, ignore_errors=True)
        if os.path.exists(root):
            left.append(root)
    return left


def cli(root, *args, cwd=None, home=None, extra_env=None):
    env = dict(os.environ, BURNDOWN_CACHE_DIR=root, **(extra_env or {}))
    if home:
        env["HOME"] = home
    return subprocess.run([sys.executable, COUNTS, *args], env=env, cwd=cwd,
                          capture_output=True, text=True)


def reviews_dir_fixture():
    return tracked_tempdir("counts-sidecars-")


def home_fixture():
    """A directory standing in for `$HOME`, and the parent the fixture repos
    are made under."""
    return tracked_tempdir("counts-home-")


def write_sidecar(reviews_dir, lowest, lines):
    path = runfile.dispositions_path(reviews_dir, lowest)
    with open(path, "w") as fh:
        for obj in lines:
            fh.write(json.dumps(obj) + "\n")
    return path


def test_counts_sums_fixed_and_moved_across_landed_clumps():
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-c", slots=2, root=root, repo=REPO)
    runfile.clump("burn-c", [901], "/w/a", "agent-a", root=root)
    runfile.clump("burn-c", [905], "/w/b", "agent-b", root=root)
    runfile.land("burn-c", 901, "abc1234", root=root)
    runfile.land("burn-c", 905, "def5678", root=root)
    write_sidecar(reviews, 901, [
        {"id": "S1", "outcome": "fixed", "sha": "aaa"},
        {"id": "S2", "outcome": "fixed", "sha": "bbb"},
        {"id": "S4", "outcome": "disputed", "reason": "why"},
    ])
    write_sidecar(reviews, 905, [
        {"id": "P1", "outcome": "moved", "ticket": 1234},
    ])
    run = runfile.load("burn-c", root=root)
    got = counts_mod.counts(run, reviews)
    assert got == {"fixed": 2, "moved": 1, "carried": 0, "closed": []}, got


def test_counts_ignores_an_unlanded_clumps_sidecar():
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-d", slots=2, root=root, repo=REPO)
    runfile.clump("burn-d", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-d", 901, "abc1234", root=root)
    runfile.clump("burn-d", [905], "/w/b", "agent-b", root=root)
    write_sidecar(reviews, 901, [{"id": "S1", "outcome": "fixed", "sha": "a"}])
    # 905 is not landed and has no sidecar file at all — its absence must
    # not be refused, only a *landed* clump's missing sidecar is.
    run = runfile.load("burn-d", root=root)
    got = counts_mod.counts(run, reviews)
    assert got == {"fixed": 1, "moved": 0, "carried": 0, "closed": []}, got


def test_a_pre_1401_sidecar_still_counts_filed_as_moved_and_names_the_leftovers_nothing_sweeps():
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-l", slots=1, root=root, repo=REPO)
    runfile.clump("burn-l", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-l", 901, "abc1234", root=root)
    write_sidecar(reviews, 901, [
        {"id": "S1", "outcome": "fixed", "sha": "a"},
        {"id": "S2", "outcome": "filed", "ticket": 5},
        {"id": "S3", "outcome": "leftover", "file": "f", "title": "t", "severity": "hard", "text": "x"},
        {"id": "S4", "outcome": "handed-back", "command": "gh issue create"},
    ])
    got = cli(root, "burn-l", "--reviews-dir", reviews)
    assert got.returncode == 0, got.stderr
    assert "fixed: 1  moved: 1" in got.stdout, got.stdout
    assert "swept by nothing: 2" in got.stdout, got.stdout


def test_counts_refuses_a_landed_clump_with_no_sidecar_rather_than_read_zero():
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-e", slots=1, root=root, repo=REPO)
    runfile.clump("burn-e", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-e", 901, "abc1234", root=root)
    run = runfile.load("burn-e", root=root)
    try:
        counts_mod.counts(run, reviews)
    except runfile.RunFileError as exc:
        assert "901" in str(exc), exc
    else:
        raise AssertionError("a missing sidecar was read as zero")


def test_counts_names_a_closed_clump_as_skipped_rather_than_refusing_it():
    # burn-skills-2026-09-30: #1236 (already fixed on main) and #1262 (a
    # nested spec run) closed with no PR here, so neither has a sidecar. The
    # report names them, so a reader can tell them from a clump never read.
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-g", slots=3, root=root, repo=REPO)
    runfile.clump("burn-g", [901], "/w/a", "agent-a", root=root)
    runfile.clump("burn-g", [1236], "/w/b", "agent-b", root=root)
    runfile.clump("burn-g", [1262], "/w/c", "agent-c", root=root)
    runfile.land("burn-g", 901, "abc1234", root=root)
    runfile.close("burn-g", 1236, "duplicate of #1202", root=root)
    runfile.close("burn-g", 1262, "nested spec run", root=root)
    write_sidecar(reviews, 901, [{"id": "S1", "outcome": "fixed", "sha": "a"}])
    got = cli(root, "burn-g", "--reviews-dir", reviews)
    assert got.returncode == 0, got.stderr
    assert "fixed: 1" in got.stdout, got.stdout
    assert ("skipped, closed without a landing: #1236 (duplicate of #1202), "
            "#1262 (nested spec run)") in got.stdout, got.stdout


def test_cli_counts_prints_fixed_and_moved():
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-f", slots=1, root=root, repo=REPO)
    runfile.clump("burn-f", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-f", 901, "abc1234", root=root)
    write_sidecar(reviews, 901, [
        {"id": "S1", "outcome": "fixed", "sha": "aaa"},
        {"id": "S2", "outcome": "moved", "ticket": 5},
    ])
    got = cli(root, "burn-f", "--reviews-dir", reviews)
    assert got.returncode == 0, got
    assert "fixed: 1" in got.stdout, got.stdout
    assert "moved: 1" in got.stdout, got.stdout


def test_counts_refuses_a_malformed_sidecar_line_rather_than_count_low():
    # `runfile.read_dispositions` refuses these lines; a reader that skipped them
    # would report a low count with a clean exit (codex-second-M1, #1097).
    bad_lines = ['{"id": "S1", "outcome": "fi', '[1, 2]',
                 '{"id": "S1", "outcome": "mystery"}']
    for n, bad in enumerate(bad_lines):
        root = cache()
        reviews = reviews_dir_fixture()
        run_id = f"burn-m{n}"
        runfile.start(run_id, slots=1, root=root, repo=REPO)
        runfile.clump(run_id, [901], "/w/a", "agent-a", root=root)
        runfile.land(run_id, 901, "abc1234", root=root)
        path = runfile.dispositions_path(reviews, 901)
        with open(path, "w") as fh:
            fh.write('{"id": "S0", "outcome": "fixed", "sha": "aaa"}\n')
            fh.write(bad + "\n")
        got = cli(root, run_id, "--reviews-dir", reviews)
        assert got.returncode == 1, (bad, got)
        assert "dispositions-901.jsonl:2" in got.stderr, (bad, got.stderr)


def git_repo(parent, name):
    path = os.path.join(parent, name)
    os.makedirs(path)
    subprocess.run(["git", "init", "-q", path], check=True)
    return path


def test_cli_counts_accepts_the_primary_checkout_of_a_run_started_in_a_worktree_1254():
    # #1190 C2: `start --repo <linked worktree>` and `counts --repo <primary>`
    # name one target and read one sidecar directory.
    root = cache()
    home = home_fixture()
    target = git_repo(home, "target-repo")
    linked = linked_worktree(target, "linked")
    runfile.start("burn-x", slots=1, root=root, repo=linked)
    runfile.clump("burn-x", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-x", 901, "abc1234", root=root)
    d = os.path.join(home, ".cache", "agent-reviews", "target-repo")
    os.makedirs(d)
    write_sidecar(d, 901, [{"id": "S1", "outcome": "moved", "sha": "a",
                            "ticket": 5}])
    for where in (target, linked):
        got = cli(root, "burn-x", "--repo", where, home=home)
        assert got.returncode == 0, (where, got)
        assert "moved: 1" in got.stdout, got.stdout


def test_cli_counts_keys_the_cache_on_the_common_git_dir_not_the_checkout_name_1254():
    # multi-axis-code-review keys its directory on the dirname of
    # `--git-common-dir`; a `--separate-git-dir` checkout is the layout where
    # that and the checkout's own name differ.
    root = cache()
    home = home_fixture()
    work = os.path.join(home, "the-checkout")
    gitdir = os.path.join(home, "gitdirs", "sep.git")
    os.makedirs(os.path.dirname(gitdir))
    os.makedirs(work)
    subprocess.run(["git", "init", "-q", "--separate-git-dir", gitdir, work],
                   check=True)
    runfile.start("burn-x", slots=1, root=root, repo=work)
    runfile.clump("burn-x", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-x", 901, "abc1234", root=root)
    d = os.path.join(home, ".cache", "agent-reviews", "gitdirs")
    os.makedirs(d)
    write_sidecar(d, 901, [{"id": "S1", "outcome": "moved", "sha": "a",
                            "ticket": 5}])
    got = cli(root, "burn-x", "--repo", work, home=home)
    assert got.returncode == 0, got
    assert "moved: 1" in got.stdout, got.stdout


def test_cli_counts_reads_the_target_repos_sidecars_from_another_cwd():
    # The controller runs from one primary checkout and addresses another
    # with `--repo` (#1093): the sidecar directory is the target's, not the
    # cwd's — and a same-named sidecar under the cwd repo must not be read.
    root = cache()
    home = home_fixture()
    target = git_repo(home, "target-repo")
    other = git_repo(home, "other-repo")
    runfile.start("burn-x", slots=1, root=root, repo=target)
    runfile.clump("burn-x", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-x", 901, "abc1234", root=root)
    for name, outcome in (("target-repo", "moved"), ("other-repo", "fixed")):
        d = os.path.join(home, ".cache", "agent-reviews", name)
        os.makedirs(d)
        write_sidecar(d, 901, [{"id": "S1", "outcome": outcome, "sha": "a",
                                "ticket": 5}])
    got = cli(root, "burn-x", "--repo", target, cwd=other, home=home)
    assert got.returncode == 0, got
    assert "moved: 1" in got.stdout, got.stdout
    assert "fixed: 0" in got.stdout, got.stdout


def test_cli_counts_refuses_with_neither_repo_nor_reviews_dir():
    # No cwd default: from the wrong repo it reads another repo's sidecars
    # or reports every landed clump missing.
    root = cache()
    runfile.start("burn-y", slots=1, root=root, repo=REPO)
    got = cli(root, "burn-y", cwd=git_repo(home_fixture(), "any"))
    assert got.returncode == 1, got
    assert "--repo" in got.stderr, got.stderr


def test_cli_counts_refuses_a_repo_that_is_not_a_git_checkout():
    # A path git cannot resolve must not read as some other repo's cache
    # directory (#1093 C1, C2).
    root = cache()
    home = home_fixture()
    runfile.start("burn-z", slots=1, root=root, repo=REPO)
    got = cli(root, "burn-z", "--repo", os.path.join(home, "nope"),
              home=home)
    assert got.returncode == 1 and "not a git checkout" in got.stderr, got
    assert "Traceback" not in got.stderr, got.stderr


def landed_run(root, run_id, repo):
    runfile.start(run_id, slots=1, root=root, repo=repo)
    runfile.clump(run_id, [901], "/w/a", "agent-a", root=root)
    runfile.land(run_id, 901, "abc1234", root=root)


def test_cli_counts_refuses_a_repo_other_than_the_runs_target_1190():
    # The other checkout has a sidecar of its own waiting to be misread; the
    # run's recorded target decides, so it is refused before any is read.
    root = cache()
    home = home_fixture()
    target = git_repo(home, "target-repo")
    other = git_repo(home, "other-repo")
    landed_run(root, "burn-o", target)
    d = os.path.join(home, ".cache", "agent-reviews", "other-repo")
    os.makedirs(d)
    write_sidecar(d, 901, [{"id": "S1", "outcome": "fixed", "sha": "a"}])
    got = cli(root, "burn-o", "--repo", other, home=home)
    assert got.returncode == 1, got
    assert os.path.realpath(target) in got.stderr, got.stderr
    assert os.path.realpath(other) in got.stderr, got.stderr
    assert got.stdout == "", got.stdout  # a refusal prints no counts


def test_cli_counts_accepts_the_recorded_checkout_from_a_subdirectory_1190():
    root = cache()
    home = home_fixture()
    target = git_repo(home, "target-repo")
    sub = os.path.join(target, "deep")
    os.makedirs(sub)
    landed_run(root, "burn-s", target)
    d = os.path.join(home, ".cache", "agent-reviews", "target-repo")
    os.makedirs(d)
    write_sidecar(d, 901, [{"id": "S1", "outcome": "moved", "ticket": 5}])
    for spelled in (target, sub, target + "/"):
        got = cli(root, "burn-s", "--repo", spelled, home=home)
        assert got.returncode == 0, (spelled, got)
        assert "moved: 1" in got.stdout, got.stdout


def test_cli_counts_refuses_a_run_file_that_names_no_target_repo_1190():
    root = cache()
    home = home_fixture()
    target = git_repo(home, "target-repo")
    landed_run(root, "burn-l", target)
    drop_repo_field("burn-l", root)
    got = cli(root, "burn-l", "--repo", target, home=home)
    assert got.returncode == 1, got
    assert "names no target repo" in got.stderr, got.stderr
    # `--reviews-dir` is the explicit escape and is not checked.
    d = os.path.join(home, "sidecars")
    os.makedirs(d)
    write_sidecar(d, 901, [{"id": "S1", "outcome": "moved", "ticket": 5}])
    got = cli(root, "burn-l", "--reviews-dir", d, home=home)
    assert got.returncode == 0, got


def test_cli_counts_ignores_a_git_dir_in_the_environment():
    # The sidecar exists only under the target's cache dir: a GIT_DIR that
    # repointed git at the other repo would read a directory with none and
    # refuse the landed clump as missing.
    root = cache()
    home = home_fixture()
    target = git_repo(home, "target-repo")
    other = git_repo(home, "other-repo")
    runfile.start("burn-g", slots=1, root=root, repo=target)
    runfile.clump("burn-g", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-g", 901, "abc1234", root=root)
    d = os.path.join(home, ".cache", "agent-reviews", "target-repo")
    os.makedirs(d)
    write_sidecar(d, 901, [{"id": "S1", "outcome": "moved", "ticket": 5}])
    got = cli(root, "burn-g", "--repo", target, home=home,
              extra_env={"GIT_DIR": os.path.join(other, ".git")})
    assert got.returncode == 0, got
    assert "moved: 1" in got.stdout, got.stdout


def test_cli_counts_refuses_both_repo_and_reviews_dir():
    root = cache()
    runfile.start("burn-w", slots=1, root=root, repo=REPO)
    got = cli(root, "burn-w", "--repo", "/x", "--reviews-dir", "/y")
    assert got.returncode == 2, got
    assert "not allowed with" in got.stderr, got.stderr


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    try:
        for test in tests:
            test()
            print(f"ok  {test.__name__}")
        print(f"{len(tests)} passed")
    finally:
        left = clean_fixtures()
        if left:
            print(f"fixtures left behind: {', '.join(left)}", file=sys.stderr)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
