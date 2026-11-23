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

BUCKET_OF = {"no-mechanism": "gap", "never-reached": "gap", "has-mechanism": "carried"}
MIN_GAP_SEARCHES = 2


def _is_instruction_file(rel):
    return os.path.basename(rel) in INSTRUCTION_NAMES or (
        rel.endswith(".md") and "/flow/claude/" in "/" + rel)


def _comment_lines(lines):
    """(line number, comment or docstring text) for each such line: `#` and
    `//` comments, triple-quoted docstrings and `/* */` blocks."""
    closer = None
    for number, line in enumerate(lines, 1):
        if closer:
            yield number, line
            if closer in line:
                closer = None
            continue
        opened = None
        for mark, end in (('"""', '"""'), ("'''", "'''"), ("/*", "*/")):
            if mark in line:
                opened = (mark, end)
                break
        if opened:
            mark, end = opened
            yield number, line
            if end not in line.split(mark, 1)[1]:
                closer = end
            continue
        stripped = line.strip()
        if stripped.startswith(("#", "//")):
            yield number, stripped
        elif " #" in line:
            yield number, line.split(" #", 1)[1]


def candidates(root):
    """Rows `{file, line, text, trigger}` for every rule-stating line under
    `root`, in path then line order. An unreadable directory raises: a pass
    that skipped it would report a smaller tree as the whole one."""
    def fail(error):
        raise error

    rows = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=fail):
        dirnames[:] = sorted(d for d in dirnames if d not in auditlib.EXCLUDED_DIRS
                             and (d == ".claude" or not d.startswith(".")))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            instruction = _is_instruction_file(rel)
            if not os.path.isfile(path) or (not instruction and not name.endswith(CODE_SUFFIXES)):
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            found = enumerate(lines, 1) if instruction else _comment_lines(lines)
            pattern = IMPERATIVE if instruction else TRIGGER
            for number, text in found:
                hit = pattern.search(text)
                if hit:
                    rows.append({"file": rel, "line": number, "text": text.strip(), "trigger": hit.group(0)})
    return rows


def _search_errors(searched, bucket):
    if not isinstance(searched, list) or not searched:
        return ["extra.searched must be a non-empty list of {where, result, ok}"]
    errors = []
    for place in searched:
        place = place if isinstance(place, dict) else {}
        for key in ("where", "result"):
            if not isinstance(place.get(key), str) or not place[key].strip():
                errors.append(f"extra.searched entry needs a non-empty {key}: {place!r}")
        if not isinstance(place.get("ok"), bool):
            errors.append(f"extra.searched entry needs ok: true or false: {place!r}")
        elif not place["ok"] and bucket == "gap":
            errors.append(f"a search that failed is not an absence, so this is not a gap: {place!r}")
    if bucket == "gap" and len(searched) < MIN_GAP_SEARCHES:
        errors.append(f"a gap lists at least two places searched (the repo, then the harness), got {len(searched)}")
    return errors


def validate(rows):
    """One message per problem in `rows`; an empty list is a valid log."""
    errors = []
    for index, row in enumerate(rows, 1):
        problems = []
        category = row.get("category")
        if category not in BUCKET_OF:
            problems.append(f"category must be one of {', '.join(BUCKET_OF)}")
        elif row.get("bucket") != BUCKET_OF[category]:
            problems.append(f"bucket must be {BUCKET_OF[category]!r} for category {category!r}, got {row.get('bucket')!r}")
        file = row.get("file")
        if not isinstance(file, str) or not file or os.path.isabs(file):
            problems.append("file must be a repo-relative path")
        if not isinstance(row.get("line"), int) or isinstance(row.get("line"), bool):
            problems.append("line must be an integer")
        if not row.get("summary"):
            problems.append("summary is empty")
        if row.get("bucket") == "gap" and not row.get("failure"):
            problems.append("a gap needs a failure naming what goes wrong")
        extra = row.get("extra")
        searched = extra.get("searched") if isinstance(extra, dict) else None
        problems += _search_errors(searched, row.get("bucket"))
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
