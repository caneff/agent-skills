#!/usr/bin/env python3
"""Tests for the include-closure clumper (#891). Two seams, both named on the
ticket: `resolve_closure(root, files)` — the set of files a change to `files`
regenerates — and `clumps(root, candidates)` — the connected components of
the collision graph over those closures, plus the mode announcement the run's
opening report carries.

Every case is a fixture repo written to a temp directory: a declaration in
`AGENTS.md` and a few files that include each other. Nothing here runs a
generator, because nothing in the resolver may.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import closure as C  # noqa: E402

CLOSURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "closure.py")

DECLARED = """# Fixture repo

## Include closure

- **Directive**: `#include <path>`
- **Generator**: `make examples`
"""


def repo(files, agents=DECLARED):
    """A fixture repo on disk: `{path: text}` plus an `AGENTS.md`, or no
    `AGENTS.md` at all when `agents` is None."""
    root = tempfile.mkdtemp(prefix="closure-fixture-")
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
    return [c["tickets"] for c in clumping["clumps"]]


def test_two_candidates_sharing_an_include_are_one_clump():
    # #781's costliest finding, as a fixture: #451 targets the shared
    # snippet, #455 targets the skyscraper component, and nothing in either
    # ticket names the other's file.
    root = repo(SHARED)
    got = C.clumps(root, [candidate(451, "examples/_shared/line-kind.js"),
                          candidate(455, "examples/skyscraper/component.js")])
    assert numbers(got) == [[451, 455]], got


def test_a_candidate_colliding_with_nothing_clumps_alone():
    root = repo(SHARED)
    got = C.clumps(root, [candidate(451, "examples/_shared/line-kind.js"),
                          candidate(501, "docs/notes.md")])
    assert numbers(got) == [[451], [501]], got


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
        "directory subtree are one clump"), got


def test_a_declared_grammar_is_announced_with_its_directive_and_generator():
    root = repo(SHARED)
    got = C.clumps(root, [candidate(1, "docs/notes.md")])
    assert got["mode"] == "closure", got
    assert got["announcement"] == (
        "clumping: include closure, from AGENTS.md "
        "(directive `#include <path>`, generator `make examples`)"), got


def test_a_declared_none_is_announced_as_its_own_third_answer():
    # Silence and a stated None both clump each candidate on its own files
    # here; the report must still tell them apart, because silence is a gap
    # someone should close and None is the truth about the repo.
    root = repo(SHARED, agents="## Include closure\n\nNone \u2014 nothing is generated.\n")
    got = C.clumps(root, [candidate(1, "docs/notes.md")])
    assert got["mode"] == "no-include-graph", got
    assert got["announcement"] == (
        "clumping: include closure, from AGENTS.md (declared None: this repo "
        "has no include graph, so each candidate closes over its own files)"), got


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
    # The resolver reports the generator command and never runs it: one
    # regeneration per candidate per wave is correct and far too expensive.
    with open(C.__file__) as fh:
        source = fh.read()
    for forbidden in ("subprocess", "os.system", "os.popen", "os.exec", "popen"):
        assert forbidden not in source, forbidden


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
    assert "clump #451, #455" in out.stdout, out.stdout
    assert "clump #501" in out.stdout, out.stdout


def test_a_malformed_candidate_is_one_stderr_line_not_a_traceback():
    root = repo(SHARED)
    out = subprocess.run([sys.executable, CLOSURE, root, "not-a-candidate"],
                         capture_output=True, text=True)
    assert out.returncode == 1, out
    assert out.stderr.startswith("closure.py: "), out.stderr
    assert "Traceback" not in out.stderr, out.stderr


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
