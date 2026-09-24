#!/usr/bin/env python3
"""The `documentation` label a candidate's targets call for.

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

It touches one label, `documentation`, in the direction its targets
prove. It adds the label to a candidate every target of which is prose, and
removes it from a candidate whose targets include code (#1118:
`implement-dispatch` reads only the ticket body's paths, so a body naming
only prose kept the filer's label and dispatched light while the clumper's
candidate line named a `SKILL.md`). A worker keeps its right to raise light
to heavy, and nothing here sends a candidate with a code target light: that
is how a code change ships unreviewed.

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


def labels_to_strip(candidate):
    """`(candidate) -> labels to remove`: `documentation` on a
    candidate whose targets include a file that is not prose. The label is a
    filer's claim and the targets are the evidence (#1045: #969 targeted a
    `SKILL.md`, carried the label, and went out light). Unknown targets are
    not evidence, so an empty file list strips nothing."""
    files = candidate["files"]
    if DOCUMENTATION_LABEL in candidate["labels"] and any(not is_prose(f) for f in files):
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


def tag(repo, candidates, run=None, write=True, written=None, stripped=None):
    """`(candidates) -> what was written`: one record per candidate that
    earned a label, `{"number": <n>, "labels": [...]}`, in candidate order.
    Removals go into `stripped` in the same shape.

    `--remove-label` is built from `labels_to_strip` alone, so the one label
    this pass can take off is `documentation`, and only where a target is
    code: a removal only ever raises the tier, and a worker's right to raise
    light to heavy is never undone from here.

    `write=False` decides identically and invokes nothing, so a dry run is a
    readable preview of the real one rather than a second code path.

    `written` is the caller's own list to accumulate into. A tracker failure
    on the third candidate leaves the first two's labels **on the tracker**,
    and a report that never names them is the run's report lying by omission
    — so the record has to survive the exception, which a return value does
    not.
    """
    written = [] if written is None else written
    stripped = [] if stripped is None else stripped
    run = run or gh
    for candidate in candidates:
        for flag, labels, record in (("--add-label", labels_to_write(candidate), written),
                                     ("--remove-label", labels_to_strip(candidate), stripped)):
            if not labels:
                continue
            if write:
                run(["issue", "edit", str(candidate["number"]), "--repo", repo,
                     flag, ",".join(labels)])
            record.append({"number": candidate["number"], "labels": labels})
    return written


def render(written, write=True, stripped=()):
    """The lines the run's opening report carries: every label this pass
    wrote and every label it stripped, against the ticket each belongs to. A
    pass that did neither says so in words — a report silent about labels
    reads the same as one from a pass that never ran.

    A dry run reports the same decisions under `would write:` and `would
    strip:`. A preview that claims a write is worse than no preview at all:
    these lines are the run's record of what the tracker now carries, and a
    controller reading `labels written:` after a dry run would take the tier
    as already fixed."""
    blocks = []
    for heading, records in (("labels written" if write else "would write", written),
                             ("labels stripped" if write else "would strip", stripped)):
        if not records:
            blocks.append(f"{heading}: none")
            continue
        blocks.append(f"{heading}:")
        blocks.extend(f"    #{r['number']}  {', '.join(r['labels'])}" for r in records)
    return "\n".join(blocks)


def fetch_labels(repo, number, run=None):
    """The labels one ticket carries right now. Read at pass time, never
    assumed: a run that assumed the label absent would write it again on
    every tick, and one that assumed it present would leave a docs ticket
    heavy forever."""
    run = run or gh
    try:
        answer = json.loads(run(["issue", "view", str(number), "--repo", repo,
                                 "--json", "labels"]) or "null")
    except ValueError as exc:
        raise TierError(f"gh issue view {number}: unreadable JSON") from exc
    return [label.get("name") for label in (answer or {}).get("labels") or []]


def candidates_from(repo, specs, run=None):
    """`<n>=<path>[,<path>]...` specs, each with the labels its ticket
    carries. The grammar is `closure.parse_candidate`'s and not a second
    parser here: the exploration pass hands both readers the same strings."""
    out = []
    for spec in specs:
        candidate = parse_candidate(spec)
        candidate["labels"] = fetch_labels(repo, candidate["number"], run)
        out.append(candidate)
    return out


def main(argv, run=None):
    """`--dry-run` is read once, here, and an argument this reader does not
    know is usage rather than a candidate: `tier.py <repo> --help` used to
    reach the candidate parser and die with "not a candidate: --help"."""
    dry_run = "--dry-run" in argv[1:]
    args = [a for a in argv[1:] if a != "--dry-run"]
    if len(args) < 2 or any(a.startswith("-") for a in args):
        print("usage: tier.py <owner/repo> <n>=<path>[,<path>]... [--dry-run]",
              file=sys.stderr)
        return 2
    written, stripped = [], []
    try:
        candidates = candidates_from(args[0], args[1:], run)
        tag(args[0], candidates, run, write=not dry_run, written=written,
            stripped=stripped)
    except (TierError, ClosureError) as exc:
        # The partial report first: whatever is already on the tracker is
        # what the next dispatch will read, failure or not.
        print(render(written, write=not dry_run, stripped=stripped))
        print(f"tier.py: {exc}", file=sys.stderr)
        return 1
    print(render(written, write=not dry_run, stripped=stripped))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
