"""The always-loaded pointer docs never tell a controller to poll (spec #1733).

`CLAUDE.md` § Work says "no poll loop, no sleep"; a pointer doc that says "poll"
or "on every poll" contradicts it and the reader cannot tell which rule wins.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["flow/claude/OPERATIONS.md", "flow/claude/agent-status.md"]
POLL = re.compile(r"\bpoll(?:s|ed|ing)?\b", re.IGNORECASE)
# The one honest use: stating that the controller does not poll.
ALLOWED = re.compile(r"never polls|no poll loop|not poll|polling loops", re.IGNORECASE)


def test_pointer_docs_do_not_tell_a_controller_to_poll():
    hits = []
    for rel in DOCS:
        for n, line in enumerate((ROOT / rel).read_text().splitlines(), 1):
            if POLL.search(line) and not ALLOWED.search(line):
                hits.append(f"{rel}:{n}: {line.strip()}")
    assert not hits, "pointer doc tells a controller to poll:\n" + "\n".join(hits)
