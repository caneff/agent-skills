"""Tests for test-audit's pytest-side detectors and its CLI.

One test per detector, parametrized over its positive and negative snippets,
so a failure names the detector and the row instead of hiding behind the first
bad assert of one long function (#1743). These were `audit.py`'s `_selfcheck`.
"""
import ast
import contextlib
import io
import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from audit import (  # noqa: E402
    EXIT_UNABLE,
    LOST_DUPLICATE,
    LOST_UNCOLLECTED,
    PROSE_SMELL,
    _test_functions,
    gate,
    has_broad_raises,
    has_called_stub,
    has_dead_assertion_in_raises,
    has_private_access,
    has_vacuous_loop_assertion,
    is_assertion_free,
    is_empty_or_skipped,
    is_interaction_only,
    is_mock_the_world,
    is_nonstrict_xfail,
    is_prose_assertion,
    is_shell_prose_test,
    is_tautology,
    lost_tests,
    main,
    private_imports,
    scan_path,
    xfail_strict_for,
)


def _func_from(src):
    return next(_test_functions(ast.parse(src)))


def _main_stderr(argv):
    """`main`'s exit status paired with what it wrote to stderr, its report
    swallowed. The gate reports its suppressed-fixtures count on stderr."""
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, err.getvalue()


def _quiet_main(argv):
    return _main_stderr(argv)[0]


@pytest.mark.parametrize("source, expected", [
    # 1. assertion-free
    ("def test_x():\n    x = compute()\n", True),
    ("def test_x():\n    x = compute()\n    assert x is not None\n", True),
    ("def test_x():\n    x = compute()\n    assert x == 5\n", False),
    # a private helper is still a delegated assertion: `_assert_*` is the
    # module-local convention for one, so the leading underscores are stripped
    # before the prefix test (#678).
    ("def test_x():\n    _assert_foo(compute())\n", False),
    ("def test_x():\n    _check_foo(compute())\n", True),
])
def test_is_assertion_free(source, expected):
    assert is_assertion_free(_func_from(source)) is expected


@pytest.mark.parametrize("source, expected", [
    # 2. tautology
    ("def test_x():\n    x = compute()\n    assert x == x\n", True),
    ("def test_x():\n    x = compute()\n    assert x == 5\n", False),
])
def test_is_tautology(source, expected):
    assert is_tautology(_func_from(source)) is expected


def test_unittest_testcase_is_not_collected_as_pytest():
    """unittest.TestCase methods are a different framework, not pytest:
    skipped, not silently treated as pytest."""
    unittest_tree = ast.parse(
        "class FooTest(unittest.TestCase):\n"
        "    def test_x(self):\n"
        "        pass\n"
    )
    assert list(_test_functions(unittest_tree)) == []


def test_pytest_class_methods_are_collected():
    pytest_class_tree = ast.parse(
        "class TestFoo:\n"
        "    def test_x(self):\n"
        "        assert 1 == 1\n"
    )
    assert len(list(_test_functions(pytest_class_tree))) == 1


@pytest.mark.parametrize("source, expected", [
    # 3. mock-the-world
    ("@patch('mod.a')\n"
            "@patch('mod.b')\n"
            "def test_x(a, b):\n"
            "    m1 = MagicMock()\n"
            "    m2 = MagicMock()\n"
            "    result = subject.run()\n", True),
    ("def test_x():\n"
            "    m = Mock()\n"
            "    result = subject.compute(1, 2)\n"
            "    assert result == 3\n", False),
    # the same underscore stripping decides the real-call count here: three
    # mocks against three `_assert_*` helpers only reads as mock-the-world
    # while the helpers are not counted as real calls (#678).
    ("def test_x():\n"
            "    m1 = MagicMock()\n"
            "    m2 = MagicMock()\n"
            "    m3 = MagicMock()\n"
            "    _assert_a(m1)\n"
            "    _assert_b(m2)\n"
            "    _assert_c(m3)\n", True),
])
def test_is_mock_the_world(source, expected):
    assert is_mock_the_world(_func_from(source)) is expected


@pytest.mark.parametrize("source, expected", [
    # 4. interaction-only assertion
    ("def test_x():\n    mock_obj.run()\n    mock_obj.assert_called_once()\n", True),
    ("def test_x():\n    result = subject.run()\n    assert result == 'ok'\n", False),
    # the private-helper spelling reaches this detector too: without it a
    # spy-only test escapes both assertion-free and interaction-only (#678).
    ("def test_x():\n    mock_obj.run()\n    _assert_called_once(mock_obj)\n", True),
])
def test_is_interaction_only(source, expected):
    assert is_interaction_only(_func_from(source)) is expected


@pytest.mark.parametrize("source, expected", [
    # 5. empty/skipped
    ("def test_x():\n    pass\n", True),
    ("@pytest.mark.skip\ndef test_x():\n    assert True\n", True),
    ("@pytest.mark.skip(reason='flaky')\ndef test_x():\n    assert True\n", False),
    ("def test_x():\n    x = compute()\n    assert x == 5\n", False),
])
def test_is_empty_or_skipped(source, expected):
    assert is_empty_or_skipped(_func_from(source)) is expected


@pytest.mark.parametrize("source, expected", [
    ("def test_x():\n    assert 'a sentence' in SKILL.read_text()\n", False),
    # a test that runs code is not a prose assertion, whatever it greps
    ("def test_x():\n    out = render('SKILL.md')\n    assert 'a sentence' in out\n", False),
    ("def test_x():\n    text = open('SKILL.md').read()\n    assert parse(text) == 3\n", False),
    # a non-containment assertion is not a prose assertion, even over a prose read
    ("def test_x():\n    text = open('SKILL.md').read()\n    assert len(text) == 3\n", False),
    # a generic method name on code under test is a call into that code
    ("def test_x():\n    out = report.format('SKILL.md')\n    assert 'a sentence' in out\n", False),
    ("def test_x():\n    out = T.resolve('SKILL.md')\n    assert 'a sentence' in out\n", False),
    # 6. prose-assertion
    ("def test_x():\n    text = (ROOT / 'SKILL.md').read_text()\n    assert 'a sentence' in text\n", True),
])
def test_is_prose_assertion(source, expected):
    assert is_prose_assertion(_func_from(source)) is expected


def test_is_prose_assertion_follows_a_module_constant_prose_path():
    """the prose path may sit in a module-level constant"""
    assert is_prose_assertion(
        _func_from("def test_x():\n    assert 'a sentence' in SKILL.read_text()\n"), {"SKILL"}
    )


@pytest.mark.parametrize("source, expected", [
    ("set -euo pipefail\nskill=\"$here/SKILL.md\"\ngrep -q 'a sentence' \"$skill\" || exit 1\n", True),
    ("check() {\n  case \"$1\" in\n    *\"x\"*) ;;\n    *) exit 1 ;;\n  esac\n}\n"
        "check \"$(sed -n '/^## A$/,/^## B$/p' SKILL.md)\"\n", True),
    ("grep -q x SKILL.md\nbash ./run-the-thing.sh\n", False),
    ("out=$(python3 gen.py)\ngrep -q x \"$out\"\n", False),
    ("grep -q x not-prose.txt\n", False),
    # shell: a command run through a quoted path, a substitution or `command`
    ('grep -q x SKILL.md\n"$here/render.sh"\n', False),
    ('grep -q x SKILL.md\nout=$("$here/run.sh")\n', False),
    ('grep -q x SKILL.md\nout="${v:-$(render)}"\n', False),
    ('grep -q x SKILL.md\necho "`./run.sh`"\n', False),
    ("grep -q x SKILL.md\ncommand ./run.sh\n", False),
])
def test_is_shell_prose_test(source, expected):
    assert is_shell_prose_test(source) is expected


def test_scan_path_flags_prose_tests_by_language():
    """the detector is wired into scanning: a prose Python test, a prose
    shell test, and a test that runs code"""
    tmp = tempfile.mkdtemp()
    try:
        with open(os.path.join(tmp, "test_prose.py"), "w", encoding="utf-8") as f:
            f.write(
                "from pathlib import Path\nSKILL = Path('SKILL.md')\n\n"
                "def test_prose():\n    assert 'a sentence' in SKILL.read_text()\n\n"
                "def test_code():\n    assert render(SKILL) == 3\n"
            )
        with open(os.path.join(tmp, "prose.test.sh"), "w", encoding="utf-8") as f:
            f.write("grep -q 'a sentence' SKILL.md\n")
        with open(os.path.join(tmp, "code.test.sh"), "w", encoding="utf-8") as f:
            f.write("grep -q 'a sentence' SKILL.md\nbash ./run.sh\n")
        found = sorted((os.path.basename(p), line) for p, line, smell in scan_path(tmp) if smell == PROSE_SMELL)
        assert found == [("prose.test.sh", 1), ("test_prose.py", 4)], found
    finally:
        shutil.rmtree(tmp)


def test_scan_path_prunes_dot_dirs():
    """scan_path walks via auditlib.walk_source (#611), so .tox is pruned
    like every other audit."""
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, ".tox"))
        with open(os.path.join(tmp, ".tox", "test_x.py"), "w", encoding="utf-8") as f:
            f.write("def test_x():\n    pass\n")
        assert scan_path(tmp) == [], scan_path(tmp)
    finally:
        shutil.rmtree(tmp)


@pytest.mark.parametrize("source, expected", [
    # 7. dead assertion in an expect-exception block: every statement after the
    # first call in the block never runs.
    ("def test_x():\n    with pytest.raises(ValueError):\n        parse('')\n        assert parse.calls == 1\n", True),
    ("def test_x():\n    with raises(ValueError) as e:\n        parse('')\n        x = 1\n", True),
    ("def test_x():\n    with pytest.raises(ValueError):\n        assert ready\n        parse('')\n", False),
    ("def test_x():\n    with pytest.raises(ValueError):\n        parse('')\n    assert after\n", False),
    ("def test_x():\n    with open(f):\n        parse('')\n        assert after\n", False),
])
def test_has_dead_assertion_in_raises(source, expected):
    assert has_dead_assertion_in_raises(_func_from(source)) is expected


@pytest.mark.parametrize("source, expected", [
    ("def test_a():\n    assert 1\n\ndef test_a():\n    assert 2\n", [(1, LOST_DUPLICATE)]),
    ("class TestA:\n    def test_a(self):\n        assert 1\n    def test_a(self):\n        assert 2\n", [(2, LOST_DUPLICATE)]),
    ("def test_a():\n    assert 1\ndef test_a():\n    assert 2\ndef test_a():\n    assert 3\n", [
        (1, LOST_DUPLICATE),
        (3, LOST_DUPLICATE),
    ]),
    # the same name in two scopes, or behind a branch, replaces nothing
    ("def test_a():\n    assert 1\nclass TestA:\n    def test_a(self):\n        assert 2\n", []),
    ("if X:\n    def test_a():\n        assert 1\nelse:\n    def test_a():\n        assert 2\n", []),
    ("def helper():\n    pass\ndef helper():\n    pass\n", []),
    ("class TestA:\n    def __init__(self):\n        pass\n    def test_a(self):\n        assert 1\n", [
        (1, LOST_UNCOLLECTED)
    ]),
    ("class TestA:\n    def test_a(self):\n        assert 1\n", []),
    ("class Helper:\n    def __init__(self):\n        pass\n    def test_a(self):\n        assert 1\n", []),
    ("class TestA:\n    def __init__(self):\n        pass\n    def helper(self):\n        pass\n", []),
    # a TestCase still loses a shadowed method, though it is exempt from the __init__ rule
    ("class TestA(unittest.TestCase):\n    def test_a(self):\n        pass\n    def test_a(self):\n        pass\n", [(2, LOST_DUPLICATE)]),
    ("class TestA(unittest.TestCase):\n    def __init__(self):\n        pass\n    def test_a(self):\n        assert 1\n", []),
])
def test_lost_tests(source, expected):
    assert list(lost_tests(ast.parse(source))) == expected


@pytest.mark.parametrize("source, expected", [
    # 9. broad exception expectation
    ("def test_x():\n    with pytest.raises(Exception):\n        parse('')\n", True),
    ("def test_x():\n    with raises(BaseException) as e:\n        parse('')\n", True),
    ("def test_x():\n    with pytest.raises(Exception, match='empty'):\n        parse('')\n", False),
    ("def test_x():\n    with pytest.raises(ValueError):\n        parse('')\n", False),
    ("def test_x():\n    with pytest.raises(expected_exception=Exception):\n        parse('')\n", True),
])
def test_has_broad_raises(source, expected):
    assert has_broad_raises(_func_from(source)) is expected


@pytest.mark.parametrize("decorators, strict, expected", [
    ("@pytest.mark.xfail\n", False, True),
    ("@pytest.mark.xfail(reason='bug')\n", False, True),
    ("@pytest.mark.xfail(strict=False)\n", False, True),
    ("@mark.xfail\n", False, True),
    ("@pytest.mark.xfail(strict=True)\n", False, False),
    ("@pytest.mark.xfail\n", True, False),
    ("@pytest.mark.xfail(strict=False)\n", True, True),
    ("@pytest.mark.xfail(strict=STRICT)\n", False, False),
    ("@pytest.mark.skip\n", False, False),
    ("@pytest.mark.parametrize('a', [1])\n", False, False),
])
def test_is_nonstrict_xfail(decorators, strict, expected):
    func = _func_from(decorators + "def test_x():\n    assert 1\n")
    assert is_nonstrict_xfail(func, strict) is expected


def test_is_nonstrict_xfail_class_mark_covers_every_method():
    # a class mark covers every method in it
    assert is_nonstrict_xfail(ast.parse("@pytest.mark.xfail\nclass TestA:\n    pass\n").body[0], False)
    assert not is_nonstrict_xfail(ast.parse("@pytest.mark.xfail(strict=True)\nclass TestA:\n    pass\n").body[0], False)


def test_xfail_strict_for_reads_the_nearest_pytest_config():
    """the ini decides when the marker is silent"""
    tmp = tempfile.mkdtemp()
    try:
        def _ini_case(name, files):
            case = os.path.join(tmp, name)
            os.makedirs(os.path.join(case, ".git"))
            os.makedirs(os.path.join(case, "pkg"))
            for fname, text in files.items():
                with open(os.path.join(case, fname), "w", encoding="utf-8") as f:
                    f.write(text)
            return xfail_strict_for(os.path.join(case, "pkg", "test_x.py"))

        assert _ini_case("none", {}) is False
        assert _ini_case("ini", {"pytest.ini": "[pytest]\nxfail_strict = true\n"}) is True
        assert _ini_case("ini-false", {"pytest.ini": "[pytest]\nxfail_strict = false\n"}) is False
        assert _ini_case("ini-new-name", {"pytest.ini": "[pytest]\nstrict_xfail = 1\n"}) is True
        assert _ini_case("umbrella", {"pytest.ini": "[pytest]\nstrict = true\n"}) is True
        assert _ini_case("umbrella-off", {"pytest.ini": "[pytest]\nstrict = true\nxfail_strict = false\n"}) is False
        assert _ini_case("pyproject", {"pyproject.toml": "[tool.pytest.ini_options]\nxfail_strict = true\n"}) is True
        assert _ini_case("pyproject-native", {"pyproject.toml": "[tool.pytest]\nstrict_xfail = true\n"}) is True
        assert _ini_case("pytest-toml", {"pytest.toml": "[pytest]\nstrict_xfail = true\n"}) is True
        assert _ini_case("tox", {"tox.ini": "[pytest]\nxfail_strict = true\n"}) is True
        assert _ini_case("setup-cfg", {"setup.cfg": "[tool:pytest]\nxfail_strict = yes\n"}) is True
        # a pyproject with no pytest table does not configure pytest, so the
        # next file up the precedence list decides
        assert _ini_case(
            "pyproject-no-table",
            {"pyproject.toml": "[project]\nname = 'x'\n", "tox.ini": "[pytest]\nxfail_strict = true\n"},
        ) is True
        # an unreadable config is not a strict one: the marker is flagged
        assert _ini_case("broken", {"pytest.ini": "[pytest\nxfail_strict = true\n"}) is False
        assert _ini_case("broken-toml", {"pyproject.toml": "[tool.pytest.ini_options\n"}) is False
        # a config that parses but has the wrong shape is unreadable too, not a crash
        assert _ini_case("wrong-shape", {"pyproject.toml": "[tool]\npytest = 'x'\n"}) is False
        # an unreadable config stops the walk: the strict file above it must not decide
        case = os.path.join(tmp, "broken-sub")
        os.makedirs(os.path.join(case, ".git"))
        os.makedirs(os.path.join(case, "sub"))
        with open(os.path.join(case, "tox.ini"), "w", encoding="utf-8") as f:
            f.write("[pytest]\nxfail_strict = true\n")
        with open(os.path.join(case, "sub", "setup.cfg"), "w", encoding="utf-8") as f:
            f.write("[tool:pytest]\n")
        assert xfail_strict_for(os.path.join(case, "sub", "test_x.py")) is False
        if os.geteuid() != 0:
            os.chmod(os.path.join(case, "sub", "setup.cfg"), 0o000)
            try:
                assert xfail_strict_for(os.path.join(case, "sub", "test_x.py")) is False
            finally:
                os.chmod(os.path.join(case, "sub", "setup.cfg"), 0o644)
        # the walk stops at the repo root: a strict config above it is not this project's
        outer = os.path.join(tmp, "outer")
        os.makedirs(os.path.join(outer, "repo", ".git"))
        with open(os.path.join(outer, "pytest.ini"), "w", encoding="utf-8") as f:
            f.write("[pytest]\nxfail_strict = true\n")
        assert xfail_strict_for(os.path.join(outer, "repo", "test_x.py")) is False
    finally:
        shutil.rmtree(tmp)


def test_scan_path_wires_in_the_exact_match_smells():
    """the four are wired into scanning, the xfail one reading the ini beside it"""
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, ".git"))
        with open(os.path.join(tmp, "test_exact.py"), "w", encoding="utf-8") as f:
            f.write(
                "import pytest\n"
                "@pytest.mark.xfail\n"
                "def test_a():\n    with pytest.raises(Exception):\n        run()\n        assert 1\n"
                "def test_b():\n    assert 1\n"
                "def test_b():\n    assert 2\n"
                "class TestC:\n    def __init__(self):\n        pass\n    def test_c(self):\n        assert 1\n"
            )
        found = sorted((line, smell) for _, line, smell in scan_path(tmp))
        assert found == [
            (3, "broad exception expectation"),
            (3, "dead assertion in an expect-exception block"),
            (3, "non-strict xfail"),
            (7, LOST_DUPLICATE),
            (11, LOST_UNCOLLECTED),
        ], found
        with open(os.path.join(tmp, "pytest.ini"), "w", encoding="utf-8") as f:
            f.write("[pytest]\nxfail_strict = true\n")
        assert "non-strict xfail" not in [smell for _, _, smell in scan_path(tmp)]
    finally:
        shutil.rmtree(tmp)


def test_gate_counts_fixture_duplicates_and_keeps_the_rest_report_only():
    # gate mode: the duplicate-name case joins assertion-free; the rest of the
    # new four stay report-only. Its own fixtures exemption and count.
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "fixtures"))
        dup = "def test_x():\n    assert 1\ndef test_x():\n    assert 2\n"
        with open(os.path.join(tmp, "fixtures", "test_specimen.py"), "w", encoding="utf-8") as f:
            f.write(dup)
        with open(os.path.join(tmp, "test_report_only.py"), "w", encoding="utf-8") as f:
            f.write(
                "import pytest\n"
                "@pytest.mark.xfail\n"
                "def test_a():\n    with pytest.raises(Exception):\n        run()\n        assert 1\n"
                "class TestC:\n    def __init__(self):\n        pass\n    def test_c(self):\n        assert 1\n"
            )
        findings, suppressed = gate(tmp)
        assert findings == [], findings
        assert suppressed == {"duplicate-name": 1}, suppressed
        code, err = _main_stderr(["audit.py", "--gate", tmp])
        assert code == 0, (code, err)
        assert "1 duplicate-name finding(s) suppressed under fixtures/" in err, err
        with open(os.path.join(tmp, "test_dup.py"), "w", encoding="utf-8") as f:
            f.write(dup)
        findings, _ = gate(tmp)
        assert [(os.path.basename(p), line, smell) for p, line, smell in findings] == [
            ("test_dup.py", 1, LOST_DUPLICATE)
        ], findings
        assert _quiet_main(["audit.py", "--gate", tmp]) == 1
    finally:
        shutil.rmtree(tmp)


def test_gate_fails_assertion_free_never_a_fixture_and_refuses_a_missing_root():
    # gate mode: assertion-free only (the duplicate-name case is below), and never a fixture.
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "fixtures"))
        with open(os.path.join(tmp, "fixtures", "test_specimen.py"), "w", encoding="utf-8") as f:
            f.write("def test_x():\n    compute()\n")
        with open(os.path.join(tmp, "test_taut.py"), "w", encoding="utf-8") as f:
            f.write("def test_x():\n    x = compute()\n    assert x == x\n")
        # a deliberate specimen and a report-only smell: neither fails a build
        assert gate(tmp)[0] == [], gate(tmp)
        assert [smell for _, _, smell in scan_path(tmp)] != [], "the report pass still sees both"

        # ...but the exemption is counted and reported. `fixtures` matches any
        # directory of that name at any depth, so without this line a repo
        # could park hollow tests under one and never see it (#685).
        assert gate(tmp)[1] == {"assertion-free": 1}, gate(tmp)
        code, err = _main_stderr(["audit.py", "--gate", tmp])
        assert code == 0, (code, err)
        assert "1 assertion-free finding(s) suppressed under fixtures/" in err, err

        with open(os.path.join(tmp, "test_hollow.py"), "w", encoding="utf-8") as f:
            f.write("def test_x():\n    compute()\n")
        gated, suppressed = gate(tmp)
        assert len(gated) == 1, gated
        assert gated[0][0].endswith("test_hollow.py"), gated
        assert suppressed == {"assertion-free": 1}, suppressed
        assert _quiet_main(["audit.py", "--gate", tmp]) == 1
        os.remove(os.path.join(tmp, "test_hollow.py"))
        assert _quiet_main(["audit.py", "--gate", tmp]) == 0

        # A root that does not exist was not checked, so the gate must not
        # report success: EXIT_UNABLE, distinct from both 0 (clean) and 1
        # (hollow tests found), so a typo in a repo's wiring reads
        # differently from a real finding (#685).
        # Each guard is witnessed by its own message: `os.access` also rejects
        # a missing path, so a status-only assertion would leave the existence
        # branch passing with its constraint stripped.
        missing = os.path.join(tmp, "no-such-dir")
        code, err = _main_stderr(["audit.py", "--gate", missing])
        assert code == EXIT_UNABLE, (code, err)
        assert "no such path" in err, err
        assert _quiet_main(["audit.py", missing]) == EXIT_UNABLE
    finally:
        shutil.rmtree(tmp)


def test_gate_refuses_an_unreadable_root_and_skips_an_unreadable_file():
    # A root that exists but cannot be read was not checked either -- the same
    # lie, reached by EACCES instead of ENOENT (#685). Its own root, never one
    # earlier assertions gate on: a hollow fixture parked under such a root is
    # what makes those assertions pass.
    #
    # Skipped for uid 0, which is granted access whatever the mode, so the tree
    # would scan and the gate would find the fixture.
    if os.geteuid() != 0:
        denied = tempfile.mkdtemp()
        try:
            with open(os.path.join(denied, "test_hollow.py"), "w", encoding="utf-8") as f:
                f.write("def test_x():\n    compute()\n")
            # Readable but not listable, then not readable at all: both leave
            # the walk with nothing, so both must refuse rather than report clean.
            for mode in (0o444, 0o000):
                os.chmod(denied, mode)
                code, err = _main_stderr(["audit.py", "--gate", denied])
                os.chmod(denied, 0o755)
                assert code == EXIT_UNABLE, (oct(mode), code, err)
                assert "cannot read" in err, err
        finally:
            os.chmod(denied, 0o755)
            shutil.rmtree(denied)

        # An unreadable *file* under a readable root is skipped, not raised.
        # audit.mjs's scanFile has always caught this; without the mirror the
        # exception reached `main` and the process exited 1, which under the
        # gate's contract means "hollow tests found". Skipping it still leaves
        # the file unexamined -- that wider hole is the documented follow-up.
        locked = tempfile.mkdtemp()
        try:
            path = os.path.join(locked, "test_locked.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write("def test_x():\n    compute()\n")
            os.chmod(path, 0o000)
            assert _quiet_main(["audit.py", "--gate", locked]) == 0
        finally:
            os.chmod(path, 0o644)
            shutil.rmtree(locked)


@pytest.mark.parametrize("source, expected", [
    # 11. stub asserted called: the stubbed receiver must be the one checked
    ("def test_x():\n    m.get.return_value = 1\n    assert f(m) == 1\n    m.get.assert_called_once()\n", True),
    ("def test_x():\n    m = Mock(side_effect=[1])\n    assert f(m) == 1\n    assert m.called\n", True),
    ("def test_x():\n    m.get.return_value = 1\n    assert f(m) == 1\n    m.put.assert_called_once()\n", False),
    ("def test_x():\n    m.get.return_value = 1\n    assert f(m) == 1\n", False),
    ("def test_x():\n    m = Mock()\n    assert f(m) == 1\n    m.assert_called_once()\n", False),
    ("def test_x():\n    with patch.object(r, 'get', return_value=1) as g:\n        assert f(r) == 1\n    g.assert_called_once()\n", True),
    ("@patch('m.put')\n@patch('m.get', return_value=1)\ndef test_x(get, put):\n    assert f() == 1\n    get.assert_called_once()\n", True),
    ("@patch('m.put')\n@patch('m.get', return_value=1)\ndef test_x(get, put):\n    assert f() == 1\n    put.assert_called_once()\n", False),
])
def test_has_called_stub(source, expected):
    assert has_called_stub(_func_from(source)) is expected


@pytest.mark.parametrize("source, expected", [
    # 12. private-API access
    ("def test_x():\n    assert c._store == 1\n", True),
    ("def test_x():\n    assert self.obj._store == 1\n", True),
    ("def test_x():\n    assert self._store == c.__class__\n", False),
])
def test_has_private_access(source, expected):
    assert has_private_access(_func_from(source)) is expected


def test_private_imports_flags_underscore_names_only():
    assert private_imports(ast.parse("from m import _a\nfrom m import b\nimport _c\nfrom m import __v__\n")) == [1]


@pytest.mark.parametrize("source, expected", [
    # 13. vacuous loop assertion
    ("def test_x():\n    r = f()\n    for i in r:\n        assert i > 0\n", True),
    ("def test_x():\n    for i in enumerate(f().items()):\n        assert i\n", True),
    ("def test_x():\n    r = f()\n    assert r\n    for i in r:\n        assert i > 0\n", False),
    ("def test_x():\n    for i in range(3):\n        assert f(i) > 0\n", False),
    ("def test_x():\n    for i in CASES:\n        assert f(i) > 0\n", False),
    ("def test_x():\n    r = f()\n    for i in r:\n        pass\n", False),
    # a call over literals is a fixed input, not the code's output
    ("def test_x():\n    for i in sorted([1, 2]):\n        assert f(i) > 0\n", False),
    ("def test_x():\n    e = sorted([1, 2])\n    for i in e:\n        assert f(i) > 0\n", False),
    ("def test_x():\n    for i in [1, 2].copy():\n        assert f(i) > 0\n", False),
])
def test_has_vacuous_loop_assertion(source, expected):
    assert has_vacuous_loop_assertion(_func_from(source)) is expected
