#!/usr/bin/env python3
"""Run the Codex adversarial gate for one ticket and write its record.

    codex-gate-run.py --repo <cache repo name> --ticket <n> --body-file <path> [--base origin/main]

Run from the ticket's workspace, after `git fetch origin`. Launch it with
`run_in_background` (`SKILL.md` § The Codex pass). It writes, in
`~/.cache/agent-reviews/<repo>/`:

  codex-adversarial-<n>-gate.out   the plugin's stdout and stderr
  codex-adversarial-<n>-gate.json  ticket, phase, node's exit status, launch and
                                   completion HEAD, both timestamps, and the
                                   usage readings from `codex-usage-gate.py --percent`

The node call's failure is recorded (`status`), not raised: the exit is 0 once
the record is written, and the reader (`fix_check.py`, `review_ledger.py`)
refuses a non-zero status or differing shas. A missing plugin entry or an
unreadable body file exits 1 and writes no record: nothing ran.
`$CODEX_USAGE_GATE` names another usage-gate script, for tests.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def head():
    return subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


def usage(gate):
    """`<percent> <resetsAt>`, or `unknown` when the gate cannot read it."""
    r = subprocess.run([sys.executable, gate, "--percent"], capture_output=True, text=True)
    line = r.stdout.strip()
    return line if r.returncode == 0 and line else "unknown"


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ticket", required=True, type=int)
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args()

    plugins = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
    try:
        with open(plugins) as f:
            root = json.load(f)["plugins"]["codex@openai-codex"][0]["installPath"]
        with open(a.body_file) as f:
            body = f.read()
    except (OSError, KeyError, IndexError, ValueError) as e:
        print(f"codex-gate-run: cannot start: codex@openai-codex entry in {plugins} "
              f"or body file unreadable: {e!r}", file=sys.stderr)
        return 1

    d = os.path.expanduser(f"~/.cache/agent-reviews/{a.repo}")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f"codex-adversarial-{a.ticket}-gate.out")
    record = os.path.join(d, f"codex-adversarial-{a.ticket}-gate.json")
    gate = os.environ.get("CODEX_USAGE_GATE") or os.path.join(HERE, "codex-usage-gate.py")

    before = usage(gate)
    launch, started = head(), now()
    with open(out, "w") as o:
        status = subprocess.run(
            ["node", os.path.join(root, "scripts", "codex-companion.mjs"),
             "adversarial-review", "--wait", "--base", a.base, "--", body],
            stdout=o, stderr=subprocess.STDOUT).returncode
    after = usage(gate)
    with open(record, "w") as f:
        json.dump({"ticket": a.ticket, "phase": "gate", "status": status,
                   "launch_sha": launch, "completion_sha": head(),
                   "started": started, "completed": now(),
                   "usage_before": before, "usage_after": after}, f)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
