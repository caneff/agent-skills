#!/usr/bin/env python3
# Emits abbreviated thinking effort for ccstatusline, wrapped in parens: e.g. "(M)".
# Source order matches ccstatusline: stdin effort.level -> settings.json effortLevel.
import json, os, sys

ABBR = {"low": "L", "medium": "M", "high": "H", "xhigh": "XH", "max": "MAX"}

def get_level():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    lvl = (data.get("effort") or {}).get("level")
    if lvl:
        return lvl
    try:
        p = os.path.expanduser("~/.claude/settings.json")
        with open(p) as f:
            return json.load(f).get("effortLevel")
    except Exception:
        return None

lvl = (get_level() or "").lower()
if lvl:
    sys.stdout.write("(" + ABBR.get(lvl, lvl + "?") + ")")
