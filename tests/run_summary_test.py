"""#1958: the reader over the run records tests/all.sh keeps."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER = os.path.join(ROOT, "tests", "run_summary.py")


def write(d, runs):
    with open(os.path.join(d, "runs.jsonl"), "w") as f:
        for r in runs:
            f.write(json.dumps(r) + "\n")


def rec(status, suites):
    return {"id": "x", "status": status, "mode": "full", "selected": len(suites), "load1": 1.0,
            "suites": [{"label": l, "verdict": v, "wall": w, "cpu": 1.0} for l, v, w in suites]}


def report(d, *args):
    return subprocess.run([sys.executable, READER, "report", "--dir", str(d), *args],
                          capture_output=True, text=True, timeout=30)


def sections(out):
    slow, failed = out.split("failed at least once", 1)
    return slow, failed


def test_slowest_suites_are_ranked_by_worst_wall_over_the_kept_runs(tmp_path):
    write(tmp_path, [rec("pass", [("a", "pass", 5.0), ("b", "pass", 90.0)]),
                     rec("pass", [("a", "pass", 60.0), ("b", "pass", 10.0)])])
    slow, _ = sections(report(tmp_path).stdout)
    assert slow.index("  b") < slow.index("  a")
    assert "90.0s" in slow and "60.0s" in slow


def test_suites_that_failed_at_least_once_are_listed_with_counts(tmp_path):
    write(tmp_path, [rec("fail", [("a", "pass", 1.0), ("b", "fail", 2.0)]),
                     rec("pass", [("a", "pass", 1.0), ("b", "pass", 2.0)]),
                     rec("fail", [("b", "fail", 2.0)])])
    _, failed = sections(report(tmp_path).stdout)
    assert "b" in failed and "2 of 3" in failed
    assert "  a" not in failed


def test_an_incomplete_run_is_counted_and_never_read_as_a_pass(tmp_path):
    write(tmp_path, [rec("incomplete", []), rec("pass", [("a", "pass", 1.0)])])
    out = report(tmp_path).stdout
    assert "2 runs" in out and "1 incomplete" in out


def test_no_records_says_so_and_fails(tmp_path):
    r = report(tmp_path)
    assert r.returncode != 0 and "no run records" in (r.stdout + r.stderr)
