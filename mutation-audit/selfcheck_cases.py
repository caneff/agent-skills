"""Fixture-driven named checks for mutation-audit (#556), run by the harness
selfcheck runner (all-audits/harness/run_selfchecks.py). Split out of
audit.py's old single `_selfcheck` function so a failure names which
behavior broke; audit.py's parser module no longer imports contextlib, io,
shutil, or tempfile — those live only here now.
"""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import audit  # noqa: E402


def check_parsing():
    sample = "\n".join(
        [
            "    sample.x_is_adult__mutmut_1: killed",
            "    sample.x_is_adult__mutmut_2: killed",
            "    sample.x_clamp__mutmut_1: survived",
            "    sample.x_clamp__mutmut_2: survived",
            "    sample.x_scale__mutmut_1: no tests",
        ]
    )
    rows = audit.parse_mutmut_results(sample)
    assert len(rows) == 3, rows

    assert rows[0]["file"] == "sample.py"
    assert rows[0]["line"] is None
    assert rows[0]["bucket"] == "rewrite"
    assert rows[0]["category"] == "surviving-mutant"
    assert rows[0]["extra"]["mutant"] == "sample.x_clamp__mutmut_1"
    assert rows[0]["extra"]["killed"] is False
    assert rows[0]["extra"]["survived"] is True
    assert rows[0]["extra"]["killed_count"] == 2
    assert rows[0]["extra"]["survived_count"] == 2
    assert rows[0]["extra"]["no_coverage_count"] == 1
    assert rows[0]["failure"] == ""

    assert rows[1]["extra"]["mutant"] == "sample.x_clamp__mutmut_2"

    # `no tests` is mutmut's own marker that no test reaches the mutant —
    # a no-coverage survivor, distinct from a covered-but-under-asserted one.
    nc = rows[2]
    assert nc["bucket"] == "no-coverage", nc
    assert nc["extra"]["mutant"] == "sample.x_scale__mutmut_1"
    assert nc["extra"]["survived"] is False
    assert nc["extra"]["no_coverage_count"] == 1
    assert nc["failure"] == ""

    no_survivors = audit.parse_mutmut_results("    sample.x_is_adult__mutmut_1: killed")
    assert no_survivors == []


def check_candidate_selection():
    paths = [
        "pkg/widget.py",
        "pkg/test_widget.py",
        "pkg/helper.py",  # no sibling test -> not a candidate
        "pkg/__init__.py",
        "pkg/gadget.py",
        "pkg/gadget_test.py",
        "pkg/fixtures/sample.py",  # fixture dir -> skipped
        "pkg/fixtures/test_sample.py",
        "vendor/lib/thing.py",
        "vendor/lib/test_thing.py",
        "pkg/test_widget_orphan.py",  # a test file itself -> not a candidate
    ]
    candidates = audit.suggest_candidates(paths)
    assert candidates == ["pkg/gadget.py", "pkg/widget.py"], candidates

    assert audit.suggest_candidates([]) == []
    assert audit.suggest_candidates(["only.py"]) == []  # no sibling test -> no candidates, not an error

    # no_test_modules is the strict inverse of suggest_candidates' sibling
    # filter: the same worthy-module set, kept only when NO sibling test
    # exists. widget/gadget have tests; helper is worthy but testless; the
    # rest (init, fixture, vendor, test files) aren't worthy modules at all.
    assert audit.no_test_modules(paths) == ["pkg/helper.py"], audit.no_test_modules(paths)
    assert audit.no_test_modules([]) == []
    assert audit.no_test_modules(["only.py"]) == ["only.py"]  # worthy, no sibling test
    assert audit.no_test_modules(["pkg/test_only.py"]) == []  # a test file is not worthy
    # The two partition the worthy universe: no module is in both.
    assert not (set(audit.suggest_candidates(paths, limit=None)) & set(audit.no_test_modules(paths)))

    limited = audit.suggest_candidates(paths, limit=1)
    assert limited == ["pkg/gadget.py"], limited


def check_cli_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_dir = os.path.join(tmpdir, "pkg")
        os.mkdir(pkg_dir)
        pair_count = 7
        for i in range(pair_count):
            with open(os.path.join(pkg_dir, f"mod_{i}.py"), "w", encoding="utf-8") as f:
                f.write("# module\n")
            with open(os.path.join(pkg_dir, f"test_mod_{i}.py"), "w", encoding="utf-8") as f:
                f.write("# test\n")
        # Two worthy modules with no sibling test — the no-test case.
        lonely_count = 2
        for i in range(lonely_count):
            with open(os.path.join(pkg_dir, f"lonely_{i}.py"), "w", encoding="utf-8") as f:
                f.write("# module, no test\n")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            audit.main(["audit.py", "--suggest", tmpdir])
        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        printed = [json.loads(line)["candidate"] for line in lines]
        assert len(printed) == pair_count, printed  # --suggest must not cap output (#395)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            audit.main(["audit.py", "--no-tests", tmpdir])
        report = json.loads(buf.getvalue())
        assert report["no_tests"] == ["pkg/lonely_0.py", "pkg/lonely_1.py"], report
        # total = worthy source modules = tested pairs + the testless ones.
        assert report["total"] == pair_count + lonely_count, report
