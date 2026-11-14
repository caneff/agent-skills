"""The one reader and writer of an audit's `findings.jsonl` (#1748).

A log is one JSON object per line. `read` returns the objects and, separately,
every line that is not one (not JSON, or JSON that is not an object) as
`(line number, text)`, so a caller reports a corrupt line and never drops it.
`tally` is the mutation counts a mutation-audit module's log carries.
"""
import collections
import json

Log = collections.namedtuple("Log", "rows corrupt")

_COUNT_KEYS = ("killed_count", "survived_count", "no_coverage_count")


def read(path):
    """The `Log` of the file at `path`: its object rows in order, and its
    corrupt lines as `(line number, text)`. Blank lines are neither. A missing
    file raises `OSError`: no log is not an empty one."""
    rows, corrupt = [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        for number, line in enumerate(f.read().splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                row = None
            if isinstance(row, dict):
                rows.append(row)
            else:
                corrupt.append((number, line))
    return Log(rows, corrupt)


def write(path, rows):
    """Write `rows` (dicts) to `path`, one JSON object per line; no rows is an
    empty file, which a reader takes as a log with no findings."""
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def tally(rows):
    """(killed, total, survived, no_coverage) from the first row whose `extra`
    carries all three counts, or None when no row does."""
    for row in rows:
        extra = row.get("extra") or {}
        if all(key in extra for key in _COUNT_KEYS):
            k, s, n = (extra[key] for key in _COUNT_KEYS)
            return k, k + s + n, s, n
    return None
