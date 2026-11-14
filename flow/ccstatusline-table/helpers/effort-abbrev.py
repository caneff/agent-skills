#!/usr/bin/env python3
# Emits abbreviated thinking effort for ccstatusline, wrapped in parens: e.g. "(M)".
# Source order matches ccstatusline: stdin effort.level -> settings.json effortLevel.
import json, os, sys

ABBR = {"low": "L", "medium": "M", "high": "H", "xhigh": "XH", "max": "MAX"}

def get_level():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    lvl = (data.get("effort") or {}).get("level")
    if lvl:
        return lvl
    try:
        p = os.path.expanduser("~/.claude/settings.json")
        with open(p) as f:
            return json.load(f).get("effortLevel")
    except (OSError, ValueError, AttributeError):
        return None

def main():
    lvl = (get_level() or "").lower()
    if lvl:
        sys.stdout.write("(" + ABBR.get(lvl, lvl + "?") + ")")

if __name__ == "__main__":
    main()
