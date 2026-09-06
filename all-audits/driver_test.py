#!/usr/bin/env python3
"""Tests for the audit sweep driver (#558) — ports run-audits.test.sh's
hermetic index test to Python (parses the index rather than grepping it, per
the family's plain-assert convention — see crap-audit/test_audit.py), plus a
new cache-decision test against a real temporary git repo, including the
bad-last-run-SHA case, which must mean RUN.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("AUDITS_NO_OPEN", "1")
os.environ.setdefault("AUDITS_NO_SYNTH", "1")
import driver  # noqa: E402


def _run_driver(*args):
    return subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "driver.py"), *args],
        capture_output=True, text=True,
        env={**os.environ, "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1"},
    )


def test_index_rebuild_runs_no_audits():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("dead-code", "test-audit"):
            d = os.path.join(tmp, "collection", name)
            os.makedirs(d)
            with open(os.path.join(d, "report.html"), "w") as f:
                f.write(f"<html><body>{name} report</body></html>")

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr

        index = os.path.join(tmp, "collection", "index.html")
        assert os.path.isfile(index)
        text = open(index).read()
        assert "dead-code" in text
        assert "test-audit" in text
        assert 'href="dead-code/report.html"' in text

        logs = os.path.join(tmp, "logs")
        assert not (os.path.isdir(logs) and os.listdir(logs)), "--index must run no audits"


def test_index_rerun_replaces_assets_without_nesting():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "collection", "dead-code", "assets", "base"))
        with open(os.path.join(tmp, "collection", "dead-code", "assets", "base", "base.css"), "w") as f:
            f.write("body{}")

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr
        assert os.path.isfile(os.path.join(tmp, "collection", "assets", "base", "base.css"))

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr
        assert os.path.isfile(os.path.join(tmp, "collection", "assets", "base", "base.css"))
        assert not os.path.isdir(os.path.join(tmp, "collection", "assets", "assets")), "assets/assets nesting"


def test_report_path_from_log_marker_wins_over_legacy():
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "log")
        with open(log, "w") as f:
            f.write("See /tmp/other-dir/unrelated.html for background.\nALL_AUDITS_REPORT=/tmp/dead-code-1/report.html\n")
        assert driver.report_path_from_log(log) == "/tmp/dead-code-1/report.html"

        log2 = os.path.join(tmp, "log2")
        with open(log2, "w") as f:
            f.write("report written to /tmp/ponytail-audit-123/report.html\n")
        assert driver.report_path_from_log(log2) == "/tmp/ponytail-audit-123/report.html"


def test_audit_prompt_whole_repo_override_and_ignore_file():
    prompt = driver.audit_prompt("dead-code", "/some/repo")
    assert prompt.startswith("/dead-code /some/repo")
    assert "ENTIRE repository" in prompt
    assert "not a git diff" in prompt
    assert "rejected" not in prompt

    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, ".audit-ignore.md"), "w") as f:
            f.write("### god object in solver.py\n- adr: docs/adr/0009-solver-shape.md\n")
        with_file = driver.audit_prompt("dead-code", tmp)
        assert "ENTIRE repository" in with_file
        assert "god object in solver.py" in with_file
        assert "0009-solver-shape.md" in with_file


def test_mutation_cap():
    capped, skipped = driver.mutation_cap(list("abcde"), 3)
    assert capped == ["a", "b", "c"] and skipped == 2
    capped, skipped = driver.mutation_cap(list("abc"), 5)
    assert capped == ["a", "b", "c"] and skipped == 0


def test_mutation_subindex_and_single_main_row():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("dead-code", "test-audit"):
            d = os.path.join(tmp, "collection", name)
            os.makedirs(d)
            open(os.path.join(d, "report.html"), "w").write(f"<html>{name}</html>")

        for module, killed, survived, nocov in (("solver.py", 8, 2, 0), ("oracle.py", 5, 1, 2)):
            d = os.path.join(tmp, "collection", module)
            os.makedirs(d)
            open(os.path.join(d, "report.html"), "w").write("<html>report</html>")
            row = {
                "bucket": "rewrite", "file": module, "line": 1, "category": "surviving-mutant",
                "summary": "s", "failure": "",
                "extra": {"mutant": "x", "killed": False, "survived": True,
                          "killed_count": killed, "survived_count": survived, "no_coverage_count": nocov},
            }
            open(os.path.join(d, "findings.jsonl"), "w").write(json.dumps(row) + "\n")

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr

        index_text = open(os.path.join(tmp, "collection", "index.html")).read()
        assert index_text.count("<td>mutation</td>") == 1
        assert 'href="mutation/index.html"' in index_text
        assert 'href="solver.py/report.html"' not in index_text

        sub = open(os.path.join(tmp, "collection", "mutation", "index.html")).read()
        assert "solver.py" in sub and "oracle.py" in sub
        assert 'href="../solver.py/report.html"' in sub
        assert 'href="../oracle.py/report.html"' in sub
        assert "8/10" in sub  # solver: killed 8, total 8+2+0
        assert "5/8" in sub  # oracle: killed 5, total 5+1+2


def test_no_mutation_reports_no_row():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("dead-code", "test-audit"):
            d = os.path.join(tmp, "collection", name)
            os.makedirs(d)
            open(os.path.join(d, "report.html"), "w").write("<html>x</html>")

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr
        index_text = open(os.path.join(tmp, "collection", "index.html")).read()
        assert "<td>mutation</td>" not in index_text
        assert not os.path.exists(os.path.join(tmp, "collection", "mutation"))


def test_no_test_modules_section():
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "collection", "solver.py")
        os.makedirs(d)
        open(os.path.join(d, "report.html"), "w").write("<html>x</html>")
        row = {
            "bucket": "rewrite", "file": "solver.py", "line": 1, "category": "surviving-mutant",
            "summary": "s", "failure": "",
            "extra": {"mutant": "x", "killed": False, "survived": True,
                      "killed_count": 8, "survived_count": 2, "no_coverage_count": 3},
        }
        open(os.path.join(d, "findings.jsonl"), "w").write(json.dumps(row) + "\n")
        open(os.path.join(tmp, "collection", "mutation-no-tests.json"), "w").write(
            json.dumps({"no_tests": ["widget.py", "gadget.py"], "total": 6})
        )

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr

        index_text = open(os.path.join(tmp, "collection", "index.html")).read()
        assert "with no tests" in index_text and "2 with no tests" in index_text

        sub = open(os.path.join(tmp, "collection", "mutation", "index.html")).read()
        assert "2 of 6 source modules have no tests" in sub
        assert "widget.py" in sub and "gadget.py" in sub
        assert "8/13" in sub
        assert "weak" in sub.lower()
        assert "no-coverage" in sub.lower() or "no coverage" in sub.lower()


def _init_git_repo(path):
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "t"], check=True)
    open(os.path.join(path, "a.py"), "w").write("x = 1\n")
    subprocess.run(["git", "-C", path, "add", "."], check=True)
    subprocess.run(["git", "-C", path, "commit", "-q", "-m", "init"], check=True)


def test_cache_decision_bad_sha_forces_run():
    """AC: a bad/unknown last-run SHA on a real temp git repo must yield
    RUN — `git diff` against a SHA that doesn't exist can't prove the repo
    is unchanged, so it must never read as SKIP."""
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as cache_dir:
        _init_git_repo(repo)
        record_path = driver._record_file(repo, cache_dir)
        driver.save_record(record_path, {
            "domain-drift": {
                "last_sha": "0" * 40,  # a SHA that was never a real commit
                "timestamp": "2026-01-01T00:00:00+00:00",
                "report_dir": os.path.join(cache_dir, "nope"),
            }
        })
        d = driver.decide(repo, "domain-drift", ["CONTEXT.md"], base=cache_dir)
        assert d.run is True, d


def test_cache_decision_clean_recent_repo_skips():
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as cache_dir:
        _init_git_repo(repo)
        sha = driver.head_sha(repo)
        report_dir = os.path.join(cache_dir, "report")
        os.makedirs(report_dir)
        driver.save_record(driver._record_file(repo, cache_dir), {
            "domain-drift": {
                "last_sha": sha,
                "timestamp": driver._dt.datetime.now(driver._dt.timezone.utc).isoformat(),
                "report_dir": report_dir,
            }
        })
        d = driver.decide(repo, "domain-drift", ["CONTEXT.md"], base=cache_dir)
        assert d.run is False, d
        assert d.report_dir == report_dir


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
