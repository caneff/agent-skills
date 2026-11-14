"""Tests for mutation-audit's parsers, candidate selection and `audit.py` CLI.

One pytest function per behaviour, so a failure names the behaviour that broke
(#1744). These were `audit.py`'s `_selfcheck` checks.
"""
import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(__file__))
from audit import (  # noqa: E402
    Inconclusive,
    main,
    no_test_modules,
    parse_mutmut_results,
    parse_stryker_report,
    suggest_candidates,
)

AUDIT_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit.py")


def test_parsing():
    sample = "\n".join(
        [
            "    sample.x_is_adult__mutmut_1: killed",
            "    sample.x_is_adult__mutmut_2: killed",
            "    sample.x_clamp__mutmut_1: survived",
            "    sample.x_clamp__mutmut_2: survived",
            "    sample.x_scale__mutmut_1: no tests",
        ]
    )
    rows = parse_mutmut_results(sample)
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

    no_survivors = parse_mutmut_results("    sample.x_is_adult__mutmut_1: killed")
    assert no_survivors == []


def test_candidate_selection():
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
    candidates = suggest_candidates(paths)
    assert candidates == ["pkg/gadget.py", "pkg/widget.py"], candidates

    assert suggest_candidates([]) == []
    assert suggest_candidates(["only.py"]) == []  # no sibling test -> no candidates, not an error

    # no_test_modules is the strict inverse of suggest_candidates' sibling
    # filter: the same worthy-module set, kept only when NO sibling test
    # exists. widget/gadget have tests; helper is worthy but testless; the
    # rest (init, fixture, vendor, test files) aren't worthy modules at all.
    assert no_test_modules(paths) == ["pkg/helper.py"], no_test_modules(paths)
    assert no_test_modules([]) == []
    assert no_test_modules(["only.py"]) == ["only.py"]  # worthy, no sibling test
    assert no_test_modules(["pkg/test_only.py"]) == []  # a test file is not worthy
    # The two partition the worthy universe: no module is in both.
    assert not (set(suggest_candidates(paths)) & set(no_test_modules(paths)))


def test_src_tests_layout():
    paths = ["src/kit/cpsat.py", "tests/test_cpsat.py",
             "src/kit/sub/deep.py", "tests/kit/sub/test_deep.py",
             "src/kit/flatsuffix.py", "tests/flatsuffix_test.py",
             "src/kit/mirsuffix.py", "tests/kit/mirsuffix_test.py",
             "nosrc/sub/inner.py", "tests/nosrc/sub/test_inner.py",
             "src/kit/lone.py",
             "src/kit/__init__.py", "tests/test_other.py",
             "flat/mod.py", "tests/test_mod.py"]
    assert suggest_candidates(paths) == ["flat/mod.py", "nosrc/sub/inner.py", "src/kit/cpsat.py", "src/kit/flatsuffix.py",
                                         "src/kit/mirsuffix.py", "src/kit/sub/deep.py"], suggest_candidates(paths)
    assert no_test_modules(paths) == ["src/kit/lone.py"], no_test_modules(paths)


def test_cli_path():
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
            main(["audit.py", "--suggest", tmpdir])
        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        printed = [json.loads(line)["candidate"] for line in lines]
        assert len(printed) == pair_count, printed  # --suggest must not cap output (#395)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["audit.py", "--no-tests", tmpdir])
        report = json.loads(buf.getvalue())
        assert report["no_tests"] == ["pkg/lonely_0.py", "pkg/lonely_1.py"], report
        # total = worthy source modules = tested pairs + the testless ones.
        assert report["total"] == pair_count + lonely_count, report


def _run_cli(argv, path_dirs, cwd=None, extra_env=None):
    """Run audit.py as a subprocess with PATH limited to `path_dirs` plus the
    interpreter's own dir; returns (returncode, stdout, stderr)."""
    # PATH is exactly `path_dirs`: the interpreter is run by absolute path, and
    # the stub uses only shell builtins, so a real uvx cannot leak in (#962).
    env = dict(os.environ, PATH=os.pathsep.join(path_dirs), **(extra_env or {}))
    r = subprocess.run([sys.executable, AUDIT_PY, *argv],
                       capture_output=True, text=True, env=env, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def _stub_uvx(dirpath, run_exit, results_text, results_exit=0, hang=False):
    """A stand-in `uvx` using shell builtins only. An invocation it does not
    model exits 99, so a changed command line cannot pass as "mutmut reported
    nothing"."""
    stub = os.path.join(dirpath, "uvx")
    body = "while :; do read -t 1 _ 2>/dev/null; done" if hang else f'echo "stub run output"; exit {run_exit}'
    with open(stub, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n"
                'case "$*" in\n'
                f"  *\"mutmut run\"*) {body};;\n"
                f"  *\"mutmut results --all true\"*) printf '%s\\n' '{results_text}'; exit {results_exit};;\n"
                "  *) echo \"stub uvx: unmodelled call: $*\" >&2; exit 99;;\n"
                "esac\n")
    os.chmod(stub, 0o755)


def test_inconclusive_when_mutmut_cannot_run():
    """A box without mutmut must say so, exit 3, and print no findings —
    never the empty output of a clean run (#962)."""
    with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as cwd:
        code, out, err = _run_cli(["--run", "sample.py"], [empty], cwd)
        assert code == 3, (code, out, err)
        assert "INCONCLUSIVE" in err and "uvx" in err, err
        assert out == "", out

    # uvx present but `mutmut run` fails (the subprocess-test abort of #962's comment).
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cwd:
        _stub_uvx(d, 1, "")
        code, out, err = _run_cli(["--run", "sample.py"], [d], cwd)
        assert code == 3, (code, out, err)
        assert "INCONCLUSIVE" in err and "mutmut run failed" in err, err
        assert out == "", out

    # A results file with no mutant lines at all is inconclusive, not clean.
    with tempfile.TemporaryDirectory() as cwd:
        empty_results = os.path.join(cwd, "r.txt")
        open(empty_results, "w").close()
        code, out, err = _run_cli([empty_results], [], cwd)
        assert code == 3, (code, out, err)
        assert "INCONCLUSIVE" in err, err


def test_run_inconclusive_on_each_broken_mutmut_output():
    """Each way `mutmut results` can be unusable names its own cause (#962)."""
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cwd:
        # mutmut ran and reported nothing: the run path must not read it as clean.
        _stub_uvx(d, 0, "no mutants here")
        code, out, err = _run_cli(["--run", "sample.py"], [d], cwd)
        assert code == 3 and out == "", (code, out, err)
        assert "no mutant lines" in err, err
        # `mutmut results` itself fails.
        _stub_uvx(d, 0, "    sample.x_clamp__mutmut_1: survived", results_exit=1)
        code, out, err = _run_cli(["--run", "sample.py"], [d], cwd)
        assert code == 3 and out == "", (code, out, err)
        assert "mutmut results failed" in err, err
        # A hung mutmut is bounded, and says so.
        _stub_uvx(d, 0, "", hang=True)
        code, out, err = _run_cli(["--run", "sample.py"], [d], cwd,
                                  extra_env={"MUTATION_AUDIT_TIMEOUT": "2"})
        assert code == 3 and out == "", (code, out, err)
        assert "timed out" in err, err


def test_unmodelled_status_is_inconclusive():
    """A mutant status the parser neither counts as killed nor emits (timeout,
    suspicious, skipped) must not pass as a clean run (#962, Codex round)."""
    for status in ("timeout", "suspicious", "skipped"):
        line = f"    sample.x_clamp__mutmut_1: {status}"
        with tempfile.TemporaryDirectory() as cwd:
            path = os.path.join(cwd, "r.txt")
            with open(path, "w") as f:
                f.write(line + "\n")
            code, out, err = _run_cli([path], [], cwd)
            assert code == 3 and out == "", (status, code, out, err)
            assert "INCONCLUSIVE" in err and status in err and "sample.x_clamp__mutmut_1" in err, err
    # Mixed with killed mutants it is still inconclusive: the unknown one is unaccounted for.
    try:
        parse_mutmut_results("    sample.x_a__mutmut_1: killed\n    sample.x_a__mutmut_2: timeout")
    except Inconclusive:
        pass
    else:
        raise AssertionError("a timeout mutant beside a killed one was accepted")


def test_run_reports_findings_when_mutmut_present():
    results = "    sample.x_clamp__mutmut_1: survived\n    sample.x_is_adult__mutmut_1: killed"
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cwd:
        _stub_uvx(d, 0, results)
        code, out, err = _run_cli(["--run", "sample.py"], [d], cwd)
        assert code == 0, (code, out, err)
        rows = [json.loads(line) for line in out.splitlines()]
        assert [r["extra"]["mutant"] for r in rows] == ["sample.x_clamp__mutmut_1"], rows
        # An all-killed run is a real clean run: exit 0, no rows, no INCONCLUSIVE.
        _stub_uvx(d, 0, "    sample.x_is_adult__mutmut_1: killed")
        code, out, err = _run_cli(["--run", "sample.py"], [d], cwd)
        assert (code, out) == (0, ""), (code, out, err)
        assert "INCONCLUSIVE" not in err, err


_JS_FIXTURES = os.path.join(os.path.dirname(AUDIT_PY), "fixtures", "js")


def test_stryker_parsing():
    """The captured StrykerJS report (`fixtures/js/stryker-report.json`, a real
    run of `sample.mjs`) maps survivors to `rewrite`, `NoCoverage` to
    `no-coverage`, and counts `Killed` into the tally."""
    with open(os.path.join(_JS_FIXTURES, "stryker-report.json"), encoding="utf-8") as f:
        text = f.read()
    rows = parse_stryker_report(text)
    got = [(r["bucket"], r["file"], r["line"], r["extra"]["mutant"]) for r in rows]
    assert got == [
        ("rewrite", "sample.mjs", 6, "sample.mjs:6:ConditionalExpression#7"),
        ("rewrite", "sample.mjs", 6, "sample.mjs:6:EqualityOperator#8"),
        ("rewrite", "sample.mjs", 7, "sample.mjs:7:ConditionalExpression#11"),
        ("rewrite", "sample.mjs", 7, "sample.mjs:7:EqualityOperator#12"),
        ("no-coverage", "sample.mjs", 11, "sample.mjs:11:BlockStatement#14"),
        ("no-coverage", "sample.mjs", 12, "sample.mjs:12:ArithmeticOperator#15"),
    ], got
    for r in rows:
        assert r["category"] == "surviving-mutant", r
        assert r["failure"] == "", r
        assert r["extra"]["killed"] is False, r
        assert (r["extra"]["killed_count"], r["extra"]["survived_count"],
                r["extra"]["no_coverage_count"]) == (10, 4, 2), r["extra"]
    assert [r["extra"]["survived"] for r in rows] == [True] * 4 + [False] * 2


def _stryker_report(*statuses):
    mutants = [{"id": str(i), "mutatorName": "M", "status": s,
                "location": {"start": {"line": i + 1, "column": 1}, "end": {"line": i + 1, "column": 2}}}
               for i, s in enumerate(statuses)]
    return json.dumps({"files": {"m.mjs": {"language": "javascript", "mutants": mutants, "source": ""}}})


def test_stryker_timeout_counts_killed_and_unjudged_statuses_stop():
    """`Timeout` is a kill (a hung mutant was caught); a `RuntimeError` mutant
    was never tested, so it must not pass as killed (the shared-sandbox trap),
    and a report with no mutant at all is not a clean run."""
    assert parse_stryker_report(_stryker_report("Killed", "Timeout")) == []
    rows = parse_stryker_report(_stryker_report("Timeout", "Killed", "Survived"))
    assert len(rows) == 1 and rows[0]["extra"]["killed_count"] == 2, rows
    # Stryker's own score leaves CompileError and Ignored out of the tally.
    assert parse_stryker_report(_stryker_report("Killed", "CompileError", "Ignored")) == []
    for status in ("RuntimeError", "Pending", "Mystery"):
        try:
            parse_stryker_report(_stryker_report("Killed", status))
        except Inconclusive as e:
            assert status in str(e), e
        else:
            raise AssertionError(f"{status} mutant was accepted")
    # Nothing judged is not a clean run: no mutant, or only unjudged ones.
    for bad in ("", "not json", "{}", _stryker_report(), _stryker_report("Ignored", "CompileError")):
        try:
            parse_stryker_report(bad)
        except Inconclusive:
            pass
        else:
            raise AssertionError(f"report {bad!r} was accepted as a run")


def test_js_candidate_selection():
    paths = ["x.mjs", "x.test.mjs", "lone.mjs", "sub/y.js", "sub/y.test.js",
             "fixtures/z.mjs", "fixtures/z.test.mjs", "node_modules/q/q.mjs", "node_modules/q/q.test.mjs",
             "pkg/w.py", "pkg/test_w.py"]
    assert suggest_candidates(paths) == ["pkg/w.py", "sub/y.js", "x.mjs"], suggest_candidates(paths)
    assert no_test_modules(paths) == ["lone.mjs"], no_test_modules(paths)
    with tempfile.TemporaryDirectory() as root:
        for name in ("x.mjs", "x.test.mjs", ".stryker-tmp/x.mjs", ".stryker-tmp/x.test.mjs"):
            os.makedirs(os.path.dirname(os.path.join(root, name)), exist_ok=True)
            open(os.path.join(root, name), "w").close()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["audit.py", "--suggest", root])
        assert [json.loads(l)["candidate"] for l in buf.getvalue().splitlines()] == ["x.mjs"], buf.getvalue()
        # The no-test stat counts JS modules in the same universe.
        for name in ("lone.mjs", "x.test.mjs"):
            open(os.path.join(root, name), "w").close()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["audit.py", "--no-tests", root])
        assert json.loads(buf.getvalue()) == {"no_tests": ["lone.mjs"], "total": 2}, buf.getvalue()


def _stub_npx(dirpath, report_text, exit_code=0, hang=False):
    """A stand-in `npx` (a Python script run by this interpreter) that records
    its argv and cwd, then writes `report_text` where the config file it was
    handed says the JSON reporter should (writes no file when it is `None`).
    `hang` leaves a grandchild running and waits, the shape of a
    Stryker that outlives `npx`; its pid goes to `child.pid`."""
    stub = os.path.join(dirpath, "npx")
    with open(stub, "w", encoding="utf-8") as f:
        f.write(f"#!{sys.executable}\n"
                "import json, os, sys\n"
                f"open({os.path.join(dirpath, 'argv.json')!r}, 'w').write(json.dumps([os.getcwd()] + sys.argv[1:]))\n"
                "conf = [a for a in sys.argv if a.endswith('.json')]\n"
                + (f"import subprocess, time\n"
                   f"open({os.path.join(dirpath, 'child.pid')!r}, 'w').write(str(subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)']).pid))\n"
                   "time.sleep(60)\n" if hang else "") +
                "if conf and " + ("False" if report_text is None else "True") + ":\n"
                "    out = json.load(open(conf[0]))['jsonReporter']['fileName']\n"
                f"    open(out, 'w').write({report_text!r})\n"
                f"sys.exit({exit_code})\n")
    os.chmod(stub, 0o755)


def test_run_js_target_through_stryker():
    """`--run x.mjs` runs the pinned StrykerJS command on x.mjs and only its
    sibling x.test.mjs, writes nothing into the audited checkout, and reports
    the survivors; every way it cannot judge exits 3."""
    with open(os.path.join(_JS_FIXTURES, "stryker-report.json"), encoding="utf-8") as f:
        report = f.read()
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cwd:
        _stub_npx(d, report)
        for name in ("sample.mjs", "sample.test.mjs"):
            open(os.path.join(cwd, name), "w").close()
        code, out, err = _run_cli(["--run", "sample.mjs"], [d], cwd)
        assert code == 0, (code, out, err)
        assert len(out.splitlines()) == 6, out
        argv = json.load(open(os.path.join(d, "argv.json")))
        assert os.path.realpath(argv[0]) == os.path.realpath(cwd), argv
        args = argv[1:]
        assert args[:5] == ["-y", "-p", "@stryker-mutator/core@10.0.0", "-p", "@stryker-mutator/tap-runner@10.0.0"], args
        assert args[5:7] == ["stryker", "run"], args
        tail = args[8:]
        assert tail == ["--testRunner", "tap", "--coverageAnalysis", "perTest",
                        "--mutate", "sample.mjs", "--testFiles", "sample.test.mjs",
                        "--reporters", "clear-text,json"], tail
        assert sorted(os.listdir(cwd)) == ["sample.mjs", "sample.test.mjs"], os.listdir(cwd)

        # No sibling test file: nothing to run against.
        os.remove(os.path.join(cwd, "sample.test.mjs"))
        code, out, err = _run_cli(["--run", "sample.mjs"], [d], cwd)
        assert code == 3 and out == "" and "INCONCLUSIVE" in err and "no sibling test file" in err, (code, out, err)
        open(os.path.join(cwd, "sample.test.mjs"), "w").close()

        # Stryker fails, or writes no report.
        _stub_npx(d, report, exit_code=1)
        code, out, err = _run_cli(["--run", "sample.mjs"], [d], cwd)
        assert code == 3 and out == "" and "stryker run failed" in err, (code, out, err)
        _stub_npx(d, None)
        code, out, err = _run_cli(["--run", "sample.mjs"], [d], cwd)
        assert code == 3 and out == "" and "wrote no JSON report" in err, (code, out, err)
        _stub_npx(d, "")
        code, out, err = _run_cli(["--run", "sample.mjs"], [d], cwd)
        assert code == 3 and out == "" and "not a Stryker JSON report" in err, (code, out, err)
        # A parseable report with nothing judged is not a clean run either.
        _stub_npx(d, _stryker_report("Ignored", "CompileError"))
        code, out, err = _run_cli(["--run", "sample.mjs"], [d], cwd)
        assert code == 3 and out == "" and "no judged mutant" in err, (code, out, err)
        # An all-killed run is a real clean run.
        _stub_npx(d, _stryker_report("Killed", "Timeout"))
        code, out, err = _run_cli(["--run", "sample.mjs"], [d], cwd)
        assert (code, out) == (0, ""), (code, out, err)

        # A hung Stryker is bounded, and its whole process group dies with it.
        # Killing only the direct child leaves the grandchild holding the
        # output pipe open, so the run would not return until it exits (20 s).
        _stub_npx(d, report, hang=True)
        started = time.monotonic()
        code, out, err = _run_cli(["--run", "sample.mjs"], [d], cwd,
                                  extra_env={"MUTATION_AUDIT_TIMEOUT": "2"})
        assert time.monotonic() - started < 10, "the timed-out run waited on its child"
        assert code == 3 and out == "" and "timed out" in err, (code, out, err)
        child = int(open(os.path.join(d, "child.pid")).read())
        for _ in range(50):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(child, signal.SIGKILL)
            raise AssertionError("the timed-out run left its child process running")

    with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as cwd:
        open(os.path.join(cwd, "sample.mjs"), "w").close()
        open(os.path.join(cwd, "sample.test.mjs"), "w").close()
        code, out, err = _run_cli(["--run", "sample.mjs"], [empty], cwd)
        assert code == 3 and out == "" and "npx" in err, (code, out, err)
