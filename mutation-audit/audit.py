#!/usr/bin/env python3
"""Pass one of mutation-audit: parse `mutmut results` text into candidate rows,
and suggest target modules when none is given.

mutmut 3.x has no clean structured export (see spec #365's recon) — `mutmut
results --all true` text is the stable contract: one line per mutant,
`    <module>.x_<func>__mutmut_<N>: <status>`. `parse_mutmut_results`
extracts the SURVIVING mutants mechanically into test-audit-vocabulary
candidate rows; a killed mutant proves a test caught it and isn't a finding,
so only survivors turn into rows (killed/survived counts still ride along in
`extra` for context). This parser never re-runs mutmut and never fills in the
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

ponytail: only `killed`/`survived` statuses feed rows — mutmut's other
statuses (`timeout`, `suspicious`, `skipped`) aren't in the ticket's contract;
they're counted towards neither killed_count nor survived_count and are
otherwise ignored here.
"""
import json
import os
import re
import sys

_RESULT_LINE_RE = re.compile(
    r"^\s*(?P<module>[\w.]+)\.x_(?P<func>\w+?)__mutmut_(?P<id>\d+):\s*(?P<status>\w+)\s*$"
)

_SKIP_DIRS = {"node_modules", "dist", "build", ".venv", "venv", "vendor", "worktrees", "mutants"}


def parse_mutmut_results(text):
    """Parse `mutmut results --all true` text into surviving-mutant candidate rows.

    Pure: raw `mutmut results` stdout in, a list of findings-schema dict rows
    out — one per SURVIVING mutant. `bucket` defaults to "rewrite" (test-audit's
    default-when-unsure bucket: a surviving mutant means a test already
    exercises that path, just not hard enough — deciding `cut` instead needs
    the judgment pass confirming the covering test proves nothing at all).
    `file`/`line` are best-effort here (`file` guessed from the dotted module
    name, `line` unknown) — SKILL.md's judgment pass overwrites both with the
    real target path and line once it reads `mutmut show <mutant>` against
    the actual source file.
    """
    rows = []
    killed_count = 0
    survived_count = 0
    for line in text.splitlines():
        m = _RESULT_LINE_RE.match(line)
        if not m:
            continue
        status = m.group("status").strip().lower()
        if status == "killed":
            killed_count += 1
            continue
        if status != "survived":
            continue  # ponytail: timeout/suspicious/skipped out of scope
        survived_count += 1
        module = m.group("module")
        func = m.group("func")
        mutant = f"{module}.x_{func}__mutmut_{m.group('id')}"
        rows.append(
            {
                "bucket": "rewrite",
                "file": module.replace(".", "/") + ".py",
                "line": None,
                "category": "surviving-mutant",
                "summary": f"mutant survives in {func}() ({mutant})",
                "failure": f"the mutation at {mutant} survives — no test fails when {func}() is mutated",
                "extra": {"mutant": mutant, "killed": False, "survived": True},
            }
        )
    for row in rows:
        row["extra"]["killed_count"] = killed_count
        row["extra"]["survived_count"] = survived_count
    return rows


def suggest_candidates(paths, limit=5):
    """Suggest candidate modules to mutation-test from repo state.

    Pure: a list of repo-relative `.py` paths in, up to `limit` candidate
    module paths out (sorted). A path is a candidate when it's a plain
    module — not `__init__.py`, not a test file, not under a skip/fixture
    dir — AND a sibling test file exists for it in `paths` (mutmut needs a
    test suite to mutate against; a module with no tests is not a useful
    target). Never errors, never falls back to "everything" — an empty
    input or a repo with no testable module returns `[]`.
    """
    pathset = set(paths)
    candidates = []
    for p in paths:
        parts = p.split("/")
        dirs, name = parts[:-1], parts[-1]
        if _SKIP_DIRS & set(dirs):
            continue
        if "fixtures" in dirs or "conftest" in name:
            continue
        if name == "__init__.py" or name.startswith("test_") or name.endswith("_test.py"):
            continue
        if not name.endswith(".py"):
            continue
        stem = name[: -len(".py")]
        sibling_tests = {
            "/".join([*dirs, f"test_{name}"]),
            "/".join([*dirs, f"{stem}_test.py"]),
        }
        if sibling_tests & pathset:
            candidates.append(p)
    return sorted(candidates)[:limit]


def _selfcheck():
    sample = "\n".join(
        [
            "    sample.x_is_adult__mutmut_1: killed",
            "    sample.x_is_adult__mutmut_2: killed",
            "    sample.x_clamp__mutmut_1: survived",
            "    sample.x_clamp__mutmut_2: survived",
        ]
    )
    rows = parse_mutmut_results(sample)
    assert len(rows) == 2, rows

    assert rows[0]["file"] == "sample.py"
    assert rows[0]["line"] is None
    assert rows[0]["bucket"] == "rewrite"
    assert rows[0]["category"] == "surviving-mutant"
    assert rows[0]["extra"]["mutant"] == "sample.x_clamp__mutmut_1"
    assert rows[0]["extra"]["killed"] is False
    assert rows[0]["extra"]["survived"] is True
    assert rows[0]["extra"]["killed_count"] == 2
    assert rows[0]["extra"]["survived_count"] == 2
    assert "sample.x_clamp__mutmut_1" in rows[0]["failure"]
    assert "clamp" in rows[0]["failure"]

    assert rows[1]["extra"]["mutant"] == "sample.x_clamp__mutmut_2"

    no_survivors = parse_mutmut_results("    sample.x_is_adult__mutmut_1: killed")
    assert no_survivors == []

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

    limited = suggest_candidates(paths, limit=1)
    assert limited == ["pkg/gadget.py"], limited

    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return
    if argv[1:2] == ["--suggest"]:
        root = argv[2] if len(argv) > 2 else "."
        paths = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for filename in filenames:
                if filename.endswith(".py"):
                    rel = os.path.relpath(os.path.join(dirpath, filename), root)
                    paths.append(rel.replace(os.sep, "/"))
        for candidate in suggest_candidates(paths):
            print(json.dumps({"candidate": candidate}))
        return
    text = sys.stdin.read() if len(argv) < 2 else open(argv[1], encoding="utf-8").read()
    for row in parse_mutmut_results(text):
        print(json.dumps(row))


if __name__ == "__main__":
    main(sys.argv)
