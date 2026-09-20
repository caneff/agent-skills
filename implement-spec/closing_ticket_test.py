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
    got = T.body(repo(), spec=366, shas=SHAS, surfaces=[])
    assert "`npm run test:e2e` over the headless solver bundle" in got, got


def test_the_body_names_what_the_seam_is_blind_to():
    got = T.body(repo(), spec=366, shas=SHAS, surfaces=[])
    assert "grid rendering at 4x4 and 6x6" in got, got
    assert "blind" in got.lower(), got


def test_a_surface_beyond_the_seam_buys_one_open_of_the_real_thing():
    got = T.body(repo(), spec=366, shas=SHAS,
                 surfaces=["the ring header in the live editor"])
    assert "the ring header in the live editor" in got, got
    assert "open of the real thing" in got, got


def test_with_no_surface_beyond_the_seam_the_body_asks_for_no_manual_open():
    got = T.body(repo(), spec=366, shas=SHAS, surfaces=[])
    assert "open of the real thing" not in got, got


def test_the_review_is_handed_the_merge_shas_and_no_git_range():
    got = T.body(repo(), spec=366, shas=SHAS, surfaces=[])
    for sha in SHAS:
        assert sha in got, got
    # `a866bf3..origin/main` held this spec's three squash commits and ~17
    # unrelated commits from other sessions. What must not appear is a range
    # against the default branch; `../review-spec-366` and the skill's own
    # `<fixed point>...HEAD` are not that.
    import re
    assert "origin/" not in got, got
    assert not re.search(r"[0-9a-f]{7,40}\.\.[^.]", got), got


def test_a_repo_that_declares_no_seam_is_refused():
    try:
        T.body(repo(agents="# Fixture repo\n"), spec=366, shas=SHAS,
               surfaces=[])
    except T.SeamError as exc:
        assert "End-to-end seam" in str(exc), exc
    else:
        raise AssertionError("a repo with no seam declaration was accepted")


def test_the_exploration_pass_can_supply_a_seam_the_repo_does_not_declare():
    got = T.body(repo(agents="# Fixture repo\n"), spec=366, shas=SHAS,
                 surfaces=[], seam="`pytest tests/e2e`",
                 blind_to="anything the browser draws")
    assert "`pytest tests/e2e`" in got, got
    assert "anything the browser draws" in got, got


def test_a_seam_with_no_blind_spot_is_refused():
    # Naming the seam is necessary and not sufficient: the seam that existed
    # on #781 had diverged from the live editor inside that same spec.
    try:
        T.body(repo(agents="""# Fixture repo

## End-to-end seam

- **Seam**: `npm run test:e2e`
"""), spec=366, shas=SHAS, surfaces=[])
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
         "--shas", SHAS[0], "--no-surface"],
        capture_output=True, text=True)
    assert out.returncode == 1, out.stdout
    assert "End-to-end seam" in out.stderr, out.stderr


def test_a_fenced_example_is_not_a_declaration():
    # #890's rule, as `burndown/references/closure.md` states it for the
    # include declaration: a grammar shown inside a fence is an example.
    # `references/closing-ticket.md` shows this very grammar in a fence, so
    # the first repo that pastes the doc would otherwise declare the sample.
    fenced = """# Fixture repo

## End-to-end seam

```
- **Seam**: `npm run test:e2e` over the headless solver bundle
- **Blind to**: the live editor
```
"""
    try:
        T.body(repo(agents=fenced), spec=366, shas=SHAS, surfaces=[])
    except T.SeamError as exc:
        assert "declares no" in str(exc), exc
    else:
        raise AssertionError("a fenced example was read as a declaration")


def test_the_colon_may_sit_inside_the_emphasis():
    # `- **Seam:** x` is as common in the wild as `- **Seam**: x`, and read
    # by the stricter grammar it yields a seam beginning with `**` — silently,
    # into the ticket body.
    got = T.body(repo(agents="""# Fixture repo

## End-to-end seam

- **Seam:** `npm run e2e`
- **Blind to:** the live editor
"""), spec=366, shas=SHAS, surfaces=[])
    assert "- **Seam**: `npm run e2e`" in got, got
    assert "**Seam**: **" not in got, got


def test_a_root_that_is_not_a_directory_is_not_a_missing_declaration():
    # A typo'd root reported as "this repo declares no seam" sends the
    # operator to edit an `AGENTS.md` that was never the problem.
    try:
        T.body(os.path.join(repo(), "no-such-dir"), spec=366, shas=SHAS,
               surfaces=[])
    except T.SeamError as exc:
        assert "not a directory" in str(exc), exc
        assert "declares no" not in str(exc), exc
    else:
        raise AssertionError("a missing root was accepted")


def test_an_agents_file_that_is_not_utf8_is_reported_not_raised():
    root = repo(agents=None)
    with open(os.path.join(root, "AGENTS.md"), "wb") as fh:
        fh.write("## End-to-end seam\n\n- **Seam**: caf\xe9 e2e\n".encode("latin-1"))
    # Decoded leniently rather than crashed on: the run this generates a
    # ticket in is unattended, and a five-frame traceback from `<frozen
    # codecs>` reads as a broken tool, not as a repo with an odd byte.
    try:
        T.body(root, spec=366, shas=SHAS, surfaces=[])
    except T.SeamError as exc:
        assert "Blind to" in str(exc), exc
    else:
        raise AssertionError("the latin-1 seam declaration was not read")


def test_an_empty_sha_list_is_refused():
    try:
        T.body(repo(), spec=366, shas=[], surfaces=[])
    except T.SeamError as exc:
        assert "sha" in str(exc), exc
    else:
        raise AssertionError("a closing ticket with nothing to review was built")


def test_the_surfaces_question_must_be_answered():
    # Not "no surfaces by default": the #781 failure was a surface nobody
    # asked about. An unanswered question is refused, an explicit none is
    # fine.
    try:
        T.body(repo(), spec=366, shas=SHAS)
    except T.SeamError as exc:
        assert "surface" in str(exc), exc
    else:
        raise AssertionError("the surfaces question went unanswered")


def test_the_body_says_where_the_test_goes():
    got = T.body(repo(), spec=366, shas=SHAS, surfaces=[])
    assert "`npm run test:e2e` over the headless solver bundle" in got, got
    assert "runs it" in got, got


def test_the_cli_takes_an_explicit_none_for_the_surfaces():
    import subprocess
    out = subprocess.run(
        [sys.executable, GENERATOR, repo(), "366", "--shas", SHAS[0],
         "--no-surface"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "open of the real thing" not in out.stdout, out.stdout


def test_the_cli_refuses_an_unanswered_surfaces_question():
    import subprocess
    out = subprocess.run(
        [sys.executable, GENERATOR, repo(), "366", "--shas", SHAS[0]],
        capture_output=True, text=True)
    assert out.returncode != 0, out.stdout
    assert "surface" in (out.stderr + out.stdout), out.stderr


def test_the_declaration_outranks_the_exploration_pass():
    # A declaration an inferred value can silently override is not a
    # declaration: a stale exploration result would replace the repo's
    # canonical seam and nothing would say so.
    try:
        T.body(repo(), spec=366, shas=SHAS, surfaces=[],
               seam="`pytest tests/e2e`", blind_to="the browser")
    except T.SeamError as exc:
        assert "npm run test:e2e" in str(exc), exc
        assert "pytest tests/e2e" in str(exc), exc
        assert "AGENTS.md" in str(exc), exc
    else:
        raise AssertionError("an exploration value overrode the declaration")


def test_the_exploration_pass_fills_only_what_the_declaration_omits():
    half = """# Fixture repo

## End-to-end seam

- **Seam**: `npm run test:e2e` over the headless solver bundle
"""
    got = T.body(repo(agents=half), spec=366, shas=SHAS, surfaces=[],
                 blind_to="anything the browser draws")
    assert "`npm run test:e2e` over the headless solver bundle" in got, got
    assert "anything the browser draws" in got, got


def test_an_exploration_value_equal_to_the_declaration_is_not_a_conflict():
    got = T.body(repo(), spec=366, shas=SHAS, surfaces=[],
                 seam="`npm run test:e2e` over the headless solver bundle")
    assert "`npm run test:e2e` over the headless solver bundle" in got, got


def test_the_review_procedure_is_executable_over_the_sha_list():
    # `/multi-axis-code-review` pins one fixed point and reads
    # `<fixed point>...HEAD`; it cannot take disjoint commits. A ticket that
    # says "review these shas" and stops leaves the worker to invent a
    # range — the shared-`main` failure this criterion exists to prevent.
    got = T.body(repo(), spec=366, shas=SHAS, surfaces=[])
    assert f"git worktree add" in got, got
    # HEAD is the last of this spec's commits, the fixed point is what the
    # first one landed on, and the cherry-picks put the rest in between.
    assert f"/multi-axis-code-review {SHAS[0]}~1" in got, got
    assert f"git cherry-pick {SHAS[1]}" in got, got
    assert "origin/main" not in got, got


def test_a_single_sha_needs_no_cherry_pick():
    got = T.body(repo(), spec=366, shas=[SHAS[0]], surfaces=[])
    assert "git cherry-pick" not in got, got
    assert f"/multi-axis-code-review {SHAS[0]}~1" in got, got


def test_the_procedure_says_how_to_fall_back_and_how_to_tear_down():
    got = T.body(repo(), spec=366, shas=SHAS, surfaces=[])
    # A cherry-pick of a spec's own squash commits usually applies, but a
    # conflict must not leave the worker inventing a range either.
    assert "conflict" in got, got
    assert f"/multi-axis-code-review {SHAS[1]}~1" in got, got
    assert "git worktree remove" in got, got


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
