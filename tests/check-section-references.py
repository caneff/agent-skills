#!/usr/bin/env python3
"""Verify Markdown section references point at headings that still exist."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PATH = re.compile(r"(?<![\w.-])([~\w./-]+\.md)\b")
SECTION = re.compile(r"§\s+(\d+|[A-Za-z][^§\n]{0,160})")
TRAILING_PUNCTUATION = ".,;:!?)]}"


def tracked_markdown() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "--", "*.md"], cwd=ROOT, text=True
    )
    return [
        ROOT / name
        for name in output.splitlines()
        if not name.startswith("docs/research/")
    ]


def heading_text(line: str) -> str | None:
    match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
    return match.group(1).strip() if match else None


def resolve(path_text: str, source: Path, tracked: set[Path]) -> Path | None:
    if path_text.startswith("~/.agents/skills/"):
        candidate = ROOT / path_text.removeprefix("~/.agents/skills/")
        return candidate if candidate in tracked else None
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate if candidate in tracked else None
    for base in (source.parent, ROOT):
        resolved = (base / candidate).resolve()
        if resolved in tracked:
            return resolved
    return None


def reference_label(match: re.Match[str]) -> str:
    value = match.group(1).strip()
    if value.isdigit():
        return value
    return value.rstrip(TRAILING_PUNCTUATION).rstrip("'s").strip()


def matches_heading(label: str, heading: str, tail: str) -> bool:
    if label.isdigit():
        return heading.startswith(f"{label}.")
    heading = " ".join(heading.rstrip(TRAILING_PUNCTUATION).split())
    tail = " ".join(tail.split())
    if not tail.startswith(heading):
        return False
    return len(tail) == len(heading) or not tail[len(heading)].isalnum()


def main() -> int:
    files = tracked_markdown()
    tracked = {path.resolve() for path in files}
    headings = {
        path.resolve(): [heading for line in path.read_text().splitlines() if (heading := heading_text(line))]
        for path in files
    }
    failures: list[str] = []

    for source in files:
        source = source.resolve()
        latest_named_file: Path | None = None
        lines = source.read_text().splitlines()
        for number, line in enumerate(lines, 1):
            for pointer in SECTION.finditer(line):
                named = [
                    resolve(path.group(1), source, tracked)
                    for path in PATH.finditer(line)
                ]
                target = next((path for path in reversed(named) if path), None)
                if "this file" in line:
                    target = source
                if target is None and "of that file" in line[pointer.start() :]:
                    target = latest_named_file
                if target is None:
                    target = source

                label = reference_label(pointer)
                tail = " ".join(lines[number - 1 : number + 1])[pointer.start() + 1 :].lstrip()
                if not any(matches_heading(label, heading, tail) for heading in headings[target]):
                    failures.append(
                        f"{source.relative_to(ROOT)}:{number}: § {label} not found in "
                        f"{target.relative_to(ROOT)}"
                    )

            named_on_line = [
                resolve(path.group(1), source, tracked) for path in PATH.finditer(line)
            ]
            latest_named_file = next(
                (path for path in reversed(named_on_line) if path), latest_named_file
            )

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
