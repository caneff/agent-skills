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
import argparse
import os
import re
import sys

# #890's fence reader, imported rather than reimplemented: a fenced region is
# an example, never a declaration, and a second copy of that rule is a second
# place for the bug it fixed. `references/closing-ticket.md` shows this very
# grammar inside a fence, so a repo that pastes the doc must declare nothing
# by showing it. `visible()` rather than the bare `unfenced()` (#999): an
# indented quotation is quoted material too, and this reader has no filter
# of its own to drop it. The import is the same coupling this skill already
# has — `implement-spec` is policy over `burndown`, and does not run without
# it.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "burndown"))
from frontier import key_line, visible  # noqa: E402

_ANY_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+\S")
_SEAM_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+end-to-end seam[ \t]*:?[ \t]*$",
                           re.IGNORECASE)


class SeamError(Exception):
    """No seam to name. Fatal: a closing ticket that names none is the one
    this check exists to stop being written again."""


def declaration(text):
    """`{seam, blind to}` from a document's `## End-to-end seam` section, or
    `None` when it has no such section — silence, which is not a
    declaration."""
    lines = visible((text or "").splitlines())
    for pos, (_, line) in enumerate(lines):
        if not _SEAM_HEADING.match(line):
            continue
        found = {}
        for _, rest in lines[pos + 1:]:
            if _ANY_HEADING.match(rest):
                break
            key = key_line(rest)
            if key:
                found[key[0]] = key[1]
        return found
    return None


def seam_of(root, seam=None, blind_to=None):
    """The repo's declared seam and blind spot.

    **The declaration wins.** The exploration pass fills only what the
    declaration omits — a repo that declares nothing still has a seam once
    the pass has found one — and where both are present and differ, this
    refuses and names them both. A declaration an inferred value may silently
    override is not a declaration, and a stale exploration result would
    replace the repo's canonical answer with nothing said. Refuses when
    either half is missing from both sources.
    """
    if not os.path.isdir(root):
        # Distinct from a repo that declares nothing: a typo'd root reported
        # as a policy gap sends the reader to edit an `AGENTS.md` that was
        # never the problem.
        raise SeamError(f"{root} is not a directory")
    try:
        # Leniently decoded rather than crashed on: this generates a ticket
        # inside an unattended run, and a traceback out of `<frozen codecs>`
        # reads as a broken tool rather than as a repo with an odd byte.
        with open(os.path.join(root, "AGENTS.md"), errors="replace") as fh:
            found = declaration(fh.read()) or {}
    except OSError:
        found = {}
    seam = _settled("**Seam**", root, found.get("seam"), seam)
    blind_to = _settled("**Blind to**", root, found.get("blind to"), blind_to)
    for key, value in (("**Seam**", seam), ("**Blind to**", blind_to)):
        # `key_line` reads `- **Seam**:**` as the value `**`; a value of
        # nothing but emphasis markers names nothing (#1104).
        if value and not value.strip("*_ \t"):
            raise SeamError(f"{root}: {key} reads {value!r}, which is only "
                            "emphasis markers and names nothing")
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


def _review_procedure(spec, shas):
    """How to run the spec-level review over a list of commits.

    `/multi-axis-code-review` pins **one** fixed point and reads
    `<fixed point>...HEAD`, so it cannot take disjoint commits. A ticket that
    names the shas and stops states a procedure nothing can carry out, and
    the worker falls back to inventing a range on a shared default branch —
    which is the failure the sha list exists to prevent. So the comparison is
    **built** first, out of the shas themselves.
    """
    first, rest = shas[0], shas[1:]
    tree = f"../review-spec-{spec}"
    lines = [
        "`/multi-axis-code-review` takes one fixed point and reads",
        "`<fixed point>...HEAD`, so build the comparison out of those commits",
        "first — never a range on the default branch, which carries every",
        "other session's work:",
        "",
        "```",
        f"git worktree add {tree} --detach {first}",
        f"cd {tree}",
    ]
    lines += [f"git cherry-pick {sha}" for sha in rest]
    lines += [
        f"/multi-axis-code-review {first}~1",
        f"git worktree remove {tree}",
        "```",
        "",
        f"HEAD is then this spec's commits and nothing else, and `{first}~1` "
        "is what",
        "the first of them landed on.",
    ]
    if rest:
        lines += [
            "",
            "Where a cherry-pick **conflicts** — the spec's own squash commits "
            "usually",
            "apply clean, but a spec that rewrote its own work may not — abort "
            "it and",
            "review the commits one at a time instead, each against its own "
            "parent:",
            "",
            "```",
            "git cherry-pick --abort",
        ]
        for sha in shas:
            lines += [f"git worktree add ../review-{sha[:7]} --detach {sha}",
                      f"cd ../review-{sha[:7]} && /multi-axis-code-review {sha}~1",
                      f"cd - && git worktree remove ../review-{sha[:7]}"]
        lines.append("```")
    return "\n".join(lines)


def _settled(key, root, declared, explored):
    """One half of the seam: the declaration where there is one, and the
    exploration pass's answer only where there is not."""
    declared = (declared or "").strip()
    explored = (explored or "").strip()
    if declared and explored and declared != explored:
        raise SeamError(
            f"{key}: {os.path.join(root, 'AGENTS.md')} declares "
            f"{declared!r} and the exploration pass supplied {explored!r}. "
            "The declaration is authoritative, so this is not a value to "
            "pick between: either the pass is stale, or the declaration is "
            "wrong and the repo's own file is where that gets fixed")
    return declared or explored


def body(root, spec, shas, surfaces=None, seam=None, blind_to=None):
    """The closing ticket's body for one spec: the seam it drives, what that
    seam cannot see, and the merge shas the spec-level review is handed.

    `shas` are the spec's squash commits, read off the run file. They are a
    **list**, never a range: `<first>..origin/main` on a shared `main` held
    this spec's three commits and ~17 unrelated ones from other sessions, and
    `/multi-axis-code-review` takes one fixed point.
    """
    if surfaces is None:
        # Not defaulted to none: the #781 failure was a user-visible surface
        # nobody asked about. The exploration pass answers the question, with
        # an empty list where the seam reaches everything.
        raise SeamError(
            "the closing ticket must answer whether the spec has a "
            "user-visible surface the seam cannot reach — pass the surfaces, "
            "or an empty list to say there are none")
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
              "This spec's merge commits, from the run file, in landing "
              "order:", ""]
    lines += [f"- `{sha}`" for sha in shas]
    lines += ["", _review_procedure(spec, shas)]
    lines += ["", "## Acceptance criteria", "",
              "- [ ] One end-to-end test drives the whole spec's acceptance "
              f"criteria at the seam above, and lives where `{seam}` runs it",
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
    parser = argparse.ArgumentParser(
        prog="closing_ticket.py",
        description="The closing ticket's body for one spec.")
    parser.add_argument("root", help="the repo root whose AGENTS.md declares "
                                     "the end-to-end seam")
    parser.add_argument("spec", type=int, help="the spec's issue number")
    parser.add_argument("--shas", required=True, action="append", default=[],
                        help="this run's merge shas, comma-separated; repeatable")
    surfaces = parser.add_mutually_exclusive_group(required=True)
    surfaces.add_argument("--surface", action="append", default=[],
                          help="a user-visible surface the seam cannot reach; "
                               "repeatable")
    surfaces.add_argument("--no-surface", action="store_true",
                          help="the seam reaches every surface this spec touches")
    parser.add_argument("--seam", help="the seam, where the repo declares none")
    parser.add_argument("--blind-to", help="what that seam cannot see")
    args = parser.parse_args(argv[1:])

    shas = [sha for group in args.shas for sha in group.split(",")]
    try:
        print(body(args.root, args.spec, shas, args.surface, args.seam,
                   args.blind_to), end="")
    except SeamError as exc:
        print(f"closing_ticket.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
