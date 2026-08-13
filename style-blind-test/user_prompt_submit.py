#!/usr/bin/env python3
"""UserPromptSubmit hook: re-anchor the session's output style each turn.

Reads hook JSON (session_id) on stdin, looks up the same (style, hook_on)
assignment() chose at session start, and -- only when hook_on is true and
the style isn't "default" -- emits a one-line reminder naming the style as
UserPromptSubmit hookSpecificOutput JSON. Emits nothing otherwise.
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


def _style_name(styles_dir: Path, style: str) -> str:
    lines = (Path(styles_dir) / FILENAMES[style]).read_text().splitlines()
    in_frontmatter = False
    for line in lines:
        if line.strip() == "---":
            if in_frontmatter:
                break
            in_frontmatter = True
            continue
        if in_frontmatter and line.startswith("name:"):
            return line[len("name:") :].strip()
    raise ValueError(f"no name: field in {style} frontmatter")


def run(hook_input: str, styles_dir: Path = DEFAULT_STYLES_DIR) -> str:
    payload = json.loads(hook_input)
    session_id = payload["session_id"]
    style, hook_on = assignment(session_id)

    if not hook_on or style == "default":
        return ""

    name = _style_name(styles_dir, style)
    reminder = f"Output style: {name}. Stay in that voice; self-check before sending."
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": reminder,
            }
        }
    )


def main() -> None:
    output = run(sys.stdin.read())
    if output:
        print(output)


if __name__ == "__main__":
    main()
