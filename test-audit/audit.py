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

ponytail: pytest-only. Framework detection is filename convention
(`test_*.py`/`*_test.py`) plus excluding unittest.TestCase methods (a
different framework: different assertion API, different discovery) — not a
general classifier. jest, go test, and other non-Python runners are
out-of-scope follow-ups per the parent spec (#275).
"""
import ast
import glob
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
            name = _call_name(n)
            if name and (name.startswith("assert") or name == "raises"):
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
        elif name and not name.startswith("assert"):
            real_calls += 1
    return mock_calls >= MOCK_CEILING and mock_calls > real_calls


def _is_interaction_check(node):
    if isinstance(node, ast.Expr):
        node = node.value
    if isinstance(node, ast.Assert):
        test = node.test
        if isinstance(test, ast.Attribute) and test.attr == "called":
            return True
        name = _call_name(test)
        return bool(name and name.startswith("assert_called"))
    name = _call_name(node)
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
        paths = [
            p
            for p in sorted(glob.glob(os.path.join(root, "**", "*.py"), recursive=True))
            if not (auditlib.EXCLUDED_DIRS & set(p.split(os.sep)))
        ]
    findings = []
    for path in paths:
        findings.extend(scan_file(path))
    return findings


def _selfcheck():
    def _func_from(src):
        tree = ast.parse(src)
        return next(_test_functions(tree))

    # 1. assertion-free
    assert is_assertion_free(_func_from("def test_x():\n    x = compute()\n"))
    assert is_assertion_free(_func_from("def test_x():\n    x = compute()\n    assert x is not None\n"))
    assert not is_assertion_free(_func_from("def test_x():\n    x = compute()\n    assert x == 5\n"))

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

    # 4. interaction-only assertion
    assert is_interaction_only(
        _func_from("def test_x():\n    mock_obj.run()\n    mock_obj.assert_called_once()\n")
    )
    assert not is_interaction_only(
        _func_from("def test_x():\n    result = subject.run()\n    assert result == 'ok'\n")
    )

    # 5. empty/skipped
    assert is_empty_or_skipped(_func_from("def test_x():\n    pass\n"))
    assert is_empty_or_skipped(_func_from("@pytest.mark.skip\ndef test_x():\n    assert True\n"))
    assert not is_empty_or_skipped(
        _func_from("@pytest.mark.skip(reason='flaky')\ndef test_x():\n    assert True\n")
    )
    assert not is_empty_or_skipped(_func_from("def test_x():\n    x = compute()\n    assert x == 5\n"))

    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return
    root = argv[1] if len(argv) > 1 else "."
    findings = scan_path(root)
    for path, lineno, smell in findings:
        print(f"{path}:{lineno}: {smell}")
    if not findings:
        print("no mechanical smells found", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)
