#!/usr/bin/env python3
"""Reader for the run summaries tests/all.sh keeps (#1958).

`run_summary.py report [--dir D] [--top K]` prints the slowest suites (worst
wall seconds over the kept runs) and the suites that failed at least once.
Records live in `$TESTS_RUN_DIR` (default `~/.cache/test-runs`) as `runs.jsonl`,
one JSON object per run, the last `TESTS_RUN_KEEP` (default 50) kept:

    id          "<pid>-<epoch>"
    mode        "full" | "narrowed"
    selected    how many suites the run selected
    load1       the 1-minute load at the start, null when unreadable
    wall_total  seconds
    status      "pass" | "fail" | "incomplete"
    suites      [{label, verdict "pass"|"fail", wall, cpu}] for the suites reported;
                wall and cpu are null when unmeasured

`tests/all.sh` writes the record `incomplete` at the start and rewrites it at
exit, so a run killed part-way (even by SIGKILL) stays `incomplete` and never
reads as a pass; a gate failure or a failing suite is `fail`. Suites that
`tests/all.sh` starts get a scratch `TESTS_RUN_DIR`, so a nested run never
writes here. A damaged line is skipped. Report-only: nothing here fails a run.
"""
import argparse
import json
import os
import sys


def load(d):
    path = os.path.join(d, "runs.jsonl")
    try:
        with open(path) as f:
            rows = []
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass  # a damaged line is skipped, as the writer does
            return rows
    except FileNotFoundError:
        return []


def report(d, top):
    runs = load(d)
    if not runs:
        print(f"no run records in {d}", file=sys.stderr)
        return 1
    worst, failed = {}, {}
    for r in runs:
        for s in r.get("suites", []):
            if s["wall"] is not None:
                worst[s["label"]] = max(worst.get(s["label"], 0.0), s["wall"])
            if s["verdict"] == "fail":
                failed[s["label"]] = failed.get(s["label"], 0) + 1
    incomplete = sum(r["status"] == "incomplete" for r in runs)
    print(f"{len(runs)} runs, {incomplete} incomplete, {sum(r['status'] == 'fail' for r in runs)} failed")
    print("slowest suites (worst wall over the kept runs):")
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
