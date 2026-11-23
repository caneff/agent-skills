# all.sh: prose-check (reads the always-on Markdown: a Markdown-only change in a directory with no suites runs it)
"""The always-on budget gate: every session loads the global
CLAUDE.md plus its `@`-imports, and tests/check-always-on.py reports that
text's word count against its budget without failing on it (#2016: the count
includes files outside this repo) and fails when an import cannot be read or a
pointer line names a path that does not exist. Each case runs the checker's command line and reads its exit status
and output; the real-tree case is the gate itself, the rest are fixtures
that prove each failure is caught by its own assertion."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "tests" / "check-always-on.py"
BUDGET = int(re.search(r"^BUDGET = (\d+)", CHECKER.read_text(), re.M).group(1))
REAL = ROOT / "flow" / "claude" / "CLAUDE.md"


def run(claude_md: Path, root: Path = ROOT, home: str | None = None):
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = home
    p = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), str(claude_md)],
        capture_output=True, text=True, env=env)
    return p.returncode, p.stdout + p.stderr


def test_real_claude_md_reports_its_count_and_passes():
    # The count is a reported number (#2016): the real tree's dead pointers and
    # wording still fail here, its size never does, whatever the vault holds.
    code, out = run(REAL)
    print(out, end="")
    assert code == 0, out
    assert re.search(r"^always-on: total \d+ words", out, re.M), out


class Fixtures:
    def __init__(self, tmp):
        self.tmp = tmp
        self.home = tmp / "home"
        (self.home / "mem").mkdir(parents=True)
        (self.home / "mem" / "A.md").write_text("one two three\n")
        self.root = tmp / "repo"
        (self.root / "flow" / "claude").mkdir(parents=True)
        (self.root / "flow" / "claude" / "WORKFLOW.md").write_text("# w\n")

    def write(self, text: str) -> Path:
        f = self.root / "flow" / "claude" / "CLAUDE.md"
        f.write_text(text)
        return f

    def check(self, text: str):
        return run(self.write(text), self.root, str(self.home))


@pytest.fixture
def fx(tmp_path):
    return Fixtures(tmp_path)


def test_imports_are_counted(fx):
    code, out = fx.check("alpha beta\n@~/mem/A.md\n")
    assert code == 0, out
    # 3 words in CLAUDE.md (the import line is one) + 3 imported.
    assert "total 6 words" in out


def test_nested_import_is_counted(fx):
    (fx.home / "mem" / "A.md").write_text("one @~/mem/B.md\n")
    (fx.home / "mem" / "B.md").write_text("x y z w\n")
    code, out = fx.check("@~/mem/A.md\n")
    assert code == 0, out
    assert "total 7 words" in out


def test_missing_import_fails(fx):
    # An import that cannot be read must not count as zero words.
    code, out = fx.check("@~/mem/Gone.md\n")
    assert code != 0, out
    assert "import not found: ~/mem/Gone.md" in out


def test_dead_pointer_fails(fx):
    code, out = fx.check(
        "- Before you land work: read `~/.agents/skills/flow/claude/NOPE.md`.\n")
    assert code != 0, out
    assert "names a path that does not exist: ~/.agents/skills/flow/claude/NOPE.md" in out


def test_live_pointer_maps_into_the_checkout(fx):
    # ~/.agents/skills/ is this repo: a pointer resolves into the checkout
    # under test, so a doc a branch adds is found before it merges.
    code, out = fx.check(
        "- Before you land work: read `~/.agents/skills/flow/claude/WORKFLOW.md`.\n")
    assert code == 0, out


def test_wrapped_pointer_is_read_as_one_line(fx):
    code, out = fx.check(
        "- Before you land work:\n  read `~/.agents/skills/flow/claude/WORKFLOW.md`.\n")
    assert code == 0, out


def test_pointer_without_an_action_fails(fx):
    code, out = fx.check("Detail: `~/.agents/skills/flow/claude/WORKFLOW.md`.\n")
    assert code != 0, out
    assert "pointer line names no action" in out


def test_over_budget_is_reported_and_does_not_fail(fx):
    budget = BUDGET
    code, out = fx.check(" ".join(["word"] * (budget + 1)) + "\n")
    assert code == 0, out
    assert f"always-on: total {budget + 1} words, over its budget of {budget}" in out
    assert "FAIL" not in out


def test_over_budget_with_a_dead_pointer_still_fails_on_the_pointer(fx):
    budget = BUDGET
    code, out = fx.check(
        " ".join(["word"] * (budget + 1))
        + "\n- Before you land work: read `~/.agents/skills/flow/claude/NOPE.md`.\n")
    assert code != 0, out
    assert "names a path that does not exist" in out
    assert "over its budget of" in out


def test_summary_prints_one_line_and_never_a_fail_line(fx):
    # tests/all.sh prints this line on every run; a FAIL line at column 0 in its
    # output would read as a failed suite to the nightly backstop.
    f = fx.write("alpha\n- Before you land work: read `~/.agents/skills/flow/claude/NOPE.md`.\n@~/mem/Gone.md\n")
    p = subprocess.run([sys.executable, str(CHECKER), "--root", str(fx.root), "--summary", str(f)],
                       capture_output=True, text=True, env={**os.environ, "HOME": str(fx.home)})
    assert p.returncode == 0, p.stdout + p.stderr
    lines = p.stdout.splitlines()
    assert len(lines) == 1 and lines[0].startswith("always-on: total "), p.stdout
    assert "incomplete" in lines[0], p.stdout


def test_summary_exits_zero_over_budget(fx):
    f = fx.write(" ".join(["word"] * (BUDGET + 1)) + "\n")
    p = subprocess.run([sys.executable, str(CHECKER), "--root", str(fx.root), "--summary", str(f)],
                       capture_output=True, text=True, env={**os.environ, "HOME": str(fx.home)})
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.strip() == f"always-on: total {BUDGET + 1} words, over its budget of {BUDGET}"
