#!/usr/bin/env python3
"""`selector_check.py command|list|comment`: the repo's per-change command
(#1593), and the selector evidence a merge leaves on its PR (#1537, Chris's
ruling of 2026-10-11 on caneff/sudokumaker-custom-constraints#809).

`command --root <dir>` prints the command every per-change run uses: the
`**Narrowed**` command of `<dir>/AGENTS.md` § End-to-end seam when one is
declared, otherwise its `**Seam**` command. It exits 1, printing nothing on
stdout and the gap on stderr, when there is no `AGENTS.md` or no such section,
when the section declares neither line, or when the line it would use names no
command: a guessed command is the absent answer read as a benign one
(`AGENTS.md` § Recurring defect classes, class 1). With `--rev <rev>` it reads
`AGENTS.md` as committed at `<rev>` instead of the working tree: a merge's run
passes its base, so a PR that edits its own seam section does not choose the
command that gates it. `list` and `comment` take the same `--rev`.

When that run is the narrowed command, the merge records what it selected
(#1593): `list` runs the narrowed command with `--list` before the run, and
`comment` posts one line, followed by the suites one per line in a fence:

    selector: listed <k> suites from `<command> --list`
    selector: not checked: <why>    no readable listing

The comment judges nothing: whether a suite that failed at night was selected
by any merge since the last green full run is the nightly backstop's question
(#1592), and this comment is what it reads. A run that is repeated for one PR
posts again, and the last `selector:` comment of a PR is the run it landed on.
Both subcommands exit 0 whatever they recorded, and a failed post is said on
stdout, so no caller has a status to read as a reason to hold or allow a merge.
A repo with no `Narrowed` line runs its `Seam` and gets no listing run (`list`
exits 3 and writes no state) and no comment.

`list --root <dir> --state <file>` runs the declared command with `--list`
appended in `<dir>` and records its exit status and output in `<file>`, after
removing whatever an earlier run left there. `comment --root <dir> --state
<file> [--pr <n> --repo <owner/name>]` prints the record and, given a PR, posts
it.

An absent listing is `not checked`, never an empty selection (class 1): a
listing that exited non-zero, printed nothing, was never run or whose state
file is gone. A suite is a whole line: the runner labels a suite with its
command (`node examples/z.test.mjs`), so the listing is read one suite per
line.
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# The seam section's reader, imported as `closing_ticket.py` imports its own
# fence reader: a second copy of the grammar is a second place for its bugs.
sys.path.insert(0, os.path.join(_HERE, os.pardir, "implement-spec"))
from closing_ticket import declaration  # noqa: E402

LISTING_SECONDS = 600
_FAIL = re.compile(r"^FAIL (\S.*?)\s*$")
# How `command` starts its refusal on stderr; `drain/drain.py` reads the reason
# after it.
UNDECLARED = "selector_check.py command: "


# `command` is the declared command, or `None` with `error` saying why a
# present line names none.
Narrowed = collections.namedtuple("Narrowed", "command error", defaults=(None,))


def command_of(value):
    """The command a declared line names: its first backtick span, or the whole
    value with none. `None` when that is empty or only emphasis markers."""
    span = re.search(r"`([^`]+)`", value)
    command = (span.group(1) if span else value).strip()
    return command if command.strip("*_ ") else None


def narrowed_in(text):
    """`None` when `text` (an `AGENTS.md`) declares no `Narrowed` line (no
    comment is owed), else a `Narrowed`."""
    found = declaration(text)
    if not found or "narrowed" not in found:
        return None
    command = command_of(found["narrowed"])
    if not command:
        return Narrowed(None, "the `Narrowed` line names no command")
    return Narrowed(command)


def agents_text(root, rev=None):
    """`(text, None)`: `root/AGENTS.md`, as committed at `rev` when given; or
    `(None, why)`."""
    if rev is None:
        try:
            with open(os.path.join(root, "AGENTS.md")) as f:
                return f.read(), None
        except OSError as exc:
            return None, f"no AGENTS.md could be read at {root} ({' '.join(str(exc).split())[:100]})"
    try:
        shown = subprocess.run(["git", "-C", root, "show", f"{rev}:./AGENTS.md"], capture_output=True, text=True)
    except OSError as exc:
        return None, f"no AGENTS.md could be read at {rev} (git could not start: {exc})"
    if shown.returncode:
        return None, f"no AGENTS.md could be read at {rev} ({' '.join(shown.stderr.split())[:100]})"
    return shown.stdout, None


def per_change(root, rev=None):
    """`(command, None)`: the repo's per-change command, the `Narrowed` one
    else the `Seam`; or `(None, why)` naming what the section lacks."""
    text, why = agents_text(root, rev)
    if why:
        return None, why
    found = declaration(text)
    if found is None:
        return None, "AGENTS.md has no `## End-to-end seam` section"
    for key, name in (("narrowed", "Narrowed"), ("seam", "Seam")):
        if key in found:
            command = command_of(found[key])
            return (command, None) if command else (None, f"the `{name}` line names no command")
    return None, "AGENTS.md § End-to-end seam declares neither a `Narrowed` nor a `Seam` line"


def read_narrowed(root, rev=None):
    """`narrowed_in` for `root/AGENTS.md` (at `rev`); no file declares
    nothing."""
    text, _ = agents_text(root, rev)
    return None if text is None else narrowed_in(text)


def record_listing(root, state_path, rev=None):
    """Run the listing and write the state file. Returns False when the repo
    declares no narrowed line: nothing is written. Any state an earlier run
    left is removed first, so a run that dies before writing is read as
    "no listing record", never as the previous merge's listing."""
    if os.path.exists(state_path):
        os.remove(state_path)
    narrowed = read_narrowed(root, rev)
    if narrowed is None:
        return False
    state = {"command": narrowed.command, "status": None, "listing": [], "error": narrowed.error}
    if narrowed.command:
        state["command"] += " --list"
        try:
            out = subprocess.run(["sh", "-c", state["command"]], cwd=root, capture_output=True, text=True,
                                 timeout=LISTING_SECONDS)
            state["status"] = out.returncode
            state["listing"] = [x.strip() for x in out.stdout.splitlines() if x.strip()]
        except (OSError, subprocess.TimeoutExpired) as exc:
            state["error"] = f"the listing command could not run ({' '.join(str(exc).split())[:150]})"
    with open(state_path, "w") as f:
        json.dump(state, f)
    return True


def failing_suites(log_path):
    """`(suites, None)` in first-seen order, or `([], why)`: the suites a seam
    log names as failed, which the nightly backstop reads (`backstop/`). A
    `FAIL <suite>` is read only at the start of a line, since a passing suite
    that reprints a child's failure indents it, and names the rest of the
    line, since a suite is labelled with its whole command."""
    try:
        with open(log_path, errors="replace") as f:
            found = [m.group(1) for m in (_FAIL.match(x) for x in f) if m]
    except OSError as exc:
        return [], f"the seam's log could not be read ({' '.join(str(exc).split())[:100]})"
    if not found:
        return [], "the seam's log has no `FAIL <suite>` line"
    return list(dict.fromkeys(found)), None


def record(state_path):
    """The comment for one merge: the listing the narrowed run selected."""
    def unchecked(why):
        return f"selector: not checked: {why}"

    try:
        with open(state_path) as f:
            state = json.load(f)
    except FileNotFoundError:
        return unchecked("no listing record (the narrowed listing step did not run)")
    except (OSError, ValueError) as exc:
        return unchecked(f"the listing record could not be read ({' '.join(str(exc).split())[:100]})")
    try:
        listing = list(state["listing"])
    except (KeyError, TypeError):
        return unchecked("the listing record has no listing")
    if state.get("error"):
        return unchecked(state["error"])
    if state.get("status") != 0:
        return unchecked(f"`{state.get('command')}` exited {state.get('status')}")
    if not listing:
        return unchecked(f"`{state.get('command')}` printed nothing")
    noun = "suite" if len(listing) == 1 else "suites"
    return f"selector: listed {len(listing)} {noun} from `{state['command']}`\n\n```\n" + "\n".join(listing) + "\n```"


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
    cmd = sub.add_parser("command")
    lst = sub.add_parser("list")
    cmt = sub.add_parser("comment")
    for p in (cmd, lst, cmt):
        p.add_argument("--root", required=True)
        p.add_argument("--rev", help="read AGENTS.md as committed at this rev, not the working tree")
    for p in (lst, cmt):
        p.add_argument("--state", required=True)
    cmt.add_argument("--pr")
    cmt.add_argument("--repo")
    args = parser.parse_args(argv)
    if args.cmd == "command":
        command, why = per_change(args.root, args.rev)
        if why:
            print(f"{UNDECLARED}{why}", file=sys.stderr)
            return 1
        print(command)
        return 0
    if args.cmd == "list":
        return 0 if record_listing(args.root, args.state, args.rev) else 3
    if read_narrowed(args.root, args.rev) is None:
        return 0  # no narrowed line: no comment is owed, and none is the answer
    line = record(args.state)
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
