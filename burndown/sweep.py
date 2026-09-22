#!/usr/bin/env python3
"""Render a run's leftovers (`runfile.py`'s `leftovers` list,
`references/run-file.md` § Leftovers) as one sweep ticket body, grouped by
file:

    python3 burndown/sweep.py <run-id>

reads the run file and prints the ticket title and body, or says the run has
no leftovers and prints nothing to file. This is the renderer #1029 left for
#1030: the run file was already the store, nothing here writes to it.

Filing the ticket through `/file-ticket` — the label, the `## Blocked by`
section, and when the controller calls this — is `burndown/SKILL.md`'s own
step, not this module's: a renderer prints a body, it does not call `gh`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runfile  # noqa: E402


def title(run_id):
    return f"Sweep: leftovers from burn {run_id}"


def grouped_by_file(leftovers):
    """Leftovers grouped by `file`, each group in the order its first item
    appeared — never sorted, so a fixture's order is the render's order and
    a test can assert on it without re-deriving a sort key."""
    order = []
    groups = {}
    for item in leftovers:
        file = item["file"]
        if file not in groups:
            groups[file] = []
            order.append(file)
        groups[file].append(item)
    return [(file, groups[file]) for file in order]


def render_body(leftovers):
    """The sweep ticket body: one `## <file>` section per file that carried
    a leftover, one bullet per item naming every field a sweep worker needs
    without reopening the PR — id, severity, title, the ticket(s) and PR it
    landed on, and its one line of finding text.

    Empty input renders to the empty string, not a placeholder body: zero
    leftovers files nothing (`references/run-file.md` § Leftovers), and an
    empty string is what tells the caller that apart from a body worth
    filing."""
    if not leftovers:
        return ""
    lines = []
    for file, items in grouped_by_file(leftovers):
        lines.append(f"## {file}")
        lines.append("")
        for item in items:
            tickets = ", ".join(f"#{n}" for n in item["tickets"])
            lines.append(
                f"- **{item['id']}** ({item['severity']}) {item['title']} "
                f"— {tickets}, PR #{item['pr']}: {item['text']}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv):
    import argparse

    parser = argparse.ArgumentParser(
        prog="sweep.py",
        description="Render a run's leftovers as a sweep ticket body")
    parser.add_argument("run_id")
    args = parser.parse_args(argv[1:])

    override = os.environ.get("BURNDOWN_CACHE_DIR")
    root = os.path.expanduser(override) if override else None
    try:
        run = runfile.load(args.run_id, root)
    except runfile.RunFileError as exc:
        print(f"sweep.py: {exc}", file=sys.stderr)
        return 1

    leftovers = run.get("leftovers", [])
    body = render_body(leftovers)
    if not body:
        print(f"run {args.run_id} has no leftovers — nothing to file")
        return 0
    print(title(args.run_id))
    print()
    print(body, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
