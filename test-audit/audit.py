#!/usr/bin/env python3
"""Pass one of test-audit: mechanical grep for the syntactically detectable smells.

Scans pytest-style test files and emits `file:line: <smell>` candidates for the
judgment pass (SKILL.md) to sort into Cut/Rewrite/Keep. This script never
classifies — it only surfaces candidates.

Ten detectors, nine small AST checks and one shell-source check:
  1. assertion-free   — no assert / pytest.raises / self.assert*, or only a
                         trivial `assert True` / `assert x is not None`.
  2. tautology         — `assert x == x` (same expression both sides).
  3. mock-the-world     — many Mock/MagicMock/patch constructs, few real calls.
  4. interaction-only   — the only checks are `assert_called*` / `.called`.
  5. empty/skipped      — `pass`-body test, or `@skip` with no reason.
  6. prose-assertion    — a test whose only assertions are that a prose file
                         (Markdown, a SKILL.md) contains or lacks a string.
                         Python tests are judged per function, `*.test.sh`
                         per file. A test that runs any code is never flagged
                         here: what it reads is the judgment pass's business.
  7. dead assertion   — a statement after the first call inside a
                         `with pytest.raises(...)` block: it never runs.
  8. lost test         — a second `def test_x` at one module or class scope
                         replaces the first; a `Test*` class that defines
                         `__init__` is never collected.
  9. broad exception   — `pytest.raises(Exception)` / `BaseException` with no
                         `match=`: it passes on the wrong error.
 10. non-strict xfail  — `@pytest.mark.xfail` without `strict=True`, when the
                         nearest pytest config does not set `xfail_strict`.

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
import configparser
import os
import re
import sys
import tomllib

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


def _interaction_check(node):
    """`(is_check, receiver)` for an assertion that a mock was called: `assert
    m.called` or `m.assert_called*(...)`. The receiver is the source text of
    `m`, None when the check is not on an attribute."""
    if isinstance(node, ast.Expr):
        node = node.value
    if isinstance(node, ast.Assert):
        test = node.test
        if isinstance(test, ast.Attribute) and test.attr == "called":
            return True, ast.unparse(test.value)
        node = test
    name = _bare_name(node)
    if name and name.startswith("assert_called"):
        func = node.func
        return True, ast.unparse(func.value) if isinstance(func, ast.Attribute) else None
    return False, None


def is_interaction_only(func):
    """4. interaction-only assertion — only checks that a mock was called."""
    checks = []
    for n in ast.walk(func):
        if isinstance(n, ast.Assert):
            checks.append(_interaction_check(n)[0])
        elif isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and _interaction_check(n.value)[0]:
            checks.append(True)
    if not checks:
        return False
    return all(checks)


STUB_SMELL = "stub asserted called"
STUB_KEYWORDS = frozenset({"return_value", "side_effect"})


def _has_stub_keyword(call):
    return isinstance(call, ast.Call) and any(kw.arg in STUB_KEYWORDS for kw in call.keywords)


def _patch_decorator_stubs(func):
    """Names of the parameters `@patch(..., return_value=...)` stubs. Decorators
    apply bottom-up, so the bottom one fills the first parameter."""
    patches = [d for d in reversed(func.decorator_list) if isinstance(d, ast.Call) and _call_name(d) in ("patch", "object")]
    params = [a.arg for a in func.args.args if a.arg not in ("self", "cls")]
    return {name for name, d in zip(params, patches) if _has_stub_keyword(d)}


def _stubbed_receivers(func):
    """Source text of every mock the test gives an input to: `m.return_value =`
    or `m.side_effect =` assigns it to `m`; `m = Mock(return_value=...)`, `with
    patch(..., return_value=...) as m` and `@patch(..., return_value=...)` give
    it to `m`."""
    stubbed = _patch_decorator_stubs(func)
    for n in ast.walk(func):
        if isinstance(n, ast.Assign):
            for target in n.targets:
                if isinstance(target, ast.Attribute) and target.attr in STUB_KEYWORDS:
                    stubbed.add(ast.unparse(target.value))
                elif _has_stub_keyword(n.value):
                    stubbed.add(ast.unparse(target))
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            stubbed.update(ast.unparse(i.optional_vars) for i in n.items if i.optional_vars and _has_stub_keyword(i.context_expr))
    return stubbed


def has_called_stub(func):
    """11. stub asserted called -- the same mock gets a `return_value` or
    `side_effect` and is also checked with `assert_called*` or `.called`.
    `is_interaction_only` misses this mixed form (SKILL.md: stub asserted
    called)."""
    stubbed = _stubbed_receivers(func)
    return any(_interaction_check(n)[1] in stubbed for n in ast.walk(func))


PRIVATE_SMELL = "private-API access"
VACUOUS_SMELL = "vacuous loop assertion"


def _is_private_name(name):
    """`_x` or `__x`, not a dunder such as `__class__`."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def has_private_access(func):
    """12. private-API access -- `x._name` on a receiver other than `self` or
    `cls`. It reaches into what a caller cannot see, so an internal rename
    turns the test red though no behavior changed. Candidate only: a stdlib
    `sys._getframe` reads the same, and the judgment pass tells them apart."""
    return any(
        isinstance(n, ast.Attribute)
        and _is_private_name(n.attr)
        and not (isinstance(n.value, ast.Name) and n.value.id in ("self", "cls"))
        for n in ast.walk(func)
    )


def private_imports(tree):
    """Lines of `from mod import _name`: the import form of private-API access,
    which sits at module scope, outside every test function."""
    return [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and any(_is_private_name(a.name) for a in n.names)
    ]


# Wrappers that pass their argument's contents through, so the iterable of
# `for i, x in enumerate(result)` is `result`. `range` and `len` are absent on
# purpose: they build numbers from nothing the code under test returned.
_PASS_THROUGH = frozenset({"enumerate", "zip", "sorted", "reversed", "list", "tuple", "set", "iter"})
_VIEW_METHODS = frozenset({"items", "values", "keys"})


def _is_literal(node):
    return isinstance(node, (ast.Constant, ast.List, ast.Tuple, ast.Set, ast.Dict))


def _is_output_call(call):
    """A call whose result is the code under test's: not a method on a literal
    (`[1, 2].copy()`) and not a call whose every argument is a literal
    (`sorted([1, 2])`)."""
    if isinstance(call.func, ast.Attribute) and _is_literal(call.func.value):
        return False
    return not (call.args and all(_is_literal(a) for a in call.args))


def _is_output_iterable(node, from_call):
    """Does iterating `node` walk something the code under test returned: a
    call's result, or a local name assigned from one (`from_call`)? A literal
    collection or a name the test never assigns (a module constant, a fixture)
    is a fixed input and is never empty by accident."""
    if isinstance(node, ast.Name):
        return node.id in from_call
    if isinstance(node, ast.Attribute):
        return _is_output_iterable(node.value, from_call)
    if not isinstance(node, ast.Call):
        return False
    name = _call_name(node)
    if name in _PASS_THROUGH and isinstance(node.func, ast.Name):
        return any(_is_output_iterable(a, from_call) for a in node.args)
    if name in _VIEW_METHODS and isinstance(node.func, ast.Attribute):
        return _is_output_iterable(node.func.value, from_call)
    return name not in ("range", "len") and _is_output_call(node)


def has_vacuous_loop_assertion(func):
    """13. vacuous loop assertion -- every assertion sits in the body of a
    `for` over what the code under test returned, so an empty result runs none
    of them and the test passes. Any assertion outside such a loop, a length or
    non-empty check included, clears it."""
    from_call = {
        t.id
        for n in ast.walk(func)
        if isinstance(n, ast.Assign) and any(isinstance(c, ast.Call) and _is_output_call(c) for c in ast.walk(n.value))
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    inside = set()
    for loop in ast.walk(func):
        if isinstance(loop, (ast.For, ast.AsyncFor)) and _is_output_iterable(loop.iter, from_call):
            inside.update(id(n) for stmt in loop.body for n in ast.walk(stmt))
    mechs = [m for m in _assertion_mechanisms(func) if not (isinstance(m, ast.Assert) and _is_trivial_assert(m))]
    return bool(mechs) and all(id(m) in inside for m in mechs)


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

# --- 7-10. exact-match smells -----------------------------------------------

LOST_DUPLICATE = "lost test (duplicate name)"
LOST_UNCOLLECTED = "lost test (uncollected class)"
BROAD_EXCEPTIONS = frozenset({"Exception", "BaseException"})


def has_dead_assertion_in_raises(func):
    """7. dead assertion — in a `with pytest.raises(...)` block, the first call
    is the one expected to raise, so every statement after the statement that
    holds it never runs and can never fail.

    ponytail: any statement after it counts, not only an `assert`, so the
    `with raises(E): setup(); target()` shape is a candidate too. The judgment
    pass tells a setup call that should sit outside the block from a target."""
    for node in ast.walk(func):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        if not any(_call_name(item.context_expr) == "raises" for item in node.items):
            continue
        for i, stmt in enumerate(node.body):
            if any(isinstance(n, ast.Call) for n in ast.walk(stmt)):
                if node.body[i + 1 :]:
                    return True
                break
    return False


def _expected_exception(call):
    """The exception argument of a `raises(...)` call, positional or by keyword."""
    if call.args:
        return call.args[0]
    return next((kw.value for kw in call.keywords if kw.arg == "expected_exception"), None)


def has_broad_raises(func):
    """9. broad exception expectation — `raises(Exception)` with no `match=`."""
    for node in ast.walk(func):
        if (
            _call_name(node) == "raises"
            and _name_of(_expected_exception(node)) in BROAD_EXCEPTIONS
            and not any(kw.arg == "match" for kw in node.keywords)
        ):
            return True
    return False


def is_nonstrict_xfail(func, xfail_strict):
    """10. non-strict xfail — `@pytest.mark.xfail` on a test function or a class
    that is not strict. Without
    a `strict=` keyword the ini decides (`xfail_strict`); a literal `strict=`
    wins over it. A non-literal `strict=` is unknown, so it is not flagged."""
    for dec in func.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if _name_of(target) != "xfail" or _name_of(getattr(target, "value", None)) != "mark":
            continue
        kws = dec.keywords if isinstance(dec, ast.Call) else []
        strict_kw = next((kw for kw in kws if kw.arg == "strict"), None)
        if strict_kw is None:
            strict = xfail_strict
        elif isinstance(strict_kw.value, ast.Constant):
            strict = bool(strict_kw.value.value)
        else:
            continue
        if not strict:
            return True
    return False


def lost_tests(tree):
    """8. lost test — yield `(lineno, smell)`. A name defined twice among one
    scope's direct statements loses all but its last definition; the shadowed
    ones are reported, in a unittest.TestCase class too. A `Test*` class with
    `__init__` and a test method is never collected; a TestCase is collected by
    unittest's rules, so it is exempt from that one."""
    all_classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    classes = [c for c in all_classes if not _is_unittest_testcase(c)]
    for body in [tree.body] + [c.body for c in all_classes]:
        by_name = {}
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith("test_"):
                by_name.setdefault(stmt.name, []).append(stmt.lineno)
        for linenos in by_name.values():
            for lineno in linenos[:-1]:
                yield lineno, LOST_DUPLICATE
    for cls in classes:
        funcs = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if (
            cls.name.startswith("Test")
            and any(f.name == "__init__" for f in funcs)
            and any(f.name.startswith("test_") for f in funcs)
        ):
            yield cls.lineno, LOST_UNCOLLECTED


# pytest 9 renamed `xfail_strict` to `strict_xfail` and keeps the old name as an
# alias; the umbrella `strict` option turns the strict family on together.
XFAIL_STRICT_KEYS = ("strict_xfail", "xfail_strict")
_TRUE_WORDS = frozenset({"1", "true", "yes", "on"})


def _truthy(value):
    return value is True or (isinstance(value, str) and value.strip().lower() in _TRUE_WORDS)


def _strictness(options):
    for key in XFAIL_STRICT_KEYS:
        if key in options:
            return _truthy(options[key])
    return _truthy(options.get("strict", False))


def _read_ini(path, section):
    parser = configparser.RawConfigParser()
    # read_file, not read: `read` skips a file it cannot open without a word,
    # which would let a parent directory's config decide in its place.
    with open(path, encoding="utf-8") as f:
        parser.read_file(f)
    return dict(parser[section]) if parser.has_section(section) else None


def _pytest_options(directory):
    """The pytest options of the config file that configures pytest in
    `directory`, in pytest's own precedence order, or None when no file there
    does. A file that matches but cannot be read yields `{}`: unreadable is not
    strict, so its xfail markers are flagged rather than waved through."""
    for name in ("pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg"):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            if name.endswith(".toml"):
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                if name == "pyproject.toml":
                    table = data.get("tool", {}).get("pytest")
                    if table is None:
                        continue
                    options = {**table, **table.get("ini_options", {})}
                else:
                    options = data.get("pytest", {})
            elif name in ("pytest.ini", ".pytest.ini"):
                options = _read_ini(path, "pytest") or {}
            else:
                options = _read_ini(path, "pytest" if name == "tox.ini" else "tool:pytest")
                if options is None:
                    continue
        except (OSError, ValueError, TypeError, AttributeError, configparser.Error):
            # ValueError covers a TOML syntax error and a bad encoding; the
            # others a config that parses to the wrong shape.
            return {}
        return options
    return None


def xfail_strict_for(path):
    """Does the pytest config nearest `path` make xfail strict? Walks up from
    the file to the first config that configures pytest, stopping at a repo
    boundary (a directory holding `.git`), as pytest's rootdir search would
    settle on the project's own file. No config is not strict."""
    directory = os.path.dirname(os.path.abspath(path))
    strict = False
    while True:
        options = _pytest_options(directory)
        if options is not None:
            strict = _strictness(options)
            break
        parent = os.path.dirname(directory)
        if os.path.exists(os.path.join(directory, ".git")) or parent == directory:
            break
        directory = parent
    return strict


# --- 6. prose-assertion ------------------------------------------------------

PROSE_FILE = re.compile(r"\.md\b")
# A call outside this set might run code under test, so the test is not a pure
# prose assertion. The set is file reads and string handling only; anything
# else (a subprocess, an imported function) keeps the test out of the category
# and leaves it to the judgment pass.
PROSE_OK_BUILTINS = frozenset({"Path", "open", "str", "len", "sorted", "set", "list", "any", "all"})
# Methods on any receiver: file reads and string handling.
PROSE_OK_METHODS = frozenset(
    {
        "read", "read_text", "read_bytes", "lower", "upper",
        "strip", "lstrip", "rstrip", "split", "splitlines", "replace", "startswith", "endswith", "find",
        "index", "count", "decode", "group",
    }
)
# Methods whose names are generic enough to belong to code under test, so they
# count only on the stdlib module that owns them.
PROSE_OK_MODULE_METHODS = {
    "re": frozenset({"search", "match", "fullmatch", "findall", "sub", "compile", "escape"}),
    "path": frozenset({"join", "dirname", "abspath", "exists"}),
}
# Shell commands that only read or reshape text. Same idea as PROSE_OK_CALLS.
SHELL_OK_WORDS = frozenset(
    {
        "grep", "egrep", "fgrep", "sed", "tr", "cat", "awk", "test", "[", "[[", "echo", "printf", "cd",
        "dirname", "pwd", "set", "case", "esac", "for", "do", "done", "if", "then", "else", "elif", "fi",
        "while", "read", "local", "return", "exit", "shift", "true", "false", ":", "head", "tail", "wc",
        "sort", "cut", "uniq", "basename", "readlink", "unset", "export", "declare", "!", "{", "}", ";;",
        "((", "unset",
    }
)


def _is_containment_assert(node):
    """True for `assert x in y`, `assert x not in y`, `assert not x in y`, and
    a bare `assert re.search(...)` / `assert not re.search(...)`."""
    test = node.test
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        test = test.operand
    if isinstance(test, ast.Compare):
        return all(isinstance(op, (ast.In, ast.NotIn)) for op in test.ops)
    return _call_name(test) in {"search", "match", "fullmatch", "findall"}


def _is_prose_call(call):
    """A file read or string handling, not a call into code under test."""
    f = call.func
    if isinstance(f, ast.Name):
        return f.id in PROSE_OK_BUILTINS
    if isinstance(f, ast.Attribute):
        if f.attr in PROSE_OK_METHODS:
            return True
        # Path operations, only on a path built in place: `Path(x).resolve()`.
        if f.attr in {"resolve", "exists", "is_file", "joinpath"} and isinstance(f.value, (ast.Call, ast.BinOp)):
            return True
        owner = _name_of(f.value)
        return f.attr in PROSE_OK_MODULE_METHODS.get(owner, ())
    return False


def _prose_names(tree):
    """Module-level names bound from an expression that spells a `.md` path."""
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            consts = [
                n.value for n in ast.walk(node.value) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
            if any(PROSE_FILE.search(c) for c in consts):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def is_prose_assertion(func, prose_names=frozenset()):
    """6. prose-assertion (Python) — every assertion is a containment check,
    the test reads a prose file, and it calls nothing but file reads and
    string handling."""
    mechs = _assertion_mechanisms(func)
    if not mechs or not all(isinstance(m, ast.Assert) and _is_containment_assert(m) for m in mechs):
        return False
    reads_prose = any(
        (isinstance(n, ast.Constant) and isinstance(n.value, str) and PROSE_FILE.search(n.value))
        or (isinstance(n, ast.Name) and n.id in prose_names)
        for n in ast.walk(func)
    )
    if not reads_prose:
        return False
    return all(_is_prose_call(n) for n in ast.walk(func) if isinstance(n, ast.Call))


def _shell_command_words(source):
    """The first word of every command in a shell script, comments dropped.
    Quoted text and `${...}` expansions are blanked first, except a quoted
    string holding a `$(` command substitution. A word the blanking misses
    can only make the script look more like code, never less."""
    words = []
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # A `${...}` holding a command substitution is code, so it stays.
        line = re.sub(r"\$\{[^}$`]*\}", "", line)
        line = re.sub(r"'[^']*'", "''", line)
        # A quoted string is blanked unless it holds a command substitution. One
        # in command position is the command itself (`"$here/run.sh"`), so it
        # becomes a word no text command matches.
        def _blank(m):
            before = line[: m.start()].rstrip()
            at_command = not before or before.endswith(("|", "&", ";", "(", "{", "then", "do", "else"))
            return "EXECQUOTED" if at_command else '""'

        line = re.sub(r'"((?:[^"\\$`]|\\.|\$(?!\())*)"', _blank, line)
        line = re.sub(r"\s#.*$", "", line)  # a trailing comment
        for part in re.split(r"\|\||&&|;|\||\$\(|`|\(|\{", line):
            tokens = part.split()
            while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
                tokens.pop(0)
            if tokens:
                word = tokens[0].rstrip(")'\"")
                # a case-arm pattern (`*"x"*)`) or a bare `)` is data, not a command
                if word and not word.startswith(("*", ")")):
                    words.append(word)
    return words


def is_shell_prose_test(source):
    """6. prose-assertion (shell) — a `*.test.sh` that names a Markdown file
    and runs nothing but text commands (`grep`, `sed`, `case`, `test`, ...)
    or functions it defines itself."""
    code = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
    if not PROSE_FILE.search(code):
        return False
    defined = set(re.findall(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)", source, re.M))
    for word in _shell_command_words(source):
        if word not in SHELL_OK_WORDS and word not in defined:
            return False
    return True


DETECTORS = [
    ("assertion-free test", is_assertion_free),
    ("tautology", is_tautology),
    ("mock-the-world", is_mock_the_world),
    ("interaction-only assertion", is_interaction_only),
    ("empty/skipped test", is_empty_or_skipped),
    ("dead assertion in an expect-exception block", has_dead_assertion_in_raises),
    ("broad exception expectation", has_broad_raises),
    (STUB_SMELL, has_called_stub),
    (PRIVATE_SMELL, has_private_access),
    (VACUOUS_SMELL, has_vacuous_loop_assertion),
]


PROSE_SMELL = "prose-assertion"


def _is_pytest_file(path, tree):
    base = os.path.basename(path)
    if not (base.startswith("test_") or base.endswith("_test.py")):
        return False
    return any(True for _ in _test_functions(tree))


def scan_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError:
        # A file we cannot read is skipped, mirroring audit.mjs's scanFile.
        # Without this an unreadable file raised through `main` and the process
        # exited 1, which under the gate's contract means "hollow tests found".
        return []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    if not _is_pytest_file(path, tree):
        return []
    findings = []
    prose_names = _prose_names(tree)
    xfail_strict = xfail_strict_for(path)
    for func in _test_functions(tree):
        for smell, detector in DETECTORS:
            if detector(func):
                findings.append((path, func.lineno, smell))
        if is_prose_assertion(func, prose_names):
            findings.append((path, func.lineno, PROSE_SMELL))
        if is_nonstrict_xfail(func, xfail_strict):
            findings.append((path, func.lineno, "non-strict xfail"))
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and not _is_unittest_testcase(n)):
        if is_nonstrict_xfail(cls, xfail_strict):
            findings.append((path, cls.lineno, "non-strict xfail"))
    findings.extend((path, lineno, smell) for lineno, smell in lost_tests(tree))
    findings.extend((path, lineno, PRIVATE_SMELL) for lineno in private_imports(tree))
    return findings


def scan_shell_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError:
        return []
    return [(path, 1, PROSE_SMELL)] if is_shell_prose_test(source) else []


def scan_path(root):
    if os.path.isfile(root):
        paths = [root]
    else:
        paths = [os.path.join(root, rel) for rel in auditlib.walk_source(root)]
        paths += [os.path.join(root, rel) for rel in auditlib.walk_source(root, suffix=".test.sh")]
    findings = []
    for path in paths:
        findings.extend(scan_shell_file(path) if path.endswith(".test.sh") else scan_file(path))
    return findings


# --- gate mode -------------------------------------------------------------

# The smells a build gates on, each with the label its fixtures-suppression
# count is reported under. SKILL.md § Gate mode says why these two and no other.
GATE_SMELLS = {"assertion-free test": "assertion-free", LOST_DUPLICATE: "duplicate-name"}

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
    """`(findings, suppressed)` -- the `GATE_SMELLS` findings that fail a build,
    and how many the fixtures exemption dropped, per `GATE_SMELLS` label.

    The count is returned, and reported by `main`, because `_under_fixtures`
    matches a `fixtures` segment at any depth: without it a repo could park
    hollow tests under any directory it named `fixtures` and never see that
    the gate had stopped looking at them (#685)."""
    gated = [f for f in scan_path(root) if f[2] in GATE_SMELLS]
    findings = [f for f in gated if not _under_fixtures(f[0])]
    suppressed = {}
    for path, _, smell in gated:
        if _under_fixtures(path):
            suppressed[GATE_SMELLS[smell]] = suppressed.get(GATE_SMELLS[smell], 0) + 1
    return findings, suppressed


def main(argv):
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
    # The same lie by a different errno: a root that exists but cannot be read
    # walks to zero files, which is indistinguishable from a clean tree. Only
    # the root is checked here -- an unreadable directory deeper in the tree is
    # still swallowed by `os.walk`, which is a wider fix than #685 asked for.
    # A directory needs X_OK as well: R_OK alone lists it, but opening the
    # files inside it still fails, so the walk yields nothing.
    needed = os.R_OK | os.X_OK if os.path.isdir(root) else os.R_OK
    if not os.access(root, needed):
        print(f"test-audit: cannot read {root} -- nothing was scanned.", file=sys.stderr)
        return EXIT_UNABLE
    if gate_mode:
        findings, suppressed = gate(root)
        for path, lineno, smell in findings:
            print(f"{path}:{lineno}: {smell}")
        for label, count in suppressed.items():
            print(f"test-audit: {count} {label} finding(s) suppressed under fixtures/.", file=sys.stderr)
        if findings:
            print(
                f"test-audit: {len(findings)} test(s) that cannot fail -- a test that cannot fail proves nothing.",
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
