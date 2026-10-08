#!/usr/bin/env python3
"""Tests for the include-closure clumper (#891). Two seams, both named on the
ticket: `resolve_closure(root, files)` — the set of files a change to `files`
regenerates — and `clumps(root, candidates)` — the connected components of
the collision graph over those closures, as families of clumps (#970), plus
the mode announcement the run's opening report carries.

Every case is a fixture repo written to a temp directory: a declaration in
`AGENTS.md` and a few files that include each other. Nothing here runs a
generator, because nothing in the resolver may.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import closure as C  # noqa: E402
from unittest import mock  # noqa: E402

CLOSURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "closure.py")

DECLARED = """# Fixture repo

## Include closure

- **Directive**: `#include <path>`
- **Generator**: `make examples`
"""


# Every fixture repo this run made, so that `clean_fixtures` can remove them
# whatever the run did. Forty per run, left behind, is how a shared box ends
# up carrying 1,863 of them (measured, 84 MB): the leak is inodes, not size.
FIXTURES = []


def git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", root, *args], check=True,
                          capture_output=True, env=env)


def clean_fixtures():
    """Remove every fixture repo this run made, and return the ones that
    survived. Some tests take a directory's or a file's read permission away,
    so each is opened back up before the tree goes — a fixture that cannot be
    removed must be reported, never ignored."""
    left = []
    while FIXTURES:
        root = FIXTURES.pop()
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


def repo(files, agents=DECLARED):
    """A fixture repo on disk: `{path: text}` plus an `AGENTS.md`, or no
    `AGENTS.md` at all when `agents` is None. Removed by `clean_fixtures` at
    the end of the run, pass or fail."""
    root = tempfile.mkdtemp(prefix="closure-fixture-")
    FIXTURES.append(root)
    git(root, "init", "-q")
    if agents is not None:
        files = {**files, "AGENTS.md": agents}
    for path, text in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)
    return root


# --- The declaration -------------------------------------------------------

def test_the_declaration_is_read_from_agents_md():
    decl = C.declaration(repo({}))
    assert decl.directive == "#include <path>", decl
    assert decl.generator == "make examples", decl


def test_a_colon_inside_the_emphasis_is_not_part_of_the_value():
    text = ("## Include closure\n\n- **Directive:** `#include <path>`\n"
            "- **Generator:** `make examples`\n")
    got = C.parse_declaration(text)
    assert got.directive == "#include <path>", got
    assert got.generator == "make examples", got


def test_a_colon_inside_the_emphasis_needs_no_space_before_the_value():
    text = ("## Include closure\n\n- **Directive:**`#include <path>`\n"
            "- **Generator:**`make examples`\n")
    got = C.parse_declaration(text)
    assert got.directive == "#include <path>", got
    assert got.generator == "make examples", got


def test_a_bold_value_keeps_its_own_markers():
    text = "## Include closure\n- **Directive**:**#include <path>**\n"
    assert C.parse_declaration(text).directive == "**#include <path>**"


# --- The closure: one hop from the candidate's own files -------------------

SHARED = {
    "examples/_shared/line-kind.js": "// the shared snippet\n",
    "examples/skyscraper/component.js": "#include ../_shared/line-kind.js\n",
    "examples/thermo/component.js": "#include ../_shared/line-kind.js\n",
    "examples/outside/component.js": "#include ../skyscraper/component.js\n",
    "docs/notes.md": "no include here\n",
}


def test_the_closure_is_every_file_that_includes_the_target():
    root = repo(SHARED)
    got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    assert got == {"examples/_shared/line-kind.js",
                   "examples/skyscraper/component.js",
                   "examples/thermo/component.js"}, got


def test_a_transitive_includer_is_not_in_the_closure():
    # One hop, stated: `outside` includes `skyscraper`, which includes the
    # shared snippet. Walking the second hop flattens the graph into most of
    # the repo and stops separating any two candidates.
    root = repo(SHARED)
    got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    assert "examples/outside/component.js" not in got, got


def test_a_file_included_by_nothing_closes_over_itself():
    root = repo(SHARED)
    got = C.resolve_closure(root, ["docs/notes.md"])
    assert got == {"docs/notes.md"}, got


def test_the_closure_does_not_follow_forward_includes():
    # Changing a component that includes the shared snippet does not
    # regenerate the snippet, nor the snippet's other includers.
    root = repo(SHARED)
    got = C.resolve_closure(root, ["examples/skyscraper/component.js"])
    assert got == {"examples/skyscraper/component.js",
                   "examples/outside/component.js"}, got


def test_a_declared_none_closes_each_candidate_over_its_own_files():
    root = repo({"a/one.md": "#include ../b/two.md\n", "b/two.md": "x\n"},
                agents="## Include closure\n\nNone \u2014 nothing here is generated.\n")
    got = C.resolve_closure(root, ["b/two.md"])
    assert got == {"b/two.md"}, got


def test_a_repo_that_declares_nothing_cannot_resolve_a_closure():
    root = repo(SHARED, agents="# Fixture\n\nNo section here.\n")
    refused = None
    try:
        got = C.resolve_closure(root, ["docs/notes.md"])
    except C.ClosureError as exc:
        refused = str(exc)
        got = None
    assert refused is not None, f"silence must not resolve as a closure: {got}"
    assert "declares no include closure" in refused, refused


def test_a_directive_may_name_a_path_between_literals():
    root = repo({"page.html": '{% include "parts/head.html" %}\n',
                 "parts/head.html": "<head>\n"},
                agents='## Include closure\n\n'
                       '- **Directive**: `{% include "<path>" %}`\n'
                       '- **Paths**: repo-root\n'
                       '- **Generator**: `make site`\n')
    got = C.resolve_closure(root, ["parts/head.html"])
    assert got == {"parts/head.html", "page.html"}, got


# --- Clumps: the connected components of the collision graph ---------------

def candidate(number, *files):
    return {"number": number, "files": list(files)}


def numbers(clumping):
    return [c["tickets"] for c in C.clump_list(clumping)]


def families(clumping):
    """Each family's clumps, as ticket lists."""
    return [[c["tickets"] for c in f["clumps"]] for f in clumping["families"]]


def test_two_candidates_sharing_an_include_are_one_family():
    # #781's costliest finding, as a fixture: #451 targets the shared
    # snippet, #455 targets the skyscraper component, and nothing in either
    # ticket names the other's file. Their closures differ, so they are two
    # clumps that wait on each other, not one clump (#970).
    root = repo(SHARED)
    got = C.clumps(root, [candidate(451, "examples/_shared/line-kind.js"),
                          candidate(455, "examples/skyscraper/component.js")])
    assert families(got) == [[[451], [455]]], got


def test_a_candidate_colliding_with_nothing_clumps_alone():
    root = repo(SHARED)
    got = C.clumps(root, [candidate(451, "examples/_shared/line-kind.js"),
                          candidate(501, "docs/notes.md")])
    assert numbers(got) == [[451], [501]], got


# --- Families: a component is run serially, not shipped whole (#970) ------

# `burn-2026-09-21-0930`, in small. That repo declares None, so a closure is
# a candidate's own files; each of five candidates names its own file and the
# same hub (`implement/SKILL.md` there). One component — and on that run the
# only move the loop had was one worker holding all 27 tickets.
NONE_DECLARED = "## Include closure\n\nNone \u2014 nothing here is generated.\n"
HUB = {"hub.md": "x\n", **{f"c{n}/own.md": "x\n" for n in range(1, 6)}}


def test_one_hub_file_chains_five_candidates_into_one_family_of_five_clumps():
    root = repo(HUB, agents=NONE_DECLARED)
    got = C.clumps(root, [candidate(n, "hub.md", f"c{n}/own.md")
                          for n in range(1, 6)])
    assert families(got) == [[[1], [2], [3], [4], [5]]], got
    assert got["families"][0]["tickets"] == [1, 2, 3, 4, 5], got


def test_two_candidates_with_identical_closures_are_one_clump_of_two():
    # They would only rebase onto each other, so one worker takes both.
    root = repo(HUB, agents=NONE_DECLARED)
    got = C.clumps(root, [candidate(7, "c1/own.md", "hub.md"),
                          candidate(3, "hub.md", "./c1/own.md")])
    assert families(got) == [[[3, 7]]], got


def test_four_identical_closures_are_capped_at_a_clump_of_three_and_one():
    root = repo(HUB, agents=NONE_DECLARED)
    got = C.clumps(root, [candidate(n, "hub.md") for n in (4, 1, 3, 2)])
    assert families(got) == [[[1, 2, 3], [4]]], got


def test_a_family_split_by_the_cap_says_so_when_rendered():
    root = repo(HUB, agents=NONE_DECLARED)
    capped = C.render(C.clumps(root, [candidate(n, "hub.md") for n in range(1, 5)]))
    assert f"split at MAX_CLUMP={C.MAX_CLUMP}" in capped, capped
    uncapped = C.render(C.clumps(root, [candidate(n, "hub.md") for n in range(1, 4)]))
    assert "MAX_CLUMP" not in uncapped, uncapped


def closure_json(root, *specs):
    """`closure.py --json`, written where `loop.py dispatch --candidates`
    would read it."""
    out = subprocess.run([sys.executable, CLOSURE, "--json", root, *specs],
                         capture_output=True, text=True)
    assert out.returncode == 0, out
    path = os.path.join(root, "candidates.json")
    with open(path, "w") as fh:
        fh.write(out.stdout)
    return path, out


def test_the_json_output_round_trips_through_read_clumps():
    import loop
    root = repo(HUB, agents=NONE_DECLARED)
    specs = [f"{n}=hub.md,c{n}/own.md" for n in (1, 2)] + ["3=c3/own.md"]
    path, out = closure_json(root, *specs)
    got = loop.read_clumps(path)
    want = C.clump_list(C.clumps(root, [C.parse_candidate(s) for s in specs]))
    assert got == want, (got, want)
    assert [c["tickets"] for c in got] == [[1], [2], [3]], got
    # The announcement is not dropped: it goes where the redirect does not.
    assert out.stderr.startswith("clumping: include closure"), out.stderr


def test_one_live_family_member_holds_the_rest_and_another_family_dispatches():
    # The serialization needs no new mechanism: `loop.py dispatch` already
    # holds a clump sharing a file with a live workspace. #1 is live; #2 and
    # #3 share the hub with it, and #4 is a different family.
    import loop
    root = repo(HUB, agents=NONE_DECLARED)
    path, _ = closure_json(root, *[f"{n}=hub.md,c{n}/own.md" for n in (1, 2, 3)],
                           "4=c4/own.md")
    listed = loop.read_clumps(path)
    live = [dict(c, workspace="/w/implement-1") for c in listed
            if c["tickets"] == [1]]
    rest = [c for c in listed if c["tickets"] != [1]]
    state = loop.frontier(rest, live)
    assert [c["tickets"] for c in state["dispatchable"]] == [[4]], state
    assert sorted(h["clump"]["tickets"] for h in state["held"]) == [[2], [3]], state
    assert all(h["over"] == ["hub.md"] for h in state["held"]), state
    assert [c["tickets"] for c in loop.refill(rest, live, 3)] == [[4]]


# --- The conservative fallback, and what the report says it got ------------

def test_a_repo_declaring_nothing_clumps_by_directory_subtree():
    root = repo({"a/one.js": "x\n", "a/two.js": "x\n", "b/three.js": "x\n"},
                agents=None)
    got = C.clumps(root, [candidate(1, "a/one.js"), candidate(2, "a/two.js"),
                          candidate(3, "b/three.js")])
    assert got["mode"] == "subtree", got
    assert numbers(got) == [[1, 2], [3]], got


def test_a_parent_directory_contains_its_subtree():
    root = repo({"a/one.js": "x\n", "a/deep/two.js": "x\n"}, agents=None)
    got = C.clumps(root, [candidate(1, "a/one.js"), candidate(2, "a/deep/two.js")])
    assert numbers(got) == [[1, 2]], got


def test_the_fallback_is_announced_in_stated_words():
    root = repo(SHARED, agents=None)
    got = C.clumps(root, [candidate(1, "docs/notes.md")])
    assert got["announcement"] == (
        "clumping: conservative, by directory subtree \u2014 AGENTS.md declares "
        "no include closure, so any two candidates touching the same "
        "directory subtree are one clump, and a family is never split"), got


def test_a_declared_grammar_is_announced_with_its_directive_and_generator():
    root = repo(SHARED)
    got = C.clumps(root, [candidate(1, "docs/notes.md")])
    assert got["mode"] == "closure", got
    assert got["announcement"] == (
        "clumping: include closure, from AGENTS.md "
        "(directive `#include <path>`, generator `make examples`); each "
        "family runs as clumps of identical closures"), got


def test_a_declared_none_is_announced_as_its_own_third_answer():
    # Silence and a stated None both clump each candidate on its own files
    # here; the report must still tell them apart, because silence is a gap
    # someone should close and None is the truth about the repo.
    root = repo(SHARED, agents="## Include closure\n\nNone \u2014 nothing is generated.\n")
    got = C.clumps(root, [candidate(1, "docs/notes.md")])
    assert got["mode"] == "no-include-graph", got
    assert got["announcement"] == (
        "clumping: include closure, from AGENTS.md (declared None: this repo "
        "has no include graph, so each candidate closes over its own files); "
        "each family runs as clumps of identical closures"), got


# --- The cost ceiling ------------------------------------------------------

def test_the_whole_queue_is_resolved_against_one_repo_scan():
    # Per-candidate resolution is the expense the declaration exists to
    # avoid; a queue of ten candidates must not read the repo ten times.
    root = repo(SHARED)
    scans = []
    real = C.repo_files
    C.repo_files = lambda r: (scans.append(r), real(r))[1]
    try:
        C.clumps(root, [candidate(n, "docs/notes.md") for n in range(1, 11)])
    finally:
        C.repo_files = real
    assert len(scans) == 1, scans


def test_no_code_path_runs_the_declared_generator():
    root = repo(SHARED)
    marker = os.path.join(root, "generator-ran")
    with open(os.path.join(root, "AGENTS.md"), "w") as fh:
        fh.write(DECLARED.replace("make examples", f"touch {marker}"))
    got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    assert "examples/skyscraper/component.js" in got, got
    C.clumps(root, [candidate(451, "examples/_shared/line-kind.js")])
    subprocess.run([sys.executable, CLOSURE, root, "1=examples/_shared/line-kind.js"],
                   capture_output=True, check=True)
    assert not os.path.exists(marker), "the declared generator ran"


# --- A quoted declaration is not a declaration -----------------------------

def test_a_fenced_declaration_is_quoted_never_declared():
    # #890's rule, reused rather than reimplemented: a doc that shows the
    # grammar inside a fence has declared nothing, and this repo's own
    # references/closure.md quotes exactly such a block.
    agents = ("# Fixture\n\n```\n## Include closure\n\n"
              "- **Directive**: `#include <path>`\n```\n")
    root = repo(SHARED, agents=agents)
    got = C.clumps(root, [candidate(1, "docs/notes.md")])
    assert got["mode"] == "subtree", got


def test_an_indented_quotation_is_not_a_declaration():
    # #999's own risk, named in the ticket: `unfenced()` now opens a fence
    # only at CommonMark's <=3-space bound, so a 4-space-indented example is
    # no longer hidden by an (incorrect) fence match. `declaration_section`
    # reads raw `unfenced()` with no `_QUOTED` filter of its own, so without
    # this it reads the quoted example as this doc's real declaration.
    text = ("## Include closure\n\n- a doc quotes another repo's block:\n\n"
            "    ```\n"
            "    - **Directive**: `#include <path>`\n"
            "    - **Generator**: `make x`\n"
            "    ```\n")
    assert C.parse_declaration(text) is None, C.parse_declaration(text)


def test_a_section_that_states_nothing_readable_is_silence():
    # An empty section, or prose naming no directive and not saying None,
    # has declared nothing — and silence is the conservative fallback.
    for section in ("", "we generate some things, probably\n"):
        root = repo(SHARED, agents="## Include closure\n\n" + section)
        got = C.clumps(root, [candidate(1, "docs/notes.md")])
        assert got["mode"] == "subtree", (section, got)


# --- The command line ------------------------------------------------------

def test_the_command_line_prints_the_mode_and_the_clumps():
    root = repo(SHARED)
    out = subprocess.run(
        [sys.executable, CLOSURE, root,
         "451=examples/_shared/line-kind.js",
         "455=examples/skyscraper/component.js",
         "501=docs/notes.md"],
        capture_output=True, text=True)
    assert out.returncode == 0, out
    assert "directive `#include <path>`" in out.stdout, out.stdout
    assert "family #451, #455  (2 clumps)" in out.stdout, out.stdout
    assert "clump #451  (" in out.stdout, out.stdout
    assert "family #501  (1 clump)" in out.stdout, out.stdout


def test_the_command_line_says_when_no_closure_was_resolved():
    # The conservative mode's own output shape: what it prints are the files
    # the tickets named, and the line says so rather than calling them a
    # closure.
    root = repo({"a/one.js": "x\n", "b/two.js": "x\n"}, agents=None)
    out = subprocess.run([sys.executable, CLOSURE, root, "1=a/one.js", "2=b/two.js"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out
    assert "conservative, by directory subtree" in out.stdout, out.stdout
    assert "named, no closure resolved" in out.stdout, out.stdout
    assert "in the closure" not in out.stdout, out.stdout


def test_a_malformed_candidate_is_one_stderr_line_not_a_traceback():
    root = repo(SHARED)
    out = subprocess.run([sys.executable, CLOSURE, root, "not-a-candidate"],
                         capture_output=True, text=True)
    assert out.returncode == 1, out
    assert out.stderr.startswith("closure.py: "), out.stderr
    assert "Traceback" not in out.stderr, out.stderr


# --- Two spellings of one file are one file (round 1: C1, C2) -------------

def test_a_dot_slash_spelling_collides_the_same_as_a_bare_one():
    # The conservative mode promises clumping too much, never too little, and
    # `./a/one.js` is ordinary ticket-body and command-line spelling.
    root = repo({"a/one.js": "x\n", "a/two.js": "x\n"}, agents=None)
    got = C.clumps(root, [candidate(1, "./a/one.js"), candidate(2, "a/two.js")])
    assert numbers(got) == [[1, 2]], got


def test_an_absolute_candidate_path_is_the_file_it_names():
    root = repo(SHARED)
    got = C.clumps(root, [
        candidate(451, os.path.join(root, "examples/_shared/line-kind.js")),
        candidate(455, "examples/skyscraper/component.js")])
    assert families(got) == [[[451], [455]]], got


def test_a_candidate_file_outside_the_repo_is_refused_not_guessed_at():
    root = repo(SHARED)
    refused = None
    try:
        got = C.resolve_closure(root, ["../elsewhere/x.js"])
    except C.ClosureError as exc:
        refused, got = str(exc), None
    assert refused is not None, got
    assert "outside the repo" in refused, refused


# --- What the scan reads, and what it refuses (round 1: C3, C5) -----------

def test_a_fenced_directive_in_a_doc_is_an_example_not_an_edge():
    # `references/closure.md` shows the repo's include line; so will any doc
    # explaining the grammar. A quoted example must not join that doc to the
    # snippet's closure.
    root = repo({"_shared/line-kind.js": "x\n",
                 "docs/guide.md": "example:\n\n```\n#include ../_shared/line-kind.js\n```\n"})
    got = C.resolve_closure(root, ["_shared/line-kind.js"])
    assert got == {"_shared/line-kind.js"}, got


def test_a_triple_backtick_in_source_does_not_hide_the_directives_after_it():
    # The other direction, and the expensive one: a ``` line in a source file
    # means nothing in particular, and reading it as a fence would drop a real
    # includer out of the closure.
    root = repo({"_shared/line-kind.js": "x\n",
                 "comp.js": "const doc = `\n```\n`;\n#include _shared/line-kind.js\n"})
    got = C.resolve_closure(root, ["_shared/line-kind.js"])
    assert "comp.js" in got, got


def test_an_indented_directive_in_a_doc_is_an_example_not_an_edge():
    # Codex on #999's PR: an indented block is a code block by the same
    # CommonMark rule `declaration_section` now applies, and the same doc
    # explaining the grammar is exactly as likely to show the include line
    # indented as fenced.
    root = repo({"_shared/line-kind.js": "x\n",
                 "docs/guide.md": "example:\n\n    #include ../_shared/line-kind.js\n"})
    got = C.resolve_closure(root, ["_shared/line-kind.js"])
    assert got == {"_shared/line-kind.js"}, got


def test_a_directory_that_cannot_be_read_is_refused_not_skipped():
    root = repo(SHARED)
    hidden = os.path.join(root, "examples/skyscraper")
    os.chmod(hidden, 0o000)
    try:
        refused = None
        try:
            got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
        except C.ClosureError as exc:
            refused, got = str(exc), None
        assert refused is not None, f"a dropped directory is a dropped includer: {got}"
        assert "cannot read" in refused, refused
    finally:
        os.chmod(hidden, 0o755)


def test_a_binary_file_is_not_scanned_for_directives():
    root = repo({"_shared/line-kind.js": "x\n"})
    with open(os.path.join(root, "build.bin"), "wb") as fh:
        # The directive is spelled exactly as a text file would spell it,
        # so the only thing keeping this file out of the closure is the
        # binary skip itself.
        fh.write(b"\x00\x01\n#include _shared/line-kind.js\n")
    got = C.resolve_closure(root, ["_shared/line-kind.js"])
    assert got == {"_shared/line-kind.js"}, got


def test_a_skipped_directory_holds_no_edges():
    root = repo({"_shared/line-kind.js": "x\n",
                 "node_modules/dep/comp.js": "#include ../../_shared/line-kind.js\n"})
    skipped = os.path.join(root, "node_modules")
    os.chmod(skipped, 0o000)
    try:
        got = C.resolve_closure(root, ["_shared/line-kind.js"])
        assert got == {"_shared/line-kind.js"}, got
    finally:
        os.chmod(skipped, 0o755)


# --- The declaration's edges (round 1: C4, C7, C8, S4) --------------------

def test_none_must_be_a_statement_not_the_first_word_of_prose():
    # "None of the docs are generated, but examples/ are" declares nothing
    # this grammar can read; reading it as a stated None clumps every
    # candidate alone and puts two workers in the same files.
    root = repo(SHARED,
                agents="## Include closure\n\n"
                       "None of the docs are generated, but examples/ are.\n")
    got = C.clumps(root, [candidate(1, "docs/notes.md")])
    assert got["mode"] == "subtree", got


def test_repo_root_paths_are_read_from_the_root_not_the_includer():
    # The two readings must disagree for this to witness anything, so the
    # includer sits in a subdirectory: file-relative would look for
    # `pages/parts/head.html`, which does not exist.
    root = repo({"pages/index.html": '{% include "parts/head.html" %}\n',
                 "parts/head.html": "<head>\n"},
                agents='## Include closure\n\n'
                       '- **Directive**: `{% include "<path>" %}`\n'
                       '- **Paths**: repo-root\n'
                       '- **Generator**: `make site`\n')
    got = C.resolve_closure(root, ["parts/head.html"])
    assert got == {"parts/head.html", "pages/index.html"}, got


def test_a_directive_whose_literals_are_regex_metacharacters_is_matched_literally():
    root = repo({"comp.js": "{{ include(shared/line-kind.js) }}\n",
                 "shared/line-kind.js": "x\n"},
                agents="## Include closure\n\n"
                       "- **Directive**: `{{ include(<path>) }}`\n"
                       "- **Paths**: repo-root\n"
                       "- **Generator**: `make examples`\n")
    got = C.resolve_closure(root, ["shared/line-kind.js"])
    assert got == {"shared/line-kind.js", "comp.js"}, got


def test_a_directive_with_no_path_slot_is_refused_by_name():
    root = repo(SHARED, agents="## Include closure\n\n"
                               "- **Directive**: `#include`\n"
                               "- **Generator**: `make examples`\n")
    refused = None
    try:
        got = C.clumps(root, [candidate(1, "docs/notes.md")])
    except C.ClosureError as exc:
        refused, got = str(exc), None
    assert refused is not None, got
    assert "<path>" in refused, refused


def test_a_candidate_touching_a_root_file_collides_with_everything():
    # Conservative means clumping too much: a change at the repo root is
    # exactly the one nobody can bound without a declaration.
    root = repo({"README.md": "x\n", "a/one.js": "x\n"}, agents=None)
    got = C.clumps(root, [candidate(1, "README.md"), candidate(2, "a/one.js")])
    assert numbers(got) == [[1, 2]], got


# --- A subtree clump reports no closure (round 1: P3) ---------------------

def test_a_subtree_clump_carries_no_closure_key():
    # There is no closure in this mode, and a `closure` key holding the
    # tickets' declared files would hand a consumer back the declared seams
    # this reader exists to stop trusting.
    root = repo({"a/one.js": "x\n"}, agents=None)
    got = C.clumps(root, [candidate(1, "a/one.js")])
    assert "closure" not in C.clump_list(got)[0], got
    assert C.clump_list(got)[0]["files"] == ["a/one.js"], got


def test_a_resolved_clump_carries_both_its_files_and_its_closure():
    root = repo(SHARED)
    got = C.clumps(root, [candidate(451, "examples/_shared/line-kind.js")])
    clump = C.clump_list(got)[0]
    assert clump["files"] == ["examples/_shared/line-kind.js"], clump
    assert "examples/thermo/component.js" in clump["closure"], clump


# --- The scan fails closed (Codex pass on PR #920: F1, F2) ---------------

def test_a_directive_past_the_old_megabyte_cutoff_is_still_an_edge():
    # `read_text` used to stop at 1 MB and report the closure as complete.
    # This repo tracks a 3.5 MB minified bundle, and a minified bundle is one
    # enormous line, so where a truncation lands has nothing to do with the
    # content. A missed edge is two workers in the same files.
    filler = "// pad\n" * 200_000  # ~1.4 MB, past the old cutoff
    root = repo({"_shared/line-kind.js": "x\n",
                 "bundle.js": filler + "#include _shared/line-kind.js\n"})
    got = C.resolve_closure(root, ["_shared/line-kind.js"])
    assert "bundle.js" in got, sorted(got)


def test_a_file_past_the_scan_limit_fails_the_resolve():
    # The limit is a memory ceiling, not a truncation point: past it the
    # closure is unresolved and says so.
    root = repo({"_shared/line-kind.js": "x\n", "huge.js": "y" * 5000})
    decl = C.declaration(root)
    refused = None
    try:
        got = C.include_edges(root, decl, limit=1000)
    except C.ClosureError as exc:
        refused, got = str(exc), None
    assert refused is not None, got
    assert "scan limit" in refused and "huge.js" in refused, refused


def test_gitignored_oversized_files_do_not_break_the_resolve():
    root = repo({**SHARED, ".gitignore": ".scratch/\n",
                 ".scratch/copycat-rsl/b14-solutions.txt": ""})
    huge = os.path.join(root, ".scratch/copycat-rsl/b14-solutions.txt")
    with open(huge, "wb") as fh:
        fh.truncate(C.SCAN_LIMIT + 1)
    got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    assert got == {"examples/_shared/line-kind.js",
                   "examples/skyscraper/component.js",
                   "examples/thermo/component.js"}, got

    os.unlink(os.path.join(root, ".gitignore"))
    refused = None
    try:
        got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    except C.ClosureError as exc:
        refused, got = str(exc), None
    assert refused is not None, got
    assert "scan limit" in refused, refused
    assert "b14-solutions.txt" in refused, refused


def test_tracked_and_untracked_includers_survive_ignore_rules():
    root = repo({"shared.js": "x\n", ".gitignore": ".scratch/\n",
                 ".scratch/tracked\ncomponent.js": "#include ../shared.js\n",
                 ".scratch/ignored.js": "#include ../shared.js\n",
                 "untracked café.js": "#include shared.js\n"})
    git(root, "add", "-f", "shared.js", ".scratch/tracked\ncomponent.js")
    got = C.resolve_closure(root, ["shared.js"])
    assert got == {"shared.js", ".scratch/tracked\ncomponent.js",
                   "untracked café.js"}, got


def test_a_tracked_file_matching_ignore_rules_still_has_a_scan_limit():
    root = repo({"shared.js": "x\n", ".gitignore": "huge.js\n",
                 "huge.js": "y" * 5000})
    git(root, "add", "-f", "huge.js")
    refused = None
    try:
        got = C.include_edges(root, C.declaration(root), limit=1000)
    except C.ClosureError as exc:
        refused, got = str(exc), None
    assert refused is not None, got
    assert "scan limit" in refused and "huge.js" in refused, refused


def test_a_failed_git_listing_is_not_an_empty_closure():
    root = repo(SHARED)
    with open(os.path.join(root, ".git/index"), "w") as fh:
        fh.write("broken index\n")
    refused = None
    try:
        got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    except C.ClosureError as exc:
        refused, got = str(exc), None
    assert refused is not None, got
    assert "git ls-files" in refused, refused


def fake_git_on_path(script):
    """A directory holding a `git` that runs `script`, and nothing else."""
    bin_dir = tempfile.mkdtemp(prefix="closure-fixture-")
    FIXTURES.append(bin_dir)
    path = os.path.join(bin_dir, "git")
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\n" + script + "\n")
    os.chmod(path, 0o755)
    return bin_dir


def resolve_with_path(root, path):
    """`(closure, refusal)` of resolving the shared file with `PATH` set to
    `path`: exactly one of the two is None."""
    try:
        with mock.patch.dict(os.environ, {"PATH": path}):
            return C.resolve_closure(root, ["examples/_shared/line-kind.js"]), None
    except C.ClosureError as exc:
        return None, str(exc)


def test_a_missing_git_is_not_an_empty_closure():
    root = repo(SHARED)
    got, refused = resolve_with_path(root, "/nonexistent")
    assert refused is not None, got
    assert "cannot read" in refused, refused


def test_a_git_that_fails_silently_is_not_an_empty_closure():
    # Exit status alone: no stderr for the other clause to catch.
    root = repo(SHARED)
    got, refused = resolve_with_path(root, fake_git_on_path("exit 1"))
    assert refused is not None, got
    assert "git ls-files" in refused, refused


def test_a_git_that_warns_on_stderr_but_exits_zero_still_lists_its_files():
    # A config warning is stderr on a good run; the exit status decides. The
    # fake warns, then runs the real git with the flags it was given.
    root = repo(SHARED)
    real = shutil.which("git")
    path = fake_git_on_path(f"echo 'warning: noisy config' >&2\nexec {real} \"$@\"")
    got, refused = resolve_with_path(root, path)
    assert refused is None, refused
    assert "examples/skyscraper/component.js" in got, got


def test_the_scan_pins_git_to_the_c_locale():
    # The unreadable-directory guard matches git's English warning text.
    root = repo(SHARED)
    got, refused = resolve_with_path(
        root, fake_git_on_path('[ "$LC_ALL" = C ] || exit 1\nexec ' + shutil.which("git") + ' "$@"'))
    assert refused is None, refused


def test_a_callers_git_environment_does_not_redirect_the_scan():
    # A hook or rebase exports GIT_DIR for its own repo; the scan is of `root`.
    other = repo({"unrelated.js": "x\n"})
    root = repo(SHARED)
    redirect = {"GIT_DIR": os.path.join(other, ".git"), "GIT_WORK_TREE": other}
    with mock.patch.dict(os.environ, redirect):
        got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    assert "examples/skyscraper/component.js" in got, got


def test_a_callers_git_config_environment_still_reaches_the_scan_1254():
    # #1209 C7: GIT_CONFIG_* repoints nothing, and stripping it drops settings
    # the scan needs (a `safe.directory` passed this way). An excludesFile
    # passed the same way shows it arrived.
    root = repo(SHARED)
    ignores = os.path.join(root, "..ignores")
    with open(ignores, "w") as fh:
        fh.write("component.js\n")
    config = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.excludesFile",
              "GIT_CONFIG_VALUE_0": ignores}
    with mock.patch.dict(os.environ, config):
        got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    assert "examples/skyscraper/component.js" not in got, got


def test_an_unreadable_gitignored_directory_does_not_break_the_resolve():
    root = repo({**SHARED, ".gitignore": ".scratch/\n",
                 ".scratch/notes.txt": "x\n"})
    ignored = os.path.join(root, ".scratch")
    os.chmod(ignored, 0o000)
    try:
        got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    finally:
        os.chmod(ignored, 0o755)
    assert "examples/skyscraper/component.js" in got, got


def test_an_unreadable_skipped_directory_does_not_break_the_resolve_1254():
    # #1209 P6: the .gitignore case above also passes a design that filters
    # git's list afterwards with no --exclude, because git never opens an
    # ignored directory. A SKIP_DIRS directory no .gitignore names is opened
    # unless the --exclude arguments keep git out of it.
    root = repo({**SHARED, "node_modules/pkg/index.js": "x\n"})
    skipped = os.path.join(root, "node_modules")
    os.chmod(skipped, 0o000)
    try:
        got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
    finally:
        os.chmod(skipped, 0o755)
    assert "examples/skyscraper/component.js" in got, got


def test_a_file_that_cannot_be_opened_is_not_a_file_with_no_includes():
    # `None` from read_text means "not text, so no edges here". A file that
    # could not be opened is "I cannot tell" — the same posture the module
    # already takes for a directory it cannot list.
    root = repo(SHARED)
    hidden = os.path.join(root, "examples/skyscraper/component.js")
    os.chmod(hidden, 0o000)
    try:
        refused = None
        try:
            got = C.resolve_closure(root, ["examples/_shared/line-kind.js"])
        except C.ClosureError as exc:
            refused, got = str(exc), None
        assert refused is not None, f"an unreadable includer was read as having none: {got}"
        assert "cannot read" in refused, refused
    finally:
        os.chmod(hidden, 0o644)


# --- Python imports as include edges (#1478) -------------------------------

PY_ROOT = ("## Include closure\n\n- **Directive**: `python imports`\n"
           "- **Paths**: repo-root\n- **Generator**: `none`\n")
PY_FILE = PY_ROOT.replace("repo-root", "relative to the including file")


def py_closure(files, target="codec.py", agents=PY_ROOT):
    return C.resolve_closure(repo(files, agents=agents), [target])


def test_the_directive_is_matched_whatever_its_case_and_spacing():
    text = "## Include closure\n- **Directive**: `Python   Imports`\n"
    got = C.resolve_closure(repo({"codec.py": "x\n", "a.py": "import codec\n"},
                                 agents=text), ["codec.py"])
    assert got == {"codec.py", "a.py"}, got


def test_each_import_form_is_an_edge_to_the_module_file():
    forms = {"a.py": "import codec\n",
             "b.py": "import codec as c\n",
             "c.py": "import os, codec\n",
             "d.py": "from codec import encode\n",
             "e.py": "def f():\n    import codec\n"}
    got = py_closure({"codec.py": "x = 1\n", **forms, "none.py": "import os\n"})
    assert got == {"codec.py", *forms}, got


def test_a_dotted_import_follows_the_path_and_a_package_is_init():
    files = {"pkg/__init__.py": "", "pkg/sub.py": "x = 1\n",
             "a.py": "import pkg.sub\n", "b.py": "from pkg import thing\n",
             "c.py": "from pkg.sub import y\n"}
    assert py_closure(files, "pkg/sub.py") == {"pkg/sub.py", "a.py", "c.py"}
    assert py_closure(files, "pkg/__init__.py") == {"pkg/__init__.py", "b.py"}


def test_a_from_import_of_a_submodule_is_an_edge_to_that_file():
    files = {"pkg/__init__.py": "", "pkg/sub.py": "x = 1\n",
             "a.py": "from pkg import sub\n"}
    assert py_closure(files, "pkg/sub.py") == {"pkg/sub.py", "a.py"}


def test_a_name_with_no_tracked_file_drops_out():
    # stdlib and third-party modules must not raise or invent an edge
    got = py_closure({"codec.py": "x\n", "a.py": "import json, numpy\nimport os.path\n"})
    assert got == {"codec.py"}, got


def test_a_relative_import_is_out_of_scope():
    got = py_closure({"codec.py": "x\n", "a.py": "from . import codec\n",
                       "b.py": "from .codec import x\n"})
    assert got == {"codec.py"}, got


def test_a_name_with_no_tracked_file_makes_no_edge():
    root = repo({"a.py": "import json\nimport numpy\n"}, agents=PY_ROOT)
    assert C.include_edges(root, C.declaration(root)) == {}


def test_a_valid_file_with_a_parse_warning_is_read_without_noise():
    import warnings
    root = repo({"codec.py": "x\n", "a.py": 'import codec\ns = "\\d"\n'},
                agents=PY_ROOT)
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("error")
        got = C.resolve_closure(root, ["codec.py"])
    assert got == {"codec.py", "a.py"} and not seen, (got, seen)


def test_a_python_file_that_is_not_text_fails_the_resolve_by_name():
    root = repo({"codec.py": "x\n", "nul.py": "import codec\0\n"},
                agents=PY_ROOT)
    try:
        C.resolve_closure(root, ["codec.py"])
    except C.ClosureError as exc:
        assert "nul.py" in str(exc), exc
    else:
        raise AssertionError("a non-text .py was read as importing nothing")


def test_an_import_in_a_string_or_comment_is_not_an_edge():
    src = '# import codec\ns = "import codec"\n'
    assert py_closure({"codec.py": "x\n", "a.py": src}) == {"codec.py"}


def test_paths_repo_root_resolves_from_the_root_not_the_includer():
    files = {"codec.py": "x\n", "puzzles/p/build.py": "import codec\n"}
    assert py_closure(files) == {"codec.py", "puzzles/p/build.py"}
    assert py_closure(files, agents=PY_FILE) == {"codec.py"}


def test_paths_file_relative_resolves_against_the_includers_directory():
    files = {"puzzles/p/helper.py": "x\n", "puzzles/p/build.py": "import helper\n"}
    got = py_closure(files, "puzzles/p/helper.py", agents=PY_FILE)
    assert got == {"puzzles/p/helper.py", "puzzles/p/build.py"}, got
    assert py_closure(files, "puzzles/p/helper.py") == {"puzzles/p/helper.py"}


def test_only_python_files_are_read_for_imports():
    got = py_closure({"codec.py": "x\n", "notes.md": "import codec\n"})
    assert got == {"codec.py"}, got


def test_a_python_file_that_does_not_parse_fails_the_resolve_by_name():
    root = repo({"codec.py": "x\n", "bad.py": "def (:\n"}, agents=PY_ROOT)
    try:
        C.resolve_closure(root, ["codec.py"])
    except C.ClosureError as exc:
        assert "bad.py" in str(exc), exc
    else:
        raise AssertionError("an unparseable includer was read as having no imports")


def test_python_imports_split_a_flat_repo_that_none_would_not():
    files = {"codec.py": "x\n", "toolkit.py": "y\n",
             "one.py": "import codec\n", "two.py": "from toolkit import y\n"}
    got = C.clumps(repo(files, agents=PY_ROOT), [candidate(1, "one.py"), candidate(2, "two.py")])
    assert len(got["families"]) == 2, got


# --- The fixtures do not outlive the run (Codex round 2 on PR #920: F2) ---

def test_a_fixture_repo_is_removed_even_after_its_permissions_are_taken_away():
    root = repo({"a/one.js": "x\n"})
    os.chmod(os.path.join(root, "a"), 0o000)
    assert os.path.exists(root), root
    left = clean_fixtures()
    assert left == [], left
    assert not os.path.exists(root), root


def test_the_suite_leaves_no_fixture_directory_behind():
    # The witness for `main`'s teardown, run as its own process with its own
    # TMPDIR so that what it leaves is countable. The child skips this test —
    # without the guard it would spawn a suite per suite, forever.
    if os.environ.get("CLOSURE_TEST_CHILD"):
        return
    own_tmp = tempfile.mkdtemp(prefix="closure-fixture-")
    FIXTURES.append(own_tmp)
    env = {**os.environ, "TMPDIR": own_tmp, "CLOSURE_TEST_CHILD": "1"}
    out = subprocess.run([sys.executable, __file__], capture_output=True,
                         text=True, env=env)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    strays = [n for n in os.listdir(own_tmp) if n.startswith("closure-fixture-")]
    assert strays == [], strays


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
