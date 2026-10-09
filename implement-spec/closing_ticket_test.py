"""Tests for the spec's closing check (#897, reshaped by #1402); runs under pytest.

One seam, named on the ticket: `body(...)` — the closing-check section's
generated body, asserted against a fixture repo that declares an end-to-end
seam and what that seam is blind to. On #781's spec run the then-separate
closing ticket named no seam at all and the closing worker stopped and asked;
the seam that existed had already diverged from the live editor inside that
same spec, so naming it is necessary and not sufficient.
"""
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import closing_ticket as T  # noqa: E402
import closure  # noqa: E402
import frontier  # noqa: E402

GENERATOR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "closing_ticket.py")

DECLARED = """# Fixture repo

## End-to-end seam

- **Seam**: `npm run test:e2e` over the headless solver bundle
- **Blind to**: the live editor — grid rendering at 4x4 and 6x6
"""


def body(*args, **kwargs):
    """`T.body` with the default branch every case but the refusal names."""
    kwargs.setdefault("default", "main")
    return T.body(*args, **kwargs)


@pytest.fixture
def repo(tmp_path):
    """Make a fixture repo dir holding `agents` as its AGENTS.md (none if None)."""
    count = 0

    def make(agents=DECLARED):
        nonlocal count
        count += 1
        root = tmp_path / f"fixture-{count}"
        root.mkdir()
        if agents is not None:
            (root / "AGENTS.md").write_text(agents)
        return str(root)

    return make


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def test_the_body_is_a_section_for_the_integration_pr(repo):
    # #1461: a spec with more than one slice lands on main in one PR from its
    # integration branch, and the closing check runs there, not in the last
    # slice's body.
    got = body(repo(), spec=366, surfaces=[])
    assert got.startswith("## Closing check"), got
    assert "integration PR" in got, got
    assert "base `main`, head `spec-366`" in got, got
    assert "last slice" not in got, got
    assert "Close out the spec" not in got, got


def test_the_review_reads_the_integration_branch_and_no_sha_list(repo):
    # The integration branch holds this spec and current main, nothing else,
    # so the range is the review's own and the cherry-pick procedure is gone.
    got = body(repo(), spec=366, surfaces=[])
    review = got.split("### The spec-level review", 1)[1].split("###", 1)[0]
    assert "`origin/main...spec-366`" in review, review
    acceptance = got.split("### Acceptance criteria", 1)[1]
    assert "`origin/main...spec-366`" in acceptance, acceptance
    assert "/multi-axis-code-review origin/main" in got, got
    assert "codex-usage-gate.py" in got, got
    assert "git cherry-pick" not in got, got
    assert "merge shas" not in got, got
    assert not re.search(r"\b[0-9a-f]{7,40}\b", got), got


def test_the_review_is_keyed_on_the_spec_number(repo):
    got = body(repo(), spec=366, surfaces=[])
    assert "dispositions-366.jsonl" in got, got
    assert "fix-check.sh 366 origin/spec-366" in got, got


def test_main_is_merged_in_never_rebased(repo):
    got = body(repo(), spec=366, surfaces=[])
    assert "git merge --no-edit origin/main" in got, got
    assert "rebase" in got and "never" in got, got


def test_the_landed_slices_are_brought_in_before_main(repo):
    # The slices merge into origin/spec-366 on GitHub; the spec run's own
    # spec-366 stays where dispatch cut it until it takes them in (#1461's
    # review, P1/C2), or the review reads none of them.
    got = body(repo(), spec=366, surfaces=[])
    block = got.split("```\n", 2)[1]
    assert block.index("git merge --ff-only origin/spec-366") < block.index(
        "git merge --no-edit origin/main"), block


def test_the_default_branch_is_never_assumed(repo):
    with pytest.raises(TypeError) as exc:
        T.body(repo(), spec=366, surfaces=[])
    assert "default" in str(exc.value), exc.value


def test_the_integration_pr_closes_every_slice_and_the_spec(repo):
    got = body(repo(), spec=366, surfaces=[])
    assert "`Closes #366`" in got, got
    assert "`Closes #<slice>`" in got, got


def test_the_default_branch_is_the_one_named(repo):
    got = body(repo(), spec=366, surfaces=[], default="trunk")
    assert "`origin/trunk...spec-366`" in got, got
    assert "base `trunk`" in got, got
    assert "origin/main" not in got, got


def test_a_one_slice_spec_gets_the_seam_in_its_slice_and_no_spec_review(repo):
    # Ruling 3a of #1457: a one-slice spec has no integration branch, its
    # slice lands on main with its own review wave, so the section goes in
    # that slice's body and names no spec-level review.
    got = body(repo(), spec=366, surfaces=[], one_slice=True)
    assert "grid rendering at 4x4 and 6x6" in got, got
    assert "`Closes #366`" in got, got
    assert "only slice" in got, got
    assert "spec-level review" not in got, got
    assert "spec-366" not in got, got
    assert "integration" not in got, got


def test_the_cli_reads_the_default_branch_off_the_repo(repo):
    root = repo()
    env = clean_env()
    for args in (["init", "-q", "-b", "trunk"],
                 ["remote", "add", "origin", root],
                 ["symbolic-ref", "refs/remotes/origin/HEAD",
                  "refs/remotes/origin/trunk"]):
        subprocess.run(["git", "-C", root, *args], check=True, env=env)
    out = subprocess.run([sys.executable, GENERATOR, root, "366",
                          "--no-surface"], capture_output=True, text=True,
                         env=env)
    assert out.returncode == 0, out.stderr
    assert "`origin/trunk...spec-366`" in out.stdout, out.stdout


def test_the_cli_refuses_when_the_default_branch_cannot_be_read(repo):
    # A fixture under a TMPDIR inside some checkout must still read as no
    # repo: the ceiling stops git's discovery at the fixture's parent.
    root = repo()
    env = clean_env()
    env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(root)
    out = subprocess.run([sys.executable, GENERATOR, root, "366",
                          "--no-surface"], capture_output=True, text=True,
                         env=env)
    assert out.returncode == 1, out.stdout
    assert "--default" in out.stderr, out.stderr


def test_the_cli_takes_a_one_slice_spec(repo):
    out = subprocess.run([sys.executable, GENERATOR, repo(), "366",
                          "--one-slice", "--no-surface"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "only slice" in out.stdout, out.stdout


def test_the_body_names_what_the_seam_is_blind_to(repo):
    got = body(repo(), spec=366, surfaces=[])
    assert "grid rendering at 4x4 and 6x6" in got, got
    assert "blind" in got.lower(), got


def test_a_surface_beyond_the_seam_buys_one_open_of_the_real_thing(repo):
    got = body(repo(), spec=366,
                 surfaces=["the ring header in the live editor"])
    assert "the ring header in the live editor" in got, got
    assert "open of the real thing" in got, got


def test_with_no_surface_beyond_the_seam_the_body_asks_for_no_manual_open(repo):
    got = body(repo(), spec=366, surfaces=[])
    assert "open of the real thing" not in got, got


def test_a_repo_that_declares_no_seam_is_refused(repo):
    with pytest.raises(T.SeamError) as exc:
        body(repo(agents="# Fixture repo\n"), spec=366, surfaces=[])
    assert "End-to-end seam" in str(exc.value), exc.value


def test_the_exploration_pass_can_supply_a_seam_the_repo_does_not_declare(repo):
    got = body(repo(agents="# Fixture repo\n"), spec=366,
                 surfaces=[], seam="`pytest tests/e2e`",
                 blind_to="anything the browser draws")
    assert "`pytest tests/e2e`" in got, got
    assert "anything the browser draws" in got, got


def test_a_seam_with_no_blind_spot_is_refused(repo):
    # Naming the seam is necessary and not sufficient: the seam that existed
    # on #781 had diverged from the live editor inside that same spec.
    with pytest.raises(T.SeamError) as exc:
        body(repo(agents="""# Fixture repo

## End-to-end seam

- **Seam**: `npm run test:e2e`
"""), spec=366, surfaces=[])
    assert "Blind to" in str(exc.value), exc.value


@pytest.fixture
def refusal(repo):
    def run(agents, **kw):
        with pytest.raises(T.SeamError) as exc:
            T.seam_of(repo(agents=agents), **kw)
        return str(exc.value)

    return run


def test_an_emphasis_only_seam_is_refused_naming_the_seam_and_the_value(refusal):
    got = refusal("# R\n\n## End-to-end seam\n\n- **Seam**:**\n"
                   "- **Blind to**: x\n")
    assert "Seam" in got and "'**'" in got, got


def test_an_emphasis_only_blind_spot_is_refused_naming_the_blind_spot(refusal):
    got = refusal("# R\n\n## End-to-end seam\n\n- **Seam**: `make e2e`\n"
                   "- **Blind to**:__\n")
    assert "Blind to" in got and "'__'" in got, got


def test_an_emphasis_only_exploration_value_is_refused_too(refusal):
    got = refusal("# R\n", seam=" * _ ", blind_to="x")
    assert "Seam" in got and "'*" in got, got


def test_any_whitespace_between_emphasis_markers_still_counts_as_only_markers(refusal):
    got = refusal("# R\n", seam="*\n*", blind_to="x")
    assert "Seam" in got and "'*\\n*'" in got, got


def test_the_cli_prints_the_body(repo):
    out = subprocess.run(
        [sys.executable, GENERATOR, repo(), "366",
         "--default", "main",
         "--surface", "the ring header in the live editor"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "open of the real thing" in out.stdout, out.stdout
    assert "origin/main...spec-366" in out.stdout, out.stdout


def test_the_cli_fails_loud_when_no_seam_is_declared(repo):
    out = subprocess.run(
        [sys.executable, GENERATOR, repo(agents="# Fixture repo\n"), "366",
         "--default", "main", "--no-surface"],
        capture_output=True, text=True)
    assert out.returncode == 1, out.stdout
    assert "End-to-end seam" in out.stderr, out.stderr


def test_a_fenced_example_is_not_a_declaration(repo):
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
    with pytest.raises(T.SeamError) as exc:
        body(repo(agents=fenced), spec=366, surfaces=[])
    assert "declares no" in str(exc.value), exc.value


def test_an_indented_quotation_is_not_a_declaration():
    # #999's own risk, named in the ticket: `unfenced()` now opens a fence
    # only at CommonMark's <=3-space bound, so a 4-space-indented example is
    # no longer hidden by an (incorrect) fence match. `declaration` reads raw
    # `unfenced()` with no `_QUOTED` filter of its own, so without this it
    # reads the quoted example as this doc's real declaration. The heading
    # itself is real and unindented, so the section is found (not `None`,
    # the "no such section" answer) — it just states nothing readable, the
    # same "empty section is silence" shape `or {}` already treats as one.
    text = ("## End-to-end seam\n\n- a doc quotes another repo's block:\n\n"
            "    ```\n"
            "    - **Seam**: `npm run test:e2e`\n"
            "    - **Blind to**: the live editor\n"
            "    ```\n")
    assert not T.declaration(text), T.declaration(text)


def test_the_colon_may_sit_inside_the_emphasis(repo):
    # `- **Seam:** x` is as common in the wild as `- **Seam**: x`, and read
    # by the stricter grammar it yields a seam beginning with `**` — silently,
    # into the ticket body.
    got = body(repo(agents="""# Fixture repo

## End-to-end seam

- **Seam:** `npm run e2e`
- **Blind to:** the live editor
"""), spec=366, surfaces=[])
    assert "- **Seam**: `npm run e2e`" in got, got
    assert "**Seam**: **" not in got, got


def test_a_colon_inside_the_emphasis_needs_no_space_before_a_code_span(repo):
    # `- **Seam:**`npm run e2e`` is a balanced key followed directly by a
    # code span. The lookahead grammar left the closing `**` in the value.
    got = body(repo(agents="""# Fixture repo

## End-to-end seam

- **Seam:**`npm run e2e`
- **Blind to:**the live editor
"""), spec=366, surfaces=[])
    assert "- **Seam**: `npm run e2e`" in got, got
    assert "**Seam**: **" not in got, got


@pytest.mark.parametrize("line", [
    "- **Seam**: bash tests/all.sh", "- **Seam:** bash tests/all.sh",
    "- **Seam**:**x**", "- Seam: plain", "* __Blind to__: a thing",
    "- **Seam**:**"])
def test_both_readers_parse_a_key_line_as_frontier_does(line):
    # One key-line parser, in `frontier` (#1000): a second copy is the drift
    # #928 fixed once already. Run the same awkward lines through each reader
    # and compare with `frontier.key_line`, so a copy under any name that parses
    # them differently fails.
    pair = frontier.key_line(line)
    got = T.declaration("## End-to-end seam\n" + line + "\n")
    assert got == ({pair[0]: pair[1]} if pair else {}), (line, got, pair)


def test_the_include_closure_reader_parses_a_key_line_as_frontier_does():
    directive = "- **Directive**: `#include <x>`"
    want = frontier.key_line(directive)[1].strip("`")
    parsed = closure.parse_declaration("## Include closure\n" + directive + "\n- **Generator**: g\n")
    assert parsed.directive == want, parsed


def test_a_root_that_is_not_a_directory_is_not_a_missing_declaration(repo):
    # A typo'd root reported as "this repo declares no seam" sends the
    # operator to edit an `AGENTS.md` that was never the problem.
    with pytest.raises(T.SeamError) as exc:
        body(os.path.join(repo(), "no-such-dir"), spec=366, surfaces=[])
    assert "not a directory" in str(exc.value), exc.value
    assert "declares no" not in str(exc.value), exc.value


def test_an_agents_file_that_is_not_utf8_is_reported_not_raised(repo):
    root = repo(agents=None)
    with open(os.path.join(root, "AGENTS.md"), "wb") as fh:
        fh.write("## End-to-end seam\n\n- **Seam**: caf\xe9 e2e\n".encode("latin-1"))
    # Decoded leniently rather than crashed on: the run this generates a
    # ticket in is unattended, and a five-frame traceback from `<frozen
    # codecs>` reads as a broken tool, not as a repo with an odd byte.
    with pytest.raises(T.SeamError) as exc:
        body(root, spec=366, surfaces=[])
    assert "Blind to" in str(exc.value), exc.value


def test_the_surfaces_question_must_be_answered(repo):
    # Not "no surfaces by default": the #781 failure was a surface nobody
    # asked about. An unanswered question is refused, an explicit none is
    # fine.
    with pytest.raises(T.SeamError) as exc:
        body(repo(), spec=366)
    assert "surface" in str(exc.value), exc.value


def test_the_body_says_where_the_test_goes(repo):
    got = body(repo(), spec=366, surfaces=[])
    assert "`npm run test:e2e` over the headless solver bundle" in got, got
    assert "runs it" in got, got


def test_the_cli_takes_an_explicit_none_for_the_surfaces(repo):
    out = subprocess.run(
        [sys.executable, GENERATOR, repo(), "366", "--default", "main",
         "--no-surface"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "open of the real thing" not in out.stdout, out.stdout


def test_the_cli_refuses_an_unanswered_surfaces_question(repo):
    out = subprocess.run(
        [sys.executable, GENERATOR, repo(), "366", "--default", "main"],
        capture_output=True, text=True)
    assert out.returncode != 0, out.stdout
    assert "surface" in (out.stderr + out.stdout), out.stderr


def test_the_declaration_outranks_the_exploration_pass(repo):
    # A declaration an inferred value can silently override is not a
    # declaration: a stale exploration result would replace the repo's
    # canonical seam and nothing would say so.
    with pytest.raises(T.SeamError) as exc:
        body(repo(), spec=366, surfaces=[],
             seam="`pytest tests/e2e`", blind_to="the browser")
    assert "npm run test:e2e" in str(exc.value), exc.value
    assert "pytest tests/e2e" in str(exc.value), exc.value
    assert "AGENTS.md" in str(exc.value), exc.value


def test_the_exploration_pass_fills_only_what_the_declaration_omits(repo):
    half = """# Fixture repo

## End-to-end seam

- **Seam**: `npm run test:e2e` over the headless solver bundle
"""
    got = body(repo(agents=half), spec=366, surfaces=[],
                 blind_to="anything the browser draws")
    assert "`npm run test:e2e` over the headless solver bundle" in got, got
    assert "anything the browser draws" in got, got


def test_an_exploration_value_equal_to_the_declaration_is_not_a_conflict(repo):
    got = body(repo(), spec=366, surfaces=[],
                 seam="`npm run test:e2e` over the headless solver bundle")
    assert "`npm run test:e2e` over the headless solver bundle" in got, got


WRAPPED = """# Fixture repo

## End-to-end seam

- **Seam**: `just test`
- **Blind to**: the live app — solve time (`just time`),
  how a link renders, and
  what the share sheet shows
- Notes: not a key of this section
"""


def test_a_wrapped_blind_spot_is_read_whole(repo):
    # #1243: a list item wrapped onto indented continuation lines was cut at
    # its first line break, and the closing ticket stated a partial blind
    # spot as the whole one.
    seam, blind_to = T.seam_of(repo(agents=WRAPPED))
    assert blind_to == ("the live app — solve time (`just time`), "
                        "how a link renders, and what the share sheet shows"), \
        blind_to


def test_a_wrapped_value_reaches_the_ticket_body(repo):
    got = body(repo(agents=WRAPPED), spec=366, surfaces=[])
    assert "what the share sheet shows" in got, got


def test_a_continuation_indented_four_spaces_is_still_the_value():
    # `visible()` drops a four-space line as quoted material; adjacent to a
    # key line it is that item's continuation, not a quotation.
    text = ("## End-to-end seam\n\n- **Seam**: `just test`\n"
            "- **Blind to**: the live app\n"
            "    and how a link renders\n")
    assert T.declaration(text)["blind to"] == \
        "the live app and how a link renders", T.declaration(text)


def test_an_indented_paragraph_after_a_blank_line_is_still_the_value():
    # A loose list item: Markdown keeps a paragraph indented under the item
    # after a blank line inside it, so the blind spot it states is part of
    # the value (#1406 C3).
    text = ("## End-to-end seam\n\n- **Blind to**: the live app\n\n"
            "  and a later paragraph\n")
    assert T.declaration(text)["blind to"] == \
        "the live app and a later paragraph", T.declaration(text)


def test_a_blank_line_ends_a_key_line_that_is_no_list_item():
    # Markdown's loose paragraph lives inside a list item only: after a
    # blank line, an indented block under a bare key line is a code block,
    # never more of the value (#1406 C4).
    text = ("## End-to-end seam\n\n**Blind to**: the live app\n\n"
            "    $ bash tests/all.sh   # an example run\n")
    assert T.declaration(text)["blind to"] == "the live app", \
        T.declaration(text)


def test_a_blank_line_then_a_line_at_the_item_depth_ends_the_item():
    text = ("## End-to-end seam\n\n- **Blind to**: the live app\n\n"
            "The gate runs the suites.\n")
    assert T.declaration(text)["blind to"] == "the live app", \
        T.declaration(text)


def test_a_declaration_nested_under_a_parent_bullet_still_reads():
    # A key line always ends the item, deeper or not: swallowing it into its
    # parent would turn a present declaration into "declares nothing".
    text = ("## End-to-end seam\n\n- Declaration:\n"
            "  - **Seam**: `just test`\n  - **Blind to**: the live app\n")
    got = T.declaration(text)
    assert got["seam"] == "`just test`", got
    assert got["blind to"] == "the live app", got


@pytest.mark.parametrize("after", [
    "- Run the gate before merging", "> quoted aside",
    "<!-- keep in sync with CI -->", "The gate runs the suites."])
def test_a_line_that_does_not_wrap_the_item_is_not_joined(after):
    # Only lines indented deeper than the item continue it: a sibling bullet,
    # a blockquote, a comment or a paragraph at the item's own depth is
    # another block, and joining it states text the author never put in the
    # blind spot.
    text = ("## End-to-end seam\n\n- **Blind to**: the live app\n"
            + after + "\n")
    assert T.declaration(text)["blind to"] == "the live app", after


def test_a_fence_after_the_value_is_not_part_of_it():
    text = ("## End-to-end seam\n\n- **Blind to**: the live app\n"
            "  ```\n  echo hi\n  ```\n  and more\n")
    assert T.declaration(text)["blind to"] == "the live app", \
        T.declaration(text)


def test_a_wrapped_value_stops_at_the_next_heading():
    text = ("## End-to-end seam\n\n- **Blind to**: the live app\n"
            "## Next\n- **Seam**: elsewhere\n")
    assert T.declaration(text) == {"blind to": "the live app"}, \
        T.declaration(text)
