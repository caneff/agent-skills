"""No tracked file says the retired skill's name (spec #1634, ruling 3).

# all.sh: repo-wide (scans every tracked file)

The name is built from two halves so this file does not carry it. The scan
reads file contents and paths, case-insensitively, over `git ls-files`.
Exempt: the dated records (`docs/research`, `docs/adr`, the friction log) and
the landing script, which still names what it moves; its removal ticket
removes that last exemption.
"""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD = b"burn" + b"down"
EXEMPT_DIRS = ("docs/research/", "docs/adr/")
EXEMPT_FILES = ("docs/agents/friction-log.md", "implement-spec/retire_landing.py")


def offenders(root):
    """Tracked paths under `root` that carry the word in name or content and are not exempt."""
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True,
                            capture_output=True).stdout.split(b"\0")
    found = []
    for raw in filter(None, listed):
        path = os.fsdecode(raw)
        if path in EXEMPT_FILES or path.startswith(EXEMPT_DIRS):
            continue
        full = os.path.join(root, path)
        if WORD in raw.lower():
            found.append(path)
        elif os.path.isfile(full) and not os.path.islink(full):
            with open(full, "rb") as fh:
                if WORD in fh.read().lower():
                    found.append(path)
    return found


def test_no_live_file_names_the_retired_skill():
    bad = offenders(ROOT)
    assert bad == [], f"the retired skill's name is back in tracked files: {bad}"


@pytest.fixture
def repo(tmp_path):
    def make(files):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        for rel, text in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        return str(tmp_path)
    return make


def test_the_word_in_a_live_file_is_found_in_any_case(repo):
    root = repo({"a/SKILL.md": "see " + WORD.decode().title() + "\n", "b.md": "clean\n"})
    assert offenders(root) == ["a/SKILL.md"]


def test_the_word_in_a_tracked_path_is_found(repo):
    root = repo({"x/" + WORD.decode() + ".md": "clean\n"})
    assert offenders(root) == ["x/" + WORD.decode() + ".md"]


def test_exempt_paths_pass_and_their_removal_leaves_the_rest_green(repo):
    w = WORD.decode()
    files = {p: w + "\n" for p in ("docs/research/r.md", "docs/adr/0001.md",
                                    "docs/agents/friction-log.md", "implement-spec/retire_landing.py")}
    root = repo(files)
    assert offenders(root) == []
    subprocess.run(["git", "rm", "-q", "-f", "implement-spec/retire_landing.py"], cwd=root, check=True)
    assert offenders(root) == []


def test_an_exempt_name_elsewhere_is_not_exempt(repo):
    root = repo({"other/retire_landing.py": WORD.decode() + "\n"})
    assert offenders(root) == ["other/retire_landing.py"]
