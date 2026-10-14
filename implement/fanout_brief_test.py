"""fanout-brief.py (#1550): the one source of a parallel sub-worker's brief.
Seam: the CLI, with HOME pointed at a temp dir so no render writes the real
review cache. Each case asserts the line it is about, so a render that fails
for another reason does not pass for the one under test (`AGENTS.md` §
Recurring defect classes, class 3).
"""
import os
import re
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "fanout-brief.py")
TEST_COMMAND = "python3 -m pytest implement/foo_test.py"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path / "home" / ".cache" / "agent-reviews"


@pytest.fixture
def wt(tmp_path):
    path = tmp_path / "wt"
    path.mkdir()
    return str(path)


def run(wt, *assigns, worker="alpha", ticket="1550", test_command=TEST_COMMAND):
    args = ["python3", RENDER, "--repo", "skills", "--worktree", wt, "--ticket", ticket,
            "--for", worker, "--test-command", test_command]
    for a in assigns:
        args += ["--assign", a]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def brief_at(line):
    path = re.search(r"(/\S+\.md)", line)
    assert path, f"the dispatch line names no brief path: {line!r}"
    with open(path.group(1)) as fh:
        return fh.read(), path.group(1)


def test_a_brief_lists_own_files_marks_others_off_limits_and_carries_test_and_mutation_rule(wt):
    code, out, err = run(wt, "alpha=a.py,b.py", "beta=c.py")
    assert code == 0, err
    text, _ = brief_at(out)
    mine = re.search(r"^Your files:(.*?)(?=^## |\Z)", text, re.M | re.S).group(1)
    assert "a.py" in mine and "b.py" in mine and "c.py" not in mine, text
    off = re.search(r"^## Off limits[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S).group(1)
    assert "c.py" in off and "a.py" not in off, text
    assert TEST_COMMAND in text, text
    assert "scratch copy" in text and "never mutate the live file" in text.lower(), text


def test_the_no_git_write_and_no_subagent_rules_are_stated(wt):
    _, out, _ = run(wt, "alpha=a.py", "beta=c.py")
    text, _ = brief_at(out)
    assert "no git write" in text.lower() and "no nested subagent" in text.lower(), text


def test_two_workers_sharing_a_file_is_refused_and_nothing_is_written(wt, home):
    code, out, err = run(wt, "alpha=a.py,b.py", "beta=b.py")
    assert code == 2 and out == "", (code, out)
    assert "b.py" in err and "alpha" in err and "beta" in err, err
    assert not home.exists() or not list(home.rglob("*.md")), list(home.rglob("*"))


def test_a_worker_with_no_files_is_refused(wt):
    code, out, err = run(wt, "alpha=a.py", "beta=")
    assert code == 2 and out == "", (code, out)
    assert "beta" in err and "no files" in err, err


def test_the_worker_must_be_one_of_the_assigned(wt):
    code, out, err = run(wt, "alpha=a.py", worker="gamma")
    assert code == 2 and out == "", (code, out)
    assert "gamma" in err, err


def test_a_second_render_for_the_same_ticket_and_worker_does_not_overwrite_the_first(wt):
    _, first, _ = run(wt, "alpha=a.py", "beta=c.py")
    _, second, _ = run(wt, "alpha=a.py,z.py", "beta=c.py")
    t1, p1 = brief_at(first)
    t2, p2 = brief_at(second)
    assert p1 != p2, (p1, p2)
    assert "z.py" not in open(p1).read() and "z.py" in t2
