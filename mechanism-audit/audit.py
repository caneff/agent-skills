#!/usr/bin/env python3
"""Pass one of mechanism-audit, and the check on its findings log.

`candidates(root)` lists the lines that state a rule: every line of an
instruction file (`SKILL.md`, `AGENTS.md`, `CLAUDE.md`, a `.md` under
`flow/claude/`) that carries an imperative word, and every comment or docstring
line in source that carries one of the class doc's trigger words
(`docs/agents/defect-classes.md` § 2). It judges nothing: whether a rule has a
mechanism is the model's pass in SKILL.md, reading these rows.

`validate(rows)` is the check on the judged log. A row must say what was
searched and what each search found, so a failed search can never pass for an
absence (the audit's own defect class 1).

CLI: `audit.py candidates <root>` prints one JSON row per candidate;
`audit.py validate <findings.jsonl>` prints each error and exits 1 on any.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "all-audits", "harness"))
import auditlib  # noqa: E402
import findings_log  # noqa: E402

INSTRUCTION_NAMES = ("SKILL.md", "AGENTS.md", "CLAUDE.md")
CODE_SUFFIXES = (".py", ".sh", ".js", ".mjs", ".ts", ".rs")
TRIGGER = re.compile(
    r"\botherwise\b|\bfalls? back\b|\bif absent\b|\brefuses?\b|\bevery\b.*\bmust\b", re.I)
IMPERATIVE = re.compile(TRIGGER.pattern + r"|\bmust\b|\bnever\b|\balways\b|\bevery\b", re.I)

CATEGORIES = ("no-mechanism", "never-reached", "has-mechanism")
GAP_BUCKET = "gap"


def _is_instruction_file(rel):
    return os.path.basename(rel) in INSTRUCTION_NAMES or (
        rel.endswith(".md") and "flow/claude/" in "/" + rel)


def _comment_lines(lines):
    """(line number, comment or docstring text) for each such line."""
    in_doc = False
    for number, line in enumerate(lines, 1):
        quotes = line.count('"""')
        if in_doc or quotes:
            yield number, line
            in_doc ^= quotes % 2 == 1
            continue
        stripped = line.strip()
        if stripped.startswith(("#", "//")):
            yield number, stripped
        elif " #" in line:
            yield number, line.split(" #", 1)[1]


def _row(rel, number, text, trigger):
    return {"file": rel, "line": number, "text": text.strip(), "trigger": trigger.group(0)}


def candidates(root):
    """Rows `{file, line, text, trigger}` for every rule-stating line under
    `root`, in path then line order."""
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in auditlib.EXCLUDED_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            instruction = _is_instruction_file(rel)
            if not instruction and not name.endswith(CODE_SUFFIXES):
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            if instruction:
                found = ((n, t) for n, t in enumerate(lines, 1))
                pattern = IMPERATIVE
            else:
                found, pattern = _comment_lines(lines), TRIGGER
            for number, text in found:
                hit = pattern.search(text)
                if hit:
                    rows.append(_row(rel, number, text, hit))
    return rows


def _search_errors(searched):
    if not isinstance(searched, list) or not searched:
        return ["extra.searched must be a non-empty list of {where, result}"]
    errors = []
    for place in searched:
        for key in ("where", "result"):
            value = place.get(key) if isinstance(place, dict) else None
            if not isinstance(value, str) or not value.strip():
                errors.append(f"extra.searched entry needs a non-empty {key}: {place!r}")
    return errors


def validate(rows):
    """One message per problem in `rows`; an empty list is a valid log."""
    errors = []
    for index, row in enumerate(rows, 1):
        problems = []
        if row.get("category") not in CATEGORIES:
            problems.append(f"category must be one of {', '.join(CATEGORIES)}")
        if not isinstance(row.get("file"), str) or not row.get("file"):
            problems.append("file must be a repo-relative path")
        if not isinstance(row.get("line"), int) or isinstance(row.get("line"), bool):
            problems.append("line must be an integer")
        if not row.get("summary"):
            problems.append("summary is empty")
        if row.get("bucket") == GAP_BUCKET and not row.get("failure"):
            problems.append("a gap needs a failure naming what goes wrong")
        extra = row.get("extra")
        problems += _search_errors(extra.get("searched") if isinstance(extra, dict) else None)
        errors += [f"row {index}: {p}" for p in problems]
    return errors


def main(argv):
    if len(argv) == 3 and argv[1] == "candidates":
        for row in candidates(argv[2]):
            print(json.dumps(row))
        return 0
    if len(argv) == 3 and argv[1] == "validate":
        log = findings_log.read(argv[2])
        errors = [f"corrupt line {n}: {t}" for n, t in log.corrupt] + validate(log.rows)
        for error in errors:
            print(error)
        return 1 if errors else 0
    print("usage: audit.py candidates <root> | validate <findings.jsonl>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
