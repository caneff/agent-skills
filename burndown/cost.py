#!/usr/bin/env python3
"""Token cost of one burndown ticket, read out of its worktree's Claude
transcripts: `python3 burndown/cost.py <worktree-path>` prints
`<builder> <review> <total>`.

Reads only. A missing projects dir prints `0 0 0` and exits 0 — a burn must
not die at settle time over a transcript it cannot find.
"""
import json
import os
import re
import sys

# The four scalar counters. `cache_creation` and `output_tokens_details` are
# breakdowns of two of them and double-count if summed as well.
COUNTERS = ("input_tokens", "cache_creation_input_tokens",
            "cache_read_input_tokens", "output_tokens")


def project_dir_name(worktree):
    """Claude names a projects dir after the absolute path with every `/` and
    `.` replaced by `-`, so a dotted segment (`.agents`) doubles the hyphen."""
    return re.sub(r"[/.]", "-", os.path.abspath(worktree))


def tally(worktree, projects_root):
    """(builder, review) tokens. Subagent transcripts sit under
    `<session>/subagents/`, and their lines carry `isSidechain: true`."""
    root = os.path.join(projects_root, project_dir_name(worktree))
    builder = review = 0
    for parent, _, files in os.walk(root):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            with open(os.path.join(parent, name), errors="replace") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue  # a half-written last line is not a failure
                    usage = (entry.get("message") or {}).get("usage")
                    if not isinstance(usage, dict):
                        continue
                    n = sum(usage.get(k) or 0 for k in COUNTERS)
                    if entry.get("isSidechain"):
                        review += n
                    else:
                        builder += n
    return builder, review


def main(argv):
    if len(argv) != 2:
        print("usage: cost.py <worktree-path>", file=sys.stderr)
        return 2
    projects_root = os.environ.get("BURNDOWN_PROJECTS_DIR") or os.path.expanduser(
        "~/.claude/projects")
    builder, review = tally(argv[1], projects_root)
    print(f"{builder} {review} {builder + review}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
