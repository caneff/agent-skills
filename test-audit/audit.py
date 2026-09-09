#!/usr/bin/env python3
"""Pass one of test-audit: mechanical grep for the syntactically detectable smells.

Scans pytest-style test files and emits `file:line: <smell>` candidates for the
judgment pass (SKILL.md) to sort into Cut/Rewrite/Keep. This script never
classifies — it only surfaces candidates.

Five detectors, each a small AST check:
  1. assertion-free   — no assert / pytest.raises / self.assert*, or only a
                         trivial `assert True` / `assert x is not None`.
  2. tautology         — `assert x == x` (same expression both sides).
  3. mock-the-world     — many Mock/MagicMock/patch constructs, few real calls.
  4. interaction-only   — the only checks are `assert_called*` / `.called`.
  5. empty/skipped      — `pass`-body test, or `@skip` with no reason.

Wherever a detector keys off the `assert` name prefix, leading underscores are
stripped first: `_assert_*` is the private-helper spelling of a delegated
assertion (#678).

ponytail: pytest-only. Framework detection is filename convention
(`test_*.py`/`*_test.py`) plus excluding unittest.TestCase methods (a
different framework: different assertion API, different discovery) — not a
general classifier. jest, go test, and other non-Python runners are
out-of-scope follow-ups per the parent spec (#275).
"""
import ast
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "all-audits", "harness"))
import auditlib  # noqa: E402

MOCK_NAMES = {"Mock", "MagicMock", "patch"}
# ponytail: 3 is the ceiling. Below it, a test with one or two mocked
# collaborators and real logic in between is normal isolation, not a smell.
MOCK_CEILING = 3


def _name_of(node):
    """Attribute -> its `.attr`, Name -> its `.id`, else None."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _call_name(node):
    if not isinstance(node, ast.Call):
        return None
    return _name_of(node.func)


def _bare_name(node):
    """`_call_name` with leading underscores stripped. `_assert_*` is the
    private-helper spelling of a delegated assertion, and every detector that
    keys off the `assert` prefix means the same thing by it (#678)."""
    name = _call_name(node)
    return name.lstrip("_") if name else name


def _is_unittest_testcase(cls):
    return any(_name_of(base) == "TestCase" for base in cls.bases)


def _test_functions(tree):
    """Yield pytest-style test_* functions: module-level, or methods of a
    class that isn't a unittest.TestCase subclass. unittest is a different
    framework from pytest (different assertion API, different discovery) —
    a TestCase's test_ methods are out of scope here, not silently treated
    as pytest. This is the framework-detection line: filename + test_ name
    alone can't tell pytest from unittest, but the base class can."""
    unittest_ranges = [
        (n.lineno, n.end_lineno) for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and _is_unittest_testcase(n)
    ]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            if any(start <= node.lineno <= end for start, end in unittest_ranges):
                continue
            yield node


def _is_trivial_assert(node):
    test = node.test
    if isinstance(test, ast.Constant) and test.value is True:
        return True
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.IsNot):
        comp = test.comparators[0]
        if isinstance(comp, ast.Constant) and comp.value is None:
            return True
    return False


def _assertion_mechanisms(func):
    mechs = []
    for n in ast.walk(func):
        if isinstance(n, ast.Assert):
            mechs.append(n)
        else:
            bare = _bare_name(n)
            # `raises` stays on the raw name: `pytest.raises` is spelled one
            # way, and there is no `_raises` private-helper convention.
            if (bare and bare.startswith("assert")) or _call_name(n) == "raises":
                mechs.append(n)
    return mechs


def is_assertion_free(func):
    """1. assertion-free test."""
    mechs = _assertion_mechanisms(func)
    if not mechs:
        return True
    return all(isinstance(m, ast.Assert) and _is_trivial_assert(m) for m in mechs)


def is_tautology(func):
    """2. tautology — asserts a value against itself.

    ponytail: covers the literal self-comparison (`assert x == x`), including
    the case where both sides are the identical call expression (e.g.
    `assert f(x) == f(x)`). The broader form named in #277 — the test body
    re-implements the function under test with different code and compares —
    needs reading what the implementation actually does, which isn't
    syntactically detectable; that's judgment-pass territory, not this pass.
    """
    for n in ast.walk(func):
        if (
            isinstance(n, ast.Assert)
            and isinstance(n.test, ast.Compare)
            and len(n.test.ops) == 1
            and isinstance(n.test.ops[0], ast.Eq)
        ):
            left, right = n.test.left, n.test.comparators[0]
            if ast.dump(left) == ast.dump(right):
                return True
    return False


def is_mock_the_world(func):
    """3. mock-the-world — many mocks, little real code exercised."""
    mock_calls = real_calls = 0
    for n in ast.walk(func):
        name = _call_name(n)
        if name in MOCK_NAMES:
            mock_calls += 1
        elif name and not _bare_name(n).startswith("assert"):
            real_calls += 1
    return mock_calls >= MOCK_CEILING and mock_calls > real_calls


def _is_interaction_check(node):
    if isinstance(node, ast.Expr):
        node = node.value
    if isinstance(node, ast.Assert):
        test = node.test
        if isinstance(test, ast.Attribute) and test.attr == "called":
            return True
        name = _bare_name(test)
        return bool(name and name.startswith("assert_called"))
    name = _bare_name(node)
    return bool(name and name.startswith("assert_called"))


def is_interaction_only(func):
    """4. interaction-only assertion — only checks that a mock was called."""
    checks = []
    for n in ast.walk(func):
        if isinstance(n, ast.Assert):
            checks.append(_is_interaction_check(n))
        elif isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and _is_interaction_check(n.value):
            checks.append(True)
    if not checks:
        return False
    return all(checks)


def is_empty_or_skipped(func):
    """5. empty/skipped test — pass-body, or @skip with no reason."""
    body = [
        n
        for n in func.body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))
    ]
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return True
    for dec in func.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        attr = _name_of(target)
        if attr != "skip":
            continue
        if isinstance(dec, ast.Call):
            has_reason = bool(dec.args) or any(kw.arg == "reason" for kw in dec.keywords)
            if not has_reason:
                return True
        else:
            return True
    return False


DETECTORS = [
    ("assertion-free test", is_assertion_free),
    ("tautology", is_tautology),
    ("mock-the-world", is_mock_the_world),
    ("interaction-only assertion", is_interaction_only),
    ("empty/skipped test", is_empty_or_skipped),
]


def _is_pytest_file(path, tree):
    base = os.path.basename(path)
    if not (base.startswith("test_") or base.endswith("_test.py")):
        return False
    return any(True for _ in _test_functions(tree))


def scan_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        source = f.read()
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    if not _is_pytest_file(path, tree):
        return []
    findings = []
    for func in _test_functions(tree):
        for smell, detector in DETECTORS:
            if detector(func):
                findings.append((path, func.lineno, smell))
    return findings


def scan_path(root):
    if os.path.isfile(root):
        paths = [root]
    else:
        paths = [os.path.join(root, rel) for rel in auditlib.walk_source(root)]
    findings = []
    for path in paths:
        findings.extend(scan_file(path))
    return findings


# --- gate mode -------------------------------------------------------------

# The one smell a build gates on. The other four are report-only: a
# mock-the-world or interaction-only test still runs and still fails when the
# behavior breaks, so blocking a merge on one costs more than it buys. An
# assertion-free test cannot fail at all, which is the one finding a machine
# can call a defect without reading anything.
GATE_SMELL = "assertion-free test"

# Exit status contract: 0 clean, 1 hollow tests found, 2 unable to check. Only
# gate mode ever returns 1 -- a report never fails a build -- but 0 and 2 mean
# the same in both. A root that does not exist gets 2 and never 0 --
# a gate that reports success while it scanned nothing is a lie, and it fails
# silently and permanently once wired into a repo's build (#685).
EXIT_UNABLE = 2


def _under_fixtures(path):
    """True when `path` lies under a `fixtures/` directory.

    A fixture is a deliberate specimen of the smell -- this skill's own
    `fixtures/test_pytest_smells.py` exists to be flagged -- so the gate
    never counts one. The report pass still sees them; only the gate skips."""
    return "fixtures" in path.replace(os.sep, "/").split("/")


def gate(root):
    """`(findings, suppressed)` -- the `GATE_SMELL` findings that fail a build,
    and how many the fixtures exemption dropped.

    The count is returned, and reported by `main`, because `_under_fixtures`
    matches a `fixtures` segment at any depth: without it a repo could park
    hollow tests under any directory it named `fixtures` and never see that
    the gate had stopped looking at them (#685)."""
    gated = [f for f in scan_path(root) if f[2] == GATE_SMELL]
    findings = [f for f in gated if not _under_fixtures(f[0])]
    return findings, len(gated) - len(findings)


def _main_stderr(argv):
    """`main`'s exit status paired with what it wrote to stderr, its report
    swallowed -- a passing suite should print only `ok`. The gate reports its
    suppressed-fixtures count on stderr, so the selfcheck reads it there."""
    import contextlib
    import io

    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, err.getvalue()


def _quiet_main(argv):
    return _main_stderr(argv)[0]


def _selfcheck():
    def _func_from(src):
        tree = ast.parse(src)
        return next(_test_functions(tree))

    # 1. assertion-free
    assert is_assertion_free(_func_from("def test_x():\n    x = compute()\n"))
    assert is_assertion_free(_func_from("def test_x():\n    x = compute()\n    assert x is not None\n"))
    assert not is_assertion_free(_func_from("def test_x():\n    x = compute()\n    assert x == 5\n"))
    # a private helper is still a delegated assertion: `_assert_*` is the
    # module-local convention for one, so the leading underscores are stripped
    # before the prefix test (#678).
    assert not is_assertion_free(_func_from("def test_x():\n    _assert_foo(compute())\n"))
    assert is_assertion_free(_func_from("def test_x():\n    _check_foo(compute())\n"))

    # 2. tautology
    assert is_tautology(_func_from("def test_x():\n    x = compute()\n    assert x == x\n"))
    assert not is_tautology(_func_from("def test_x():\n    x = compute()\n    assert x == 5\n"))

    # framework detection: unittest.TestCase methods are a different
    # framework, not pytest — skipped rather than silently treated as pytest.
    unittest_tree = ast.parse(
        "class FooTest(unittest.TestCase):\n"
        "    def test_x(self):\n"
        "        pass\n"
    )
    assert list(_test_functions(unittest_tree)) == []
    pytest_class_tree = ast.parse(
        "class TestFoo:\n"
        "    def test_x(self):\n"
        "        assert 1 == 1\n"
    )
    assert len(list(_test_functions(pytest_class_tree))) == 1

    # 3. mock-the-world
    assert is_mock_the_world(
        _func_from(
            "@patch('mod.a')\n"
            "@patch('mod.b')\n"
            "def test_x(a, b):\n"
            "    m1 = MagicMock()\n"
            "    m2 = MagicMock()\n"
            "    result = subject.run()\n"
        )
    )
    assert not is_mock_the_world(
        _func_from(
            "def test_x():\n"
            "    m = Mock()\n"
            "    result = subject.compute(1, 2)\n"
            "    assert result == 3\n"
        )
    )

    # the same underscore stripping decides the real-call count here: three
    # mocks against three `_assert_*` helpers only reads as mock-the-world
    # while the helpers are not counted as real calls (#678).
    assert is_mock_the_world(
        _func_from(
            "def test_x():\n"
            "    m1 = MagicMock()\n"
            "    m2 = MagicMock()\n"
            "    m3 = MagicMock()\n"
            "    _assert_a(m1)\n"
            "    _assert_b(m2)\n"
            "    _assert_c(m3)\n"
        )
    )

    # 4. interaction-only assertion
    assert is_interaction_only(
        _func_from("def test_x():\n    mock_obj.run()\n    mock_obj.assert_called_once()\n")
    )
    assert not is_interaction_only(
        _func_from("def test_x():\n    result = subject.run()\n    assert result == 'ok'\n")
    )
    # the private-helper spelling reaches this detector too: without it a
    # spy-only test escapes both assertion-free and interaction-only (#678).
    assert is_interaction_only(
        _func_from("def test_x():\n    mock_obj.run()\n    _assert_called_once(mock_obj)\n")
    )

    # 5. empty/skipped
    assert is_empty_or_skipped(_func_from("def test_x():\n    pass\n"))
    assert is_empty_or_skipped(_func_from("@pytest.mark.skip\ndef test_x():\n    assert True\n"))
    assert not is_empty_or_skipped(
        _func_from("@pytest.mark.skip(reason='flaky')\ndef test_x():\n    assert True\n")
    )
    assert not is_empty_or_skipped(_func_from("def test_x():\n    x = compute()\n    assert x == 5\n"))

    # scan_path walks via auditlib.walk_source (#611), so a dot-dir like
    # .tox is pruned the same way every other audit prunes it.
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, ".tox"))
        with open(os.path.join(tmp, ".tox", "test_x.py"), "w", encoding="utf-8") as f:
            f.write("def test_x():\n    pass\n")
        assert scan_path(tmp) == [], scan_path(tmp)
    finally:
        shutil.rmtree(tmp)

    # gate mode: assertion-free only, and never a fixture.
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
        assert gate(tmp)[1] == 1, gate(tmp)
        code, err = _main_stderr(["audit.py", "--gate", tmp])
        assert code == 0, (code, err)
        assert "1 assertion-free finding(s) suppressed under fixtures/" in err, err

        with open(os.path.join(tmp, "test_hollow.py"), "w", encoding="utf-8") as f:
            f.write("def test_x():\n    compute()\n")
        gated, suppressed = gate(tmp)
        assert len(gated) == 1, gated
        assert gated[0][0].endswith("test_hollow.py"), gated
        assert suppressed == 1, suppressed
        assert _quiet_main(["audit.py", "--gate", tmp]) == 1
        os.remove(os.path.join(tmp, "test_hollow.py"))
        assert _quiet_main(["audit.py", "--gate", tmp]) == 0

        # A root that does not exist was not checked, so the gate must not
        # report success: EXIT_UNABLE, distinct from both 0 (clean) and 1
        # (hollow tests found), so a typo in a repo's wiring reads
        # differently from a real finding (#685).
        missing = os.path.join(tmp, "no-such-dir")
        assert _quiet_main(["audit.py", "--gate", missing]) == EXIT_UNABLE
        assert _quiet_main(["audit.py", missing]) == EXIT_UNABLE
    finally:
        shutil.rmtree(tmp)

    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return 0
    gate_mode = argv[1:2] == ["--gate"]
    rest = argv[2:] if gate_mode else argv[1:]
    root = rest[0] if rest else "."
    # Refuse a root that does not exist before scanning it. Walking a missing
    # directory finds nothing, and "nothing" is indistinguishable from a clean
    # tree -- so a typo in a repo's wiring would make its gate permanently
    # green (#685).
    if not os.path.exists(root):
        print(f"test-audit: no such path: {root} -- nothing was scanned.", file=sys.stderr)
        return EXIT_UNABLE
    if gate_mode:
        findings, suppressed = gate(root)
        for path, lineno, smell in findings:
            print(f"{path}:{lineno}: {smell}")
        if suppressed:
            print(
                f"test-audit: {suppressed} assertion-free finding(s) suppressed under fixtures/.",
                file=sys.stderr,
            )
        if findings:
            print(
                f"test-audit: {len(findings)} assertion-free test(s) -- a test that cannot fail proves nothing.",
                file=sys.stderr,
            )
            return 1
        return 0
    findings = scan_path(root)
    for path, lineno, smell in findings:
        print(f"{path}:{lineno}: {smell}")
    if not findings:
        print("no mechanical smells found", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
