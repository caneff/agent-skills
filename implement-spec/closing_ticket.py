#!/usr/bin/env python3
"""The spec's closing check: the end-to-end seam it names, and what that
seam is blind to, and the spec-level review. The text is a section for the
spec's integration PR (#1461), or for the slice of a one-slice spec, never a
ticket of its own (#1402).

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
import subprocess
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
from frontier import key_line, unfenced, visible  # noqa: E402

_ANY_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+\S")
# A list item's marker: a bare `**Key**:` line also matches `key_line`, by
# its first `*`, but is no list item.
_LIST_ITEM = re.compile(r"^[ \t]*[-*+][ \t]+")
_SEAM_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+end-to-end seam[ \t]*:?[ \t]*$",
                           re.IGNORECASE)


class SeamError(Exception):
    """No seam to name. Fatal: a closing check that names none is the one
    this check exists to stop being written again."""


def _indent(line):
    return len(line) - len(line.lstrip(" \t"))


def _continuation(raw, start, reachable):
    """The lines wrapping the list item at `raw[start]`, one stripped string
    per line, and the index after the last: each line indented deeper than
    the item, up to a heading, a key line, or a line `reachable` (the indices
    outside a fence) does not hold. Under a list item, blank lines are
    skipped when the next line still continues it, so a loose item's
    indented second paragraph is part of it, as in Markdown (#1406). Under a
    key line that is no list item a blank line ends the value: what follows
    indented is a code block, not a paragraph of it. A key line always ends
    the item, deeper or not, so a declaration nested under a parent bullet
    still reads as before. Read from the raw lines, not from `visible()`,
    because a four-space continuation is what `visible()` drops as quoted
    material, and dropping it is the truncation (#1243)."""
    depth = _indent(raw[start])
    loose = bool(_LIST_ITEM.match(raw[start]))
    wrapped = []
    end = start + 1
    for index in range(start + 1, len(raw)):
        line = raw[index]
        if not line.strip():
            if loose:
                continue
            break
        if (index not in reachable or _indent(line) <= depth
                or _ANY_HEADING.match(line) or key_line(line)):
            break
        wrapped.append(line.strip())
        end = index + 1
    return wrapped, end


def declaration(text):
    """`{seam, blind to}` from a document's `## End-to-end seam` section, or
    `None` when it has no such section — silence, which is not a
    declaration. A value wrapped onto continuation lines is read whole
    (#1243): a partial blind spot stated as the whole one is worse than none."""
    raw = (text or "").splitlines()
    lines = visible(raw)
    reachable = {index for index, _ in unfenced(raw)}
    for pos, (_, line) in enumerate(lines):
        if not _SEAM_HEADING.match(line):
            continue
        found = {}
        skip_to = 0
        for index, rest in lines[pos + 1:]:
            if _ANY_HEADING.match(rest):
                break
            if index < skip_to:
                continue
            pair = key_line(rest)
            if pair:
                key, value = pair
                wrapped, skip_to = _continuation(raw, index, reachable)
                found[key] = " ".join([value] + wrapped).strip()
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
    either half is missing from both sources, and when either settled value
    is only emphasis markers (`- **Seam**:**` reads as the value `**`),
    which names nothing (#1104).
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
    if not seam:
        raise SeamError(
            f"{root} declares no `## End-to-end seam` section and the "
            "exploration pass supplied no seam: the closing check has "
            "nothing to name")
    if not blind_to:
        raise SeamError(
            f"{root}: the seam is named but `**Blind to**` is not. The seam "
            "that existed on #781 had diverged from the live editor inside "
            "that same spec; a seam with no stated blind spot sends the "
            "worker at it anyway")
    return seam, blind_to


def _settled(key, root, declared, explored):
    """One half of the seam: the declaration where there is one, and the
    exploration pass's answer only where there is not. An emphasis-only
    value is refused."""
    declared = (declared or "").strip()
    explored = (explored or "").strip()
    if declared and explored and declared != explored:
        raise SeamError(
            f"{key}: {os.path.join(root, 'AGENTS.md')} declares "
            f"{declared!r} and the exploration pass supplied {explored!r}. "
            "The declaration is authoritative, so this is not a value to "
            "pick between: either the pass is stale, or the declaration is "
            "wrong and the repo's own file is where that gets fixed")
    value = declared or explored
    # `key_line` reads `- **Seam**:**` as the value `**`; a value of
    # nothing but emphasis markers names nothing (#1104).
    if value and not re.sub(r"[\s*_]", "", value):
        raise SeamError(f"{root}: {key} reads {value!r}, which is only "
                        "emphasis markers and names nothing")
    return value


def body(root, spec, surfaces=None, seam=None, blind_to=None, default="main",
         one_slice=False):
    """The closing check for one spec: the seam it drives, what that seam
    cannot see, and the spec-level review.

    A spec with more than one slice lands on `<default>` in one integration PR
    from `spec-<spec>` (#1461), and this is that PR's section. The review reads
    `origin/<default>...spec-<spec>`: the integration branch holds this spec's
    slices and merges of `<default>`, nothing else, so the range is the
    review's own. The merge-sha list and its cherry-pick procedure, which a
    spec landing slice by slice on a shared `main` needed (#781's range held
    ~17 unrelated commits), are gone.

    A one-slice spec has no integration branch (ruling 3a of #1457): its slice
    lands on `<default>` with its own review wave, so `one_slice` makes a
    section for that slice's body with no spec-level review.
    """
    if surfaces is None:
        # Not defaulted to none: the #781 failure was a user-visible surface
        # nobody asked about. The exploration pass answers the question, with
        # an empty list where the seam reaches everything.
        raise SeamError(
            "the closing check must answer whether the spec has a "
            "user-visible surface the seam cannot reach — pass the surfaces, "
            "or an empty list to say there are none")
    seam, blind_to = seam_of(root, seam, blind_to)
    surfaces = [s.strip() for s in surfaces if s and s.strip()]
    branch = f"spec-{spec}"
    merge_in = f"git fetch origin && git merge --no-edit origin/{default}"

    if one_slice:
        lines = ["## Closing check", "",
                 f"This is the only slice of spec #{spec}: its PR also carries "
                 "one end-to-end test at this repo's seam, and its own review "
                 f"wave is the spec's review. Add a bare `Closes #{spec}` line "
                 "to the PR body and to the last commit: the spec closes when "
                 "this slice merges.", ""]
    else:
        lines = ["## Closing check", "",
                 f"The closing check of spec #{spec}, run on its integration "
                 f"PR: base `{default}`, head `{branch}`, opened once every "
                 f"slice has landed on `{branch}`. Its body carries a bare "
                 "`Closes #<slice>` line for every slice of the spec and a "
                 f"bare `Closes #{spec}`.", ""]
    lines += ["### The seam", "",
              f"- **Seam**: {seam}",
              f"- **Blind to**: {blind_to}",
              ""]
    if surfaces:
        lines += ["The spec touches a user-visible surface this seam cannot "
                  "reach:", ""]
        lines += [f"- {s}" for s in surfaces]
        lines.append("")
    if not one_slice:
        lines += [
            f"The end-to-end check is that seam run on `{branch}` merged with "
            f"current `origin/{default}`.", "",
            "### The spec-level review", "",
            f"Merge `origin/{default}` into `{branch}` first, and again before "
            "the integration PR goes up — a merge, never a rebase, which "
            "would rewrite the shas the dispositions name:", "",
            "```", merge_in, "```", "",
            f"Then one wave over `origin/{default}...{branch}` from a "
            f"workspace on `{branch}`: `/multi-axis-code-review "
            f"origin/{default}`'s three axes and one Codex pass behind "
            "`codex-usage-gate.py`. The ticket text they judge against is "
            f"spec #{spec} and every slice, bodies and comments. The findings "
            f"sidecars, `dispositions-{spec}.jsonl` and the review-ledger "
            f"rows are keyed on #{spec}. One fix worker disposes of every "
            "finding (`implement/SKILL.md` § Review steps 2–3) and runs the "
            f"full seam; `fix-check.sh {spec} origin/{branch}` then exits 0.",
            ""]
    lines += ["### Acceptance criteria", "",
              "- [ ] One end-to-end test drives the whole spec's acceptance "
              f"criteria at the seam above, and lives where `{seam}` runs it",
              "- [ ] What the seam is blind to is stated in the test's own "
              "comment, so the next reader knows what a green run does not "
              "cover"]
    if not one_slice:
        lines.append(f"- [ ] The spec-level review run over "
                     f"`origin/{default}...{branch}`, every finding disposed "
                     f"of, and `fix-check.sh {spec} origin/{branch}` exits 0")
    for surface in surfaces:
        lines.append(f"- [ ] One open of the real thing: {surface} — checked "
                     "in the shipping surface, not in the seam")
    return "\n".join(lines) + "\n"


def default_branch(root):
    """`<default>` off the repo's `origin/HEAD`, or None when git cannot say."""
    try:
        done = subprocess.run(["git", "-C", root, "symbolic-ref", "--short",
                               "refs/remotes/origin/HEAD"],
                              capture_output=True, text=True)
    except OSError:
        return None
    ref = done.stdout.strip()
    if done.returncode != 0 or not ref.startswith("origin/"):
        return None
    return ref[len("origin/"):]


def main(argv):
    parser = argparse.ArgumentParser(
        prog="closing_ticket.py",
        description="The closing check section of a spec's integration PR, "
                    "or of the slice of a one-slice spec.")
    parser.add_argument("root", help="the repo root whose AGENTS.md declares "
                                     "the end-to-end seam")
    parser.add_argument("spec", type=int, help="the spec's issue number")
    parser.add_argument("--one-slice", action="store_true",
                        help="the spec has one slice and no integration "
                             "branch: a section for that slice's body")
    parser.add_argument("--default",
                        help="the default branch; read off the root's "
                             "origin/HEAD when omitted")
    surfaces = parser.add_mutually_exclusive_group(required=True)
    surfaces.add_argument("--surface", action="append", default=[],
                          help="a user-visible surface the seam cannot reach; "
                               "repeatable")
    surfaces.add_argument("--no-surface", action="store_true",
                          help="the seam reaches every surface this spec touches")
    parser.add_argument("--seam", help="the seam, where the repo declares none")
    parser.add_argument("--blind-to", help="what that seam cannot see")
    args = parser.parse_args(argv[1:])

    default = args.default or default_branch(args.root)
    try:
        # A one-slice section names no range, so it needs no default branch.
        if not default and not args.one_slice:
            # Never assumed to be `main`: a section naming the wrong range
            # sends the review at the wrong diff.
            raise SeamError(f"{args.root} has no readable origin/HEAD: pass "
                            "--default <branch>")
        print(body(args.root, args.spec, args.surface, args.seam,
                   args.blind_to, default, args.one_slice), end="")
    except SeamError as exc:
        print(f"closing_ticket.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
