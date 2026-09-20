#!/usr/bin/env python3
"""The spec's closing ticket: the end-to-end seam it names, and what that
seam is blind to.

On #781's spec run the closing ticket said "write one end-to-end test over
the whole spec's acceptance criteria" and named no seam, so the closing
worker stopped and asked. The seam that existed — a headless solver bundle —
had already diverged from the live editor **inside that same spec**: a
no-ring header verified green headless and broke 4x4 and 6x6 in the real app.
Naming the seam is necessary and not sufficient; the worker needs its blind
spot too, and one open of the real thing wherever the spec put a user-visible
surface the seam cannot reach.

The declaration grammar and the evidence: `references/closing-ticket.md`.
"""
import os
import re
import sys

_ANY_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+\S")
_SEAM_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+end-to-end seam[ \t]*:?[ \t]*$",
                           re.IGNORECASE)
_KEY = re.compile(r"^[ \t]*[-*+][ \t]*[*_]{0,2}([A-Za-z][A-Za-z -]*?)[*_]{0,2}"
                  r"[ \t]*:[ \t]*(.*?)[ \t]*$")


class SeamError(Exception):
    """No seam to name. Fatal: a closing ticket that names none is the one
    this check exists to stop being written again."""


def declaration(text):
    """`{seam, blind to}` from a document's `## End-to-end seam` section, or
    `None` when it has no such section — silence, which is not a
    declaration."""
    lines = (text or "").splitlines()
    for pos, line in enumerate(lines):
        if not _SEAM_HEADING.match(line):
            continue
        found = {}
        for rest in lines[pos + 1:]:
            if _ANY_HEADING.match(rest):
                break
            match = _KEY.match(rest)
            if match:
                found[match.group(1).strip().lower()] = match.group(2).strip()
        return found
    return None


def seam_of(root, seam=None, blind_to=None):
    """The repo's declared seam and blind spot, with the exploration pass's
    own answers taking precedence — a repo that declares nothing still has a
    seam once the pass has found one. Refuses when either half is missing."""
    found = {}
    try:
        with open(os.path.join(root, "AGENTS.md")) as fh:
            found = declaration(fh.read()) or {}
    except OSError:
        found = {}
    seam = (seam or found.get("seam") or "").strip()
    blind_to = (blind_to or found.get("blind to") or "").strip()
    if not seam:
        raise SeamError(
            f"{root} declares no `## End-to-end seam` section and the "
            "exploration pass supplied no seam: the closing ticket has "
            "nothing to name")
    if not blind_to:
        raise SeamError(
            f"{root}: the seam is named but `**Blind to**` is not. The seam "
            "that existed on #781 had diverged from the live editor inside "
            "that same spec; a seam with no stated blind spot sends the "
            "closing worker at it anyway")
    return seam, blind_to


def body(root, spec, shas, surfaces=(), seam=None, blind_to=None):
    """The closing ticket's body for one spec: the seam it drives, what that
    seam cannot see, and the merge shas the spec-level review is handed.

    `shas` are the spec's squash commits, read off the run file. They are a
    **list**, never a range: `<first>..origin/main` on a shared `main` held
    this spec's three commits and ~17 unrelated ones from other sessions, and
    `/multi-axis-code-review` takes one fixed point.
    """
    seam, blind_to = seam_of(root, seam, blind_to)
    shas = [s.strip() for s in shas if s and s.strip()]
    if not shas:
        raise SeamError("the closing ticket has no merge shas to review: the "
                        "run file's landings are what the spec-level review "
                        "reads")
    surfaces = [s.strip() for s in surfaces if s and s.strip()]

    lines = [f"Close out the spec (#{spec}): one end-to-end test at this "
             "repo's seam, and the spec-level review.",
             "",
             "## The seam",
             "",
             f"- **Seam**: {seam}",
             f"- **Blind to**: {blind_to}",
             ""]
    if surfaces:
        lines += ["The spec touches a user-visible surface this seam cannot "
                  "reach:", ""]
        lines += [f"- {s}" for s in surfaces]
        lines.append("")
    lines += ["## The spec-level review", "",
              "`/multi-axis-code-review` over this spec's merge commits — the "
              "list below, from the run file, not a git range:", ""]
    lines += [f"- `{sha}`" for sha in shas]
    lines += ["", "## Acceptance criteria", "",
              "- [ ] One end-to-end test drives the whole spec's acceptance "
              "criteria at the seam above",
              "- [ ] What the seam is blind to is stated in the test's own "
              "comment, so the next reader knows what a green run does not "
              "cover",
              "- [ ] `/multi-axis-code-review` run over the merge shas listed "
              "above, every finding disposed of"]
    for surface in surfaces:
        lines.append(f"- [ ] One open of the real thing: {surface} — checked "
                     "in the shipping surface, not in the seam")
    return "\n".join(lines) + "\n"


def main(argv):
    args, shas, surfaces, seam, blind_to = list(argv[1:]), [], [], None, None
    positional = []
    while args:
        arg = args.pop(0)
        if arg == "--shas":
            shas += (args.pop(0) if args else "").split(",")
        elif arg == "--surface":
            surfaces.append(args.pop(0) if args else "")
        elif arg == "--seam":
            seam = args.pop(0) if args else ""
        elif arg == "--blind-to":
            blind_to = args.pop(0) if args else ""
        else:
            positional.append(arg)
    if len(positional) != 2:
        print("usage: closing_ticket.py <repo-root> <spec> --shas <sha>[,<sha>...] "
              "[--surface <what>]... [--seam <what> --blind-to <what>]",
              file=sys.stderr)
        return 2
    try:
        print(body(positional[0], positional[1], shas, surfaces, seam, blind_to),
              end="")
    except SeamError as exc:
        print(f"closing_ticket.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
