#!/usr/bin/env python3
"""Always-on budget gate (#1413): the global CLAUDE.md plus every file it
`@`-imports is the text every session loads, so its word count is a cost paid
everywhere. Fails when that total passes BUDGET, when an import cannot be read
(an unread import is not zero words), and when a pointer line names a path
that does not exist or names no action.

A pointer line is any line naming a backticked absolute or `~/` path to a
Markdown doc; it must read "Before you <action>: read `<path>`". Every
backticked absolute or `~/` path must exist. `~/.agents/skills/` is this repo,
so those paths resolve into the checkout under test (--root): a doc a branch
adds is found before it merges, and one a branch deletes is missed before it
merges. Words are counted as `wc -w` counts them.

Usage: check-always-on.py [--root <repo>] [<CLAUDE.md>]
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
    ap.add_argument("claude_md", type=Path, nargs="?")
    args = ap.parse_args()
    claude_md = args.claude_md or args.root / "flow" / "claude" / "CLAUDE.md"
    rows, errors = [], []
    count(claude_md, "CLAUDE.md", args.root, 0, rows, errors)
    check_pointers(claude_md, args.root, errors)
    total = sum(w for _, w in rows)
    for label, words in rows:
        print(f"  {words:5d}  {label}")
    if total > BUDGET:
        errors.append(f"over budget: total {total} words > {BUDGET}")
    for e in errors:
        print(f"FAIL {e}")
    if not errors:
        print(f"always-on: total {total} words, within budget {BUDGET}")
    else:
        print(f"always-on: total {total} words")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
