"""The edge finder behind `tests/all.sh --changed` (#1955): what is an edge,
which file it reaches, and what each changed path selects. The shell-side
fail-closed cases (no answer, no verdict) are in changed.test.sh."""
import importlib.util
import os

import pytest

_spec = importlib.util.spec_from_file_location("suite_edges", os.path.join(os.path.dirname(__file__), "suite-edges.py"))
se = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(se)


def scan_tree(tmp_path, monkeypatch, files):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    monkeypatch.chdir(tmp_path)
    tracked = sorted(files)
    return tracked, *se.scan(tracked)


def targets(edges, src):
    return sorted(edges.get(src, {}))


def test_a_comment_a_docstring_and_a_commit_message_name_nothing(tmp_path, monkeypatch):
    tracked, edges, _ = scan_tree(tmp_path, monkeypatch, {
        "a/x.txt": "x",
        "b/c.py": '# sys.path "../a/x.txt"\n',
        "b/d.py": '"""sys.path "../a/x.txt" """\nx = 1\n',
        "b/e.py": 'git("commit", "-qm", "sys.path ../a/x.txt")\n',
        "b/f.sh": 'echo hi # source ../a/x.txt\n',
    })
    assert edges == {}


def test_a_reference_reaches_the_named_file_not_the_directory(tmp_path, monkeypatch):
    tracked, edges, _ = scan_tree(tmp_path, monkeypatch, {
        "a/x.txt": "x", "a/y.txt": "y",
        "b/c.py": 'P = os.path.join(HERE, "..", "a", "x.txt")\n',
        "b/d.sh": 'cat "$here/../a/y.txt"\n',
    })
    assert targets(edges, "b/c.py") == ["a/x.txt"]
    assert targets(edges, "b/d.sh") == ["a/y.txt"]


def test_a_bare_directory_reaches_every_file_in_it(tmp_path, monkeypatch):
    _, edges, _ = scan_tree(tmp_path, monkeypatch, {
        "a/x.txt": "x", "a/y.txt": "y", "b/c.py": 'P = os.path.join(HERE, "..", "a")\n',
    })
    assert targets(edges, "b/c.py") == ["a/x.txt", "a/y.txt"]


def test_a_path_that_names_nothing_tracked_is_no_edge(tmp_path, monkeypatch):
    _, edges, _ = scan_tree(tmp_path, monkeypatch, {
        "a/x.txt": "x", "b/c.py": 'P = os.path.join(HERE, "..", "a", "made-at-runtime.txt")\n',
    })
    assert edges == {}


def test_a_sys_path_directory_is_reached_through_what_is_imported(tmp_path, monkeypatch):
    _, edges, _ = scan_tree(tmp_path, monkeypatch, {
        "common/used.py": "", "common/unused.py": "",
        "b/c.py": 'import used\nsys.path.insert(0, os.path.join(HERE, "..", "common"))\n',
    })
    assert targets(edges, "b/c.py") == ["common/used.py"]


def dirs_for(tmp_path, monkeypatch, files, changed, suite_dirs):
    tracked, edges, reach = scan_tree(tmp_path, monkeypatch, files)
    return se.select(changed, set(suite_dirs), tracked, edges, reach)


CHAIN = {
    "a/x.txt": "x", "a/other.txt": "o",
    "b/lib.py": 'P = os.path.join(HERE, "..", "a", "x.txt")\n',
    "d/lib.py": 'P = os.path.join(HERE, "..", "b", "lib.py")\n',
    "c/note.md": "n",
}


def test_edges_chain_by_file(tmp_path, monkeypatch):
    verdict, dirs, _ = dirs_for(tmp_path, monkeypatch, CHAIN, ["a/x.txt"], "abd")
    assert (verdict, dirs) == ("dirs", ["a", "b", "d"])


def test_a_change_to_another_file_of_the_directory_does_not_chain(tmp_path, monkeypatch):
    verdict, dirs, _ = dirs_for(tmp_path, monkeypatch, CHAIN, ["a/other.txt"], "abd")
    assert (verdict, dirs) == ("dirs", ["a"])


@pytest.mark.parametrize("changed, why", [
    (["tests/all.sh"], "tests/all.sh itself changed"),
    (["tests/suite-edges.py"], "tests/suite-edges.py itself changed"),
    (["README.md"], "repo root"),
    (["a/pic.png"], "does not know"),
    (["a/Makefile"], "does not know"),
    (["c/tool.py"], "holds no suite"),
])
def test_what_the_selector_cannot_place_runs_the_full_seam(tmp_path, monkeypatch, changed, why):
    verdict, _, notes = dirs_for(tmp_path, monkeypatch, CHAIN, changed, "abd")
    assert verdict == "full"
    assert why in notes[0]


def test_markdown_only_in_a_directory_with_no_suites_is_prose_mode(tmp_path, monkeypatch):
    assert dirs_for(tmp_path, monkeypatch, CHAIN, ["c/note.md"], "abd")[:2] == ("prose", [])


def test_markdown_beside_a_suite_directory_change_is_an_ordinary_run(tmp_path, monkeypatch):
    assert dirs_for(tmp_path, monkeypatch, CHAIN, ["c/note.md", "a/other.txt"], "abd")[:2] == ("dirs", ["a"])


def test_an_empty_diff_is_an_empty_dirs_verdict_not_a_missing_one(tmp_path, monkeypatch):
    assert dirs_for(tmp_path, monkeypatch, CHAIN, [], "abd")[:2] == ("dirs", [])


def test_a_deleted_path_runs_the_files_that_reach_its_directory(tmp_path, monkeypatch):
    verdict, dirs, _ = dirs_for(tmp_path, monkeypatch, CHAIN, ["a/gone.txt"], "abd")
    assert (verdict, dirs) == ("dirs", ["a", "b", "d"])
