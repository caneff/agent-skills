#!/usr/bin/env python3
"""Which suites `tests/all.sh --changed` keeps, from the files a diff changed.

    suite-edges.py --select --suite-dirs "<dir> ..."   changed paths on stdin
    suite-edges.py --edges                             every file edge, with its source line

`--select` reads the changed paths from stdin (NUL- or newline-separated) and
prints exactly one line, a verdict word and a tab-separated directory list:

    full<TAB>          run the whole seam; the reason is on stderr
    dirs<TAB>a b c     run the suites under those directories (+ tests/ + repo-wide)
    prose<TAB>a b      a Markdown-only diff in directories with no suites: run the
                       prose checks and the suites under those directories

The verdict word is the answer. An empty directory list after `dirs` means an
empty diff, so a caller that gets no verdict line, a word it does not know, or
a non-zero exit has no answer and must run the full seam (`all.sh` does).

The seam widens to `full` when the diff cannot be pinned to what owns it: the
runner (`tests/all.sh`) or this file changed, a file at the repo root, a file
type this finder does not know, a non-Markdown file in a directory with no
suites, or a changed path git no longer tracks and that nothing can be said
about but by directory (it then widens to every directory that reaches it).

**Edges are between files, not directories.** An edge `F -> T` means tracked
source file `F` (`.py`, `.sh`, `.rs`, `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`) has
a line, with comments, docstrings and commit-message lines removed, that
reaches tracked file `T` in another directory: a `sys.path`, `..`, `parent`,
`__file__`, `source` / `.`, `pardir`, `include_str`, `importlib` or
root-variable (`ROOT`, `root`) line where the directory appears as a path
segment or a component of a path built in code (`PATH_SEGMENT`, `BUILT_PATH`)
on that line or the two after it (a call split over lines). What follows the
directory (`X/sub/file.py`, `"X" / "file.py"`) names the target file or the
files under it; a directory named with nothing after it is every file under it,
except for a `.py` source that puts the directory on `sys.path`, which reaches
only the modules it imports from there. A same-directory `import` is an edge
too, so a change reaches a module's importers by chaining.

A changed file is run for by the suites of every directory that holds a file in
its reverse closure: its own directory and the directories of the files that
(transitively) reach it. The rule over-matches by design: an extra edge only
widens the run, a missing one is the miss this exists to close.
"""
import ast
import io
import re
import subprocess
import sys
import tokenize

# A directory is reached as a path segment (`X/`, or `../X"` ending a path) or as
# a quoted word that is a component of a path built in code (`"..", "X"`,
# `ROOT / "X"`). A bare quoted word alone (`"landed"`) names nothing: dictionary
# keys and prose are full of directory-like words. `docs/research/` names `docs`,
# not `research`, hence the delimiters before the name.
PATH_SEGMENT = r"(?:(?:^|[\s\"'(=,:])|\.\./|(?:root|ROOT|here|HERE|[})])/)%s(?:/|(?<=\.\./%s)[\"'\s])"
BUILT_PATH = r"(?:(?:[\"']\.\.[\"']|pardir)\s*,\s*[\"']%s[\"']|/\s*[\"']%s[\"']|[\"']%s[\"']\s*/)"
# Further quoted components of a built path: `/ "sub" / "f.py"`, `, "sub", "f.py"`.
BUILT_MORE = re.compile(r"\s*[,/]\s*[\"']([^\"']*)[\"']")
HINT = re.compile(r"sys\.path|pardir|\.\.|\bparent\b|__file__|include_str|importlib|\bsource\b|^\s*\.\s|ROOT|\broot\b")
SCANNED = (".py", ".sh", ".rs", ".js", ".mjs", ".cjs", ".ts", ".tsx")
# Types this finder knows: the scanned sources, prose and data. Anything else
# (an image, a binary, a file with no extension) cannot be placed, so it runs
# the full seam.
KNOWN = SCANNED + (".md", ".toml", ".lock", ".json", ".jsonl", ".txt", ".yml", ".yaml", ".html", ".css", ".svg", ".csv")
SPAN = 3  # a hint line and the two after it (a call split over lines)
RUNNER = ("tests/all.sh", "tests/suite-edges.py")
CREATES = re.compile(r"\bmkdir|makedirs|mktemp")  # a line that makes the directory it names is building a fixture
COMMIT_LINE = re.compile(r"\bcommit\b.*\s[\"']?-\w*m\b")  # a `git commit -m` line: its message is prose
TAIL = re.compile(r"[^\s\"'`),;:(<>|&]*")
VARIABLE = re.compile(r"[$*{%?]")


class ScanError(Exception):
    """A tracked file could not be read: the scan has no answer."""


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


# ---- source with comments, docstrings and commit messages removed ----------

def _strip_line_comment(line, markers):
    """Cut a `#` or `//` comment that is not inside a quoted string."""
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif any(line.startswith(m, i) for m in markers):
            before = line[i - 1] if i else " "
            if line.startswith("//", i) and before == ":":  # a URL scheme
                i += 1
                continue
            if line.startswith("#", i) and not before.isspace():
                i += 1
                continue
            return line[:i]
        i += 1
    return line


def _python_lines(text):
    lines = text.splitlines()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start
                lines[row - 1] = lines[row - 1][:col]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass  # a file that will not tokenise keeps its comments: more edges, never fewer
    try:
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                for n in range(node.lineno - 1, node.end_lineno):
                    lines[n] = ""
    except SyntaxError:
        pass
    return lines


def _c_like_lines(text, markers):
    out, in_block = [], False
    for raw in text.splitlines():
        line = raw
        if in_block:
            if "*/" not in line:
                out.append("")
                continue
            line = line.split("*/", 1)[1]
            in_block = False
        if "/*" in line and "*/" not in line.split("/*", 1)[1]:
            line, in_block = line.split("/*", 1)[0], True
        out.append(_strip_line_comment(line, markers))
    return out


def source_lines(path, text):
    """The lines of `text` that are code: a comment, a docstring and a line that
    commits with `-m` are blanked, keeping every line number."""
    if path.endswith(".py"):
        lines = _python_lines(text)
    elif path.endswith(".sh"):
        lines = [_strip_line_comment(l, ("#",)) for l in text.splitlines()]
    else:
        lines = _c_like_lines(text, ("//",))
    return ["" if COMMIT_LINE.search(l) else l for l in lines]


# ---- what a reaching line names ---------------------------------------------

def reaches(span, top):
    name = re.escape(top)
    return bool(re.search(PATH_SEGMENT % (name, name), span) or re.search(BUILT_PATH % (name, name, name), span))


def tails(span, top):
    """What follows `top` at each place `span` reaches it: `sub/file.py` for
    `top/sub/file.py` or `"top" / "sub" / "file.py"`, `` for the bare directory."""
    name = re.escape(top)
    found = []
    for m in re.finditer(PATH_SEGMENT % (name, name), span):
        found.append(TAIL.match(span, m.end()).group(0) if span[m.end() - 1] == "/" else "")
    for m in re.finditer(BUILT_PATH % (name, name, name), span):
        parts, pos = [], m.end()
        if m.group(0).endswith("/"):  # `"top" /` already consumed the separator
            pass
        while True:
            more = BUILT_MORE.match(span, pos)
            if not more:
                break
            parts.append(more.group(1))
            pos = more.end()
        found.append("/".join(p.strip("/") for p in parts if p))
    return found


def resolve(top, tail, by_top):
    """The tracked files under `top` that a reference with this tail names: the
    file, the files under that directory, or those a variable part could name.
    A bare directory (no tail) is every file under it. A tail that names
    nothing tracked names nothing: a file a test writes into a scratch tree, or
    a path inside a fixture repository, is not this repo's file."""
    files = by_top.get(top, [])
    tail = VARIABLE.split(tail, 1)[0]
    if not tail:
        return files
    want = f"{top}/{tail}"
    return [f for f in files if f.startswith(want.rstrip("/") + "/") or f.startswith(want)]


def imported_modules(text):
    names = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            names.add(n.module.split(".")[0])
        elif isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            f = n.func
            if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")) in ("import_module", "__import__"):
                names.add(n.args[0].value.split(".")[0])
    return names


def scan(files):
    """`(edges, reach_dirs)`: `edges[src] = {(target file, source line)}` and
    `reach_dirs[src] = {top directories src reaches}` (for a path git no longer
    tracks, which can only be matched by directory). Raises ScanError."""
    tracked_set = set(files)
    tops = {p.split("/", 1)[0] for p in files if "/" in p}
    by_top = {}
    for p in files:
        if "/" in p:
            by_top.setdefault(p.split("/", 1)[0], []).append(p)
    edges, reach_dirs = {}, {}

    def add(src, target, why):
        if target != src:
            edges.setdefault(src, {})[target] = why

    for path in files:
        if not path.endswith(SCANNED):
            continue
        home = path.split("/", 1)[0] if "/" in path else ""
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as exc:
            raise ScanError(f"cannot read {path}: {exc}")
        lines = source_lines(path, text)
        imports = imported_modules(text) if path.endswith(".py") else set()
        if path.endswith(".py") and imports:
            here = path.rsplit("/", 1)[0] + "/" if "/" in path else ""
            for mod in imports:
                for cand in (f"{here}{mod}.py", f"{here}{mod}/__init__.py"):
                    if cand in tracked_set:
                        add(path, cand, f"{path}: import {mod}")
        for i, line in enumerate(lines):
            if not HINT.search(line) or CREATES.search(line):
                continue
            span = "\n".join(lines[i:i + SPAN])
            for top in tops - {home}:
                if not reaches(span, top):
                    continue
                reach_dirs.setdefault(path, set()).add(top)
                for tail in tails(span, top):
                    targets = resolve(top, tail, by_top)
                    if imports and "sys.path" in span:
                        # A directory put on sys.path is reached through what the
                        # file imports from it, not through every file in it.
                        mods = [f for f in targets if f.endswith(".py") and f.rsplit("/", 1)[1][:-3] in imports]
                        mods += [f for f in targets if f.endswith("/__init__.py") and f.split("/")[-2] in imports]
                        targets = mods or targets
                    for t in targets:
                        add(path, t, f"{path}:{i + 1}: {line.strip()[:100]}")
    return edges, reach_dirs


# ---- selection --------------------------------------------------------------

def closure(changed, edges, reach_dirs, files, deleted):
    """The changed files plus every file that transitively reaches one. A
    deleted path matches no edge target, so the files that reach its top
    directory at all stand in for it."""
    back = {}
    for src, targets in edges.items():
        for t in targets:
            back.setdefault(t, set()).add(src)
    kept = set(changed)
    dead_tops = {p.split("/", 1)[0] for p in deleted if "/" in p}
    work = list(kept)
    for src, tops_reached in reach_dirs.items():
        if tops_reached & dead_tops and src not in kept:
            kept.add(src)
            work.append(src)
    while work:
        f = work.pop()
        for src in back.get(f, ()):
            if src not in kept:
                kept.add(src)
                work.append(src)
    return kept


def select(paths, suite_dirs, files, edges, reach_dirs):
    """`(verdict, dirs, notes)` for the changed `paths`."""
    tracked_set = set(files)
    notes, direct, prose_only, deleted, live = [], set(), True, [], []
    for p in paths:
        top = p.split("/", 1)[0]
        if p in RUNNER:
            return "full", [], [f"{p} itself changed (the runner and the edge finder pick every other selection)"]
        if "/" not in p:
            return "full", [], [f"{p} is at the repo root, which no directory of suites owns"]
        if not p.endswith(KNOWN):
            return "full", [], [f"{p} is a file type the selector does not know"]
        if top not in suite_dirs:
            if not p.endswith(".md"):
                return "full", [], [f"{top}/ holds no suite ({p})"]
        else:
            prose_only = False
            direct.add(top)
        if p in tracked_set:
            live.append(p)
        else:
            deleted.append(p)
    if not paths:
        return "dirs", [], notes
    kept = closure(live, edges, reach_dirs, files, deleted)
    dirs = sorted({f.split("/", 1)[0] for f in kept if "/" in f} & set(suite_dirs) | direct)
    if prose_only:
        return "prose", dirs, notes
    widened = sorted(set(dirs) - direct)
    if widened:
        notes.append(f"cross-directory edges widen {' '.join(sorted(direct)) or 'nothing'} to: {' '.join(dirs)}")
    return "dirs", dirs, notes


def read_paths(data):
    sep = "\0" if "\0" in data else "\n"
    return [p for p in data.split(sep) if p]


def main(argv):
    try:
        if argv[:1] == ["--edges"]:
            edges, _ = scan(tracked())
            for src in sorted(edges):
                for t, why in sorted(edges[src].items()):
                    print(f"{src} -> {t}\t{why}")
            return 0
        if argv[:1] == ["--select"] and len(argv) == 3 and argv[1] == "--suite-dirs":
            suite_dirs = set(argv[2].split())
            files = tracked()
            edges, reach_dirs = scan(files)
            verdict, dirs, notes = select(read_paths(sys.stdin.read()), suite_dirs, files, edges, reach_dirs)
            for note in notes:
                print(("full suite: " if verdict == "full" else "") + note, file=sys.stderr)
            print(f"{verdict}\t{' '.join(dirs)}")
            return 0
    except (ScanError, subprocess.CalledProcessError, OSError) as exc:
        print(f"suite-edges.py: {exc}", file=sys.stderr)
        return 2
    print(__doc__.split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
