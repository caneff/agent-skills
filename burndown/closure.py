#!/usr/bin/env python3
"""The include closure of a change, and the clumps it implies.

A **clump** is one connected component of a run's file-collision graph: one
worker, one workspace, one PR. Built from each candidate's *declared seams* —
prose typed by whoever filed the ticket — the graph lies. On #781 ticket #451
named each component's `update` and `validate` and nothing about skyscraper;
its diff touched 41 files across six example families through a shared
`#include ../_shared/line-kind.js`, and collided with a worker already
committing to four of them.

So the graph is built from the **include closure** instead: the files a change
to a candidate's target files actually regenerates. The repo declares its
include directive and its generator command in `AGENTS.md` and this resolver
follows that declaration one hop. It never runs the generator — resolving the
closure empirically would cost one regeneration per candidate per wave.

The grammar, the two modes and what each answers: `references/closure.md`.
"""
import collections
import os
import posixpath
import re
import sys

# The fence rule is #890's, bug-for-bug: a declaration inside ``` or ~~~ is
# quoted material, and a fence closes CommonMark's way. Imported rather than
# copied — a second parser is a second place for the quoted-template bug.
from frontier import unfenced

_ANY_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+\S")
_CLOSURE_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+include closure[ \t]*:?[ \t]*$",
                              re.IGNORECASE)
# `- **Directive**: `#include <path>`` — the key in optional emphasis, the
# value in optional backticks.
_KEY = re.compile(r"^[ \t]*[-*+][ \t]*[*_]{0,2}([A-Za-z][A-Za-z -]*?)[*_]{0,2}[ \t]*:[ \t]*(.*?)[ \t]*$")
# "None", however it is dressed, as a *statement*: `None`, `- None`,
# `None — nothing here is generated.` What follows it must end the clause, so
# that `None of the docs are generated, but examples/ are` — a sentence
# somebody will write in this section one day — is read as prose this grammar
# cannot parse rather than as "this repo has no include graph", which would
# clump every candidate alone and dispatch two workers into the same files.
# Silence is a third answer again; see `declaration`.
_NONE = re.compile(r"^[-*\s]*none[ \t]*([.,;:\u2014\u2013-]|$)", re.IGNORECASE)


PATH_SLOT = "<path>"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".claude"}
MARKDOWN = {"md", "markdown"}
MAX_BYTES = 1_000_000


class ClosureError(Exception):
    """The closure could not be resolved from a declaration. The caller
    decides whether that is fatal or a fall back to conservative clumping."""


# What a repo's `AGENTS.md` says regenerates what. `directive` is a template
# naming where a path sits in the repo's include line — `#include <path>` — or
# `None` when the repo states it has no include graph at all. `generator` is
# the command that regenerates, reported and never run.
Declaration = collections.namedtuple(
    "Declaration", "directive generator relative_to")
Declaration.__new__.__defaults__ = (None, None, "file")


def declaration_section(text):
    """The lines under an `## Include closure` heading, or `None` when the
    document has no such section — silence, which is not a declaration."""
    visible = list(unfenced((text or "").splitlines()))
    for pos, (_, line) in enumerate(visible):
        if not _CLOSURE_HEADING.match(line):
            continue
        section = []
        for _, rest in visible[pos + 1:]:
            if _ANY_HEADING.match(rest):
                break
            section.append(rest)
        return "\n".join(section).strip()
    return None


def parse_declaration(text):
    """`Declaration` for a repo's `AGENTS.md` text, or `None` when it
    declares nothing."""
    section = declaration_section(text)
    if section is None:
        return None
    fields = {}
    for line in section.splitlines():
        key = _KEY.match(line)
        if key:
            fields[key.group(1).strip().lower()] = key.group(2).strip().strip("`")
    directive = fields.get("directive")
    if not directive:
        # A stated `None` is an answer: this repo generates nothing, so a
        # closure is the candidate's own files. Anything else in the section
        # states nothing this grammar can read, which is silence.
        if _NONE.match(section):
            return Declaration()
        return None
    return Declaration(directive=directive,
                       generator=fields.get("generator"),
                       relative_to=fields.get("paths") or "file")


def declaration(root):
    """`Declaration` for a repo on disk, or `None` when its `AGENTS.md` is
    missing or declares nothing."""
    try:
        with open(f"{root}/AGENTS.md") as fh:
            return parse_declaration(fh.read())
    except OSError:
        return None


def directive_pattern(directive):
    """The repo's include line as a regex with the path captured. The
    declaration is a template — `#include <path>`, `{% include "<path>" %}` —
    so everything but `<path>` is matched literally and the repo is never
    asked to write a regex into a doc for agents."""
    if PATH_SLOT not in directive:
        raise ClosureError(
            f"the declared directive `{directive}` has no `{PATH_SLOT}` in it")
    head, _, tail = directive.partition(PATH_SLOT)
    # A path runs to the next literal the template names, or to whitespace
    # when the template ends at the path.
    slot = r"(.+?)" if tail.strip() else r"(\S+)"
    return re.compile(re.escape(head) + slot + re.escape(tail))


def canonical(root, path):
    """One repo-relative posix spelling for a candidate's file, whatever the
    ticket or the command line wrote: `./a/x.js`, `a//x.js` and an absolute
    path inside `root` all come back `a/x.js`.

    Both modes compare paths, and two spellings of one file collide with
    nobody — the silent under-clumping this whole reader exists to stop. A
    path that leaves the repo is refused rather than guessed at."""
    text = str(path).replace(os.sep, "/").strip()
    if posixpath.isabs(text) or (len(text) > 1 and text[1] == ":"):
        absolute = os.path.realpath(text)
        inside = os.path.realpath(root)
        rel = os.path.relpath(absolute, inside).replace(os.sep, "/")
    else:
        rel = posixpath.normpath(text)
    if rel == ".." or rel.startswith("../"):
        raise ClosureError(f"candidate file outside the repo: {path}")
    return rel


def repo_files(root):
    """Every file under `root` as a repo-relative posix path, minus the
    directories in `SKIP_DIRS`. Text is not filtered here — `read_text` drops
    what does not read as text, since that needs the bytes.

    A directory that cannot be read raises rather than vanishing: a dropped
    directory is a dropped includer, and a closure short of one file clumps
    two workers apart that belong together."""
    def refuse(error):
        raise ClosureError(f"cannot read {getattr(error, 'filename', root)}: {error}")

    out = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=refuse):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out.append(rel)
    return out


def read_text(path):
    """A file's text, or `None` when it is not text or cannot be read. Only
    the first `MAX_BYTES` are read: an include directive that sits past a
    megabyte of generated output is not the case this is protecting."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_BYTES)
    except OSError:
        return None
    if b"\0" in raw:
        return None
    return raw.decode("utf-8", errors="ignore")


def scanned_lines(rel, text):
    """The lines of one file a directive may be read from.

    In Markdown a fenced block is quotation by definition, so a doc that
    *shows* the repo's include line — `references/closure.md` does, and so
    will any doc explaining the grammar — must not register as an edge.
    Everywhere else every line counts: a ``` line in source code means
    nothing in particular, and treating it as a fence would hide the real
    directives after it, which is the under-clumping direction."""
    lines = text.splitlines()
    if rel.rsplit(".", 1)[-1].lower() in MARKDOWN:
        return [line for _, line in unfenced(lines)]
    return lines


def include_edges(root, decl):
    """`{included path: {files that include it}}` over the whole repo — one
    scan, whatever the queue's size. Resolving this per candidate is the
    expense the declaration exists to avoid."""
    pattern = directive_pattern(decl.directive)
    edges = {}
    for rel in repo_files(root):
        text = read_text(os.path.join(root, rel))
        if text is None:
            continue
        for line in scanned_lines(rel, text):
            for match in pattern.finditer(line):
                target = resolve_reference(rel, match.group(1).strip(),
                                           decl.relative_to)
                edges.setdefault(target, set()).add(rel)
    return edges


def resolve_reference(includer, reference, relative_to):
    """The repo-relative path an include line names, from the file that
    wrote it. Declared `paths: repo-root` reads the reference as written;
    the default reads it against the including file's own directory, which
    is what `#include ../_shared/line-kind.js` means."""
    reference = reference.strip().strip("\"'")
    base = "" if "root" in relative_to else posixpath.dirname(includer)
    return posixpath.normpath(posixpath.join(base, reference))


def resolve_closure(root, files, decl=None, edges=None):
    """`(repo, files) -> file set`: the files a change to `files`
    regenerates, **one hop** — the candidate's own files plus every file
    that includes one of them.

    One hop is the declared cost ceiling, not an approximation of a
    transitive walk: the second hop is where the graph flattens into "most
    of the repo" and stops separating any two candidates. A repo whose
    generator cascades states that by declaring the hub file as a target,
    not by asking this resolver to walk further.

    Returns the files themselves when the repo declares it has no include
    graph, and raises `ClosureError` when it declares nothing at all — the
    caller falls back to subtree clumping, which is a decision above this
    function.
    """
    decl = decl if decl is not None else declaration(root)
    if decl is None:
        raise ClosureError(f"{root}/AGENTS.md declares no include closure")
    targets = {canonical(root, f) for f in files}
    if not decl.directive:
        return targets
    edges = include_edges(root, decl) if edges is None else edges
    closure = set(targets)
    for target in targets:
        closure |= edges.get(target, set())
    return closure


# The three states the opening report must tell apart. A controller reading
# "conservative" needs to know whether the repo said nothing — a gap someone
# should close — or said None, which is the truth about that repo.
ANNOUNCEMENTS = {
    "closure": ("clumping: include closure, from AGENTS.md "
                "(directive `{directive}`, generator `{generator}`)"),
    "no-include-graph": ("clumping: include closure, from AGENTS.md "
                         "(declared None: this repo has no include graph, so "
                         "each candidate closes over its own files)"),
    "subtree": ("clumping: conservative, by directory subtree \u2014 AGENTS.md "
                "declares no include closure, so any two candidates touching "
                "the same directory subtree are one clump"),
}


def mode(decl):
    """Which of the three answers this repo gave: a declared directive, a
    stated `None`, or silence."""
    if decl is None:
        return "subtree"
    return "no-include-graph" if not decl.directive else "closure"


def announcement(decl):
    """The line the run's opening report carries, in stated words, saying
    which of the three modes this repo got. One cascade, in `mode`: a fourth
    state must not need editing in two places to be announced."""
    return ANNOUNCEMENTS[mode(decl)].format(
        directive=decl.directive if decl else None,
        generator=(decl.generator if decl else None) or "none declared")


def subtree_collides(left, right):
    """The conservative rule for a repo that declares nothing: two candidates
    collide when either one's directory contains the other's. A candidate
    touching a file at the repo root therefore collides with everything,
    which is the point — conservative means clumping too much, never too
    little."""
    for a in {posixpath.dirname(f) for f in left}:
        for b in {posixpath.dirname(f) for f in right}:
            if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                return True
            if b == "" or a == "":
                return True
    return False


def components(candidates, collides):
    """Connected components of the collision graph, each sorted by ticket
    number, the components ordered by their lowest — which is the ticket a
    clump's branch and workspace are named for."""
    parent = {c["number"]: c["number"] for c in candidates}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for i, left in enumerate(candidates):
        for right in candidates[i + 1:]:
            if collides(left, right):
                parent[find(left["number"])] = find(right["number"])
    groups = {}
    for c in candidates:
        groups.setdefault(find(c["number"]), []).append(c["number"])
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


def clumps(root, candidates, decl=None):
    """`(candidates) -> components`: one clump per connected component of
    the collision graph over the candidates' closures.

    A candidate is `{"number": <n>, "files": [...]}` — the files its ticket
    targets. The answer carries the mode and the announcement line as well as
    the clumps, because a controller reading a set of clumps has to know
    whether it was clumped precisely or conservatively.

    The whole queue is resolved against one repo scan, not one per
    candidate: that scan is the entire reason the declaration exists.
    """
    decl = decl if decl is not None else declaration(root)
    how = mode(decl)
    named = {c["number"]: {canonical(root, f) for f in c["files"]}
             for c in candidates}
    closures = {}
    if how == "subtree":
        def collides(left, right):
            return subtree_collides(named[left["number"]], named[right["number"]])
    else:
        edges = include_edges(root, decl) if decl.directive else {}
        for c in candidates:
            closures[c["number"]] = resolve_closure(root, c["files"], decl, edges)

        def collides(left, right):
            return bool(closures[left["number"]] & closures[right["number"]])

    groups = components(list(candidates), collides)
    out = []
    for g in groups:
        clump = {"tickets": g,
                 "files": sorted(set().union(*(named[n] for n in g)))}
        if how != "subtree":
            # Only where a closure was resolved. In subtree mode there is no
            # closure, and a `closure` key holding the tickets' declared files
            # would hand a consumer the declared seams this reader exists to
            # stop trusting.
            clump["closure"] = sorted(set().union(*(closures[n] for n in g)))
        out.append(clump)
    return {"mode": how, "announcement": announcement(decl), "clumps": out}


def render(clumping):
    lines = [clumping["announcement"]]
    for clump in clumping["clumps"]:
        tickets = ", ".join(f"#{n}" for n in clump["tickets"])
        paths = clump.get("closure")
        what = "closure" if paths is not None else "files named, no closure resolved"
        paths = clump["files"] if paths is None else paths
        lines.append(f"clump {tickets}  ({len(paths)} {what})")
        lines.extend(f"    {path}" for path in paths)
    return "\n".join(lines)


def parse_candidate(spec):
    """`<n>=<path>[,<path>...]` — one candidate and the files its ticket
    targets."""
    number, sep, files = spec.partition("=")
    if not sep or not number.strip().lstrip("#").isdigit():
        raise ClosureError(f"not a candidate: {spec}")
    paths = [f.strip() for f in files.split(",") if f.strip()]
    if not paths:
        raise ClosureError(f"candidate {number} names no files")
    return {"number": int(number.strip().lstrip("#")), "files": paths}


def main(argv):
    if len(argv) < 3:
        print("usage: closure.py <repo-root> <n>=<path>[,<path>]...",
              file=sys.stderr)
        return 2
    try:
        candidates = [parse_candidate(spec) for spec in argv[2:]]
        print(render(clumps(argv[1], candidates)))
    except ClosureError as exc:
        print(f"closure.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
