"""Tests for auditlib (#1744; were `auditlib.py`'s `_selfcheck`).

The excluded-dirs drift check had never run before this file: `auditlib.py`
carried no `audit.py` name, so `tests/all.sh` never found its `--selfcheck`.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import auditlib  # noqa: E402


def test_finding_failure_defaults_empty():
    assert auditlib.finding("cut", "a.py", 1, "x", "s")["failure"] == ""


def test_finding_extra_is_kept():
    assert auditlib.finding("cut", "a.py", 1, "x", "s", foo=1)["extra"] == {"foo": 1}


def test_walk_source_prunes_excluded_dirs(tmp_path):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "vendor" / "skip.py").write_text("")
    (tmp_path / "pkg" / "keep.py").write_text("")
    assert auditlib.walk_source(str(tmp_path)) == ["pkg/keep.py"]


def test_excluded_dirs_json_mirror_is_not_stale():
    mirror = os.path.join(os.path.dirname(__file__), "excluded-dirs.json")
    with open(mirror, encoding="utf-8") as f:
        assert set(json.load(f)) == auditlib.EXCLUDED_DIRS, (
            "excluded-dirs.json is stale: re-run "
            "`python3 auditlib.py --write-json-mirror excluded-dirs.json`")


def test_run_cli_has_no_selfcheck_flag(tmp_path, capsys):
    """`--selfcheck` is an ordinary file argument now: it is read, not special-cased."""
    with pytest.raises(FileNotFoundError):
        auditlib.run_cli(["audit.py", "--selfcheck"], lambda text: [])


def test_run_cli_prints_one_json_line_per_row(tmp_path, capsys):
    path = tmp_path / "in.txt"
    path.write_text("abc", encoding="utf-8")
    auditlib.run_cli(["audit.py", str(path)], lambda text: [{"n": len(text)}, {"n": 0}])
    assert capsys.readouterr().out.splitlines() == ['{"n": 3}', '{"n": 0}']


def _git_repo(path, *files):
    """`git init` `path` and track `files` (created empty)."""
    env = auditlib.scrubbed_env()
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True, env=env)
    for f in files:
        (path / f).parent.mkdir(parents=True, exist_ok=True)
        (path / f).write_text("")
    if files:
        subprocess.run(["git", "-C", str(path), "add", *files], check=True, env=env)


def test_not_applicable_names_the_language_found(tmp_path):
    _git_repo(tmp_path, "src/a.js", "b.mjs")
    assert auditlib.not_applicable(str(tmp_path)) == "JavaScript"


def test_not_applicable_is_none_with_python_source(tmp_path):
    _git_repo(tmp_path, "a.js", "b.py")
    assert auditlib.not_applicable(str(tmp_path)) is None


def test_not_applicable_ignores_vendored_python_and_unknown_languages(tmp_path):
    _git_repo(tmp_path, "node_modules/dep.py", "a.js")
    assert auditlib.not_applicable(str(tmp_path)) == "JavaScript"
    empty = tmp_path / "empty"
    empty.mkdir()
    _git_repo(empty, "notes.txt")
    assert auditlib.not_applicable(str(empty)) is None, "no recognised language: nothing to call not applicable"


def test_not_applicable_reads_tracked_files_only(tmp_path):
    """#1751 says "no tracked Python source": an untracked stray `.py` does not
    make a JavaScript repo applicable, and untracked `.js` (a report folder's
    assets) does not make a Python-less repo read as JavaScript."""
    _git_repo(tmp_path, "app.js")
    (tmp_path / "stray.py").write_text("")
    assert auditlib.not_applicable(str(tmp_path)) == "JavaScript"
    bare = tmp_path / "bare"
    bare.mkdir()
    _git_repo(bare, "README.md")
    (bare / "out").mkdir()
    (bare / "out" / "base.js").write_text("")
    assert auditlib.not_applicable(str(bare)) is None


def test_not_applicable_walks_a_folder_outside_git(tmp_path):
    (tmp_path / "a.js").write_text("")
    assert auditlib.not_applicable(str(tmp_path)) == "JavaScript"


def _applicable_cli(path):
    return subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "auditlib.py"), "--applicable", str(path)],
                          capture_output=True, text=True)


def test_applicable_cli_exits_3_naming_the_language(tmp_path):
    """The one step-0 command of the Python-only audits."""
    _git_repo(tmp_path, "index.js")
    r = _applicable_cli(tmp_path)
    assert (r.returncode, r.stdout.strip()) == (3, "not applicable: JavaScript"), r.stdout + r.stderr


def test_applicable_cli_exits_0_with_python_source(tmp_path):
    _git_repo(tmp_path, "a.py")
    r = _applicable_cli(tmp_path)
    assert (r.returncode, r.stdout.strip()) == (0, "applicable"), r.stdout + r.stderr


def test_run_cli_takes_applicable_as_a_file_argument(tmp_path):
    """Only the Python-only audits answer "not applicable", through
    auditlib.py's own main; run_cli serves every parser, JS-capable ones too."""
    with pytest.raises(FileNotFoundError):
        auditlib.run_cli(["audit.py", "--applicable", str(tmp_path / "nowhere")], lambda text: [], nargs=2)
