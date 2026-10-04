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
prove. It adds the label to a candidate every target of which is prose, unless
the ticket body names code the way `implement-dispatch` reads it (#1211:
dispatch would strip the label again, so the pass withholds it and says so
under `labels withheld:`), and
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


# The ticket body's own reading, the one `implement-dispatch` applies at claim
# time (`flow/lane/src/targets.rs`, which owns these lists; `tier_test.py`
# compares them literal for literal, and both suites run the body-to-verdict
# cases in `flow/lane/tests/fixtures/body_targets.json`, #1239). A label
# written for a ticket whose body names code is a label dispatch strips again,
# so the run's report would say it wrote a label the ticket no longer carries
# (#1211).
BODY_CODE_EXTENSIONS = {
    "py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "sh", "bash", "rs", "yml", "yaml", "toml", "json", "go", "zsh",
    "fish", "ps1", "psm1", "bat", "cmd", "lua", "ini", "cfg", "conf", "rb", "pl", "php", "java", "kt", "swift",
    "c", "h", "cpp", "hpp", "mk",
}
BODY_CODE_DIRS = {"bin", "sbin", "hooks", ".githooks", ".husky"}
BODY_PROSE_TOKENS = {"node.js"}
BODY_CODE_BASENAMES = {"skill.md", "makefile", "dockerfile", "justfile", "rakefile", "gemfile", "procfile", "build.gradle"}
_PATH_CHARS = "/-_."


def _body_token_is_code(token):
    name = token.rsplit("/", 1)[-1].lower()
    if name in BODY_CODE_BASENAMES:
        return True
    if "/" not in token and name in BODY_PROSE_TOKENS:
        return False
    stem, dot, ext = name.rpartition(".")
    if dot:
        return (bool(stem) and ext in BODY_CODE_EXTENSIONS) or (
            "/" in token and any(c.isalpha() for c in ext) and ext not in PROSE_EXTENSIONS)
    return "/" in token and any(d.lower() in BODY_CODE_DIRS for d in token.split("/")[:-1])


def body_code_target(body):
    """The first path-shaped token in a ticket body that is code, as
    `implement-dispatch` reads it, or None."""
    text = "".join(c if (c.isalnum() or c in _PATH_CHARS) else " "
                   for c in body.replace("\\", "/"))
    for token in text.split():
        token = token.rstrip(".")
        if token and _body_token_is_code(token):
            return token
    return None


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
    if _targets_are_prose(candidate) and not label_withheld_for(candidate):
        return [DOCUMENTATION_LABEL]
    return []


def _targets_are_prose(candidate):
    files = candidate["files"]
    # `all()` over an empty list is True, and a candidate whose files nobody
    # resolved is the one case where that reading is a code change landing
    # unreviewed. Unknown goes heavy.
    return bool(files) and all(is_prose(f) for f in files)


def label_withheld_for(candidate):
    """The code path in the ticket body that stops the label being written
    on an otherwise all-prose, unlabelled candidate, or None. Dispatch would
    strip that label at claim, so writing it makes the report false (#1211).
    A missing "body" raises: an absent body is not a prose-only one."""
    if DOCUMENTATION_LABEL in candidate["labels"] or not _targets_are_prose(candidate):
        return None
    return body_code_target(candidate["body"])


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


def tag(repo, candidates, run=None, write=True, written=None, stripped=None,
        withheld=None):
    """`(candidates) -> what was written`: one record per candidate that
    earned a label, `{"number": <n>, "labels": [...]}`, in candidate order.
    Removals go into `stripped` in the same shape; a label held back because
    the body names code goes into `withheld` as `{"number", "target"}`.

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
    withheld = [] if withheld is None else withheld
    run = run or gh
    for candidate in candidates:
        number = candidate["number"]
        add, strip = labels_to_write(candidate), labels_to_strip(candidate)
        blocked = label_withheld_for(candidate)
        if blocked:
            withheld.append({"number": number, "target": blocked})
        if add:
            if write:
                run(["issue", "edit", str(number), "--repo", repo,
                     "--add-label", ",".join(add)])
            written.append({"number": number, "labels": add})
        if strip:
            if write:
                run(["issue", "edit", str(number), "--repo", repo,
                     "--remove-label", ",".join(strip)])
            stripped.append({"number": number, "labels": strip})
    return written


def render(written, stripped, withheld, write=True):
    """The lines the run's opening report carries: every label this pass
    wrote, every label it stripped and every ticket it withheld the label
    from, against the ticket each belongs to. A pass that did none says so
    in words — a report silent about labels
    reads the same as one from a pass that never ran.

    A dry run reports the same decisions under `would write:`, `would
    strip:` and `would withhold:`. A preview that claims a write is worse than no
    preview at all: these lines are the run's record of what the tracker now carries, and a
    controller reading `labels written:` after a dry run would take the tier
    as already fixed.

    `stripped` and `withheld` have no default: an in-process caller that
    forgot one would print `none` over changes that happened. `withheld` names
    the tickets whose body names code, so they go out heavy with no label."""
    return "\n".join([
        _block("labels written" if write else "would write",
               [(r["number"], ", ".join(r["labels"])) for r in written]),
        _block("labels stripped" if write else "would strip",
               [(r["number"], ", ".join(r["labels"])) for r in stripped]),
        _block("labels withheld" if write else "would withhold",
               [(w["number"], f"body names {w['target']}") for w in withheld]),
    ])


def _block(heading, rows):
    if not rows:
        return f"{heading}: none"
    return "\n".join([f"{heading}:", *(f"    #{n}  {text}" for n, text in rows)])


def fetch_ticket(repo, number, run=None):
    """The labels and body one ticket carries right now. Read at pass time, never
    assumed: a run that assumed the label absent would write it again on
    every tick, and one that assumed it present would leave a docs ticket
    heavy forever."""
    run = run or gh
    try:
        answer = json.loads(run(["issue", "view", str(number), "--repo", repo,
                                 "--json", "labels,body"]) or "null")
    except ValueError as exc:
        raise TierError(f"gh issue view {number}: unreadable JSON") from exc
    if not isinstance(answer, dict) or not isinstance(answer.get("body"), str):
        # A body that did not come back is not a body that names no code.
        raise TierError(f"gh issue view {number}: no body in the answer")
    if not isinstance(answer.get("labels"), list):
        # Nor are missing labels no labels: read so, the pass writes the label
        # again on every tick.
        raise TierError(f"gh issue view {number}: no labels in the answer")
    return [label.get("name") for label in answer["labels"]], answer["body"]


def candidates_from(repo, specs, run=None):
    """`<n>=<path>[,<path>]...` specs, each with the labels its ticket
    carries. The grammar is `closure.parse_candidate`'s and not a second
    parser here: the exploration pass hands both readers the same strings."""
    out = []
    for spec in specs:
        candidate = parse_candidate(spec)
        candidate["labels"], candidate["body"] = fetch_ticket(repo, candidate["number"], run)
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
    written, stripped, withheld = [], [], []
    try:
        candidates = candidates_from(args[0], args[1:], run)
        tag(args[0], candidates, run, write=not dry_run, written=written,
            stripped=stripped, withheld=withheld)
    except (TierError, ClosureError) as exc:
        # The partial report first: whatever is already on the tracker is
        # what the next dispatch will read, failure or not.
        print(render(written, stripped, withheld, write=not dry_run))
        print(f"tier.py: {exc}", file=sys.stderr)
        return 1
    print(render(written, stripped, withheld, write=not dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
