#!/usr/bin/env python3
"""`selector_check.py list|comment`: the selector evidence a merge leaves on its
PR (#1537, Chris's ruling of 2026-10-11 on caneff/sudokumaker-custom-
constraints#809).

A repo whose `AGENTS.md` § End-to-end seam declares a `**Narrowed**` line (a
command such as `bash tests/all.sh --changed origin/main`) is asked, at every
merge, whether that narrowed run would have selected what the full seam failed
on. The merge step runs the narrowed command with `--list` before the seam
(`list`) and posts one comment after it (`comment`):

    selector: clean                 the seam was green
    selector: miss <suite>...       red, and a failing suite is not in the listing
    selector: hit <suite>...        red, and every failing suite is in it
    selector: not checked: <why>    no readable listing, or no readable verdict

The count of `selector: miss` comments over merged PRs is the evidence for
dropping the full run at merge. The comment is evidence only: both subcommands
exit 0 whatever the verdict, and a failed post is said on stdout, so no caller
has a status to read as a reason to hold or allow a merge. A repo with no
`Narrowed` line gets no listing run (`list` exits 3 and writes no state) and
no comment.

`list --root <dir> --state <file> [--base <rev>]` runs the declared command
with `--list` appended in `<dir>` and records its exit status and output in
`<file>`. `--base` swaps the argument of the command's `--changed` for `<rev>`,
so a merge made earlier is listed against its own parent (drain).
`comment --root <dir> --state <file> --seam-exit <n> --seam-log <file>
[--pr <n> --repo <owner/name>]` prints the verdict and, given a PR, posts it.

Absent answers are `not checked`, never `clean` (`AGENTS.md` § Recurring
defect classes, class 1): a listing that exited non-zero, printed nothing, was
never run or whose state file is gone; a seam exit that was not recorded; a
red log with no `FAIL <suite>` line at the start of a line.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# The seam section's reader, imported as `closing_ticket.py` imports its own
# fence reader: a second copy of the grammar is a second place for its bugs.
sys.path.insert(0, os.path.join(_HERE, os.pardir, "implement-spec"))
from closing_ticket import declaration  # noqa: E402

LISTING_SECONDS = 600
_FAIL = re.compile(r"^FAIL (\S+)")
_CHANGED = re.compile(r"--changed(?:=|\s+)\S+")


class Narrowed:
    """`command` is the declared command, or `None` with `error` saying why a
    present line names none."""

    def __init__(self, command, error=None):
        self.command, self.error = command, error


def narrowed_in(text):
    """`None` when `text` (an `AGENTS.md`) declares no `Narrowed` line (no
    comment is owed), else a `Narrowed`. The value is the first backtick span
    of the line, or the whole value with none."""
    found = declaration(text)
    if not found or "narrowed" not in found:
        return None
    value = found["narrowed"]
    span = re.search(r"`([^`]+)`", value)
    command = (span.group(1) if span else value).strip()
    if not command or not command.strip("*_ "):
        return Narrowed(None, "the `Narrowed` line names no command")
    return Narrowed(command)


def read_narrowed(root):
    """`narrowed_in` for `root/AGENTS.md`; no file declares nothing."""
    try:
        with open(os.path.join(root, "AGENTS.md")) as f:
            return narrowed_in(f.read())
    except OSError:
        return None


def with_base(command, base):
    """`command` with its `--changed` argument swapped for `base`, or `None`
    when it has none to swap."""
    if not _CHANGED.search(command):
        return None
    return _CHANGED.sub(lambda _: "--changed " + shlex.quote(base), command, count=1)


def record_listing(root, state_path, base=None):
    """Run the listing and write the state file. Returns False when the repo
    declares no narrowed line: nothing is written and any state left by an
    earlier run is removed, so a stale one is never read for this merge."""
    narrowed = read_narrowed(root)
    if narrowed is None:
        if os.path.exists(state_path):
            os.remove(state_path)
        return False
    state = {"command": narrowed.command, "status": None, "listing": [], "error": narrowed.error}
    if narrowed.command and base:
        swapped = with_base(narrowed.command, base)
        if swapped is None:
            state["error"] = f"the narrowed command has no `--changed <base>` to point at {base}"
        else:
            state["command"] = swapped
    if narrowed.command and not state["error"]:
        state["command"] += " --list"
        try:
            out = subprocess.run(["sh", "-c", state["command"]], cwd=root, capture_output=True, text=True,
                                 timeout=LISTING_SECONDS)
            state["status"] = out.returncode
            state["listing"] = out.stdout.split()
            state["stderr"] = " ".join(out.stderr.split())[:200]
        except (OSError, subprocess.TimeoutExpired) as exc:
            state["error"] = f"the listing command could not run ({' '.join(str(exc).split())[:150]})"
    with open(state_path, "w") as f:
        json.dump(state, f)
    return True


def failing_suites(log_path):
    """`(suites, None)` in first-seen order, or `([], why)`. A `FAIL <suite>`
    is read only at the start of a line: a passing suite that reprints a
    child's failure indents it."""
    try:
        with open(log_path, errors="replace") as f:
            found = [m.group(1) for m in (_FAIL.match(x) for x in f) if m]
    except OSError as exc:
        return [], f"the seam's log could not be read ({' '.join(str(exc).split())[:100]})"
    if not found:
        return [], "the seam's log has no `FAIL <suite>` line"
    return list(dict.fromkeys(found)), None


def verdict(state_path, seam_exit, seam_log):
    """The comment line for one merge."""
    def unchecked(why):
        return f"selector: not checked: {why}"

    try:
        with open(state_path) as f:
            state = json.load(f)
        listing = set(state["listing"])
    except (OSError, ValueError, KeyError, TypeError):
        return unchecked("no listing record (the narrowed listing step did not run)")
    if state.get("error"):
        return unchecked(state["error"])
    if state.get("status") != 0:
        return unchecked(f"`{state.get('command')}` exited {state.get('status')}")
    if not listing:
        return unchecked(f"`{state.get('command')}` printed nothing")
    if not isinstance(seam_exit, int):
        return unchecked("the seam's exit status was not recorded")
    if seam_exit == 0:
        return "selector: clean"
    failed, why = failing_suites(seam_log)
    if why:
        return unchecked(why)
    missed = [s for s in failed if s not in listing]
    if missed:
        return "selector: miss " + ", ".join(missed)
    return "selector: hit " + ", ".join(failed)


def post(pr, repo, body):
    """`None` when posted, else why not: said, never raised."""
    try:
        out = subprocess.run(["gh", "pr", "comment", str(pr), "--repo", repo, "--body", body],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return " ".join(str(exc).split())[:150]
    if out.returncode:
        return " ".join((out.stderr or out.stdout).split())[:150] or f"gh exited {out.returncode}"
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    lst = sub.add_parser("list")
    cmt = sub.add_parser("comment")
    for p in (lst, cmt):
        p.add_argument("--root", required=True)
        p.add_argument("--state", required=True)
    lst.add_argument("--base")
    cmt.add_argument("--seam-exit", required=True)
    cmt.add_argument("--seam-log", required=True)
    cmt.add_argument("--pr")
    cmt.add_argument("--repo")
    args = parser.parse_args(argv)
    if args.cmd == "list":
        return 0 if record_listing(args.root, args.state, args.base) else 3
    if read_narrowed(args.root) is None:
        return 0  # no narrowed line: no comment is owed, and none is the answer
    try:
        seam_exit = int(args.seam_exit)
    except ValueError:
        seam_exit = None
    line = verdict(args.state, seam_exit, args.seam_log)
    print(line)
    if args.pr:
        if not args.repo:
            parser.error("--pr needs --repo")
        why = post(args.pr, args.repo, line)
        if why:
            print(f"selector comment not posted: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
