#!/usr/bin/env python3
"""Pass one of mutation-audit: parse `mutmut results` text into candidate rows,
and suggest target modules when none is given.

mutmut 3.x has no clean structured export (see spec #365's recon) — `mutmut
results --all true` text is the stable contract: one line per mutant,
`    <module>.x_<func>__mutmut_<N>: <status>`. `parse_mutmut_results`
extracts every non-killed mutant mechanically into candidate rows — a
`survived` mutant as a `rewrite`, a `no tests` mutant as a `no-coverage`. A
killed mutant proves a test caught it and isn't a finding, so it is counted
and dropped; the killed/survived/no-coverage counts ride along in `extra` for
context. This parser never re-runs mutmut and never fills in the
real source line or a concrete before/after — `mutmut show <mutant>` gives a
diff normalized to the isolated mutant, not the file's real line numbers, so
resolving the real line means reading the target module. That's the judgment
pass in SKILL.md, same as dead-code's judgment pass reads code to re-bucket a
vulture hit — here it also fills `line`/`before`/`after`/`failure`.

`suggest_candidates` is the second seam: given a list of repo-relative `.py`
paths, return the subset worth mutation-testing — a module with a sibling
test file, skipping vendored/build/fixture/test files themselves. Pure, no
filesystem walk inside it; the caller collects `paths` (via `os.walk` or
similar) and hands them in. Never returns "everything" — an empty list is a
valid answer when nothing in scope looks testable.

ponytail: `survived` and `no tests` statuses feed rows — `survived` as a
`rewrite` candidate, `no tests` as a `no-coverage` one (mutmut's own marker
that no test reaches the mutant). `killed` is counted and dropped. mutmut's
remaining statuses (`timeout`, `suspicious`, `skipped`) aren't in the
ticket's contract and are ignored here.
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "all-audits", "harness"))
import auditlib  # noqa: E402

_RESULT_LINE_RE = re.compile(
    r"^\s*(?P<module>[\w.]+)\.x_(?P<func>\w+?)__mutmut_(?P<id>\d+):\s*(?P<status>.+?)\s*$"
)

_SKIP_DIRS = auditlib.EXCLUDED_DIRS


def parse_mutmut_results(text):
    """Parse `mutmut results --all true` text into surviving-mutant candidate rows.

    Pure: raw `mutmut results` stdout in, a list of findings-schema dict rows
    out — one per surviving mutant. mutmut's status IS the coverage signal:
    `survived` means a test runs the line but under-asserts (`bucket:
    rewrite`); `no tests` means no test reaches it at all (`bucket:
    no-coverage`). `killed` mutants are counted and dropped — they aren't
    findings. The judgment pass still reads the module to fill the real `line`
    and, for a `rewrite`, the before/after (and may re-bucket a `rewrite` to
    `cut`); it never re-derives coverage, since mutmut already marked it.
    `file`/`line` are best-effort here (`file` guessed from the dotted module
    name, `line` unknown) — SKILL.md's judgment pass overwrites both with the
    real target path and line once it reads `mutmut show <mutant>` against
    the actual source file.
    """
    rows = []
    killed_count = 0
    survived_count = 0
    no_coverage_count = 0
    for line in text.splitlines():
        m = _RESULT_LINE_RE.match(line)
        if not m:
            continue
        status = m.group("status").strip().lower()
        if status == "killed":
            killed_count += 1
            continue
        module = m.group("module")
        func = m.group("func")
        mutant = f"{module}.x_{func}__mutmut_{m.group('id')}"
        if status == "survived":
            # A test runs the line but doesn't assert hard enough — a covered
            # survivor. Pass two decides rewrite (default) vs cut.
            survived_count += 1
            bucket, extra = "rewrite", {"mutant": mutant, "killed": False, "survived": True}
        elif status == "no tests":
            # mutmut's own marker that no test reaches this mutant — a genuine
            # coverage hole, not a weak assertion. The fix is a new test, so
            # this bucket carries no before/after.
            no_coverage_count += 1
            bucket, extra = "no-coverage", {"mutant": mutant, "killed": False, "survived": False}
        else:
            continue  # ponytail: timeout/suspicious/skipped out of scope
        row = auditlib.finding(
            bucket,
            module.replace(".", "/") + ".py",
            None,
            "surviving-mutant",
            f"mutant survives in {func}() ({mutant})",
            **extra,
        )
        rows.append(row)
    for row in rows:
        row["extra"]["killed_count"] = killed_count
        row["extra"]["survived_count"] = survived_count
        row["extra"]["no_coverage_count"] = no_coverage_count
    return rows


def _sibling_tests(p):
    """The sibling-test paths for a mutation-worthy source module `p`, or
    `None` when `p` is not a worthy source module at all — an `__init__.py`, a
    test file, or anything under a skip/fixture dir. The single predicate both
    `suggest_candidates` (keep when a sibling exists) and `no_test_modules`
    (keep when none does) share, so the two can never drift apart.
    """
    parts = p.split("/")
    dirs, name = parts[:-1], parts[-1]
    if _SKIP_DIRS & set(dirs):
        return None
    if "fixtures" in dirs or "conftest" in name:
        return None
    if name == "__init__.py" or name.startswith("test_") or name.endswith("_test.py"):
        return None
    if not name.endswith(".py"):
        return None
    stem = name[: -len(".py")]
    return {
        "/".join([*dirs, f"test_{name}"]),
        "/".join([*dirs, f"{stem}_test.py"]),
    }


def suggest_candidates(paths):
    """Suggest candidate modules to mutation-test from repo state.

    Pure: a list of repo-relative `.py` paths in, candidate module paths out
    (sorted). A path is a candidate when it's a worthy source module (see
    `_sibling_tests`) AND a sibling test file exists for it in `paths` (mutmut
    needs a test suite to mutate against; a module with no tests is not a
    useful target — `no_test_modules` reports those instead). Never errors,
    never falls back to "everything" — an empty input or a repo with no
    testable module returns `[]`.
    """
    pathset = set(paths)
    candidates = []
    for p in paths:
        siblings = _sibling_tests(p)
        if siblings is not None and siblings & pathset:
            candidates.append(p)
    return sorted(candidates)


def no_test_modules(paths):
    """The worthy source modules in `paths` that have NO sibling test — the
    strict inverse of `suggest_candidates`' sibling filter over the same
    worthy universe. A worthy module with zero tests can't be mutated (mutmut
    has nothing to run), so it is the worst case — 0% coverage — not something
    to drop silently. Pure, sorted, uncapped; `[]` when every worthy module
    has a test.
    """
    pathset = set(paths)
    return sorted(
        p for p in paths
        if (siblings := _sibling_tests(p)) is not None and not (siblings & pathset)
    )


def _check_parsing():
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


def _check_candidate_selection():
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


def _check_cli_path():
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


_CHECKS = (_check_parsing, _check_candidate_selection, _check_cli_path)


def _selfcheck():
    """Run each named check in turn so a failure says which behaviour broke.

    The old `check_audit_module_is_not_globally_shared` witness is gone with
    the split (#609): there is no by-path module loader left to collide.
    """
    for fn in _CHECKS:
        try:
            fn()
        except Exception:
            print(f"FAIL {fn.__name__}", file=sys.stderr)
            traceback.print_exc()
            sys.exit(1)
    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return
    if argv[1:2] == ["--suggest"]:
        root = argv[2] if len(argv) > 2 else "."
        for candidate in suggest_candidates(auditlib.walk_source(root)):
            print(json.dumps({"candidate": candidate}))
        return
    if argv[1:2] == ["--no-tests"]:
        # The worthy source modules with no sibling test, plus the worthy-module
        # total, for the repo-wide "N of M source modules have no tests" stat.
        root = argv[2] if len(argv) > 2 else "."
        paths = auditlib.walk_source(root)
        worthy = sum(1 for p in paths if _sibling_tests(p) is not None)
        print(json.dumps({"no_tests": no_test_modules(paths), "total": worthy}))
        return
    text = sys.stdin.read() if len(argv) < 2 else open(argv[1], encoding="utf-8").read()
    for row in parse_mutmut_results(text):
        print(json.dumps(row))


if __name__ == "__main__":
    main(sys.argv)
