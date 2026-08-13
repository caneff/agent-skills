#!/usr/bin/env python3
"""SessionStart hook: inject a blind-randomized output style per session.

Reads hook JSON (session_id, source) on stdin, picks a style deterministically
from session_id via assignment(), and emits the SessionStart hookSpecificOutput
JSON on stdout carrying that style's file body verbatim. Emits nothing for the
"default" style. `source` is never consulted -- the assignment is stable across
startup/clear/resume/compact for the same session_id.
"""
import json
import sys
from pathlib import Path

from assignment import assignment

DEFAULT_STYLES_DIR = Path.home() / ".claude" / "output-styles"

FILENAMES = {
    "clarity-and-grace": "clarity-and-grace.md",
    "orwell-ste": "orwell-ste.md",
    "plain-speak": "plain-speak.md",
}


def run(hook_input: str, styles_dir: Path = DEFAULT_STYLES_DIR) -> str | None:
    payload = json.loads(hook_input)
    session_id = payload["session_id"]
    style, _hook_on = assignment(session_id)

    if style == "default":
        return None

    body = (Path(styles_dir) / FILENAMES[style]).read_text()
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": body,
            }
        }
    )


def main() -> None:
    output = run(sys.stdin.read())
    if output is not None:
        print(output)


if __name__ == "__main__":
    main()
