"""The backstop imports from common/, implement/ and implement-spec/, and a
change to the file it imports from one of them must select `backstop/`'s suites
under `tests/all.sh --changed`: `tests/suite-edges.py` has to see each edge in
`backstop/backstop.py`. It lives under `tests/` so it runs on every narrowed
run, whichever side of the edge changed.
"""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def suite_dirs():
    out = subprocess.run(["git", "ls-files", "*.test.sh", "*_test.py", "*Cargo.toml", "*/.claude-plugin/plugin.json"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return " ".join(sorted({p.split("/")[0] for p in out if "/" in p}))


@pytest.mark.parametrize("touched", ["common/shellcmd.py", "implement/selector_check.py", "implement-spec/closing_ticket.py"])
def test_a_change_to_a_file_the_backstop_imports_selects_the_backstop(touched):
    out = subprocess.run(["python3", os.path.join(ROOT, "tests", "suite-edges.py"), "--select", "--suite-dirs", suite_dirs()],
                         cwd=ROOT, input=touched, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    verdict, _, dirs = out.stdout.rstrip("\n").partition("\t")
    assert verdict == "dirs", out.stdout
    assert "backstop" in dirs.split(), out.stdout
