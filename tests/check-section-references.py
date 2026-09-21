#!/usr/bin/env python3
"""Verify Markdown section references point at headings that still exist.

The grammar this enforces is written down in docs/agents/section-references.md.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(os.environ.get("SECTION_REFERENCES_ROOT", Path(__file__).resolve().parent.parent)).resolve()
PATH = re.compile(r"(?<![\w.-])([~\w./-]+\.md)\b")
# A reference is a section sign, whitespace, then a name that runs to the line
# end, another section sign, or a backtick (the close of a code span). A sign
# written "\\§" is the word, not a reference, and is never read.
SECTION = re.compile(r"(?<!\\)§\s+(\d+|[A-Za-z][^§`\n]*)")
TRAILING_PUNCTUATION = ".,;:!?)]}"
# "§ The merge step 3 ..." points at the section "The merge" and its third
# numbered step; whatever follows the locator is prose, not part of the name.
# "§ Before the PR: step 6" is the same pointer with a colon. The name may
# hold no punctuation, so a sentence break cannot join two clauses into one.
# The non-empty name and the mandatory whitespace before "step" are joint
# guards on a heading that is itself "Step 3: ...": either one alone keeps
# the locator from matching there, so relax both at once and every
# "§ Step N" label becomes "", which matches_heading accepts against any
# heading at all. Such a heading keeps only "Step 3" as its label
# (HEADING_STEP), so prose after it cannot leak into the name.
# The locator takes "step"/"steps", any case, a number or a spelled-out one
# to ten, and an optional range ("steps 3-5"); every number named must be a
# "<n>." or "<n>)" list item, or a "Step <n>" sub-heading, in the target
# section (section_has_steps).
# Known limits: a spelled-out number above ten is not recognised; a second
# locator in the same pointer ("step 3 and step 9") is not read; lazily
# numbered lists ("1." on every item) do not satisfy the check.
NUMBER_WORDS = {
    word: number
    for number, word in enumerate(
        "one two three four five six seven eight nine ten".split(), 1
    )
}
STEP_NUMBER = rf"(\d+|{'|'.join(NUMBER_WORDS)})"
STEP_LOCATOR = re.compile(
    rf"^([^.,;:!?)}}\]]+?):?\s+steps?\s+{STEP_NUMBER}(?:\s*[-\u2013\u2014]\s*{STEP_NUMBER})?\b",
    re.IGNORECASE,
)
# A fence closes on its own character, at least as long as the one that
# opened it, with nothing after it: "~~~" inside a longer backtick fence is text.
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
LOOSE_STEP_LOCATOR = re.compile(STEP_LOCATOR.pattern.replace("[^.,;:!?)}\\]]+?", ".+?"), re.IGNORECASE)
HEADING_STEP = re.compile(r"^(step\s+\d+)\b", re.IGNORECASE)


def tracked_markdown() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "--", "*.md"], cwd=ROOT, text=True
    )
    return [
        ROOT / name
        for name in output.splitlines()
        if not name.startswith(("docs/research/", "tests/fixtures/"))
    ]


def heading_text(line: str) -> str | None:
    match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
    return match.group(1).strip() if match else None


def sections(path: Path) -> list[tuple[str, str]]:
    """Each heading with its text, down to the next heading of its level or
    higher. Fenced code is not a heading and not part of the text."""
    lines = path.read_text().splitlines()
    fence = None  # (character, length) of the fence that is open
    prose = []  # per line: a fence marker or a line inside one is not
    starts = []  # (line index, level, heading text)
    for index, line in enumerate(lines):
        marker = FENCE.match(line)
        if marker and (
            fence is None
            or (
                marker.group(1)[0] == fence[0]
                and len(marker.group(1)) >= fence[1]
                and not marker.group(2).strip()
            )
        ):
            fence = None if fence else (marker.group(1)[0], len(marker.group(1)))
            prose.append(False)
            continue
        prose.append(fence is None)
        if fence is None and (heading := heading_text(line)):
            starts.append((index, len(line) - len(line.lstrip("#")), heading))
    found = []
    for position, (index, level, heading) in enumerate(starts):
        end = next(
            (later for later, deeper, _ in starts[position + 1 :] if deeper <= level),
            len(lines),
        )
        body = [lines[i] for i in range(index + 1, end) if prose[i]]
        found.append((heading, "\n".join(body)))
    return found


def section_has_steps(body: str, steps: list[int]) -> bool:
    return all(
        re.search(rf"(?mi)^(?:\s*{n}[.)]\s|#{{1,6}}\s+step\s+{n}\b)", body)
        for n in steps
    )


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


def step_number(text: str) -> int:
    return int(text) if text.isdigit() else NUMBER_WORDS[text.lower()]


def located_steps(locator: re.Match[str]) -> list[int]:
    first = step_number(locator.group(2))
    last = step_number(locator.group(3)) if locator.group(3) else first
    # A descending range is a typo; name both ends so the check can fail.
    return list(range(first, last + 1)) if last >= first else [first, last]


# Pinned by tests/section_reference_trimmers_test.py. PROSE_TRIMMERS run in
# order before the step-locator reading, which needs the label's own
# punctuation ("Before the PR: step 5") intact; add a new one here and it runs.
# PUNCTUATION_TRIMMER is separate and runs last, feeding only the final reading.
PROSE_TRIMMERS = (
    ("cross-reference conjunction", lambda v: v.split(" and §", 1)[0]),
    ("trailing conjunction", lambda v: re.sub(r"\s+and\s*$", "", v)),
    ("possessive", lambda v: v.split("'s", 1)[0]),
)
PUNCTUATION_TRIMMER = (
    "sentence punctuation",
    lambda v: re.split(r"[.,;:!?)}\]]", v, maxsplit=1)[0].strip(),
)


def reference_targets(match: re.Match[str]) -> list[tuple[str, list[int]]]:
    """The (section name, step numbers) readings of a pointer, best first.

    The first reads the name up to the step locator whatever punctuation it
    holds, which is right for a heading like "Build: deployment"; the last
    stops the name at the first punctuation mark, which is right when prose
    follows ("§ Alpha. Then step 2 matters"). The caller takes the first
    reading that names a heading."""
    value = match.group(1).strip()
    if value.isdigit():
        return [(value, [])]
    for _, trim in PROSE_TRIMMERS:
        value = trim(value)
    readings = []
    for pattern in (LOOSE_STEP_LOCATOR, STEP_LOCATOR):
        locator = pattern.match(value)
        if locator:
            readings.append((locator.group(1).strip(), located_steps(locator)))
    value = PUNCTUATION_TRIMMER[1](value)
    heading_step = HEADING_STEP.match(value)
    readings.append((heading_step.group(1) if heading_step else value, []))
    return readings


def matches_heading(label: str, heading: str) -> bool:
    if label.isdigit():
        return heading.startswith(f"{label}.")
    label = " ".join(label.rstrip(TRAILING_PUNCTUATION).split())
    heading = " ".join(heading.rstrip(TRAILING_PUNCTUATION).split())
    return heading.startswith(label)


def main() -> int:
    files = tracked_markdown()
    tracked = {path.resolve() for path in files}
    headings = {path.resolve(): sections(path) for path in files}
    failures: list[str] = []

    for source in files:
        source = source.resolve()
        latest_named_file: Path | None = None
        previous_line_named_file: Path | None = None
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
                    if previous_line_named_file not in (None, source):
                        failures.append(
                            f"{source.relative_to(ROOT)}:{number}: bare § {reference_targets(pointer)[-1][0]} "
                            f"follows {previous_line_named_file.relative_to(ROOT)}"
                        )
                        continue
                    target = source

                # The name stops at a backtick. That is the close of a code
                # span only when the sign sits inside one; anywhere else it is
                # inline code in the name, and cutting there would let a prefix
                # of the heading match after the code part is renamed.
                cut_at_backtick = line[pointer.end() : pointer.end() + 1] == "`"
                inside_span = line[: pointer.start()].count("`") % 2 == 1
                if (
                    cut_at_backtick
                    and not inside_span
                    and reference_targets(pointer)[-1][0] == pointer.group(1).strip()
                ):
                    failures.append(
                        f"{source.relative_to(ROOT)}:{number}: § {pointer.group(1).strip()} "
                        "is cut at inline code: inline code in a heading name is "
                        "unsupported, write the plain heading"
                    )
                    continue

                for label, steps in reference_targets(pointer):
                    candidates = [
                        body
                        for heading, body in headings[target]
                        if matches_heading(label, heading)
                    ]
                    if candidates:
                        break
                where = target.relative_to(ROOT)
                if not candidates:
                    failures.append(
                        f"{source.relative_to(ROOT)}:{number}: § {label} not found in {where}"
                    )
                elif steps != sorted(steps):
                    failures.append(
                        f"{source.relative_to(ROOT)}:{number}: § {label} steps "
                        f"{steps} run backwards"
                    )
                elif not any(section_has_steps(body, steps) for body in candidates):
                    failures.append(
                        f"{source.relative_to(ROOT)}:{number}: § {label} steps "
                        f"{steps} not all numbered items in {where}"
                    )

            named_on_line = [
                resolve(path.group(1), source, tracked) for path in PATH.finditer(line)
            ]
            previous_line_named_file = next(
                (path for path in reversed(named_on_line) if path), None
            )
            latest_named_file = previous_line_named_file or latest_named_file

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
