#!/usr/bin/env python3
"""Tests for `burndown/sweep.py`, the sweep-ticket renderer #1030 built on
#1029's leftovers store. Two seams: `render_body` over an in-memory leftover
list, and the CLI over a fixture run file — the pattern `runfile_test.py`
already uses for its own CLI tests.
"""
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


def cache():
    root = tempfile.mkdtemp(prefix="sweep-fixture-")
    FIXTURES.append(root)
    return root


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
                   "#901", "#902", "950", "tick2 says nothing"):
        assert needle in body, (needle, body)


def test_title_names_the_run_id():
    assert sweep.title("burn-2026-09-20-0905") == \
        "Sweep: leftovers from burn burn-2026-09-20-0905"


def cli(root, *args):
    env = dict(os.environ, BURNDOWN_CACHE_DIR=root)
    return subprocess.run([sys.executable, SWEEP, *args], env=env,
                          capture_output=True, text=True)


SIDECAR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "implement", "fixtures",
    "dispositions-sidecar.jsonl")


def test_cli_prints_the_title_and_grouped_body_for_a_run_with_leftovers():
    root = cache()
    runfile.start("burn-1", slots=2, root=root)
    runfile.clump("burn-1", [901, 902], "/w/a", "agent-a", root=root)
    runfile.land("burn-1", 901, "abc1234", root=root)
    runfile.leftover("burn-1", 901, 950, SIDECAR, root=root)
    got = cli(root, "burn-1")
    assert got.returncode == 0, got
    assert "Sweep: leftovers from burn burn-1" in got.stdout, got.stdout
    assert "## burndown/loop.py" in got.stdout, got.stdout


def test_cli_on_a_run_with_no_leftovers_prints_nothing_to_file():
    root = cache()
    runfile.start("burn-2", slots=1, root=root)
    got = cli(root, "burn-2")
    assert got.returncode == 0, got
    assert "no leftovers" in got.stdout, got.stdout
    assert "Sweep:" not in got.stdout, got.stdout


def test_cli_on_an_unknown_run_is_refused():
    root = cache()
    got = cli(root, "burn-missing")
    assert got.returncode != 0, got
    assert "sweep.py:" in got.stderr, got.stderr


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
