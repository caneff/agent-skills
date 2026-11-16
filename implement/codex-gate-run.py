#!/usr/bin/env python3
"""Run the Codex adversarial gate for one ticket and write its record.

    codex-gate-run.py --ticket <n> --body-file <path> --base origin/<default>

Run from the ticket's workspace, after `git fetch origin`, with
`run_in_background` (`SKILL.md` § The Codex pass). It writes, in this repo's
review cache (`review_cache.cache_dir_for`, the one rule for the directory):

  codex-adversarial-<n>-gate.out   the plugin's stdout and stderr
  codex-adversarial-<n>-gate.json  ticket, phase, node's exit status, launch
                                   and completion HEAD, both timestamps, and
                                   the `codex-usage-gate.py --percent` readings

A failed launch is recorded, not raised: node's exit status, or 127 when node
could not start, goes in `status`, and the exit is 0 once the record is
written. An earlier record for the ticket is deleted before the launch, so a
crash never leaves a stale one. A missing plugin entry or an unreadable body
file exits 1, names which, and writes no record: nothing ran.
`$CODEX_USAGE_GATE` names another usage-gate script, for tests.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "multi-axis-code-review"))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
import review_cache  # noqa: E402
import shellcmd  # noqa: E402


def head():
    return shellcmd.git(["rev-parse", "HEAD"]).stdout.strip()


def usage(gate):
    """`<percent> <resetsAt>`, or `unknown` when the gate cannot read it."""
    r = subprocess.run([sys.executable, gate, "--percent"], capture_output=True, text=True)
    line = r.stdout.strip()
    return line if r.returncode == 0 and line else "unknown"


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def start_error(plugins, body_file):
    """The cause that keeps the run from starting, or `(root, body)` when none does."""
    try:
        with open(plugins) as f:
            root = json.load(f)["plugins"]["codex@openai-codex"][0]["installPath"]
    except (OSError, KeyError, IndexError, ValueError) as e:
        return f"no codex@openai-codex entry readable in {plugins}: {e!r}"
    try:
        with open(body_file) as f:
            return root, f.read()
    except OSError as e:
        return f"body file unreadable: {e!r}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ticket", required=True, type=int)
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--base", required=True)
    a = ap.parse_args()

    started_with = start_error(os.path.expanduser("~/.claude/plugins/installed_plugins.json"),
                               a.body_file)
    if isinstance(started_with, str):
        print(f"codex-gate-run: cannot start: {started_with}", file=sys.stderr)
        return 1
    root, body = started_with

    d = review_cache.cache_dir_for(Path.cwd())
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"codex-adversarial-{a.ticket}-gate.out"
    record = d / f"codex-adversarial-{a.ticket}-gate.json"
    record.unlink(missing_ok=True)
    gate = os.environ.get("CODEX_USAGE_GATE") or os.path.join(HERE, "codex-usage-gate.py")

    before = usage(gate)
    launch, started = head(), now()
    with open(out, "w") as o:
        try:
            status = subprocess.run(
                ["node", os.path.join(root, "scripts", "codex-companion.mjs"),
                 "adversarial-review", "--wait", "--base", a.base, "--", body],
                stdout=o, stderr=subprocess.STDOUT).returncode
        except OSError as e:
            status = 127
            print(f"codex-gate-run: node did not start: {e!r}", file=o)
    after = usage(gate)
    try:
        completion = head()
    except shellcmd.CmdError:
        completion = "unknown"
    record.write_text(json.dumps({
        "ticket": a.ticket, "phase": "gate", "status": status,
        "launch_sha": launch, "completion_sha": completion,
        "started": started, "completed": now(),
        "usage_before": before, "usage_after": after}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
