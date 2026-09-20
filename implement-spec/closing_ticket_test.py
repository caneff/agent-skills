#!/usr/bin/env python3
"""Tests for the spec's closing ticket (#897).

One seam, named on the ticket: `body(...)` — the closing ticket's generated
body, asserted against a fixture repo that declares an end-to-end seam and
what that seam is blind to. On #781's spec run the closing ticket named no
seam at all and the closing worker stopped and asked; the seam that existed
had already diverged from the live editor inside that same spec, so naming
it is necessary and not sufficient.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import closing_ticket as T  # noqa: E402

GENERATOR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "closing_ticket.py")

DECLARED = """# Fixture repo

## End-to-end seam

- **Seam**: `npm run test:e2e` over the headless solver bundle
- **Blind to**: the live editor — grid rendering at 4x4 and 6x6
"""

SHAS = ["a866bf3f0000000000000000000000000000abcd",
        "b12cafe10000000000000000000000000000abcd"]

FIXTURES = []


def repo(agents=DECLARED):
    root = tempfile.mkdtemp(prefix="closing-ticket-fixture-")
    FIXTURES.append(root)
    if agents is not None:
        with open(os.path.join(root, "AGENTS.md"), "w") as fh:
            fh.write(agents)
    return root


def clean_fixtures():
    left = []
    while FIXTURES:
        root = FIXTURES.pop()
        shutil.rmtree(root, ignore_errors=True)
        if os.path.exists(root):
            left.append(root)
    return left


def test_the_body_names_the_repos_declared_seam():
    got = T.body(repo(), spec=366, shas=SHAS)
    assert "`npm run test:e2e` over the headless solver bundle" in got, got


def test_the_body_names_what_the_seam_is_blind_to():
    got = T.body(repo(), spec=366, shas=SHAS)
    assert "grid rendering at 4x4 and 6x6" in got.lower() or \
           "grid rendering at 4x4 and 6x6" in got, got
    assert "blind" in got.lower(), got


def test_a_surface_beyond_the_seam_buys_one_open_of_the_real_thing():
    got = T.body(repo(), spec=366, shas=SHAS,
                 surfaces=["the ring header in the live editor"])
    assert "the ring header in the live editor" in got, got
    assert "open of the real thing" in got, got


def test_with_no_surface_beyond_the_seam_the_body_asks_for_no_manual_open():
    got = T.body(repo(), spec=366, shas=SHAS)
    assert "open of the real thing" not in got, got


def test_the_review_is_handed_the_merge_shas_and_no_git_range():
    got = T.body(repo(), spec=366, shas=SHAS)
    for sha in SHAS:
        assert sha in got, got
    # `a866bf3..origin/main` held this spec's three squash commits and ~17
    # unrelated commits from other sessions; the review takes one fixed point.
    assert ".." not in got.replace("...", ""), got


def test_a_repo_that_declares_no_seam_is_refused():
    try:
        T.body(repo(agents="# Fixture repo\n"), spec=366, shas=SHAS)
    except T.SeamError as exc:
        assert "End-to-end seam" in str(exc), exc
    else:
        raise AssertionError("a repo with no seam declaration was accepted")


def test_the_exploration_pass_can_supply_a_seam_the_repo_does_not_declare():
    got = T.body(repo(agents="# Fixture repo\n"), spec=366, shas=SHAS,
                 seam="`pytest tests/e2e`", blind_to="anything the browser draws")
    assert "`pytest tests/e2e`" in got, got
    assert "anything the browser draws" in got, got


def test_a_seam_with_no_blind_spot_is_refused():
    # Naming the seam is necessary and not sufficient: the seam that existed
    # on #781 had diverged from the live editor inside that same spec.
    try:
        T.body(repo(agents="""# Fixture repo

## End-to-end seam

- **Seam**: `npm run test:e2e`
"""), spec=366, shas=SHAS)
    except T.SeamError as exc:
        assert "Blind to" in str(exc), exc
    else:
        raise AssertionError("a seam with no blind spot was accepted")


def test_the_cli_prints_the_body():
    import subprocess
    out = subprocess.run(
        [sys.executable, GENERATOR, repo(), "366",
         "--shas", ",".join(SHAS),
         "--surface", "the ring header in the live editor"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "open of the real thing" in out.stdout, out.stdout
    assert SHAS[0] in out.stdout, out.stdout


def test_the_cli_fails_loud_when_no_seam_is_declared():
    import subprocess
    out = subprocess.run(
        [sys.executable, GENERATOR, repo(agents="# Fixture repo\n"), "366",
         "--shas", SHAS[0]],
        capture_output=True, text=True)
    assert out.returncode == 1, out.stdout
    assert "End-to-end seam" in out.stderr, out.stderr


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
