#!/usr/bin/env python3
"""Pass one of mutation-audit: parse `mutmut results` text (Python) or a
StrykerJS JSON report (`.mjs`/`.js`) into candidate rows, and suggest target
modules when none is given.

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

`parse_stryker_report` is the same seam for a JS target: Stryker's `Survived`
-> `rewrite`, `NoCoverage` -> `no-coverage`, `Killed`/`Timeout` counted and
dropped, and it carries the real source line.

`suggest_candidates` is the second seam: given a list of repo-relative `.py`,
`.mjs` and `.js` paths, return the subset worth mutation-testing — a module
with a sibling test file, skipping vendored/build/fixture/test files themselves. Pure, no
filesystem walk inside it; the caller collects `paths` (via `os.walk` or
similar) and hands them in. Never returns "everything" — an empty list is a
valid answer when nothing in scope looks testable.

`survived` and `no tests` statuses feed rows — `survived` as a
`rewrite` candidate, `no tests` as a `no-coverage` one (mutmut's own marker
that no test reaches the mutant). `killed` is counted and dropped. mutmut's
remaining statuses (`timeout`, `suspicious`, `skipped`) raise `Inconclusive`:
ignoring them would read as a clean run.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "all-audits", "harness"))
import auditlib  # noqa: E402

_RESULT_LINE_RE = re.compile(
    r"^\s*(?P<module>[\w.]+)\.x_(?P<func>\w+?)__mutmut_(?P<id>\d+):\s*(?P<status>.+?)\s*$"
)


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
            # timeout/suspicious/skipped: neither killed nor a finding, so
            # dropping it would read as a clean run (#962).
            raise Inconclusive(f"mutant {mutant} has status {status!r}, which this audit does not judge")
        row = auditlib.finding(
            bucket,
            module.replace(".", "/") + ".py",
            None,
            "surviving-mutant",
            f"mutant survives in {func}() ({mutant})",
            **extra,
        )
        rows.append(row)
    return _stamp_counts(rows, killed_count, survived_count, no_coverage_count)


def _stamp_counts(rows, killed_count, survived_count, no_coverage_count):
    """Stamp the run's three counts on every row's `extra`, the keys the
    all-audits driver's mutation tally reads. Both parsers end here."""
    for row in rows:
        row["extra"]["killed_count"] = killed_count
        row["extra"]["survived_count"] = survived_count
        row["extra"]["no_coverage_count"] = no_coverage_count
    return rows


class Inconclusive(Exception):
    """The audit could not produce a verdict: distinct from a clean run."""


INCONCLUSIVE_EXIT = 3

STRYKER_VERSION = "10.0.0"

# Stryker statuses that carry no verdict of their own: its own score leaves
# them out of the tally, so they are neither killed nor a finding.
_STRYKER_NOT_RUN = frozenset({"CompileError", "Ignored"})


def parse_or_inconclusive(text):
    """`parse_mutmut_results`, but text holding no mutant line at all (mutmut
    absent, misconfigured, or crashed before reporting) raises `Inconclusive`
    instead of returning `[]`, which reads as a clean run (#962)."""
    if not any(_RESULT_LINE_RE.match(line) for line in text.splitlines()):
        raise Inconclusive("no mutant lines in mutmut's results; mutmut did not report a run")
    return parse_mutmut_results(text)


def _run_bounded(args, target):
    """Run `args` to completion in its own process group and return the
    `CompletedProcess`. Past `MUTATION_AUDIT_TIMEOUT` seconds (default 3600)
    the whole group is killed and `Inconclusive` raised: killing only the
    direct child (`npx`, `uvx`) would leave the tool it started running and
    writing into the audited checkout."""
    limit = float(os.environ.get("MUTATION_AUDIT_TIMEOUT", "3600"))
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            stdin=subprocess.DEVNULL, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise Inconclusive(f"`{' '.join(args)}` timed out after {limit:g}s (target {target})") from None
    return subprocess.CompletedProcess(args, proc.returncode, out, err)


def _output_tail(run):
    return "\n".join((run.stdout + run.stderr).strip().splitlines()[-5:])


def run_mutmut(target):
    """Run mutmut through `uvx` in the cwd and return its `results --all true`
    text. Raises `Inconclusive`, saying why, when uvx is missing, a mutmut
    command fails, or one outlives `MUTATION_AUDIT_TIMEOUT` seconds (default
    3600). Never installs anything. `target` is for the messages only: what
    mutmut mutates is the `source_paths` config SKILL.md step 3 writes."""
    if shutil.which("uvx") is None:
        raise Inconclusive(f"mutmut unavailable: `uvx` is not on PATH, so nothing was mutated (target {target})")
    run = _run_bounded(["uvx", "--with", "pytest", "mutmut", "run"], target)
    if run.returncode != 0:
        raise Inconclusive(f"mutmut run failed (exit {run.returncode}) (target {target}):\n{_output_tail(run)}")
    res = _run_bounded(["uvx", "mutmut", "results", "--all", "true"], target)
    if res.returncode != 0:
        raise Inconclusive(f"mutmut results failed (exit {res.returncode}): {res.stderr.strip()}")
    return res.stdout


def parse_stryker_report(text):
    """Parse a StrykerJS `json` reporter report into surviving-mutant rows.

    Pure, like `parse_mutmut_results`. `Survived` -> `rewrite`, `NoCoverage` ->
    `no-coverage`; `Killed` and `Timeout` (a hung mutant was caught) are
    counted into `killed_count` and dropped. `CompileError` and `Ignored`
    never ran, and Stryker's own score leaves them out too. Anything else
    (`RuntimeError`, `Pending`, an unknown status) raises `Inconclusive`: the
    mutant was not judged, and dropping it would read as a clean run. So does
    a report in which no mutant was judged at all (none, or all `Ignored`/
    `CompileError`): `[]` is for a run whose every mutant was killed. Unlike
    mutmut, the report carries the real source `line`.
    """
    try:
        report = json.loads(text)
        files = report["files"]
    except (ValueError, KeyError, TypeError) as e:
        raise Inconclusive(f"not a Stryker JSON report ({type(e).__name__}: {e})") from None
    rows = []
    killed_count = survived_count = no_coverage_count = 0
    for path, entry in files.items():
        for m in entry["mutants"]:
            status = m["status"]
            if status in ("Killed", "Timeout"):
                killed_count += 1
                continue
            if status in _STRYKER_NOT_RUN:
                continue
            line = m["location"]["start"]["line"]
            mutant = f"{path}:{line}:{m['mutatorName']}#{m['id']}"
            if status == "Survived":
                survived_count += 1
                bucket, extra = "rewrite", {"mutant": mutant, "killed": False, "survived": True}
            elif status == "NoCoverage":
                no_coverage_count += 1
                bucket, extra = "no-coverage", {"mutant": mutant, "killed": False, "survived": False}
            else:
                raise Inconclusive(f"mutant {mutant} has status {status!r}, which this audit does not judge")
            rows.append(auditlib.finding(
                bucket, path, line, "surviving-mutant",
                f"mutant survives at {path}:{line} ({m['mutatorName']}, {mutant})", **extra))
    if killed_count + survived_count + no_coverage_count == 0:
        raise Inconclusive("Stryker's report holds no judged mutant; it did not mutate the target")
    rows.sort(key=lambda r: (r["file"], r["line"], int(r["extra"]["mutant"].rsplit("#", 1)[1])))
    return _stamp_counts(rows, killed_count, survived_count, no_coverage_count)


def js_test_file(target):
    """The sibling test file of a `.mjs`/`.js` target (`_sibling_tests`' rule),
    or `None` when the target is not a worthy module or none exists."""
    return next((t for t in sorted(_sibling_tests(target) or ()) if os.path.isfile(t)), None)


def run_stryker(target):
    """Run StrykerJS's tap runner on one `.mjs`/`.js` target, from the cwd,
    and return its JSON report text. Raises `Inconclusive`, saying why, when
    `npx` or the sibling test file is missing, Stryker fails or outlives
    `MUTATION_AUDIT_TIMEOUT`, or it wrote no report.

    Only the target's own test file is passed: the tap runner's workers write
    `stryker-output-<pid>.json` into the shared sandbox root, which a test
    that lists the repo root reads as false kills. The JSON reporter is
    pointed at a temp dir through a config file passed by path, so no
    `reports/` lands in the audited checkout (Stryker removes `.stryker-tmp/`
    itself on a normal exit; a timeout kills its whole process group). The audited repo's `package.json` is untouched: the packages come
    from `npx -p`.
    """
    if shutil.which("npx") is None:
        raise Inconclusive(f"StrykerJS unavailable: `npx` is not on PATH, so nothing was mutated (target {target})")
    test_file = js_test_file(target)
    if test_file is None:
        raise Inconclusive(f"no sibling test file for {target} (looked for <stem>.test.mjs and <stem>.test.js); nothing to mutate against")
    with tempfile.TemporaryDirectory() as out:
        report = os.path.join(out, "report.json")
        conf = os.path.join(out, "stryker.conf.json")
        with open(conf, "w", encoding="utf-8") as f:
            json.dump({"jsonReporter": {"fileName": report}}, f)
        args = ["npx", "-y", "-p", f"@stryker-mutator/core@{STRYKER_VERSION}",
                "-p", f"@stryker-mutator/tap-runner@{STRYKER_VERSION}", "stryker", "run", conf,
                "--testRunner", "tap", "--coverageAnalysis", "perTest",
                "--mutate", target, "--testFiles", test_file, "--reporters", "clear-text,json"]
        run = _run_bounded(args, target)
        if run.returncode != 0:
            raise Inconclusive(f"stryker run failed (exit {run.returncode}) (target {target}):\n{_output_tail(run)}")
        try:
            with open(report, encoding="utf-8") as f:
                return f.read()
        except OSError:
            raise Inconclusive(f"stryker run wrote no JSON report (target {target})") from None


def _sibling_tests(p):
    """The test paths for a mutation-worthy source module `p` (beside it, or
    under a root `tests/` tree, see below), or `None` when `p` is not a worthy
    source module at all — an `__init__.py`, a test file, or anything under a
    skip/fixture dir (the shared `auditlib.is_test_or_fixture` check, #611).
    The single predicate both `suggest_candidates` (keep when a test exists)
    and `no_test_modules` (keep when none does) share, so the two can never
    drift apart.
    """
    if auditlib.is_test_or_fixture(p):
        return None
    parts = p.split("/")
    dirs, name = parts[:-1], parts[-1]
    stem = name[: name.rindex(".")]
    if name.endswith(auditlib.JS_SUFFIXES):
        return {"/".join([*dirs, f"{stem}.test.mjs"]), "/".join([*dirs, f"{stem}.test.js"])}
    # A `src/` layout keeps tests in a root `tests/` tree: flat, or mirroring
    # the module's path below `src/` (below the repo root, with no `src/`).
    mirror = dirs[1:] if dirs[:1] == ["src"] else dirs
    return {
        "/".join([*base, leaf])
        for base in (dirs, ["tests"], ["tests", *mirror])
        for leaf in (f"test_{name}", f"{stem}_test.py")
    }


def _source_paths(root):
    """Every `.py`, `.mjs` and `.js` path under `root`, in one walk."""
    return auditlib.walk_source(root, (".py", *auditlib.JS_SUFFIXES))


def suggest_candidates(paths):
    """Suggest candidate modules to mutation-test from repo state.

    Pure: a list of repo-relative `.py`/`.mjs`/`.js` paths in, candidate module paths out
    (sorted). A path is a candidate when it's a worthy source module (see
    `_sibling_tests`) AND one of those test files exists for it in `paths` (the
    mutation tool needs a test suite to mutate against; a module with no tests is not a
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
    worthy universe. A worthy module with zero tests can't be mutated (the tool
    has nothing to run), so it is the worst case — 0% coverage — not something
    to drop silently. Pure, sorted, uncapped; `[]` when every worthy module
    has a test.
    """
    pathset = set(paths)
    return sorted(
        p for p in paths
        if (siblings := _sibling_tests(p)) is not None and not (siblings & pathset)
    )


def plan(repo):
    """What a mutation sweep of `repo` works from, in one walk: `candidates`
    (worthy modules with a sibling test, as `suggest_candidates`), `no_tests`
    (worthy modules with none), `total` (the worthy modules), and `siblings`
    ({candidate: its possible sibling test paths, sorted}). The one public
    entry the all-audits driver reads, so it never reaches `_sibling_tests`.
    """
    paths = _source_paths(repo)
    candidates = suggest_candidates(paths)
    return {
        "candidates": candidates,
        "no_tests": no_test_modules(paths),
        "total": sum(1 for p in paths if _sibling_tests(p) is not None),
        "siblings": {c: sorted(_sibling_tests(c)) for c in candidates},
    }


def main(argv):
    if argv[1:2] in (["--suggest"], ["--no-tests"]):
        planned = plan(argv[2] if len(argv) > 2 else ".")
        if argv[1] == "--suggest":
            for candidate in planned["candidates"]:
                print(json.dumps({"candidate": candidate}))
        else:
            # The worthy source modules with no sibling test, plus the worthy-module
            # total, for the repo-wide "N of M source modules have no tests" stat.
            print(json.dumps({"no_tests": planned["no_tests"], "total": planned["total"]}))
        return
    try:
        if argv[1:2] == ["--run"]:
            if len(argv) < 3:
                print("usage: audit.py --run <target-module.py|.mjs|.js>", file=sys.stderr)
                sys.exit(1)
            if argv[2].endswith(auditlib.JS_SUFFIXES):
                rows = parse_stryker_report(run_stryker(argv[2]))
            else:
                rows = parse_or_inconclusive(run_mutmut(argv[2]))
            for row in rows:
                print(json.dumps(row))
            return
        # The file/stdin parse path goes through auditlib.run_cli.
        auditlib.run_cli(argv, parse_or_inconclusive)
    except Inconclusive as e:
        print(f"INCONCLUSIVE: {e}", file=sys.stderr)
        sys.exit(INCONCLUSIVE_EXIT)


if __name__ == "__main__":
    main(sys.argv)
