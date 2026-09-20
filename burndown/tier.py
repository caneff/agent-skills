#!/usr/bin/env python3
"""The `documentation` label a docs-only candidate is missing.

A ticket's tier is read off its `documentation` label at dispatch: present is
light — the worker lands on the default branch, no PR, no reviewer — and
absent is heavy. A docs-only ticket whose author forgot the label therefore
takes TDD, a three-axis review and a pull request for a page of prose. On
#781 that was ticket #371, one new `docs/research/*.md`: the exploration pass
had already tagged it docs-only before dispatch, and the lane ignored what it
knew.

So this reader writes the missing label onto the ticket, not a flag into the
run: `--tier` is invisible the moment dispatch returns, while `merge-cleanup`,
`/landed` and a resumed controller all read the ticket.

It only ever adds. A label is never removed here, and a worker keeps its right
to raise light to heavy — the reverse of both is how a code change ships
unreviewed.

The grammar and the evidence: `references/tier.md`.
"""
import json
import posixpath
import subprocess
import sys

# The candidate grammar the exploration pass already speaks, imported rather
# than written a second time: `<n>=<path>[,<path>]...` is what the clumper is
# handed, and two parsers for it are two places for it to drift.
from closure import ClosureError, parse_candidate

DOCUMENTATION_LABEL = "documentation"

# What reads as prose. This is a whitelist, and everything outside it is
# treated as code: `flow/claude/WORKFLOW.md` § Gate 2 names the code
# extensions, but a classifier built from *that* list labels every extension
# nobody thought of as documentation, and a wrong `documentation` label lands
# a code change with no PR and no reviewer. A wrong heavy tier costs one
# review nobody needed.
PROSE_EXTENSIONS = {"md", "markdown", "txt", "rst"}
# The one Markdown file that is not prose. A skill's body is executable
# instruction — it changes what every later session does — which is why
# § Gate 2 names it as code, at any depth in the tree.
SKILL_BODY = "skill.md"


def is_prose(path):
    """Whether one file is prose, and so cannot make a candidate code."""
    name = posixpath.basename(path.replace("\\", "/")).lower()
    if name == SKILL_BODY:
        return False
    return name.rsplit(".", 1)[-1] in PROSE_EXTENSIONS


def labels_to_write(candidate):
    """`(candidate) -> labels to write`: the labels the exploration pass adds
    to one ticket, in the order it adds them. Only ever additions."""
    if DOCUMENTATION_LABEL in candidate["labels"]:
        return []
    files = candidate["files"]
    # `all()` over an empty list is True, and a candidate whose files nobody
    # resolved is the one case where that reading is a code change landing
    # unreviewed. Unknown goes heavy.
    if files and all(is_prose(f) for f in files):
        return [DOCUMENTATION_LABEL]
    return []


class TierError(Exception):
    """The tagging pass could not do what it was asked. One stderr line, not
    a traceback: a label that failed to land has to be readable as a fact by
    the controller, because the ticket it belongs on will be dispatched heavy
    without it."""


def gh(args):
    """`gh <args>`, for its exit status. Raises `TierError` on anything that
    stops it writing — an unwritten label is a tier decision made wrong, and
    it must not pass for a write that happened."""
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True)
    except OSError as exc:  # gh not installed, not executable, ...
        raise TierError(f"gh: {exc}") from exc
    if out.returncode != 0:
        raise TierError(out.stderr.strip() or f"gh {' '.join(args)} failed")
    return out.stdout


def add_labels(repo, number, labels, run=gh):
    """Add `labels` to one ticket. `--add-label` and nothing else: this pass
    has no spelling for removing a label, which is what keeps a worker's
    right to raise light to heavy from being undone from here."""
    run(["issue", "edit", str(number), "--repo", repo,
         "--add-label", ",".join(labels)])


def tag(repo, candidates, run=gh, write=True):
    """`(candidates) -> what was written`: one record per candidate that
    earned a label, `{"number": <n>, "labels": [...]}`, in candidate order.

    `write=False` decides identically and invokes nothing — the answer is
    the same either way, so a dry run is a readable preview of the real one
    rather than a second code path."""
    written = []
    for candidate in candidates:
        labels = labels_to_write(candidate)
        if not labels:
            continue
        if write:
            add_labels(repo, candidate["number"], labels, run)
        written.append({"number": candidate["number"], "labels": labels})
    return written


def render(written):
    """The lines the run's opening report carries: every label this pass
    wrote, against the ticket it went on. A pass that wrote none says so in
    words — a report silent about labels reads the same as one from a pass
    that never ran."""
    if not written:
        return "labels written: none — no labels written by the exploration pass"
    lines = ["labels written:"]
    lines.extend(f"    #{w['number']}  {', '.join(w['labels'])}" for w in written)
    return "\n".join(lines)


def fetch_labels(repo, number, run=gh):
    """The labels one ticket carries right now. Read at pass time, never
    assumed: a run that assumed the label absent would write it again on
    every tick, and one that assumed it present would leave a docs ticket
    heavy forever."""
    try:
        answer = json.loads(run(["issue", "view", str(number), "--repo", repo,
                                 "--json", "labels"]) or "null")
    except ValueError as exc:
        raise TierError(f"gh issue view {number}: unreadable JSON") from exc
    return [label.get("name") for label in (answer or {}).get("labels") or []]


def candidates_from(repo, specs, run=gh):
    """`<n>=<path>[,<path>]...` specs, each with the labels its ticket
    carries. The grammar is `closure.parse_candidate`'s and not a second
    parser here: the exploration pass hands both readers the same strings."""
    out = []
    for spec in specs:
        candidate = parse_candidate(spec)
        candidate["labels"] = fetch_labels(repo, candidate["number"], run)
        out.append(candidate)
    return out


def main(argv):
    args = [a for a in argv[1:] if a != "--dry-run"]
    if len(args) < 2:
        print("usage: tier.py <owner/repo> <n>=<path>[,<path>]... [--dry-run]",
              file=sys.stderr)
        return 2
    try:
        candidates = candidates_from(args[0], args[1:])
        print(render(tag(args[0], candidates, write="--dry-run" not in argv)))
    except (TierError, ClosureError) as exc:
        print(f"tier.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
