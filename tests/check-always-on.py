#!/usr/bin/env python3
"""Always-on budget gate: the global CLAUDE.md plus every file it `@`-imports
is the text every session loads, so its word count is a cost paid everywhere.
The total is a reported number, never a failure (#2016): it includes files
outside this repo (the vault's Memory/RULES.md), so an overrun can arrive with
no commit here. Fails when an import cannot be read (an unread import is not
zero words), and when a pointer line names a path that does not exist or names
no action: those are this repo's own text.

A pointer line is any line naming a backticked absolute or `~/` path to a
Markdown doc; it must read "Before you <action>: read `<path>`". Every
backticked absolute or `~/` path must exist. `~/.agents/skills/` is this repo,
so those paths resolve into the checkout under test (--root): a doc a branch
adds is found before it merges, and one a branch deletes is missed before it
merges. Words are counted as `wc -w` counts them.

Usage: check-always-on.py [--root <repo>] [--summary] [<CLAUDE.md>]

`--summary` prints the one `always-on: total <n> words...` line and always
exits 0, for `tests/all.sh` to print on every run; it prints no `FAIL` line, so
the nightly backstop never reads it as a failed suite. A count that could not
read an import says `incomplete` on that line.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

BUDGET = 1100
MAX_IMPORT_DEPTH = 4  # the memory doc's own limit on nested imports
SKILLS_PREFIX = "~/.agents/skills/"
# `@path` anywhere in the text, but never an email address (a word character
# before the `@`) or a span inside backticks; a path holds at least one `/`.
IMPORT = re.compile(r"(?<![\w`])@([~.\w-]*/[^\s`]*)")
# A `/landed` slash command is one segment; a path has at least two.
CODE_PATH = re.compile(r"`(~/[^`\s]*|/[^`\s/]+/[^`\s]*)`")
POINTER = re.compile(r"Before you [^:]+: read `")


def resolve(path: str, root: Path, base: Path) -> Path:
    if path.startswith(SKILLS_PREFIX):
        return root / path[len(SKILLS_PREFIX):]
    if path.startswith("~/"):
        return Path(os.environ["HOME"]) / path[2:]
    p = Path(path)
    return p if p.is_absolute() else base / p


def count(file: Path, label: str, root: Path, depth: int, rows: list, errors: list) -> None:
    text = file.read_text()
    rows.append((label, len(text.split())))
    if depth >= MAX_IMPORT_DEPTH:
        return
    for name in IMPORT.findall(text):
        target = resolve(name, root, file.parent)
        if not target.is_file():
            errors.append(f"import not found: {name}")
            continue
        count(target, name, root, depth + 1, rows, errors)


def logical_lines(text: str):
    """(first line number, text) per bullet or paragraph line, with a wrapped
    bullet's indented continuation lines joined onto it."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if out and line.startswith("  ") and line.strip():
            out[-1] = (out[-1][0], out[-1][1] + " " + line.strip())
        else:
            out.append((n, line))
    return out


def check_pointers(file: Path, root: Path, errors: list) -> None:
    for n, line in logical_lines(file.read_text()):
        for path in CODE_PATH.findall(line):
            if not resolve(path, root, file.parent).exists():
                errors.append(f"{file.name}:{n}: names a path that does not exist: {path}")
            if path.endswith(".md") and not POINTER.search(line):
                errors.append(f"{file.name}:{n}: pointer line names no action "
                              f"(want \"Before you <action>: read `{path}`\")")


def main() -> int:
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=here)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("claude_md", type=Path, nargs="?")
    args = ap.parse_args()
    claude_md = args.claude_md or args.root / "flow" / "claude" / "CLAUDE.md"
    rows, errors = [], []
    count(claude_md, "CLAUDE.md", args.root, 0, rows, errors)
    total = sum(w for _, w in rows)
    if args.summary:
        print(f"always-on: total {total} words" + (f", incomplete: {errors[0]}" if errors else "")
              + (f", over its budget of {BUDGET}" if total > BUDGET else ""))
        return 0
    check_pointers(claude_md, args.root, errors)
    for label, words in rows:
        print(f"  {words:5d}  {label}")
    for e in errors:
        print(f"FAIL {e}")
    print(f"always-on: total {total} words, "
          + (f"over its budget of {BUDGET}" if total > BUDGET else f"within budget {BUDGET}"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
