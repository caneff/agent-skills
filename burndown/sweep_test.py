#!/usr/bin/env python3
"""Tests for `burndown/sweep.py`, the sweep-ticket renderer #1030 built on
#1029's leftovers store. Two seams: `render_body` over an in-memory leftover
list, and the CLI over a fixture run file — the pattern `runfile_test.py`
already uses for its own CLI tests.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runfile  # noqa: E402
import sweep  # noqa: E402

SWEEP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep.py")

FIXTURES = []


def tracked_tempdir(prefix):
    """A temp dir `clean_fixtures` removes at the end of the run."""
    root = tempfile.mkdtemp(prefix=prefix)
    FIXTURES.append(root)
    return root


def cache():
    return tracked_tempdir("sweep-fixture-")


def clean_fixtures():
    left = []
    for root in FIXTURES:
        shutil.rmtree(root, ignore_errors=True)
        if os.path.exists(root):
            left.append(root)
    return left


def leftover(clump, tickets, pr, id_, file, title, severity, text):
    return {"clump": clump, "tickets": tickets, "pr": pr, "id": id_,
            "file": file, "title": title, "severity": severity,
            "text": text}


def test_zero_leftovers_renders_the_empty_string():
    assert sweep.render_body([]) == ""


def test_leftovers_group_by_file_in_first_seen_order():
    items = [
        leftover(901, [901], 950, "S1", "b/two.py", "T1", "low", "one"),
        leftover(901, [901], 950, "S2", "a/one.py", "T2", "medium", "two"),
        leftover(901, [901], 950, "S3", "b/two.py", "T3", "hard", "three"),
    ]
    body = sweep.render_body(items)
    # b/two.py appeared first, so its section leads even though a/one.py
    # sorts first alphabetically.
    assert body.index("## b/two.py") < body.index("## a/one.py"), body
    # Both S1 and S3 land inside the b/two.py section, not split across it.
    two_section = body[body.index("## b/two.py"):body.index("## a/one.py")]
    assert "S1" in two_section and "S3" in two_section, two_section
    assert "S2" not in two_section, two_section


def test_every_field_of_a_leftover_appears_in_the_render():
    items = [leftover(901, [901, 902], 950, "P2", "burndown/loop.py",
                       "Mysterious name", "judgement",
                       "tick2 says nothing about what it does")]
    body = sweep.render_body(items)
    for needle in ("burndown/loop.py", "P2", "judgement", "Mysterious name",
                   "clump #901", "#901", "#902", "950", "tick2 says nothing"):
        assert needle in body, (needle, body)


def test_render_defuses_mentions_and_raw_html_in_finding_text():
    # A finding's text lands in a ticket body: `@user` would notify someone
    # and `<tag>` would be parsed as HTML (#1097 P2). Backticked code stays.
    body = sweep.render_body([leftover(
        901, [901], 950, "S1", "a.py", "T <b>", "hard",
        "ping @caneff about <img src=x> and `x < y`")])
    assert "@caneff" not in body, body
    assert "<img" not in body and "<b>" not in body, body
    assert "`x < y`" in body, body


def test_render_treats_unmatched_and_escaped_backticks_as_plain_text():
    # CommonMark: a backtick run closes only on a run of the same length, and
    # a backslash-escaped backtick opens nothing (#1097 C1).
    for text in ("``<img src=x>`", "\\`<img src=x>`", "``@caneff`"):
        body = sweep.render_body([leftover(
            901, [901], 950, "S1", "a.py", "T", "hard", text)])
        assert "<img" not in body and "@caneff" not in body, (text, body)


def test_title_names_the_run_id():
    assert sweep.title("burn-2026-09-20-0905") == \
        "Sweep: leftovers from burn burn-2026-09-20-0905"


def cli(root, *args, cwd=None, home=None, extra_env=None):
    env = dict(os.environ, BURNDOWN_CACHE_DIR=root, **(extra_env or {}))
    if home:
        env["HOME"] = home
    return subprocess.run([sys.executable, SWEEP, *args], env=env, cwd=cwd,
                          capture_output=True, text=True)


SIDECAR = sweep.dispositions_path(cache(), 901)
shutil.copyfile(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "implement", "fixtures",
    "dispositions-sidecar.jsonl"), SIDECAR)


def test_cli_prints_the_title_and_grouped_body_for_a_run_with_leftovers():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    got = cli(root, "render", "burn-1")
    assert got.returncode == 0, got
    assert "Sweep: leftovers from burn burn-1" in got.stdout, got.stdout
    assert "## burndown/loop.py" in got.stdout, got.stdout


def test_cli_on_a_run_with_no_leftovers_prints_nothing_to_file():
    # stdout is what a caller pipes into `/file-ticket`, so it is empty here
    # — not a sentence that reads as a fileable body. The "nothing to file"
    # notice goes to stderr instead (#1030 round-1 findings S4, C3).
    root = cache()
    runfile.start("burn-2", slots=1, root=root)
    got = cli(root, "render", "burn-2")
    assert got.returncode == 0, got
    assert got.stdout == "", got.stdout
    assert "no leftovers" in got.stderr, got.stderr


def test_cli_on_an_unknown_run_is_refused():
    root = cache()
    got = cli(root, "render", "burn-missing")
    assert got.returncode != 0, got
    assert "sweep.py:" in got.stderr, got.stderr


def reviews_dir_fixture():
    return tracked_tempdir("sweep-sidecars-")


def home_fixture():
    """A directory standing in for `$HOME`, and the parent the fixture repos
    are made under."""
    return tracked_tempdir("sweep-home-")


def write_sidecar(reviews_dir, lowest, lines):
    path = sweep.dispositions_path(reviews_dir, lowest)
    with open(path, "w") as fh:
        for obj in lines:
            fh.write(json.dumps(obj) + "\n")
    return path


def test_counts_sums_fixed_adjacent_leftover_and_standalone_across_landed_clumps():
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-c", slots=2, root=root)
    runfile.clump("burn-c", [901], "/w/a", "agent-a", root=root)
    runfile.clump("burn-c", [905], "/w/b", "agent-b", root=root)
    runfile.land("burn-c", 901, "abc1234", root=root)
    runfile.land("burn-c", 905, "def5678", root=root)
    write_sidecar(reviews, 901, [
        {"id": "S1", "outcome": "fixed", "sha": "aaa"},
        {"id": "S2", "outcome": "fixed", "sha": "bbb", "scope": "adjacent"},
        {"id": "S3", "outcome": "leftover", "file": "f", "title": "t",
         "severity": "judgement", "text": "x"},
        {"id": "S4", "outcome": "disputed", "reason": "why"},
    ])
    write_sidecar(reviews, 905, [
        {"id": "P1", "outcome": "filed", "ticket": 1234},
        {"id": "P2", "outcome": "handed-back", "command": "gh issue create"},
    ])
    run = runfile.load("burn-c", root=root)
    got = sweep.counts(run, reviews)
    assert got == {"fixed": 2, "adjacent": 1, "leftover": 1, "standalone": 1}, got


def test_counts_ignores_an_unlanded_clumps_sidecar():
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-d", slots=2, root=root)
    runfile.clump("burn-d", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-d", 901, "abc1234", root=root)
    runfile.clump("burn-d", [905], "/w/b", "agent-b", root=root)
    write_sidecar(reviews, 901, [{"id": "S1", "outcome": "leftover",
                                  "file": "f", "title": "t",
                                  "severity": "judgement", "text": "x"}])
    # 905 is not landed and has no sidecar file at all — its absence must
    # not be refused, only a *landed* clump's missing sidecar is.
    run = runfile.load("burn-d", root=root)
    got = sweep.counts(run, reviews)
    assert got == {"fixed": 0, "adjacent": 0, "leftover": 1, "standalone": 0}, got


def test_counts_refuses_a_landed_clump_with_no_sidecar_rather_than_read_zero():
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-e", slots=1, root=root)
    runfile.clump("burn-e", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-e", 901, "abc1234", root=root)
    run = runfile.load("burn-e", root=root)
    try:
        sweep.counts(run, reviews)
    except runfile.RunFileError as exc:
        assert "901" in str(exc), exc
    else:
        raise AssertionError("a missing sidecar was read as zero")


def test_cli_counts_prints_the_three_counts():
    root = cache()
    reviews = reviews_dir_fixture()
    runfile.start("burn-f", slots=1, root=root)
    runfile.clump("burn-f", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-f", 901, "abc1234", root=root)
    write_sidecar(reviews, 901, [
        {"id": "S1", "outcome": "fixed", "sha": "aaa"},
        {"id": "S2", "outcome": "filed", "ticket": 5},
    ])
    got = cli(root, "counts", "burn-f", "--reviews-dir", reviews)
    assert got.returncode == 0, got
    assert "fixed in-round: 1 (0 adjacent)" in got.stdout, got.stdout
    assert "leftover: 0" in got.stdout, got.stdout
    assert "standalone: 1" in got.stdout, got.stdout


def test_counts_refuses_a_malformed_sidecar_line_rather_than_count_low():
    # runfile.leftover refuses these same lines; a reader that skipped them
    # would report a low count with a clean exit (codex-second-M1, #1097).
    bad_lines = ['{"id": "S1", "outcome": "fi', '[1, 2]',
                 '{"id": "S1", "outcome": "mystery"}']
    for n, bad in enumerate(bad_lines):
        root = cache()
        reviews = reviews_dir_fixture()
        run_id = f"burn-m{n}"
        runfile.start(run_id, slots=1, root=root)
        runfile.clump(run_id, [901], "/w/a", "agent-a", root=root)
        runfile.land(run_id, 901, "abc1234", root=root)
        path = sweep.dispositions_path(reviews, 901)
        with open(path, "w") as fh:
            fh.write('{"id": "S0", "outcome": "fixed", "sha": "aaa"}\n')
            fh.write(bad + "\n")
        got = cli(root, "counts", run_id, "--reviews-dir", reviews)
        assert got.returncode == 1, (bad, got)
        assert "dispositions-901.jsonl:2" in got.stderr, (bad, got.stderr)


def git_repo(parent, name):
    path = os.path.join(parent, name)
    os.makedirs(path)
    subprocess.run(["git", "init", "-q", path], check=True)
    return path


def test_cli_counts_reads_the_target_repos_sidecars_from_another_cwd():
    # The controller runs from one primary checkout and addresses another
    # with `--repo` (#1093): the sidecar directory is the target's, not the
    # cwd's — and a same-named sidecar under the cwd repo must not be read.
    root = cache()
    home = home_fixture()
    target = git_repo(home, "target-repo")
    other = git_repo(home, "other-repo")
    runfile.start("burn-x", slots=1, root=root)
    runfile.clump("burn-x", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-x", 901, "abc1234", root=root)
    for name, outcome in (("target-repo", "filed"), ("other-repo", "fixed")):
        d = os.path.join(home, ".cache", "agent-reviews", name)
        os.makedirs(d)
        write_sidecar(d, 901, [{"id": "S1", "outcome": outcome, "sha": "a",
                                "ticket": 5}])
    got = cli(root, "counts", "burn-x", "--repo", target, cwd=other, home=home)
    assert got.returncode == 0, got
    assert "standalone: 1" in got.stdout, got.stdout
    assert "fixed in-round: 0" in got.stdout, got.stdout


def test_cli_counts_refuses_with_neither_repo_nor_reviews_dir():
    # No cwd default: from the wrong repo it reads another repo's sidecars
    # or reports every landed clump missing.
    root = cache()
    runfile.start("burn-y", slots=1, root=root)
    got = cli(root, "counts", "burn-y", cwd=git_repo(home_fixture(), "any"))
    assert got.returncode == 1, got
    assert "--repo" in got.stderr, got.stderr


def test_cli_counts_refuses_a_repo_that_is_not_a_checkout_root():
    # A subdirectory of a repo, or a GIT_DIR in the environment, must not
    # resolve to some other repo's cache directory (#1093 C1, C2).
    root = cache()
    home = home_fixture()
    outer = git_repo(home, "outer")
    sub = os.path.join(outer, "deep")
    os.makedirs(sub)
    runfile.start("burn-z", slots=1, root=root)
    got = cli(root, "counts", "burn-z", "--repo", sub, home=home)
    assert got.returncode == 1, got
    assert "not a git checkout" in got.stderr, got.stderr
    assert "Traceback" not in got.stderr, got.stderr
    got = cli(root, "counts", "burn-z", "--repo", os.path.join(home, "nope"),
              home=home)
    assert got.returncode == 1 and "not a git checkout" in got.stderr, got


def test_cli_counts_ignores_a_git_dir_in_the_environment():
    # The sidecar exists only under the target's cache dir: a GIT_DIR that
    # repointed git at the other repo would read a directory with none and
    # refuse the landed clump as missing.
    root = cache()
    home = home_fixture()
    target = git_repo(home, "target-repo")
    other = git_repo(home, "other-repo")
    runfile.start("burn-g", slots=1, root=root)
    runfile.clump("burn-g", [901], "/w/a", "agent-a", root=root)
    runfile.land("burn-g", 901, "abc1234", root=root)
    d = os.path.join(home, ".cache", "agent-reviews", "target-repo")
    os.makedirs(d)
    write_sidecar(d, 901, [{"id": "S1", "outcome": "filed", "ticket": 5}])
    got = cli(root, "counts", "burn-g", "--repo", target, home=home,
              extra_env={"GIT_DIR": os.path.join(other, ".git")})
    assert got.returncode == 0, got
    assert "standalone: 1" in got.stdout, got.stdout


def test_cli_counts_refuses_both_repo_and_reviews_dir():
    root = cache()
    runfile.start("burn-w", slots=1, root=root)
    got = cli(root, "counts", "burn-w", "--repo", "/x", "--reviews-dir", "/y")
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
