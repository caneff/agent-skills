"""The backstop imports from drain/, implement/ and implement-spec/, and a
change confined to one of them must select `backstop/`'s suites under
`tests/all.sh --changed` (#1592): `tests/suite-edges.py` has to see each
edge in `backstop/backstop.py`. It lives under `tests/` so it runs on every
narrowed run, whichever side of the edge changed.
"""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("touched", ["drain", "implement", "implement-spec"])
def test_a_change_to_a_backstop_import_selects_the_backstop(touched):
    out = subprocess.run(["python3", os.path.join(ROOT, "tests", "suite-edges.py"), touched], cwd=ROOT,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "backstop" in out.stdout.split(), out.stdout
