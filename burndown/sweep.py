#!/usr/bin/env python3
"""Render a run's leftovers (`runfile.py`'s `leftovers` list,
`references/run-file.md` § Leftovers) as one sweep ticket body, grouped by
file:

    python3 burndown/sweep.py render <run-id>

reads the run file and prints the ticket title and body, or says on stderr
that the run has no leftovers and prints nothing to file on stdout. This is
the renderer #1029 left for #1030: the run file was already the store,
nothing here writes to it.

    python3 burndown/sweep.py counts <run-id> [--reviews-dir <dir>]

prints the closing report's three counts — fixed in-round, leftover,
standalone — read from each landed clump's dispositions sidecar
(`implement/SKILL.md` § Review's `dispositions-<lowest ticket>.jsonl`, the
same file the verification pass writes). Nothing here writes one either.

Filing the ticket through `/file-ticket` — the label, the `## Blocked by`
section, and when the controller calls this — is `burndown/SKILL.md`'s own
step, not this module's: a renderer prints a body, it does not call `gh`.
"""
import os
import re
import subprocess
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


# A CommonMark code span: a backtick run closes only on a run of the same
# length, and a backslash-escaped backtick opens nothing.
_CODE_SPAN = re.compile(r"(?<![`\\])(`+)(?!`)(?:(?!\1).)+?(?<!`)\1(?!`)")


def inline_safe(text):
    """A finding's title or text made safe to sit in a ticket body: an
    `@mention` is broken with a zero-width space so it notifies nobody, and
    `<` becomes `&lt;` so raw HTML is not parsed. Backticked code spans are
    left as written. `runfile.leftover_field` already keeps the text to one
    line, so no heading or fence can start a line."""
    def defuse(chunk):
        chunk = re.sub(r"(?<!\w)@(?=\w)", "@\u200b", chunk)
        return chunk.replace("<", "&lt;")
    out, pos = [], 0
    for m in _CODE_SPAN.finditer(text):
        out.append(defuse(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(defuse(text[pos:]))
    return "".join(out)


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
                f"- **{item['id']}** ({item['severity']}) {inline_safe(item['title'])} "
                f"— clump #{item['clump']}, {tickets}, PR #{item['pr']}: "
                f"{inline_safe(item['text'])}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def default_reviews_dir(repo_root=None):
    """`~/.cache/agent-reviews/<repo>`, keyed the same way
    `multi-axis-code-review/SKILL.md`'s own dir expansion is: the primary
    checkout's basename, read off the common `.git` rather than
    `git rev-parse --show-toplevel` — a review always runs from a task
    worktree, and that command there returns the worktree's own path, not
    the repo's name every review's cache directory is keyed on."""
    top = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout.strip()
    repo = os.path.basename(os.path.dirname(top))
    return os.path.join(os.path.expanduser("~/.cache/agent-reviews"), repo)


def dispositions_path(reviews_dir, lowest):
    return os.path.join(reviews_dir, f"dispositions-{lowest}.jsonl")


def counts(run, reviews_dir):
    """The closing report's three counts, read from each **landed** clump's
    dispositions sidecar: **fixed in-round** is every `fixed` line
    (an adjacent fix included, and counted again separately so the report
    can say how many of the fixes were adjacent); **leftover** is every
    `leftover` line; **standalone** is every `filed` line — a ticket of its
    own. `disputed` and `handed-back` land in none of the three: a disputed
    finding shipped nothing, and a handed-back one is not yet filed by
    anyone. Controller loop observations are not in any sidecar — they are
    filed by the controller itself, never a worker — so they are not this
    function's to count; the controller adds its own filed-observation
    count to standalone by hand (`burndown/SKILL.md` § The sweep).

    A landed clump with no sidecar on disk is refused by clump number,
    never silently counted as zero: a controller reading a low count cannot
    otherwise tell "this clump genuinely left nothing" from "this run's own
    bookkeeping is missing" (defect class 1)."""
    fixed = adjacent = leftover = standalone = 0
    missing = []
    for entry in run["clumps"]:
        if not entry["landed"]:
            continue
        lowest = entry["tickets"][0]
        path = dispositions_path(reviews_dir, lowest)
        if not os.path.exists(path):
            missing.append(lowest)
            continue
        for _, obj in runfile.read_dispositions(path):
            outcome = obj["outcome"]
            if outcome == "fixed":
                fixed += 1
                if obj.get("scope") == "adjacent":
                    adjacent += 1
            elif outcome == "leftover":
                leftover += 1
            elif outcome == "filed":
                standalone += 1
    if missing:
        raise runfile.RunFileError(
            "landed clump(s) " +
            ", ".join(f"#{n}" for n in missing) +
            " have no dispositions sidecar under " + reviews_dir +
            " — counts refused rather than read as zero")
    return {"fixed": fixed, "adjacent": adjacent, "leftover": leftover,
            "standalone": standalone}


def render_counts(c):
    return (f"fixed in-round: {c['fixed']} ({c['adjacent']} adjacent)  "
            f"leftover: {c['leftover']}  standalone: {c['standalone']}")


def main(argv):
    import argparse

    parser = argparse.ArgumentParser(
        prog="sweep.py",
        description="Render a run's leftovers as a sweep ticket body, or "
                     "its closing-report counts")
    subs = parser.add_subparsers(dest="command", required=True)

    r = subs.add_parser(
        "render", help="render the run's leftovers as a sweep ticket body")
    r.add_argument("run_id")

    c = subs.add_parser(
        "counts",
        help="print the run's fixed-in-round/leftover/standalone counts")
    c.add_argument("run_id")
    c.add_argument("--reviews-dir",
                   help="override ~/.cache/agent-reviews/<repo> (tests)")

    args = parser.parse_args(argv[1:])

    override = os.environ.get("BURNDOWN_CACHE_DIR")
    root = os.path.expanduser(override) if override else None
    try:
        run = runfile.load(args.run_id, root)
    except runfile.RunFileError as exc:
        print(f"sweep.py: {exc}", file=sys.stderr)
        return 1

    if args.command == "render":
        leftovers = run.get("leftovers", [])
        body = render_body(leftovers)
        if not body:
            # To stderr, not stdout: SKILL.md tells the controller to file
            # what this prints, and a caller piping stdout straight into
            # `gh issue create` must see an empty string here, never a
            # sentence that reads as a fileable body (#1030 round-1
            # findings S4, C3).
            print(f"run {args.run_id} has no leftovers — nothing to file",
                  file=sys.stderr)
            return 0
        print(title(args.run_id))
        print()
        print(body, end="")
        return 0

    reviews_dir = (os.path.expanduser(args.reviews_dir) if args.reviews_dir
                   else default_reviews_dir())
    try:
        c = counts(run, reviews_dir)
    except runfile.RunFileError as exc:
        print(f"sweep.py: {exc}", file=sys.stderr)
        return 1
    print(render_counts(c))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
