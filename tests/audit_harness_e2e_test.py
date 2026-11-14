"""End-to-end test for spec #1729: the audit harness and the audit skills.

Each slice's public entry, driven the way a sweep or a seam run reaches it:

- every audit's self-checks are ordinary tests: no audit script carries a
  `--selfcheck`, each has a `*_test.py` beside it, and `tests/all.sh --list`
  selects it by the one Python rule (#1743, #1744);
- the sweep driver's modes are subcommands that refuse a flag they do not take
  (#1747);
- `findings_log` names a corrupt line instead of skipping it (#1748);
- a repo whose tracked source holds no Python is "not applicable" to the
  Python-only audits, and an untracked stray `.py` does not change that
  (#1751);
- crap-audit's CLI scores a class method once (#1752);
- mutation-audit's public `plan(repo)` is the one planning interface (#1746);
- comment-audit's answer key carries the three mis-cuts (#1750).

What a green run does NOT cover (the seam is blind to it):
- whether a model follows the audit SKILL.md files: comment-audit's per-row
  judgement and each audit's step 0 are prose a model reads, and only a real
  sweep exercises them;
- a real sweep against GitHub and `claude`: the driver is driven here only up
  to argument parsing, so nothing below spawns an audit.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPTS = [
    "crap-audit/audit.py", "dead-code/audit.py", "docstring-coverage/audit.py",
    "duplication/audit.py", "error-handling/audit.py", "mutation-audit/audit.py",
    "skill-audit/audit.py", "test-audit/audit.py",
    "all-audits/harness/auditlib.py", "create-lmd-page/extract_puzzle.py",
]


def _git_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _run(args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          env=_git_env(), timeout=120)


def _load(rel):
    spec = importlib.util.spec_from_file_location(Path(rel).stem + "_e2e", ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_audit_self_check_is_a_test_the_seam_selects():
    listed = _run(["bash", "tests/all.sh", "--list"])
    assert listed.returncode == 0, listed.stderr
    suites = set(listed.stdout.split())
    for rel in AUDIT_SCRIPTS:
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert "--selfcheck" not in source and "def _selfcheck" not in source, rel
        tests = sorted(p.relative_to(ROOT).as_posix()
                       for p in (ROOT / rel).parent.glob("*_test.py"))
        assert tests, f"{rel} has no *_test.py beside it"
        assert suites & set(tests), f"tests/all.sh --list selects none of {tests}"


def test_each_driver_mode_refuses_a_flag_it_does_not_take():
    driver = str(ROOT / "all-audits" / "driver.py")
    refused = _run([sys.executable, driver, "sweep", str(ROOT), "--modules", "a.py"])
    assert refused.returncode == 2
    assert "unrecognized arguments: --modules" in refused.stderr
    no_mode = _run([sys.executable, driver])
    assert no_mode.returncode == 2
    help_text = _run([sys.executable, driver, "mutation", "--help"])
    assert help_text.returncode == 0 and "--modules" in help_text.stdout


def test_findings_log_names_a_corrupt_line(tmp_path):
    findings_log = _load("all-audits/harness/findings_log.py")
    log = tmp_path / "findings.jsonl"
    log.write_text('{"file": "a.py"}\nnot json\n[1, 2]\n', encoding="utf-8")
    read = findings_log.read(log)
    assert read.rows == [{"file": "a.py"}]
    assert read.corrupt == [(2, "not json"), (3, "[1, 2]")]


def test_a_repo_with_no_tracked_python_is_not_applicable(tmp_path):
    repo = tmp_path / "jsrepo"
    repo.mkdir()
    (repo / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    (repo / "stray.py").write_text("x = 1\n", encoding="utf-8")
    assert _run(["git", "init", "-q"], cwd=repo).returncode == 0
    assert _run(["git", "add", "app.js"], cwd=repo).returncode == 0
    check = [sys.executable, str(ROOT / "all-audits/harness/auditlib.py"),
             "--applicable", str(repo)]
    verdict = _run(check)
    assert (verdict.returncode, verdict.stdout.strip()) == (3, "not applicable: JavaScript")
    assert _run(["git", "add", "stray.py"], cwd=repo).returncode == 0
    tracked = _run(check)
    assert (tracked.returncode, tracked.stdout.strip()) == (0, "applicable")


def test_crap_audit_scores_a_class_method_once(tmp_path):
    method = {"type": "method", "name": "handle", "lineno": 10, "complexity": 3,
              "classname": "C", "closures": []}
    radon = [{"type": "function", "name": "top", "lineno": 1, "complexity": 2,
              "closures": []},
             method,
             {"type": "class", "name": "C", "lineno": 8, "complexity": 4,
              "methods": [method]}]
    (tmp_path / "radon.json").write_text(json.dumps({"m.py": radon}), encoding="utf-8")
    (tmp_path / "coverage.json").write_text(
        json.dumps({"files": {"m.py": {"functions": {}}}}), encoding="utf-8")
    out = _run([sys.executable, str(ROOT / "crap-audit/audit.py"),
                str(tmp_path / "radon.json"), str(tmp_path / "coverage.json")])
    assert out.returncode == 0, out.stderr
    ranking = json.loads(out.stdout)["ranking"]
    assert sorted((r["name"], r["line"]) for r in ranking) == [("handle", 10), ("top", 1)]


def test_mutation_audit_plan_is_the_one_planning_interface(tmp_path):
    plan = _load("mutation-audit/audit.py").plan(str(tmp_path))
    assert set(plan) == {"candidates", "no_tests", "total", "siblings"}
    driver_source = (ROOT / "all-audits/driver.py").read_text(encoding="utf-8")
    assert "_sibling_tests" not in driver_source


def test_comment_audit_answer_key_carries_the_three_mis_cuts():
    key = (ROOT / "comment-audit/fixtures/answer-key.md").read_text(encoding="utf-8")
    rows = {}
    for line in key.splitlines():
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if len(cells) == 6 and cells[0].isdigit():
            rows[(cells[1], int(cells[2]))] = cells[3:]
    module_docstring = rows[("sample.py", 1)]
    assert module_docstring[:2] == ["cut", "citation"] and module_docstring[2]
    assert rows[("test_sample.py", 5)][0] == "keep"
    assert rows[("sample.rs", 1)][0] == "keep"
