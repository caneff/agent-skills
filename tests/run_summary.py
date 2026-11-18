#!/usr/bin/env python3
"""Reader for the run summaries tests/all.sh keeps (#1958).

`run_summary.py report [--dir D] [--top K]` prints the slowest suites (worst
wall seconds over the kept runs) and the suites that failed at least once.
Records live in `$TESTS_RUN_DIR` (default `~/.cache/test-runs`) as `runs.jsonl`,
one JSON object per run: id, started, repo, mode (full|narrowed), selected,
load1, wall_total, status (pass|fail|incomplete), suites [{label, verdict,
wall, cpu}]. An `incomplete` run (killed, or still going) is counted and never
read as a pass. Report-only: nothing here fails a run.
"""
import argparse
import json
import os
import sys


def load(d):
    path = os.path.join(d, "runs.jsonl")
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []


def report(d, top):
    runs = load(d)
    if not runs:
        print(f"no run records in {d}", file=sys.stderr)
        return 1
    worst, seen, failed = {}, {}, {}
    for r in runs:
        for s in r.get("suites", []):
            worst[s["label"]] = max(worst.get(s["label"], 0.0), s["wall"])
            if s["verdict"] == "fail":
                failed[s["label"]] = failed.get(s["label"], 0) + 1
    incomplete = sum(r["status"] == "incomplete" for r in runs)
    print(f"{len(runs)} runs, {incomplete} incomplete, {sum(r['status'] == 'fail' for r in runs)} failed")
    print(f"slowest suites (worst wall over the kept runs):")
    for label, w in sorted(worst.items(), key=lambda kv: -kv[1])[:top]:
        print(f"  {w:8.1f}s  {label}")
    print("suites that failed at least once:")
    for label, n in sorted(failed.items(), key=lambda kv: -kv[1]):
        print(f"  {label}: {n} of {len(runs)} runs")
    if not failed:
        print("  none")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("--dir", default=os.environ.get("TESTS_RUN_DIR") or os.path.expanduser("~/.cache/test-runs"))
    r.add_argument("--top", type=int, default=10)
    a = p.parse_args()
    return report(a.dir, a.top)


if __name__ == "__main__":
    sys.exit(main())
